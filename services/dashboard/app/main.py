"""
Valhalla Capital Dashboard - Main Application

    "Time to mix drinks and save lives."
                    — Jill, probably

FastAPI app serving the monitoring dashboard with Jinja2 templates
and htmx for live updates. Reads from:
  - Local SQLite for health snapshots
  - Overseer PostgreSQL (249) for Valkyrie's cycle logs & decision journal
  - Trading PostgreSQL (248) for trade history & portfolio state
"""

import logging
import math
import time
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.gzip import GZipMiddleware

import markupsafe
import mistune

from .auth import (
    check_rate_limit,
    clear_failed_attempts,
    create_csrf_token,
    create_session,
    record_failed_attempt,
    validate_csrf_token,
    validate_session,
    verify_password,
)
from .config import SERVICES, SERVICE_GROUPS, DashboardConfig, ServiceStatus
from .database import Database
from .external_db import ExternalDB
from .fmp import fetch_quotes, enrich_positions
from .health_checker import run_health_checks

logger = logging.getLogger(__name__)
config = DashboardConfig()

# Paths
BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# Storage
db = Database(config.db_path)
ext_db = ExternalDB(config)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown hooks."""
    logging.basicConfig(
        level=config.log_level,
        format="%(asctime)s  %(name)-28s  %(levelname)-7s  %(message)s",
    )
    await db.connect()
    await ext_db.connect()
    if not config.session_secret:
        logger.warning(
            "SESSION_SECRET is not set — auth disabled. "
            "All visitors get %s access based on PUBLIC_DASHBOARD.",
            "public" if config.public_mode else "OWNER (full)",
        )
    logger.info("Valhalla Capital web service online")
    yield
    await ext_db.close()
    await db.close()
    logger.info("Valhalla Capital web service shutting down")


app = FastAPI(
    title="Valhalla Capital",
    description="Fund monitoring terminal",
    lifespan=lifespan,
)

app.add_middleware(GZipMiddleware, minimum_size=500)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)
templates.env.trim_blocks = True
templates.env.lstrip_blocks = True


# ---------------------------------------------------------------------------
# Template helpers
# ---------------------------------------------------------------------------


@lru_cache(maxsize=32)
def _asset_version(filename: str) -> str:
    target = STATIC_DIR / filename
    if not target.exists():
        return "0"
    return str(int(target.stat().st_mtime))


def asset_url(filename: str) -> str:
    return f"/static/{filename}?v={_asset_version(filename)}"


def build_csp() -> str:
    return "; ".join([
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data:",
        "font-src 'self' data:",
        "connect-src 'self'",
        "media-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ])


def request_config(base: DashboardConfig, is_owner: bool) -> DashboardConfig:
    """Build a per-request config based on auth state."""
    if is_owner:
        return replace(
            base,
            expose_internal_details=True,
            allow_manual_checks=True,
            public_mode=False,
        )
    return replace(
        base,
        expose_internal_details=False,
        allow_manual_checks=False,
        public_mode=True,
    )


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Set request.state.is_owner and request.state.config per-request."""
    is_owner = False
    if config.session_secret:
        cookie = request.cookies.get("valhalla_session", "")
        max_age = config.session_ttl_days * 86400
        if validate_session(cookie, config.session_secret, max_age):
            is_owner = True
    else:
        # No session secret configured -- fall back to static config
        is_owner = not config.public_mode

    request.state.is_owner = is_owner
    request.state.config = request_config(config, is_owner)
    response = await call_next(request)
    return response


def service_error_for_display(
    status: str, error: str | None, cfg: DashboardConfig | None = None,
) -> str | None:
    if not error:
        return None
    effective = cfg if cfg is not None else config
    if effective.expose_internal_details:
        return error
    if status == ServiceStatus.MIXING.value:
        return "Performance degraded"
    if status == ServiceStatus.EIGHTY_SIXED.value:
        return "Temporarily unavailable"
    return None


@app.middleware("http")
async def add_response_headers(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid4().hex
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = (
        "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
        "magnetometer=(), microphone=(), payment=(), usb=()"
    )
    response.headers["Content-Security-Policy"] = build_csp()
    response.headers["Server-Timing"] = f"app;dur={elapsed_ms}"

    forwarded_proto = request.headers.get("x-forwarded-proto")
    if request.url.scheme == "https" or forwarded_proto == "https":
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains; preload"
        )

    if request.url.path.startswith("/static/"):
        response.headers.setdefault(
            "Cache-Control", "public, max-age=31536000, immutable"
        )
    else:
        response.headers.setdefault("Cache-Control", "no-store")

    if elapsed_ms >= config.slow_request_ms or response.status_code >= 500:
        logger.warning(
            "Request %s %s -> %s in %dms [%s]",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            request_id,
        )

    return response

