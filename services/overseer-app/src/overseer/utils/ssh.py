from __future__ import annotations

import asyncio
import shlex

import structlog

log = structlog.get_logger()

DEFAULT_SSH_KEY = "/opt/Valkyrie/valhalla_key"
SSH_TIMEOUT = 30


async def ssh_command(
    host: str,
    command: str,
    *,
    user: str = "root",
    key_path: str = DEFAULT_SSH_KEY,
    timeout: int = SSH_TIMEOUT,
) -> str:
    ssh_args = [
        "ssh",
        "-i", key_path,
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=10",
        "-o", "BatchMode=yes",
        f"{user}@{host}",
        command,
    ]

    log.debug("ssh_command", host=host, command=command[:100])

    proc = await asyncio.create_subprocess_exec(
        *ssh_args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        raise TimeoutError(f"SSH command timed out after {timeout}s: {command[:80]}")

    if proc.returncode != 0:
        err_msg = stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"SSH command failed (rc={proc.returncode}): {err_msg}")

    return stdout.decode("utf-8", errors="replace")


async def ssh_sqlite_query(
    host: str,
    db_path: str,
    query: str,
    *,
    mode: str = "json",
    key_path: str = DEFAULT_SSH_KEY,
) -> str:
    safe_query = shlex.quote(query)
    if mode == "json":
        cmd = f"sqlite3 -json {shlex.quote(db_path)} {safe_query}"
    else:
        cmd = f"sqlite3 -header -separator '|' {shlex.quote(db_path)} {safe_query}"
    return await ssh_command(host, cmd, key_path=key_path)


async def ssh_read_file(
    host: str,
    file_path: str,
    *,
    key_path: str = DEFAULT_SSH_KEY,
) -> str:
    return await ssh_command(host, f"cat {shlex.quote(file_path)}", key_path=key_path)
