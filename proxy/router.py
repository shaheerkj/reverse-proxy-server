import yaml
import logging
from pathlib import Path

class Router:
    def __init__(self, routing_file):
        self.routing_file = Path(routing_file)
        self.routes = {}
        self.load_routes()

    def load_routes(self):
        try:
            with open(self.routing_file, "r") as f:
                self.routes = yaml.safe_load(f) or {}
            logging.info(f"Loaded routing table: {self.routes}")
        except FileNotFoundError:
            logging.error(f"Routing file not found: {self.routing_file}")
        except yaml.YAMLError as e:
            logging.error(f"Error parsing routing file: {e}")

    def get_backend(self, host):
        """Return (backend_host, backend_port) for given Host header"""
        host = host.lower().strip()
        if ":" in host:  # Remove port if present
            host = host.split(":")[0]

        backend_url = self.routes.get(host, {}).get("backend")
        if not backend_url:
            logging.warning(f"No backend found for host: {host}")
            return None

        # Parse URL like http://127.0.0.1:8000
        try:
            without_scheme = backend_url.replace("http://", "").replace("https://", "")
            backend_host, backend_port = without_scheme.split(":")
            return backend_host, int(backend_port)
        except Exception as e:
            logging.error(f"Invalid backend format for host {host}: {backend_url}")
            return None
