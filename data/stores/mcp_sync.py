#!/usr/bin/env python3

import subprocess
import threading
import queue
import sys
import time
import os
import json
import argparse
import requests

# Default configuration
DEFAULT_HA_HOST = "192.168.1.40"
DEFAULT_HA_PORT = "8080"
HA_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJlOGY5YmMzOTA3MTU0YTQzODBhN2Q1YTY2NzliYzEyMyIsImlhdCI6MTc0MjkzNDk1MSwiZXhwIjoyMDU4Mjk0OTUxfQ."
    "pElNSlO0xteZwKsQzXR-jllN7Zr_uOmEpGymAkVsExo"
)

# Vector store configuration
VECTOR_URL = 'http://192.168.1.40:5050/vectorstore'
VECTOR_HEADERS = {'Content-Type': 'application/json'}

# Files to process - use full paths
DEFAULT_FILES = [
    'wake.txt',
    'tools.txt',
    'ha_entities.txt',
]

def log(message):
    """Logging helper function."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

class MCPClient:
    """Client for Home Assistant MCP integration."""
    def __init__(self, host=DEFAULT_HA_HOST, port=DEFAULT_HA_PORT):
        self.ha_url = f"http://{host}:{port}/mcp_server/sse"
        self.ha_token = HA_TOKEN
        self.proc = None
        self.out_queue = queue.Queue()
        self.reader = None
        self.request_id = 100  # Start with a high number to avoid conflicts
        self.tools = []
        self.tool_names = []
        self.entities = []
    
    def start(self):
        """Start the MCP proxy subprocess."""
        log("Starting mcp-proxy subprocess...")
        try:
            self.proc = subprocess.Popen(
                ["mcp-proxy", self.ha_url],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={"API_ACCESS_TOKEN": self.ha_token, **os.environ},
                text=True,
                bufsize=1  # line-buffered
            )
        except FileNotFoundError:
            log("ERROR: mcp-proxy not found. Is it installed and in PATH?")
            return False
        
        # Start reader thread
        self.reader = threading.Thread(target=self._reader_thread, daemon=True)
        self.reader.start()
        
        # Wait for startup
        time.sleep(1.0)
        if self.proc.poll() is not None:
            err_out = self.proc.stderr.read().strip() if self.proc.stderr else ""
            log(f"ERROR: mcp-proxy process exited prematurely. Stderr: {err_out}")
            return False
        
        # Initialize the connection
        if not self._initialize():
            return False
        
        # Get available tools
        if not self._get_tools():
            return False
        
        return True
    
    def _reader_thread(self):
        """Continuously read lines from mcp-proxy stdout and put them in a queue."""
        for line in self.proc.stdout:
            line = line.strip()
            if line:
                self.out_queue.put(line)
                # Uncomment for debugging
                # log(f"[mcp-proxy] {line}")
    
    def _read_json(self, timeout=5.0):
        """Keep reading lines until a valid JSON message is received or timeout expires."""
        end_time = time.time() + timeout
        while time.time() < end_time:
            try:
                remaining = end_time - time.time()
                line = self.out_queue.get(timeout=remaining)
            except queue.Empty:
                return None
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                log(f"WARNING: Ignoring non-JSON line: {line}")
        return None
    
    def _initialize(self):
        """Initialize the MCP connection."""
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}, "prompts": {}},
                "clientInfo": {"name": "TwinMCPSync", "version": "1.0"}
            }
        }
        log("Sending initialize request...")
        self.proc.stdin.write(json.dumps(init_request) + "\n")
        self.proc.stdin.flush()
        
        init_response = self._read_json(timeout=10.0)
        if not init_response:
            log("ERROR: No response to initialize request (timeout).")
            return False
        if "error" in init_response:
            log(f"ERROR: Initialize failed: {init_response['error']}")
            return False
        
        log("Received initialize response from server.")
        capabilities = init_response.get("result", {}).get("capabilities", {})
        log(f"Server capabilities: {json.dumps(capabilities)}")
        
        # Send initialized notification
        initialized_note = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        log("Sending initialized notification...")
        self.proc.stdin.write(json.dumps(initialized_note) + "\n")
        self.proc.stdin.flush()
        
        time.sleep(0.5)
        return True
    
    def _get_tools(self):
        """Get available tools from Home Assistant."""
        tools_req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        log("Requesting list of available tools...")
        self.proc.stdin.write(json.dumps(tools_req) + "\n")
        self.proc.stdin.flush()
        
        tools_resp = self._read_json(timeout=10.0)
        if not tools_resp:
            log("ERROR: No response to tools/list (timeout).")
            return False
        if "error" in tools_resp:
            log(f"ERROR: tools/list returned an error: {tools_resp['error']}")
            return False
        
        # Extract the tools list from the result object
        self.tools = tools_resp.get("result", {}).get("tools", [])
        self.tool_names = [tool.get("name") for tool in self.tools]
        log(f"Available tools: {self.tool_names}")
        
        for t in self.tools:
            log(f"Tool '{t.get('name')}': {t.get('description')}")
        
        return True
    
    def call_tool(self, tool_name, arguments):
        """Call a tool with specified arguments."""
        self.request_id += 1
        req = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        log(f"Calling tool '{tool_name}' with arguments: {json.dumps(arguments)}")
        self.proc.stdin.write(json.dumps(req) + "\n")
        self.proc.stdin.flush()
        
        while True:
            resp = self._read_json(timeout=10.0)
            if resp is None:
                log(f"ERROR: No response for tool call (id={self.request_id})")
                return None
            if str(resp.get("id", "")) == str(self.request_id):
                if "error" in resp:
                    err = resp["error"]
                    log(f"Tool call '{tool_name}' ERROR: {err.get('message')} (code {err.get('code')})")
                    return None
                else:
                    result = resp.get("result")
                    log(f"Tool call '{tool_name}' result: {json.dumps(result)}")
                    return result
            else:
                log(f"Received async/unrelated message: {resp}")
    
    def query_inventory(self):
        """Query all entities from Home Assistant."""
        log("Querying full inventory of Home Assistant entities...")
        host = self.ha_url.split('/')[2].split(':')[0]
        url = f"http://{host}:{DEFAULT_HA_PORT}/api/states"
        headers = {"Authorization": f"Bearer {self.ha_token}", "Content-Type": "application/json"}
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200:
                log(f"ERROR: Inventory query returned status code {response.status_code}")
                return False
            
            self.entities = response.json()
            log(f"Inventory query returned {len(self.entities)} entities.")
            return True
        except Exception as e:
            log(f"ERROR: Exception during inventory query: {e}")
            return False
    
    def stop(self):
        """Stop the MCP proxy subprocess."""
        log("Stopping mcp-proxy...")
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        self.proc.terminate()
        log("MCP proxy stopped.")

def create_ha_tools_file(mcp_client, output_path):
    """Create a tools.txt file with the available Home Assistant tools."""
    if not mcp_client.tools:
        log("No tools available to save to file.")
        return False
    
    with open(output_path, 'w', encoding='utf-8') as f:
        # Add existing CLI commands
        f.write("thermostat --help                            # Understand how to use the tool and its arguments\n")
        f.write("thermostat --status                          # Get the current status of the thermostat or AC\n")
        f.write("lights --status                              # Get the current status of the lights\n")
        f.write("lights --help                                # Understand how to use the tool and its arguments\n")
        
        # Add MCP tools with descriptions
        for tool in mcp_client.tools:
            name = tool.get("name", "")
            desc = tool.get("description", "")
            f.write(f"{name}                                  # {desc}\n")
    
    log(f"Created Home Assistant tools file at {output_path}")
    return True

def create_ha_entities_file(mcp_client, output_path):
    """Create a file with entity information for vector store."""
    if not mcp_client.entities:
        log("No entities available to save to file.")
        return False
    
    # Group entities by domain
    domains = {}
    for entity in mcp_client.entities:
        entity_id = entity.get("entity_id", "")
        if not entity_id:
            continue
        
        domain = entity_id.split(".")[0]
        if domain not in domains:
            domains[domain] = []
        domains[domain].append(entity)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        for domain, entities in domains.items():
            # Write domain information
            f.write(f"Domain: {domain} has {len(entities)} entities\n")
            
            # For each entity, write its ID only (without state)
            for entity in entities:
                entity_id = entity.get("entity_id", "")
                # Don't include state information as it will become outdated
                f.write(f"Entity {entity_id} in domain {domain}\n")
    
    log(f"Created entities file at {output_path} with {len(mcp_client.entities)} entities (without state information)")
    return True

# Vector store functions
def clear_collection(collection_name):
    """Clear a collection in the vector store"""
    payload = {
        "type": "clear",
        "collection": collection_name
    }
    
    log(f"Clearing collection: {collection_name}")
    try:
        response = requests.post(VECTOR_URL, headers=VECTOR_HEADERS, json=payload, timeout=30)
        if response.status_code == 200:
            log(f"Collection '{collection_name}' cleared successfully")
            return True
        else:
            log(f"Failed to clear collection: {response.status_code}")
            return False
    except Exception as e:
        log(f"Error clearing collection: {str(e)}")
        return False

def load_line(text, collection_name):
    """Load a single line to the vector store"""
    payload = {
        "type": "load",
        "text": text,
        "collection": collection_name
    }
    
    try:
        response = requests.post(VECTOR_URL, headers=VECTOR_HEADERS, json=payload, timeout=60)
        if response.status_code == 200:
            return True
        else:
            log(f"Failed to load: {response.status_code}")
            return False
    except Exception as e:
        log(f"Error loading text: {str(e)}")
        return False

def load_file_to_vectorstore(file_path, reload=False, delay=5.0):
    """Load a file to the vector store"""
    collection_name = os.path.basename(file_path).split('.')[0]
    log(f"Loading file {file_path} to collection {collection_name}")
    
    # Clear the collection if requested
    if reload:
        if not clear_collection(collection_name):
            log(f"Skipping {file_path} due to clear error")
            return False
    
    # Count lines and successful loads
    total_lines = 0
    successful_loads = 0
    
    # Read and process the file
    with open(file_path, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f, 1):
            text = line.strip()
            if not text or text.startswith('#'):
                continue
            
            total_lines += 1
            log(f"Loading line {i}: {text[:50]}...")
            
            # Load the line and add a delay
            if load_line(text, collection_name):
                successful_loads += 1
                log(f"Line {i} loaded successfully")
            else:
                log(f"Line {i} failed to load")
            
            # Add a delay between requests
            time.sleep(delay)
    
    log(f"Completed {file_path}: {successful_loads}/{total_lines} lines loaded")
    return successful_loads > 0

def main():
    parser = argparse.ArgumentParser(description="Sync Home Assistant data via MCP protocol")
    parser.add_argument('--host', default=DEFAULT_HA_HOST, help=f"Home Assistant host (default: {DEFAULT_HA_HOST})")
    parser.add_argument('--port', default=DEFAULT_HA_PORT, help=f"Home Assistant port (default: {DEFAULT_HA_PORT})")
    parser.add_argument('--output-dir', default=".", help="Directory to save output files (default: current directory)")
    parser.add_argument('--load', action='store_true', help="Load files to vector store after creating them")
    parser.add_argument('--load-only', action='store_true', help="Only load existing files to vector store (skip MCP sync)")
    parser.add_argument('--file', action='append', dest='files', help="Specific file(s) to load (can be used multiple times)")
    parser.add_argument('--delay', type=float, default=5.0, help="Delay between vector store requests in seconds (default: 5.0)")
    args = parser.parse_args()
    
    # Ensure output directory exists
    os.makedirs(args.output_dir, exist_ok=True)
    
    if args.load_only:
        # Only load files to vector store
        if args.files:
            # Use provided file paths directly
            files_to_load = args.files
        else:
            # Use default files
            files_to_load = DEFAULT_FILES
        
        success = True
        for file_path in files_to_load:
            if os.path.exists(file_path):
                if not load_file_to_vectorstore(file_path, reload=True, delay=args.delay):
                    success = False
                    log(f"Failed to load {file_path} to vector store")
            else:
                log(f"File not found: {file_path}")
                success = False
        
        return 0 if success else 1
    
    # Initialize the MCP client
    log("Starting MCP sync process...")
    mcp_client = MCPClient(host=args.host, port=args.port)
    
    if mcp_client.start():
        success = True
        created_files = []
        
        # Query inventory
        if mcp_client.query_inventory():
            # Create files with Home Assistant data
            entity_file = os.path.join(args.output_dir, 'ha_entities.txt')
            if create_ha_entities_file(mcp_client, entity_file):
                created_files.append(entity_file)
            else:
                success = False
                log("Failed to create entities file.")
            
            # Create tools file with MCP tools
            tools_file = os.path.join(args.output_dir, 'tools.txt')
            if create_ha_tools_file(mcp_client, tools_file):
                created_files.append(tools_file)
            else:
                success = False
                log("Failed to create tools file.")
        else:
            success = False
            log("Failed to query Home Assistant inventory.")
        
        # Stop the MCP client
        mcp_client.stop()
        
        # Load files to vector store if requested
        if args.load and success:
            log("Loading files to vector store...")
            files_to_load = args.files or [os.path.join(args.output_dir, f) for f in DEFAULT_FILES]
            
            for file_path in files_to_load:
                if os.path.exists(file_path):
                    if not load_file_to_vectorstore(file_path, reload=True, delay=args.delay):
                        success = False
                        log(f"Failed to load {file_path} to vector store")
                else:
                    log(f"File not found: {file_path}")
        
        if success:
            log("MCP sync completed successfully.")
            return 0
        else:
            log("MCP sync completed with errors.")
            return 1
    else:
        log("Failed to initialize MCP client.")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 