def status_class(status: str) -> str:
    return {
        ServiceStatus.SERVED.value: "status-served",
        ServiceStatus.MIXING.value: "status-mixing",
        ServiceStatus.EIGHTY_SIXED.value: "status-86d",
        ServiceStatus.ON_ORDER.value: "status-on-order",
        ServiceStatus.LAST_CALL.value: "status-last-call",
    }.get(status, "status-on-order")


def time_ago(iso_str) -> str:
    if not iso_str:
        return "never"
    try:
        dt = iso_str if isinstance(iso_str, datetime) else datetime.fromisoformat(str(iso_str))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        seconds = int(delta.total_seconds())
        if seconds < 0:
            return "just now"
        if seconds < 60:
            return f"{seconds}s ago"
        elif seconds < 3600:
            return f"{seconds // 60}m ago"
        elif seconds < 86400:
            return f"{seconds // 3600}h ago"
        else:
            return f"{seconds // 86400}d ago"
    except Exception:
        return "—"


def format_ms(ms: int | None) -> str:
    if ms is None:
        return "—"
    if ms < 1000:
        return f"{ms}ms"
    return f"{ms / 1000:.1f}s"


def format_timestamp(val) -> str:
    if val is None:
        return "—"
    try:
        dt = val if isinstance(val, datetime) else datetime.fromisoformat(str(val))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(val)


# Markdown renderer
_md = mistune.create_markdown(escape=True)


def render_markdown(text: str | None) -> markupsafe.Markup:
    """Convert markdown text to safe HTML."""
    if not text:
        return markupsafe.Markup("")
    return markupsafe.Markup(_md(str(text)))


def sparkline_points(history: list[dict], width: int = 80, height: int = 20, max_val: int = 500) -> str:
    """Generate x,y coordinates for an SVG sparkline."""
    if not history:
        return ""
    count = len(history)
    if count < 2:
        return f"0,{height} {width},{height}"
    
    points = []
    for i, entry in enumerate(history):
        x = (i / (count - 1)) * width
        ms = entry.get("ms", 0) or 0
        # Normalize: higher ms is higher up (y=0) but SVG y is inverted
        # Clamp to max_val
        val = min(ms, max_val)
        y = height - (val / max_val * height)
        points.append(f"{x:.1f},{y:.1f}")
    return " ".join(points)


def ticker_excerpt(text: str | None, length: int = 120) -> str:
    """Extract a useful excerpt for the ticker, skipping boilerplate."""
    if not text:
        return ""
    lines = str(text).split("\n")
    for line in lines:
        stripped = line.strip().lstrip("#").strip()
        # Skip empty lines, boilerplate openers, and markdown headings that just repeat the cycle type
        if not stripped:
            continue
        lower = stripped.lower()
        if lower.startswith("i'll ") or lower.startswith("i will ") or lower.startswith("let me "):
            continue
        if lower.startswith("good.") or lower.startswith("ok."):
            continue
        # Found a real content line
        if len(stripped) > length:
            return stripped[:length] + "..."
        return stripped
    # Fallback: just truncate the whole thing
    flat = " ".join(text.split())
    if len(flat) > length:
        return flat[:length] + "..."
    return flat


templates.env.filters["markdown"] = render_markdown
templates.env.filters["sparkline"] = sparkline_points
templates.env.filters["ticker_excerpt"] = ticker_excerpt

import random

QUOTES = [
    "Time to mix drinks and save lives.",
    "Everything is going to be alright.",
    "A glass of Sunshine Cloud coming up.",
    "Sometimes you just need to talk to someone.",
    "The world is a harsh place, but we have each other.",
    "Quality service, quality drinks.",
    "Valkyrie is watching the flows.",
    "Stay hydrated, stay solvent.",
    "The market never sleeps, but it sometimes dreams.",
    "Mixing the future, one trade at a time.",
]

def get_random_quote() -> str:
    return random.choice(QUOTES)


