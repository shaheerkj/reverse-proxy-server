import asyncio
import logging
from proxy.router import Router
from request_logging.normalize import normalize_and_log_request
from request_logging.normalize import log_request

class ProxyServer:
    def __init__(self, host, port, routing_file):
        self.host = host
        self.port = port
        self.router = Router(routing_file)

    async def handle_client(self, reader, writer):
        try:
            # Read incoming request
            request = await reader.read(65536)
            if not request:
                writer.close()
                await writer.wait_closed()
                return

            # Send raw request to normalize_and_log_request and get request_id
            peername = writer.get_extra_info("peername")
            client_ip = peername[0] if peername else None
            # Patch: get request_id from normalize_and_log_request
            import uuid
            request_id = str(uuid.uuid4())
            from request_logging.normalize import log_request
            request_text = request.decode(errors="ignore")
            lines = request_text.split("\r\n")
            request_line = lines[0].split()
            method = request_line[0] if len(request_line) > 0 else ""
            path = request_line[1] if len(request_line) > 1 else ""
            headers = {}
            i = 1
            while i < len(lines) and lines[i]:
                if ":" in lines[i]:
                    k, v = lines[i].split(":", 1)
                    headers[k.strip()] = v.strip()
                i += 1
            body = "\r\n".join(lines[i+1:]) if i+1 < len(lines) else ""
            host = headers.get("Host", "")
            from datetime import datetime as dt
            timestamp = dt.utcnow().isoformat() + "Z"
            request_data = {
                "id": request_id,
                "timestamp": timestamp,
                "client_ip": client_ip,
                "host": host,
                "method": method,
                "path": path,
                "headers": headers,
                "body": body
            }
            log_request(request_data)

            # Extract Host header
            headers = request.decode(errors="ignore").split("\r\n")
            host_header = None
            for h in headers:
                if h.lower().startswith("host:"):
                    host_header = h.split(":", 1)[1].strip()
                    break

            if not host_header:
                logging.warning("No Host header found in request")
                writer.close()
                await writer.wait_closed()
                return

            backend = self.router.get_backend(host_header)
            if not backend:
                writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\nNo backend found")
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                return

            backend_host, backend_port = backend
            logging.info(f"Routing {host_header} -> {backend_host}:{backend_port}")

            backend_reader, backend_writer = await asyncio.open_connection(
                backend_host, backend_port
            )

            backend_writer.write(request)
            await backend_writer.drain()

            # Relay response and log it
            from request_logging.normalize import log_response, parse_response
            full_response = b""
            while True:
                data = await backend_reader.read(65536)
                if not data:
                    break
                writer.write(data)
                await writer.drain()
                full_response += data

            backend_writer.close()
            await backend_writer.wait_closed()
            writer.close()
            await writer.wait_closed()

            # Log the response
            status_line, response_headers, response_body = parse_response(full_response)
            response_data = {
                "id": request_id,
                "timestamp": dt.utcnow().isoformat() + "Z",
                "status_line": status_line,
                "headers": response_headers,
                "body": response_body
            }
            log_response(response_data)

        except Exception as e:
            logging.error(f"Error in handle_client: {e}")

    async def start(self):
        server = await asyncio.start_server(self.handle_client, self.host, self.port)
        logging.info(f"Proxy server listening on {self.host}:{self.port}")
        async with server:
            await server.serve_forever()
