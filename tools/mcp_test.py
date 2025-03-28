#!/usr/bin/env python3
import subprocess, json, threading, queue, sys, time, os, requests

# Configuration: Using port 8080 and your valid token
HA_URL = "http://localhost:8080/mcp_server/sse"  # SSE endpoint of Home Assistant MCP
HA_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJlOGY5YmMzOTA3MTU0YTQzODBhN2Q1YTY2NzliYzEyMyIsImlhdCI6MTc0MjkzNDk1MSwiZXhwIjoyMDU4Mjk0OTUxfQ."
    "pElNSlO0xteZwKsQzXR-jllN7Zr_uOmEpGymAkVsExo"
)  # Replace with your valid token

# Logging helper
def log(message):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

log("Starting mcp-proxy subprocess...")
try:
    proc = subprocess.Popen(
        ["mcp-proxy", HA_URL],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={"API_ACCESS_TOKEN": HA_TOKEN, **os.environ},
        text=True,
        bufsize=1  # line-buffered
    )
except FileNotFoundError:
    log("ERROR: mcp-proxy not found. Is it installed and in PATH?")
    sys.exit(1)

# Queue to collect lines from mcp-proxy stdout
out_queue = queue.Queue()

def reader_thread():
    """Continuously read lines from mcp-proxy stdout and put them in a queue."""
    for line in proc.stdout:
        line = line.strip()
        if line:
            out_queue.put(line)
            # Also log raw output for debugging
            log(f"[mcp-proxy] {line}")

reader = threading.Thread(target=reader_thread, daemon=True)
reader.start()

def read_json(timeout=5.0):
    """
    Keep reading lines until a valid JSON message is received
    or timeout expires.
    """
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            remaining = end_time - time.time()
            line = out_queue.get(timeout=remaining)
        except queue.Empty:
            return None
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            log(f"WARNING: Ignoring non-JSON line: {line}")
    return None

# Wait a moment for any initial SSE output (like connection logs)
time.sleep(1.0)
if proc.poll() is not None:
    err_out = proc.stderr.read().strip() if proc.stderr else ""
    log(f"ERROR: mcp-proxy process exited prematurely. Stderr: {err_out}")
    sys.exit(1)

# Step 1: Send 'initialize' request
init_request = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {"tools": {}, "prompts": {}},
        "clientInfo": {"name": "TestClient", "version": "1.0"}
    }
}
log("Sending initialize request...")
proc.stdin.write(json.dumps(init_request) + "\n")
proc.stdin.flush()

# Step 2: Wait for initialize response
init_response = read_json(timeout=10.0)
if not init_response:
    log("ERROR: No response to initialize request (timeout).")
    proc.terminate()
    sys.exit(1)
if "error" in init_response:
    log(f"ERROR: Initialize failed: {init_response['error']}")
    proc.terminate()
    sys.exit(1)
log("Received initialize response from server.")
capabilities = init_response.get("result", {}).get("capabilities", {})
log(f"Server capabilities: {json.dumps(capabilities)}")

# Step 3: Send 'initialized' notification
initialized_note = {"jsonrpc": "2.0", "method": "notifications/initialized"}
log("Sending initialized notification...")
proc.stdin.write(json.dumps(initialized_note) + "\n")
proc.stdin.flush()

time.sleep(0.5)

# Step 4: List available tools
tools_req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
log("Requesting list of available tools...")
proc.stdin.write(json.dumps(tools_req) + "\n")
proc.stdin.flush()

tools_resp = read_json(timeout=10.0)
if not tools_resp:
    log("ERROR: No response to tools/list (timeout).")
    proc.terminate()
    sys.exit(1)
if "error" in tools_resp:
    log(f"ERROR: tools/list returned an error: {tools_resp['error']}")
    proc.terminate()
    sys.exit(1)

# Extract the tools list from the result object.
tools = tools_resp.get("result", {}).get("tools", [])
tool_names = [tool.get("name") for tool in tools]
log(f"Available tools: {tool_names}")

for t in tools:
    log(f"Tool '{t.get('name')}': {t.get('description')}")

# Helper function to call a tool
def call_tool(tool_name, arguments, request_id):
    """
    Calls a domain-based tool (e.g. HassTurnOn / HassTurnOff) with arguments
    and logs the response.
    """
    req = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments
        }
    }
    log(f"Calling tool '{tool_name}' with arguments: {json.dumps(arguments)}")
    proc.stdin.write(json.dumps(req) + "\n")
    proc.stdin.flush()

    while True:
        resp = read_json(timeout=10.0)
        if resp is None:
            log(f"ERROR: No response for tool call (id={request_id})")
            return
        if str(resp.get("id", "")) == str(request_id):
            if "error" in resp:
                err = resp["error"]
                log(f"Tool call '{tool_name}' ERROR: {err.get('message')} (code {err.get('code')})")
            else:
                result = resp.get("result")
                log(f"Tool call '{tool_name}' result: {json.dumps(result)}")
            break
        else:
            log(f"Received async/unrelated message: {resp}")

# Step 5: Turn on the "Office" light
time.sleep(1)
call_tool(
    tool_name="HassTurnOn",
    arguments={"name": "Office", "domain": ["light"]},
    request_id=10
)

# Wait a moment, then turn it off
time.sleep(3)
call_tool(
    tool_name="HassTurnOff",
    arguments={"name": "Office", "domain": ["light"]},
    request_id=11
)

# Step 6: Query full inventory from Home Assistant via REST API
def query_inventory():
    log("Querying full inventory of Home Assistant entities...")
    # Assuming Home Assistant REST API is available on the same host and port
    url = "http://localhost:8080/api/states"
    headers = {"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            log(f"ERROR: Inventory query returned status code {response.status_code}")
            return
        states = response.json()
        log(f"Inventory query returned {len(states)} entities.")
        # Log all entities (you can modify this to log a sample if too verbose)
        for entity in states:
            log(f"Entity: {entity.get('entity_id')} - state: {entity.get('state')}")
    except Exception as e:
        log(f"ERROR: Exception during inventory query: {e}")

# Perform the inventory query
time.sleep(1)
query_inventory()

log("Test sequence completed. Terminating mcp-proxy.")
try:
    proc.stdin.close()
except Exception:
    pass
proc.terminate()
