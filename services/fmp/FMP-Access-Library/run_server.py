#!/usr/bin/env python3
"""Start the FMP Data Client REST API server."""

import os
import sys

try:
    import uvicorn
except ImportError:
    print("Error: uvicorn is not installed. Install with: pip install 'fmp-data-client[server]'")
    sys.exit(1)

from fmp_data_client.server import app

if __name__ == "__main__":
    # Get configuration from environment
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    reload = os.getenv("API_RELOAD", "false").lower() == "true"
    workers = int(os.getenv("API_WORKERS", "1"))

    print(f"Starting FMP Data Client API server on {host}:{port}")
    print(f"Documentation available at: http://{host}:{port}/docs")
    print(f"ReDoc available at: http://{host}:{port}/redoc")
    print("\nPress CTRL+C to quit\n")

    uvicorn.run(
        "fmp_data_client.server:app",
        host=host,
        port=port,
        reload=reload,
        workers=workers if not reload else 1,
        log_level="info",
    )
