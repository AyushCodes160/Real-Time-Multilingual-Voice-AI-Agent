"""
Keep-Alive Pinger for Render Free Tier
───────────────────────────────────────
Render spins down free-tier services after 15 min of inactivity.
This module self-pings the /health endpoint every 10 minutes
so the service stays up 24/7.
"""

import asyncio
import os
import aiohttp

SELF_PING_INTERVAL = int(os.getenv("KEEP_ALIVE_INTERVAL", "600"))  # 10 min default

async def _ping_loop():
    """Continuously ping the service's own /health endpoint."""
    # Determine the public URL (Render sets RENDER_EXTERNAL_URL automatically)
    base_url = os.getenv("RENDER_EXTERNAL_URL") or os.getenv("SERVICE_URL")
    if not base_url:
        port = os.getenv("PORT", "7860")
        base_url = f"http://0.0.0.0:{port}"

    health_url = f"{base_url}/health"
    print(f"[KEEP-ALIVE] Pinging {health_url} every {SELF_PING_INTERVAL}s")

    async with aiohttp.ClientSession() as session:
        while True:
            await asyncio.sleep(SELF_PING_INTERVAL)
            try:
                async with session.get(health_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    print(f"[KEEP-ALIVE] Ping → {resp.status}")
            except Exception as e:
                print(f"[KEEP-ALIVE] Ping failed: {e}")


def start_keep_alive():
    """Spawn the keep-alive ping loop as a background asyncio task."""
    loop = asyncio.get_event_loop()
    loop.create_task(_ping_loop())
    print("[KEEP-ALIVE] Background keep-alive pinger started (24/7 uptime).")
