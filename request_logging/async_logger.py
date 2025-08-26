import json
import asyncio
from collections import deque
from datetime import datetime
import aiofiles
import logging
from typing import Dict, List

class AsyncLogBuffer:
    def __init__(self, filename: str, flush_interval: int = 5, max_buffer: int = 100):
        self.filename = filename
        self.buffer = deque()
        self.flush_interval = flush_interval
        self.max_buffer = max_buffer
        self.lock = asyncio.Lock()
        self.flush_task = None

    async def start(self):
        self.flush_task = asyncio.create_task(self._periodic_flush())

    async def stop(self):
        if self.flush_task:
            self.flush_task.cancel()
            await self._flush()

    async def add(self, data: Dict):
        async with self.lock:
            self.buffer.append(data)
            if len(self.buffer) >= self.max_buffer:
                await self._flush()

    async def _periodic_flush(self):
        while True:
            await asyncio.sleep(self.flush_interval)
            await self._flush()

    async def _flush(self):
        if not self.buffer:
            return

        try:
            async with self.lock:
                to_write = list(self.buffer)
                self.buffer.clear()

            async with aiofiles.open(self.filename, "a") as f:
                for item in to_write:
                    await f.write(json.dumps(item) + "\n")
        except Exception as e:
            logging.error(f"Error flushing log buffer: {e}")

# Global log buffers
request_logger = AsyncLogBuffer("request_logging/logs.jsonl")
response_logger = AsyncLogBuffer("request_logging/responses.jsonl")

async def init_loggers():
    await request_logger.start()
    await response_logger.start()

async def shutdown_loggers():
    await request_logger.stop()
    await response_logger.stop()

async def log_request(request_data):
    await request_logger.add(request_data)

async def log_response(response_data):
    await response_logger.add(response_data)
