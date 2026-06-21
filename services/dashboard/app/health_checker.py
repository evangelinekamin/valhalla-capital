"""
Valhalla Capital Dashboard - Health Checker

Polls each registered service and records health snapshots.
Supports HTTP health endpoints and SSH status commands.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone

import httpx

from .config import SERVICES, DashboardConfig, ServiceDef, ServiceStatus
from .database import Database

logger = logging.getLogger(__name__)
config = DashboardConfig()


async def check_http_health(service: ServiceDef, client: httpx.AsyncClient) -> dict:
    """
    Check a service via its HTTP health endpoint.

    Returns:
        dict with keys: status, response_ms, details, error
    """
    if not service.health_url:
        return {
            "status": ServiceStatus.ON_ORDER.value,
            "response_ms": None,
            "details": None,
            "error": "No health endpoint configured",
        }

    try:
        t0 = time.monotonic()
        resp = await client.get(service.health_url, timeout=service.timeout)
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        if resp.status_code == 200:
            try:
                data = resp.json()
            except Exception:
                data = {"raw": resp.text[:500]}

            # Determine status from response
            svc_status = data.get("status", "").lower()
            if svc_status in ("ok", "healthy", "up"):
                status = ServiceStatus.SERVED.value
            elif svc_status in ("degraded", "warning"):
                status = ServiceStatus.MIXING.value
            else:
                # Got a 200 but status field is ambiguous — still "Served"
                status = ServiceStatus.SERVED.value

            return {
                "status": status,
                "response_ms": elapsed_ms,
                "details": data,
                "error": None,
            }
        else:
            return {
                "status": ServiceStatus.MIXING.value,
                "response_ms": elapsed_ms,
                "details": {"http_status": resp.status_code},
                "error": f"HTTP {resp.status_code}",
            }

    except httpx.TimeoutException:
        return {
            "status": ServiceStatus.EIGHTY_SIXED.value,
            "response_ms": service.timeout * 1000,
            "details": None,
            "error": f"Timeout after {service.timeout}s",
        }
    except httpx.ConnectError as e:
        return {
            "status": ServiceStatus.EIGHTY_SIXED.value,
            "response_ms": None,
            "details": None,
            "error": f"Connection refused: {e}",
        }
    except Exception as e:
        logger.exception(f"Health check failed for {service.name}")
        return {
            "status": ServiceStatus.EIGHTY_SIXED.value,
            "response_ms": None,
            "details": None,
            "error": str(e),
        }


async def check_ssh_status(service: ServiceDef) -> dict:
    """
    Check a service via SSH status command.

    Runs the command on the remote host and parses JSON output.
    Requires SSH key auth to be set up (no password prompts).
    """
    if not service.status_cmd:
        return {
            "status": ServiceStatus.ON_ORDER.value,
            "response_ms": None,
            "details": None,
            "error": "No status command configured",
        }

    try:
        t0 = time.monotonic()
        proc = await asyncio.create_subprocess_exec(
            "ssh", "-i", config.ssh_key_path,
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=5",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", f"UserKnownHostsFile={config.ssh_known_hosts_path}",
            f"root@{service.host}", service.status_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=service.timeout
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        if proc.returncode == 0:
            try:
                data = json.loads(stdout.decode())
                svc_status = data.get("status", "").lower()
                if svc_status in ("ok", "healthy"):
                    status = ServiceStatus.SERVED.value
                elif svc_status in ("degraded", "warning"):
                    status = ServiceStatus.MIXING.value
                else:
                    status = ServiceStatus.SERVED.value
                return {
                    "status": status,
                    "response_ms": elapsed_ms,
                    "details": data,
                    "error": None,
                }
            except json.JSONDecodeError:
                return {
                    "status": ServiceStatus.MIXING.value,
                    "response_ms": elapsed_ms,
                    "details": {"raw": stdout.decode()[:500]},
                    "error": "Non-JSON response from status command",
                }
        else:
            return {
                "status": ServiceStatus.EIGHTY_SIXED.value,
                "response_ms": elapsed_ms,
                "details": None,
                "error": f"Exit code {proc.returncode}: {stderr.decode()[:200]}",
            }

    except asyncio.TimeoutError:
        return {
            "status": ServiceStatus.EIGHTY_SIXED.value,
            "response_ms": service.timeout * 1000,
            "details": None,
            "error": f"SSH timeout after {service.timeout}s",
        }
    except Exception as e:
        logger.exception(f"SSH status check failed for {service.name}")
        return {
            "status": ServiceStatus.EIGHTY_SIXED.value,
            "response_ms": None,
            "details": None,
            "error": str(e),
        }


async def check_service(service: ServiceDef, client: httpx.AsyncClient) -> dict:
    """Check a single service using the best available method."""
    if service.health_url:
        return await check_http_health(service, client)
    elif service.status_cmd:
        return await check_ssh_status(service)
    else:
        return {
            "status": ServiceStatus.ON_ORDER.value,
            "response_ms": None,
            "details": None,
            "error": "No health check configured — wire up an endpoint",
        }


async def run_health_checks(db: Database):
    """Run health checks for all registered services and store results."""
    logger.info("Running health checks for %d services", len(SERVICES))
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(10.0),
        limits=httpx.Limits(
            max_connections=max(len(SERVICES) + 2, 10),
            max_keepalive_connections=10,
        ),
    ) as client:
        tasks = [check_service(svc, client) for svc in SERVICES]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    snapshots_to_save = []
    for service, result in zip(SERVICES, results):
        if isinstance(result, Exception):
            logger.error(f"Check failed for {service.name}: {result}")
            result = {
                "status": ServiceStatus.EIGHTY_SIXED.value,
                "response_ms": None,
                "details": None,
                "error": str(result),
            }
        snapshots_to_save.append({
            "service_name": service.name,
            "status": result["status"],
            "response_ms": result.get("response_ms"),
            "details": result.get("details"),
            "error": result.get("error"),
        })
    await db.save_snapshots(snapshots_to_save)
    logger.info("Health checks complete")
