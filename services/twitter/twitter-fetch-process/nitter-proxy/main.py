"""Nitter RSS proxy with automatic PoW challenge solving.

Sits between Miniflux and public Nitter instances. Solves Anubis
proof-of-work challenges and caches auth cookies so Miniflux gets
clean RSS XML without needing a browser.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx
from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse, PlainTextResponse

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("nitter-proxy")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

INSTANCES = [
    s.strip()
    for s in os.environ.get(
        "NITTER_INSTANCES",
        "nitter.privacyredirect.com",
    ).split(",")
    if s.strip()
]

USER_AGENT = os.environ.get(
    "PROXY_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
)

REQUEST_TIMEOUT = float(os.environ.get("REQUEST_TIMEOUT", "20"))
COOKIE_TTL_DAYS = float(os.environ.get("COOKIE_TTL_DAYS", "6"))

# ---------------------------------------------------------------------------
# Cookie cache
# ---------------------------------------------------------------------------


@dataclass
class CachedAuth:
    cookies: dict[str, str] = field(default_factory=dict)
    expires_at: float = 0.0
    user_agent: str = ""


_auth_cache: dict[str, CachedAuth] = {}
_cache_lock = asyncio.Lock()


def _get_cached(instance: str) -> Optional[dict[str, str]]:
    entry = _auth_cache.get(instance)
    if entry and entry.expires_at > time.time() and entry.user_agent == USER_AGENT:
        return dict(entry.cookies)
    return None


async def _set_cached(instance: str, cookies: dict[str, str]) -> None:
    async with _cache_lock:
        _auth_cache[instance] = CachedAuth(
            cookies=dict(cookies),
            expires_at=time.time() + COOKIE_TTL_DAYS * 86400,
            user_agent=USER_AGENT,
        )


# ---------------------------------------------------------------------------
# PoW solvers
# ---------------------------------------------------------------------------


def _solve_anubis_preact(random_data: str) -> str:
    return hashlib.sha256(random_data.encode()).hexdigest()


def _solve_anubis_fast(random_data: str, difficulty: int) -> tuple[str, int]:
    prefix = "0" * difficulty
    for nonce in range(20_000_000):
        candidate = (random_data + str(nonce)).encode()
        h = hashlib.sha256(candidate).hexdigest()
        if h.startswith(prefix):
            return h, nonce
    raise RuntimeError(f"Failed to solve fast PoW after 20M attempts (difficulty={difficulty})")


def _solve_sgcaptcha(challenge: str, complexity: int) -> tuple[str, int]:
    """SHA1-based PoW used by some instances (sgcaptcha)."""
    challenge_bytes = challenge.encode()
    for nonce in range(10_000_000):
        candidate = challenge_bytes + str(nonce).encode()
        digest = hashlib.sha1(candidate).digest()
        first_word = int.from_bytes(digest[:4], byteorder="big")
        if (first_word >> (32 - complexity)) == 0:
            return candidate.decode(), nonce
    raise RuntimeError(f"Failed to solve sgcaptcha after 10M attempts (complexity={complexity})")


# ---------------------------------------------------------------------------
# Challenge detection and solving
# ---------------------------------------------------------------------------


def _parse_anubis_challenge(html: str) -> Optional[dict]:
    match = re.search(
        r'<script\s+id="anubis_challenge"[^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except (json.JSONDecodeError, KeyError):
        return None


def _parse_sgcaptcha_redirect(html: str) -> Optional[str]:
    match = re.search(r'content="0;(/.well-known/sgcaptcha/[^"]*)"', html)
    return match.group(1) if match else None


async def _solve_anubis(
    client: httpx.AsyncClient,
    instance: str,
    challenge_data: dict,
    original_path: str,
) -> Optional[dict[str, str]]:
    """Solve an Anubis challenge and return cookies dict."""
    rules = challenge_data.get("rules", {})
    ch = challenge_data.get("challenge", {})
    algorithm = rules.get("algorithm", "")
    difficulty = rules.get("difficulty", 4)
    random_data = ch.get("randomData", "")
    challenge_id = ch.get("id", "")

    base = f"https://{instance}"
    pass_url = f"{base}/.within.website/x/cmd/anubis/api/pass-challenge"

    if algorithm == "preact":
        result = _solve_anubis_preact(random_data)
        await asyncio.sleep(difficulty * 0.080 + 0.150)
        log.info("Solved Anubis preact for %s (difficulty=%d)", instance, difficulty)
        r = await client.get(
            pass_url,
            params={"id": challenge_id, "redir": original_path, "result": result},
            follow_redirects=False,
        )

    elif algorithm in ("fast", "slow"):
        result_hash, nonce = _solve_anubis_fast(random_data, difficulty)
        log.info(
            "Solved Anubis %s for %s (difficulty=%d, nonce=%d)",
            algorithm, instance, difficulty, nonce,
        )
        r = await client.get(
            pass_url,
            params={
                "id": challenge_id,
                "redir": original_path,
                "response": result_hash,
                "nonce": str(nonce),
                "elapsedTime": "500",
            },
            follow_redirects=False,
        )

    else:
        log.warning("Unknown Anubis algorithm: %s", algorithm)
        return None

    cookies = {k: v for k, v in client.cookies.items()}
    if cookies:
        return cookies
    return None


async def _solve_sgcaptcha_flow(
    client: httpx.AsyncClient,
    instance: str,
    redirect_path: str,
    original_path: str,
) -> Optional[dict[str, str]]:
    """Solve an SGCaptcha challenge and return cookies dict."""
    base = f"https://{instance}"
    r = await client.get(f"{base}{redirect_path}")

    challenge_match = re.search(r'const sgchallenge="([^"]+)"', r.text)
    submit_match = re.search(r'const sgsubmit_url="([^"]+)"', r.text)
    if not challenge_match or not submit_match:
        return None

    challenge = challenge_match.group(1)
    submit_url = submit_match.group(1)
    complexity = int(challenge.split(":")[0])

    solution, nonce = _solve_sgcaptcha(challenge, complexity)
    import base64
    sol_b64 = base64.b64encode(solution.encode()).decode()

    log.info("Solved SGCaptcha for %s (complexity=%d, nonce=%d)", instance, complexity, nonce)

    r = await client.get(
        f"{base}{submit_url}&sol={sol_b64}&s=500:{nonce}",
        follow_redirects=False,
    )

    cookies = {k: v for k, v in client.cookies.items()}
    return cookies if cookies else None


# ---------------------------------------------------------------------------
# RSS fetcher
# ---------------------------------------------------------------------------


def _is_valid_rss(text: str) -> bool:
    return bool(text) and ("<rss" in text or "<?xml" in text)


async def _fetch_from_instance(
    instance: str,
    path: str,
) -> Optional[tuple[str, str]]:
    """Fetch RSS from a single instance. Returns (content, instance) or None."""
    cached = _get_cached(instance)

    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        timeout=REQUEST_TIMEOUT,
    ) as client:
        if cached:
            for name, value in cached.items():
                client.cookies.set(name, value, domain=instance)

        url = f"https://{instance}{path}"
        r = await client.get(url)

        # Already valid RSS (cached cookie worked)
        if _is_valid_rss(r.text):
            return r.text, instance

        # Check for Anubis challenge
        challenge_data = _parse_anubis_challenge(r.text)
        if challenge_data:
            cookies = await _solve_anubis(client, instance, challenge_data, path)
            if cookies:
                await _set_cached(instance, cookies)
                for name, value in cookies.items():
                    client.cookies.set(name, value, domain=instance)
                r = await client.get(url)
                if _is_valid_rss(r.text):
                    return r.text, instance
                log.warning("Anubis solved but still no RSS from %s (status=%d)", instance, r.status_code)
            else:
                log.warning("Failed to solve Anubis challenge for %s", instance)
            return None

        # Check for SGCaptcha redirect (HTTP 202 pattern)
        sg_redirect = _parse_sgcaptcha_redirect(r.text)
        if sg_redirect:
            cookies = await _solve_sgcaptcha_flow(client, instance, sg_redirect, path)
            if cookies:
                await _set_cached(instance, cookies)
                for name, value in cookies.items():
                    client.cookies.set(name, value, domain=instance)
                r = await client.get(url)
                if _is_valid_rss(r.text):
                    return r.text, instance
            return None

        # Unknown challenge or RSS disabled
        log.warning(
            "No valid RSS from %s (status=%d, len=%d)",
            instance, r.status_code, len(r.text),
        )
        return None


# ---------------------------------------------------------------------------
# Instance health tracking
# ---------------------------------------------------------------------------


@dataclass
class InstanceHealth:
    successes: int = 0
    failures: int = 0
    last_success: float = 0.0
    last_failure: float = 0.0
    consecutive_failures: int = 0


_health: dict[str, InstanceHealth] = {}


def _record_success(instance: str) -> None:
    h = _health.setdefault(instance, InstanceHealth())
    _health[instance] = InstanceHealth(
        successes=h.successes + 1,
        failures=h.failures,
        last_success=time.time(),
        last_failure=h.last_failure,
        consecutive_failures=0,
    )


def _record_failure(instance: str) -> None:
    h = _health.setdefault(instance, InstanceHealth())
    _health[instance] = InstanceHealth(
        successes=h.successes,
        failures=h.failures + 1,
        last_success=h.last_success,
        last_failure=time.time(),
        consecutive_failures=h.consecutive_failures + 1,
    )


def _sorted_instances() -> list[str]:
    """Return instances sorted by health (fewest consecutive failures first)."""
    return sorted(
        INSTANCES,
        key=lambda i: _health.get(i, InstanceHealth()).consecutive_failures,
    )


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Nitter RSS Proxy")


@app.get("/health")
async def health():
    return JSONResponse({
        "status": "ok",
        "instances": INSTANCES,
        "cached": [
            {"instance": k, "expires_in_hours": round((v.expires_at - time.time()) / 3600, 1)}
            for k, v in _auth_cache.items()
            if v.expires_at > time.time()
        ],
        "health": {
            k: {
                "successes": v.successes,
                "failures": v.failures,
                "consecutive_failures": v.consecutive_failures,
            }
            for k, v in _health.items()
        },
    })


@app.get("/{username}/rss")
async def proxy_rss(username: str):
    path = f"/{username}/rss"
    errors = []

    for instance in _sorted_instances():
        h = _health.get(instance, InstanceHealth())
        # Skip instances with 10+ consecutive failures (check every 5 min)
        if h.consecutive_failures >= 10 and (time.time() - h.last_failure) < 300:
            continue

        try:
            result = await _fetch_from_instance(instance, path)
            if result:
                content, inst = result
                _record_success(inst)
                return Response(
                    content=content,
                    media_type="application/rss+xml",
                    headers={"X-Nitter-Instance": inst},
                )
            else:
                _record_failure(instance)
                errors.append(f"{instance}: no valid RSS")
        except Exception as e:
            _record_failure(instance)
            errors.append(f"{instance}: {type(e).__name__}: {e}")
            log.error("Error fetching from %s: %s", instance, e)

    log.error("All instances failed for %s: %s", username, "; ".join(errors))
    return PlainTextResponse(
        f"All Nitter instances failed for @{username}",
        status_code=502,
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8090"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
