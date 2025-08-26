import json
from datetime import datetime as dt
import asyncio
import uuid
import aiofiles

async def log_request(request_data, filename="request_logging/logs.json"):
    try:
        async with aiofiles.open(filename, "r+") as f:
            content = await f.read()
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                data = []
            data.append(request_data)
            await f.seek(0)
            await f.write(json.dumps(data, indent=2))
            await f.truncate()
    except Exception as e:
        print(f"Error logging request: {e}")

async def log_response(response_data, filename="request_logging/responses.json"):
    try:
        async with aiofiles.open(filename, "r+") as f:
            content = await f.read()
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                data = []
            data.append(response_data)
            await f.seek(0)
            await f.write(json.dumps(data, indent=2))
            await f.truncate()
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