# Register template globals
templates.env.globals.update({
    "status_class": status_class,
    "time_ago": time_ago,
    "format_ms": format_ms,
    "format_timestamp": format_timestamp,
    "asset_url": asset_url,
    "config": config,
    "now": lambda: datetime.now(timezone.utc),
    "ext_db": ext_db,
    "get_quote": get_random_quote,
})

# Navigation items
NAV_ITEMS = [
    {"path": "/", "label": "Status", "icon": "◆"},
    {"path": "/valkyrie", "label": "Valkyrie", "icon": "⟡"},
    {"path": "/decisions", "label": "Decisions", "icon": "◈"},
    {"path": "/trades", "label": "Trades", "icon": "△"},
]


# ---------------------------------------------------------------------------
# Routes — Status (home)
# ---------------------------------------------------------------------------

async def _build_status_context(cfg: DashboardConfig | None = None):
    effective_cfg = cfg if cfg is not None else config
    service_names = [svc.name for svc in SERVICES]
    snapshots, uptimes, response_histories = await db.get_service_rollup(
        service_names, hours=24
    )
    groups = {}
    for svc in SERVICES:
        group_key = svc.group
        if group_key not in groups:
            group_info = SERVICE_GROUPS.get(group_key, {"label": group_key, "order": 99})
            groups[group_key] = {
                "label": group_info["label"],
                "order": group_info["order"],
                "services": [],
            }
        snap = snapshots.get(svc.name, {})
        status = snap.get("status", ServiceStatus.ON_ORDER.value)
        groups[group_key]["services"].append({
            "def": svc,
            "status": status,
            "checked_at": snap.get("checked_at"),
            "response_ms": snap.get("response_ms"),
            "error": service_error_for_display(status, snap.get("error"), effective_cfg),
            "details": snap.get("details"),
            "uptime_24h": uptimes.get(svc.name, -1),
            "response_history": response_histories.get(svc.name, []),
        })
    sorted_groups = sorted(groups.items(), key=lambda x: x[1]["order"])
    all_statuses = [
        snapshots.get(svc.name, {}).get("status", ServiceStatus.ON_ORDER.value)
        for svc in SERVICES
    ]
    summary = {
        "total": len(SERVICES),
        "served": sum(1 for s in all_statuses if s == ServiceStatus.SERVED.value),
        "mixing": sum(1 for s in all_statuses if s == ServiceStatus.MIXING.value),
        "down": sum(1 for s in all_statuses if s == ServiceStatus.EIGHTY_SIXED.value),
        "unknown": sum(1 for s in all_statuses if s == ServiceStatus.ON_ORDER.value),
    }

    # System pulse narrative
    pulse = await db.get_system_pulse(snapshots=snapshots)
    if pulse["all_healthy"]:
        if pulse["since"]:
            delta = datetime.now(timezone.utc) - datetime.fromisoformat(pulse["since"])
            hours = int(delta.total_seconds() // 3600)
            if hours >= 24:
                pulse_text = f"All systems nominal for {hours // 24}d {hours % 24}h"
            elif hours > 0:
                pulse_text = f"All systems nominal for {hours}h {int((delta.total_seconds() % 3600) // 60)}m"
            else:
                mins = int(delta.total_seconds() // 60)
                pulse_text = f"All systems nominal for {mins}m"
        else:
            pulse_text = "All systems nominal — no incidents on record"
    else:
        down_list = ", ".join(pulse["down_services"][:3])
        count = len(pulse["down_services"])
        if count > 3:
            down_list += f" +{count - 3} more"
        pulse_text = f"{count} service{'s' if count != 1 else ''} 86'd — {down_list}"
    summary["pulse"] = pulse_text
    summary["all_healthy"] = pulse["all_healthy"]

    return sorted_groups, summary


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    sorted_groups, summary = await _build_status_context(request.state.config)
    return templates.TemplateResponse("status.html", {
        "request": request,
        "groups": sorted_groups,
        "summary": summary,
        "nav": NAV_ITEMS,
        "current_path": "/",
        "config": request.state.config,
        "is_owner": request.state.is_owner,
    })


@app.get("/partials/status-board", response_class=HTMLResponse)
async def status_board_partial(request: Request):
    sorted_groups, summary = await _build_status_context(request.state.config)
    return templates.TemplateResponse("partials/status_board.html", {
        "request": request,
        "groups": sorted_groups,
        "summary": summary,
        "config": request.state.config,
        "is_owner": request.state.is_owner,
    })


@app.post("/api/check-now", response_class=HTMLResponse)
async def check_now(request: Request):
    """Trigger a manual health check for all services."""
    if not request.state.config.allow_manual_checks:
        raise HTTPException(status_code=404, detail="Not found")
    if not request.state.is_owner:
        raise HTTPException(status_code=403, detail="Forbidden")
    await run_health_checks(db)
    sorted_groups, summary = await _build_status_context(request.state.config)
    return templates.TemplateResponse("partials/status_board.html", {
        "request": request,
        "groups": sorted_groups,
        "summary": summary,
        "config": request.state.config,
        "is_owner": request.state.is_owner,
    })


# ---------------------------------------------------------------------------
# Routes — Valkyrie Review Reader
# ---------------------------------------------------------------------------

@app.get("/valkyrie", response_class=HTMLResponse)
async def valkyrie_logs(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=5, le=100),
    cycle_type: str | None = Query(None),
):
    offset = (page - 1) * per_page
    logs = await ext_db.get_cycle_logs(
        limit=per_page, offset=offset, cycle_type=cycle_type
    )
    total = await ext_db.get_cycle_log_count(cycle_type=cycle_type)
    cycle_types = await ext_db.get_cycle_types()
    total_pages = max(1, math.ceil(total / per_page)) if total > 0 else 1

    return templates.TemplateResponse("valkyrie.html", {
        "request": request,
        "logs": logs,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "cycle_type": cycle_type,
        "cycle_types": cycle_types,
        "nav": NAV_ITEMS,
        "current_path": "/valkyrie",
        "db_available": ext_db.overseer_available,
        "config": request.state.config,
        "is_owner": request.state.is_owner,
    })


@app.get("/partials/valkyrie-logs", response_class=HTMLResponse)
async def valkyrie_logs_partial(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=5, le=100),
    cycle_type: str | None = Query(None),
):
    offset = (page - 1) * per_page
    logs = await ext_db.get_cycle_logs(
        limit=per_page, offset=offset, cycle_type=cycle_type
    )
    total = await ext_db.get_cycle_log_count(cycle_type=cycle_type)
    total_pages = max(1, math.ceil(total / per_page)) if total > 0 else 1

    return templates.TemplateResponse("partials/valkyrie_logs.html", {
        "request": request,
        "logs": logs,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "cycle_type": cycle_type,
        "config": request.state.config,
        "is_owner": request.state.is_owner,
    })


