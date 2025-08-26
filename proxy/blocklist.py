import json
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Set

class BlocklistManager:
    def __init__(self, blocklist_file: str):
        self.blocklist_file = Path(blocklist_file)
        self._blocked_ips: Set[str] = set()
        self._last_modified = None
        self._lock = asyncio.Lock()
        self._load_interval = 30  # Reload blocklist every 30 seconds
        self._running = False

    async def start(self):
        """Start the periodic blocklist reload task"""
        self._running = True
        await self._load_blocklist()  # Initial load
        asyncio.create_task(self._periodic_reload())

    async def stop(self):
        """Stop the periodic blocklist reload task"""
        self._running = False

    async def is_blocked(self, ip: str) -> bool:
        """Check if an IP is blocked"""
        async with self._lock:
            return ip in self._blocked_ips

    async def add_ip(self, ip: str):
        """Add an IP to the blocklist"""
        async with self._lock:
            self._blocked_ips.add(ip)
            await self._save_blocklist()

    async def remove_ip(self, ip: str):
        """Remove an IP from the blocklist"""
        async with self._lock:
            self._blocked_ips.discard(ip)
            await self._save_blocklist()

    async def _load_blocklist(self):
        """Load the blocklist from file"""
        try:
            if not self.blocklist_file.exists():
                await self._save_blocklist()  # Create initial file if it doesn't exist
                return

            modified_time = self.blocklist_file.stat().st_mtime
            if self._last_modified == modified_time:
                return  # File hasn't changed

            async with self._lock:
                with open(self.blocklist_file, 'r') as f:
                    data = json.load(f)
                    self._blocked_ips = set(data.get('blocked_ips', []))
                    self._last_modified = modified_time
                    logging.info(f"Loaded {len(self._blocked_ips)} blocked IPs")
        except Exception as e:
            logging.error(f"Error loading blocklist: {e}")

    async def _save_blocklist(self):
        """Save the current blocklist to file"""
        try:
            data = {
                'blocked_ips': list(self._blocked_ips),
                'last_updated': datetime.utcnow().isoformat() + 'Z'
            }
            async with self._lock:
                with open(self.blocklist_file, 'w') as f:
                    json.dump(data, f, indent=4)
                self._last_modified = self.blocklist_file.stat().st_mtime
        except Exception as e:
            logging.error(f"Error saving blocklist: {e}")

    async def _periodic_reload(self):
        """Periodically reload the blocklist to catch external changes"""
        while self._running:
            await asyncio.sleep(self._load_interval)
            await self._load_blocklist()
