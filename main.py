#!/usr/bin/env python3
import asyncio
import logging
from proxy.server import ProxyServer

async def main():
    logging.basicConfig(level=logging.INFO)

    proxy = ProxyServer(
        host="0.0.0.0",
        port=8080,
        routing_file="config/routing.yaml"
    )
    await proxy.start()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down...")
