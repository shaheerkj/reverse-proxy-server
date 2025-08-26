#!/usr/bin/env python3
import asyncio
import logging
from proxy.server import ProxyServer

async def main():
    logging.basicConfig(level=logging.INFO)
    
    # Initialize logging system
    from request_logging.async_logger import init_loggers, shutdown_loggers
    await init_loggers()
    
    try:
        proxy = ProxyServer(
            host="0.0.0.0",
            port=8080,
            routing_file="config/routing.yaml"
        )
        await proxy.start()
    finally:
        await shutdown_loggers()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down...")
