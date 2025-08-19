def log_response(response_data, filename="request_logging/responses.json"):
    try:
        with open(filename, "r+") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = []
            data.append(response_data)
            f.seek(0)
            json.dump(data, f, indent=2)
            f.truncate()
    except Exception as e:
        print(f"Error logging response: {e}")

def parse_response(raw_response):
    response_text = raw_response.decode(errors="ignore")
    lines = response_text.split("\r\n")
    status_line = lines[0] if lines else ""
    headers = {}
    i = 1
    while i < len(lines) and lines[i]:
        if ":" in lines[i]:
            k, v = lines[i].split(":", 1)
            headers[k.strip()] = v.strip()
        i += 1
    body = "\r\n".join(lines[i+1:]) if i+1 < len(lines) else ""
    return status_line, headers, body
import json
from datetime import datetime as dt
import asyncio
import uuid

def log_request(request_data, filename="request_logging/logs.json"):
    try:
        with open(filename, "r+") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = []
            data.append(request_data)
            f.seek(0)
            json.dump(data, f, indent=2)
            f.truncate()
    except Exception as e:
        print(f"Error logging request: {e}")

async def normalize_and_log_request(raw_request, client_ip=None, filename="request_logging/logs.json"):
    try:
        request_text = raw_request.decode(errors="ignore")
        lines = request_text.split("\r\n")
        if not lines:
            print("No lines in request text") #debug statement
            return
        # Parse request line
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
        # Body (if any)
        body = "\r\n".join(lines[i+1:]) if i+1 < len(lines) else ""
        # Host
        host = headers.get("Host", "")
        # Timestamp
        timestamp = dt.utcnow().isoformat() + "Z"
        # Build JSON object with unique id
        request_id = str(uuid.uuid4())
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
        print("Logging request:", request_data) #debug statement
        log_request(request_data, filename)
    except Exception as e:
        print(f"Error normalizing request: {e}")