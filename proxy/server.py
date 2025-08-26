import asyncio
import logging
from proxy.router import Router
from request_logging.normalize import log_request, log_response, parse_response

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
            
            # Check if this is a WebSocket upgrade request
            request_text = request.decode(errors="ignore")
            is_websocket = "upgrade: websocket" in request_text.lower()

            # Send raw request to log_request and get request_id
            peername = writer.get_extra_info("peername")
            client_ip = peername[0] if peername else None
            # Patch: get request_id from log_request
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
            # Run logging in background
            asyncio.create_task(log_request(request_data))

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

            try:
                # Set a timeout for backend connection
                backend_reader, backend_writer = await asyncio.wait_for(
                    asyncio.open_connection(backend_host, backend_port), timeout=10.0
                )
            except asyncio.TimeoutError:
                logging.error(f"Timeout connecting to backend {backend_host}:{backend_port}")
                writer.write(b"HTTP/1.1 504 Gateway Timeout\r\n\r\nBackend connection timed out")
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                return
            except Exception as e:
                logging.error(f"Error connecting to backend {backend_host}:{backend_port}: {e}")
                writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\nBackend connection error")
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                return

            try:
                # Remove Host, Referer, and Origin headers, then add Host for backend
                request_lines = request.decode(errors="ignore").split("\r\n")
                new_lines = []
                for line in request_lines:
                    lower_line = line.lower()
                    if lower_line.startswith("host:") or lower_line.startswith("referer:") or lower_line.startswith("origin:"):
                        continue  # Skip these headers
                    new_lines.append(line)
                # Add Host header for backend (do not leak proxy info)
                new_lines.insert(1, f"Host: {backend_host}:{backend_port}")
                new_request = "\r\n".join(new_lines).encode()

                backend_writer.write(new_request)
                await backend_writer.drain()

                if is_websocket:
                    # Handle WebSocket connection
                    await self._handle_websocket(reader, writer, backend_reader, backend_writer)
                else:
                    # Handle normal HTTP connection
                    first_chunk = True
                    full_response = b""
                    while True:
                        try:
                            data = await asyncio.wait_for(backend_reader.read(65536), timeout=15.0)
                        except asyncio.TimeoutError:
                            logging.error(f"Timeout reading from backend {backend_host}:{backend_port}")
                            break
                        except Exception as e:
                            logging.error(f"Error reading from backend {backend_host}:{backend_port}: {e}")
                            break
                        if not data:
                            break
                        
                        # Rewrite URLs in response to use proxy domain
                        response_data = data.decode('utf-8', errors='ignore')
                        response_data = response_data.replace(f'http://{backend_host}:{backend_port}', f'http://{host_header}')
                        response_data = response_data.replace(f'https://{backend_host}:{backend_port}', f'http://{host_header}')
                        
                        writer.write(response_data.encode('utf-8'))
                        await writer.drain()
                        full_response += data
                        if first_chunk:
                            status_line, response_headers, response_body = parse_response(full_response)
                            response_data = {
                                "id": request_id,
                                "timestamp": dt.utcnow().isoformat() + "Z",
                                "status_line": status_line,
                                "headers": response_headers,
                                "body": response_body
                            }
                            # Run logging in background
                            asyncio.create_task(log_response(response_data))
                            first_chunk = False
            finally:
                try:
                    backend_writer.close()
                    await backend_writer.wait_closed()
                except Exception as e:
                    logging.error(f"Error closing backend connection: {e}")
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception as e:
                    logging.error(f"Error closing client connection: {e}")

        except Exception as e:
            logging.error(f"Error in handle_client: {e}")

    async def _handle_websocket(self, client_reader, client_writer, backend_reader, backend_writer):
        """Handle WebSocket connection by forwarding data in both directions"""
        async def forward(reader, writer):
            try:
                while True:
                    data = await reader.read(65536)
                    if not data:
                        break
                    writer.write(data)
                    await writer.drain()
            except Exception as e:
                logging.error(f"Error in WebSocket forwarding: {e}")

        # Create tasks for both directions
        client_to_backend = asyncio.create_task(forward(client_reader, backend_writer))
        backend_to_client = asyncio.create_task(forward(backend_reader, client_writer))

        # Wait for both directions to complete
        try:
            await asyncio.gather(client_to_backend, backend_to_client)
        except Exception as e:
            logging.error(f"Error in WebSocket connection: {e}")
        finally:
            client_to_backend.cancel()
            backend_to_client.cancel()

    async def start(self):
        server = await asyncio.start_server(self.handle_client, self.host, self.port)
        logging.info(f"Proxy server listening on {self.host}:{self.port}")
        async with server:
            await server.serve_forever()
