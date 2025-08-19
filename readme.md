## Reverse Proxy Server

This project is a Python-based reverse proxy server that routes incoming HTTP requests to backend servers based on the `Host` header. It also logs both requests and responses for auditing and analysis.


### File and Function Data Flow

| Step                | File                        | Function(s) Used                  |
|---------------------|----------------------------|-----------------------------------|
| Start server        | `main.py`                  | `ProxyServer`                     |
| Handle request      | `proxy/server.py`          | `handle_client`, `Router.get_backend` |
| Log request         | `request_logging/normalize.py` | `normalize_and_log_request`, `log_request` |
| Forward request     | `proxy/server.py`          | `handle_client`                   |
| Receive response    | `proxy/server.py`          | `handle_client`                   |
| Log response        | `request_logging/normalize.py` | `log_response`, `parse_response`  |
| Relay response      | `proxy/server.py`          | `handle_client`                   |

### Data Flow Summary
When a client sends an HTTP request to the proxy server:
1. The proxy receives the request and extracts the Host header.
2. It looks up the backend server for the requested host using the routing table.
3. The proxy forwards the request to the backend server.
4. The backend server processes the request and sends a response back to the proxy.
5. The proxy relays the response to the client.
6. Both the request and response are logged with a unique ID for tracking and analysis.

### Usage

1. Run `pip install -r requirements.txt` to install the dependencies.
2. `config/routing.yaml` contains the mapping of domains to ips. Start backend servers on the ports specified in `config/routing.yaml`. Run both commands in different terminals.
    - `python -m http.server 8000`
    - `python -m http.server 9000`
3. Run the proxy server with `python main.py`.
4. Send HTTP requests to the proxy port (e.g., using `curl`), specifying the desired host in the `Host` header.
    - e.g `curl localhost:8080 -H "Host: customer1.com"` 
    - If both client and server are different machines: `curl http://<serverip>:8080 -H "Host: customer2.net"`
5. The `request_logging/logs.json` contains an array of the request that are intercepted by the server and `request_logging/responses.json` contains a log of the responses the proxy server gets back from the backend servers.

### How It Works

1. **Startup**
	- The proxy server is started by running `main.py`.
	- It listens on a configurable port (default: 8080).
	- Routing rules are loaded from `config/routing.yaml`.

2. **Request Handling**
	- When a client sends an HTTP request to the proxy, the server reads the request and extracts the `Host` header.
	- The proxy looks up the backend server for the given host in the routing table.
	- The request is forwarded to the appropriate backend server.

3. **Response Relay**
	- The proxy receives the response from the backend server.
	- The response is relayed back to the client.

4. **Logging**
	- Each request is logged in `request_logging/logs.json` with a unique `id` and full details (timestamp, client IP, headers, body, etc.).
	- Each response is logged in `request_logging/responses.json` with the same `id` and response details (status line, headers, body, etc.).
	- This allows requests and responses to be matched for auditing.

### Features
- Host-based routing using a YAML configuration file
- Request and response logging with unique IDs
- Easy extensibility for custom logging or routing logic


### Note
Log files and the virtual environment are excluded from version control using `.gitignore`.
