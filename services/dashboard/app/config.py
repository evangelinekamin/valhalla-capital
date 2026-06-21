"""
Valhalla Capital Dashboard - Configuration

Service definitions and dashboard settings.
Each service entry defines how to health-check a component of the trading system.
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from dotenv import load_dotenv

load_dotenv()


def env_bool(name: str, default: bool) -> bool:
    """Parse a boolean env var with a sane fallback."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


PUBLIC_DASHBOARD = env_bool("PUBLIC_DASHBOARD", False)
EXPOSE_INTERNAL_DETAILS = env_bool(
    "EXPOSE_INTERNAL_DETAILS", not PUBLIC_DASHBOARD
)
ALLOW_MANUAL_CHECKS = env_bool(
    "ALLOW_MANUAL_CHECKS", not PUBLIC_DASHBOARD
)


class ServiceStatus(str, Enum):
    """Service health states, VA-11 Hall-A style."""
    SERVED = "Served"       # Healthy - everything nominal
    MIXING = "Mixing"       # Degraded - responding but issues detected
    EIGHTY_SIXED = "86'd"   # Down - not responding
    ON_ORDER = "On Order"   # Unknown - hasn't been checked yet
    LAST_CALL = "Last Call"  # Warning - approaching limits


@dataclass
class ServiceDef:
    """Definition of a monitorable service."""
    name: str
    host: str
    description: str
    health_url: str | None = None       # HTTP health endpoint
    status_cmd: str | None = None       # SSH command for status (fallback)
    port: int | None = None
    group: str = "infrastructure"       # For grouping on the status page
    check_interval: int = 60            # Seconds between checks
    timeout: int = 10                   # Health check timeout
    expected_fields: list[str] = field(default_factory=list)  # Fields to extract from health JSON


# ---------------------------------------------------------------------------
# Service Registry
# ---------------------------------------------------------------------------
# Each service your system runs gets an entry here. The dashboard polls these
# on a schedule and stores snapshots in its local SQLite.
# ---------------------------------------------------------------------------

SERVICES: list[ServiceDef] = [
    # -- Data Collection LXC (<LAN_IP>) --
    ServiceDef(
        name="Twitter Monitor",
        host="<LAN_IP>",
        port=8082,
        description="Nitter RSS → Miniflux → Claude triage pipeline",
        health_url="http://<LAN_IP>:8082/health",
        group="data",
        expected_fields=["status", "database", "processing"],
    ),
    ServiceDef(
        name="News Monitor",
        host="<LAN_IP>",
        description="RSS feed ingestion via news-worker.service",
        status_cmd="systemctl is-active news-worker.service >/dev/null 2>&1 && echo '{\"status\":\"ok\"}' || echo '{\"status\":\"down\"}'",
        group="data",
    ),
    ServiceDef(
        name="Yellowbrick Scraper",
        host="<LAN_IP>",
        description="Daily yellowbrick.com data fetch (08:00 UTC)",
        status_cmd="systemctl is-active yellowbrick-scraper.timer >/dev/null 2>&1 && echo '{\"status\":\"ok\"}' || echo '{\"status\":\"down\"}'",
        group="data",
    ),

    # -- FMP LXC (<LAN_IP>) --
    ServiceDef(
        name="FMP Data Client",
        host="<LAN_IP>",
        port=8000,
        description="Financial Modeling Prep API with MySQL cache",
        health_url="http://<LAN_IP>:8000/health",
        group="data",
        expected_fields=["status", "cache", "rate_limit"],
    ),

    # -- Trading LXC (<LAN_IP>) --
    ServiceDef(
        name="IB Gateway",
        host="<LAN_IP>",
        description="Interactive Brokers API gateway",
        status_cmd="docker inspect --format='{{.State.Status}}' ib-gateway 2>/dev/null | grep -q running && echo '{\"status\":\"ok\"}' || echo '{\"status\":\"down\"}'",
        group="execution",
    ),
    ServiceDef(
        name="Trade Executor",
        host="<LAN_IP>",
        description="Order management & Kelly sizing",
        status_cmd="docker inspect --format='{{.State.Status}}' trading-service 2>/dev/null | grep -q running && echo '{\"status\":\"ok\"}' || echo '{\"status\":\"down\"}'",
        group="execution",
    ),

    # -- Overseer LXC (<LAN_IP>) --
    ServiceDef(
        name="Overseer",
        host="<LAN_IP>",
        description="Orchestration, supervision, escalation",
        status_cmd="systemctl is-active valkyrie-overseer.service >/dev/null 2>&1 && echo '{\"status\":\"ok\"}' || echo '{\"status\":\"down\"}'",
        group="brain",
    ),

    # -- Dashboard LXC (<LAN_IP>) --
    ServiceDef(
        name="Dashboard",
        host="<LAN_IP>",
        port=8050,
        description="This service (self-check)",
        health_url="http://localhost:8050/health",
        group="infrastructure",
    ),
]


# Group display order and labels
SERVICE_GROUPS = {
    "data": {"label": "Data Intake", "order": 0},
    "execution": {"label": "Execution", "order": 1},
    "brain": {"label": "Oversight", "order": 2},
    "infrastructure": {"label": "Infrastructure", "order": 3},
}


@dataclass
class DashboardConfig:
    """Top-level dashboard configuration."""
    app_name: str = "VALHALLA CAPITAL"
    app_subtitle: str = "fund monitoring terminal"
    host: str = os.getenv("DASHBOARD_HOST", "0.0.0.0")
    port: int = int(os.getenv("DASHBOARD_PORT", "8050"))
    db_path: str = os.getenv("DASHBOARD_DB", "valhalla_capital.db")
    poll_interval: int = int(os.getenv("POLL_INTERVAL", "60"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    public_mode: bool = PUBLIC_DASHBOARD
    expose_internal_details: bool = EXPOSE_INTERNAL_DETAILS
    allow_manual_checks: bool = ALLOW_MANUAL_CHECKS
    slow_request_ms: int = int(os.getenv("SLOW_REQUEST_MS", "500"))
    ssh_key_path: str = os.getenv(
        "SSH_KEY_PATH", "/opt/valhalla-capital/.ssh/id_ed25519"
    )
    ssh_known_hosts_path: str = os.getenv(
        "SSH_KNOWN_HOSTS_PATH", "/opt/valhalla-capital/.ssh/known_hosts"
    )

    # Overseer PostgreSQL (<LAN_IP>) — Valkyrie's brain
    overseer_db_host: str = os.getenv("OVERSEER_DB_HOST", "<LAN_IP>")
    overseer_db_port: int = int(os.getenv("OVERSEER_DB_PORT", "5432"))
    overseer_db_name: str = os.getenv("OVERSEER_DB_NAME", "overseer")
    overseer_db_user: str = os.getenv("OVERSEER_DB_USER", "readonly")
    overseer_db_password: str = os.getenv("OVERSEER_DB_PASSWORD", "")

    # FMP Proxy (<LAN_IP>) — live quotes for P&L
    fmp_proxy_url: str = os.getenv("FMP_PROXY_URL", "")
    fmp_api_key: str = os.getenv("FMP_API_KEY", "")

    # Authentication
    session_secret: str = os.getenv("SESSION_SECRET", "")
    owner_password_hash: str = os.getenv("OWNER_PASSWORD_HASH", "")
    session_ttl_days: int = int(os.getenv("SESSION_TTL_DAYS", "7"))
