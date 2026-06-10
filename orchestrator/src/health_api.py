"""
ThermVate — Health Check API

Minimal FastAPI server that runs alongside the orchestrator for
Docker health checks and basic status queries.
"""

import asyncio
import logging

import uvicorn
from fastapi import FastAPI

logger = logging.getLogger("thermvate.api")

app = FastAPI(title="ThermVate", version="0.1.0")

# Reference to the orchestrator (set at startup)
_orchestrator = None


def set_orchestrator(orch):
    global _orchestrator
    _orchestrator = orch


@app.get("/health")
async def health():
    """Docker health check — returns 200 if orchestrator is running."""
    if _orchestrator and _orchestrator.running:
        return {"status": "ok", "service": "thermvate"}
    return {"status": "starting"}, 503


@app.get("/status")
async def status():
    """Detailed status of all subsystems."""
    if not _orchestrator:
        return {"status": "not_initialized"}

    return {
        "status": "running" if _orchestrator.running else "stopped",
        "uptime": None,  # TODO: track start time
        "mqtt": _orchestrator.mqtt.connected if _orchestrator.mqtt else False,
        "hal": {
            "type": _orchestrator.hal.type if _orchestrator.hal else None,
            "connected": _orchestrator.hal.connected if _orchestrator.hal else False,
        },
        "influx": _orchestrator.influx.connected if _orchestrator.influx else False,
        "zones": len(_orchestrator.config.get("zones", [])),
    }


@app.get("/zones")
async def zones():
    """List configured zones and latest data."""
    if not _orchestrator:
        return {"zones": []}

    zone_list = []
    for z in _orchestrator.config.get("zones", []):
        info = {"name": z["name"], "label": z.get("label", z["name"])}
        # Pull latest from InfluxDB
        if _orchestrator.influx and _orchestrator.influx.connected:
            for meas in ("temperature", "humidity", "co2"):
                latest = _orchestrator.influx.query_latest(meas, z["name"])
                if latest:
                    info[meas] = latest.get("value")
        zone_list.append(info)

    return {"zones": zone_list}


def start_health_api(host: str = "0.0.0.0", port: int = 8000):
    """Start the FastAPI server in a background thread."""
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)

    # Run in a separate thread so it doesn't block the async loop
    import threading
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    logger.info(f"Health API running on http://{host}:{port}")
    return server