@app.get("/partials/valkyrie-ticker", response_class=HTMLResponse)
async def valkyrie_ticker_partial(request: Request):
    events = await ext_db.get_recent_events(limit=12)
    return templates.TemplateResponse("partials/valkyrie_ticker.html", {
        "request": request,
        "events": events,
        "status_changes": [],
        "config": request.state.config,
        "is_owner": request.state.is_owner,
    })


# ---------------------------------------------------------------------------
# Routes — Decision Journal
# ---------------------------------------------------------------------------

@app.get("/decisions", response_class=HTMLResponse)
async def decisions(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=5, le=100),
    ticker: str | None = Query(None),
):
    offset = (page - 1) * per_page
    entries = await ext_db.get_decision_journal(
        limit=per_page, offset=offset, ticker=ticker
    )
    total_pages = max(1, page)

    return templates.TemplateResponse("decisions.html", {
        "request": request,
        "entries": entries,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "ticker": ticker,
        "nav": NAV_ITEMS,
        "current_path": "/decisions",
        "db_available": ext_db.overseer_available,
        "config": request.state.config,
        "is_owner": request.state.is_owner,
    })


# ---------------------------------------------------------------------------
# Routes — Trades & Portfolio
# ---------------------------------------------------------------------------

@app.get("/trades", response_class=HTMLResponse)
async def trades(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=5, le=100),
    ticker: str | None = Query(None),
):
    offset = (page - 1) * per_page
    trade_list = await ext_db.get_trades(
        limit=per_page, offset=offset, ticker=ticker
    )
    portfolio = await ext_db.get_portfolio_state()

    # Enrich positions with live prices from FMP proxy
    if portfolio and portfolio.get('positions'):
        tickers = [p['ticker'] for p in portfolio['positions'] if p.get('ticker')]
        quotes = await fetch_quotes(config, tickers)
        portfolio['positions'] = enrich_positions(portfolio['positions'], quotes)

    portfolio_history = await ext_db.get_portfolio_history()
    portfolio_snapshots = await db.get_portfolio_snapshots(days=90)
    cash_info = await ext_db.get_portfolio_cash()

    return templates.TemplateResponse("trades.html", {
        "request": request,
        "trades": trade_list,
        "portfolio": portfolio,
        "portfolio_history": portfolio_history,
        "portfolio_snapshots": portfolio_snapshots,
        "cash_info": cash_info,
        "page": page,
        "per_page": per_page,
        "ticker": ticker,
        "nav": NAV_ITEMS,
        "current_path": "/trades",
        "db_available": ext_db.trading_available,
        "config": request.state.config,
        "is_owner": request.state.is_owner,
    })


