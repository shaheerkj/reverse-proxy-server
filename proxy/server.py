import asyncio, logging
from typing import Tuple
from dataclasses import dataclass
from http import HTTPStatus
from datetime import datetime
import uuid
from proxy.router import Router
from request_logging.normalize import log_request, log_response, parse_response
from proxy.blocklist import BlocklistManager

class ProxyServer:
    def __init__(self, host, port, routing_file):
        self.host = host
        self.port = port
        self.router = Router(routing_file)
        self.blocklist = BlocklistManager("config/blocklist.json")
        

    async def handle_client(self, reader, writer):
        try:
            # Read initial request with smaller buffer
            request = await reader.read(8192)  # 8KB buffer is usually sufficient for headers
            if not request:
                writer.close()
                await writer.wait_closed()
                return
            
            # Check if this is a WebSocket upgrade request
            request_text = request.decode(errors="ignore")
            is_websocket = "upgrade: websocket" in request_text.lower()

            # Get and check client IP
            peername = writer.get_extra_info("peername")
            client_ip = peername[0] if peername else None
            
            # Check if IP is blocked
            if client_ip and await self.blocklist.is_blocked(client_ip):
                logging.warning(f"Blocked request from banned IP: {client_ip}")
                writer.write(b"HTTP/1.1 403 Forbidden\r\n\r\nYour IP is blocked")
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                return
            request_id = str(uuid.uuid4())
            
            # Parse request headers and body
            lines = request_text.split("\r\n")
            request_line = lines[0].split()
            method = request_line[0] if len(request_line) > 0 else ""
            path = request_line[1] if len(request_line) > 1 else ""
            
            # Parse headers
            headers = {}
            i = 1
            while i < len(lines) and lines[i]:
                if ":" in lines[i]:
                    k, v = lines[i].split(":", 1)
                    headers[k.strip()] = v.strip()
                i += 1
            
            # Get body
            body = "\r\n".join(lines[i+1:]) if i+1 < len(lines) else ""
            from datetime import datetime as dt
            timestamp = dt.utcnow().isoformat() + "Z"
            request_data = {
                "id": request_id,
                "timestamp": timestamp,
                "client_ip": client_ip,
                "host": headers.get("Host", ""),
                "method": method,
                "path": path,
                "headers": headers,
                "body": body
            }
            # Run logging in background
            asyncio.create_task(log_request(request_data))

            # Use the already parsed headers to get host
            host_header = headers.get("Host", "")

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
                    asyncio.open_connection(backend_host, backend_port),
                    timeout=10.0
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
                    header_buffer = bytearray()
                    
                    while True:
                        try:
                            chunk = await asyncio.wait_for(backend_reader.read(8192), timeout=5.0)
                            if not chunk:  # EOF
                                break
                            
                            if first_chunk:
                                # Only parse headers from the first chunk
                                header_buffer.extend(chunk)
                                if b'\r\n\r\n' in header_buffer:
                                    # Headers complete
                                    headers_part = header_buffer[:header_buffer.find(b'\r\n\r\n') + 4]
                                    status_line, response_headers, _ = parse_response(headers_part)
                                    
                                    # Log response headers
                                    response_data = {
                                        "id": request_id,
                                        "timestamp": dt.utcnow().isoformat() + "Z",
                                        "status_line": status_line,
                                        "headers": response_headers
                                    }
                                    asyncio.create_task(log_response(response_data))
                                    first_chunk = False
                            
                            # Write chunk directly to client
                            writer.write(chunk)
                            await writer.drain()
                            
                        except asyncio.TimeoutError:
                            logging.error(f"Timeout reading from backend {backend_host}:{backend_port}")
                            break
                        except Exception as e:
                            logging.error(f"Error reading from backend {backend_host}:{backend_port}: {e}")
                            break
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
                    data = await reader.read(8192)  # 8KB chunks for websocket data
                    if not data:  # EOF
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
        # Start the blocklist manager
        await self.blocklist.start()
        
        server = await asyncio.start_server(
            self.handle_client,
            self.host,
            self.port
        )
        logging.info(f"Proxy server listening on {self.host}:{self.port}")
        
        try:
            async with server:
                await server.serve_forever()
        finally:
            await self.blocklist.stop()