# ---------------------------------------------------------------------------
# Routes — Authentication
# ---------------------------------------------------------------------------

def _get_client_ip(request: Request) -> str:
    """Extract client IP, respecting X-Forwarded-For behind a reverse proxy."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    if request.client:
        return request.client.host
    return "unknown"


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Show the login form. Redirect to / if already authenticated."""
    if request.state.is_owner:
        return RedirectResponse("/", status_code=302)
    csrf_token = ""
    if config.session_secret:
        csrf_token = create_csrf_token(config.session_secret)
    return templates.TemplateResponse("login.html", {
        "request": request,
        "csrf_token": csrf_token,
        "error": None,
        "nav": NAV_ITEMS,
        "current_path": "/login",
        "config": request.state.config,
        "is_owner": request.state.is_owner,
    })


@app.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request):
    """Validate password, set session cookie, redirect to /."""
    form = await request.form()
    password = form.get("password", "")
    csrf_token = form.get("csrf_token", "")
    client_ip = _get_client_ip(request)

    def _login_error(msg: str):
        new_csrf = ""
        if config.session_secret:
            new_csrf = create_csrf_token(config.session_secret)
        return templates.TemplateResponse("login.html", {
            "request": request,
            "csrf_token": new_csrf,
            "error": msg,
            "nav": NAV_ITEMS,
            "current_path": "/login",
            "config": request.state.config,
            "is_owner": False,
        })

    if not config.session_secret or not config.owner_password_hash:
        return _login_error("Authentication not configured.")

    if not check_rate_limit(client_ip):
        return _login_error("Too many failed attempts. Try again later.")

    if not validate_csrf_token(csrf_token, config.session_secret):
        return _login_error("Session expired. Please try again.")

    if not verify_password(password, config.owner_password_hash):
        record_failed_attempt(client_ip)
        return _login_error("Invalid password.")

    clear_failed_attempts(client_ip)
    session_cookie = create_session(config.session_secret)
    max_age = config.session_ttl_days * 86400

    response = RedirectResponse("/", status_code=302)

    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    is_https = request.url.scheme == "https" or forwarded_proto == "https"

    response.set_cookie(
        key="valhalla_session",
        value=session_cookie,
        httponly=True,
        samesite="lax",
        secure=is_https,
        path="/",
        max_age=max_age,
    )
    return response


@app.post("/logout")
async def logout(request: Request):
    """Clear session cookie and redirect to /."""
    response = RedirectResponse("/", status_code=302)
    response.delete_cookie(key="valhalla_session", path="/")
    return response


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health(request: Request):
    cfg = request.state.config
    payload = {
        "status": "ok",
        "service": "valhalla-capital-dashboard",
    }
    if cfg.expose_internal_details:
        payload.update({
            "services_monitored": len(SERVICES),
            "overseer_db": ext_db.overseer_available,
            "trading_db": ext_db.trading_available,
        })
    return payload


@app.get("/api/services")
async def api_services(request: Request):
    cfg = request.state.config
    snapshots = await db.get_latest_snapshots()
    result = []
    for svc in SERVICES:
        snap = snapshots.get(svc.name, {})
        entry = {
            "name": svc.name,
            "group": svc.group,
            "status": snap.get("status", ServiceStatus.ON_ORDER.value),
            "checked_at": snap.get("checked_at"),
            "response_ms": snap.get("response_ms"),
        }
        if cfg.expose_internal_details:
            entry["host"] = svc.host
            entry["error"] = snap.get("error")
        result.append(entry)
    return result


@app.get("/api/time")
async def api_time():
    """Server UTC time for clock sync."""
    return {"utc": datetime.now(timezone.utc).isoformat()}
