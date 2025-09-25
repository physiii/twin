#!/usr/bin/env python3

import os
import requests
import json
import time
import sys

def log(message):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

# Vector store connection
VECTOR_URL = 'http://192.168.1.40:5050/vectorstore'
HEADERS = {'Content-Type': 'application/json'}

# Files to load
FILES = [
    'wake.txt',
    'tools.txt',
    'ha_entities.txt',
]

def clear_collection(collection_name):
    """Clear a collection in the vector store"""
    payload = {
        "type": "clear",
        "collection": collection_name
    }
    
    log(f"Clearing collection: {collection_name}")
    try:
        response = requests.post(VECTOR_URL, headers=HEADERS, json=payload, timeout=30)
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
        response = requests.post(VECTOR_URL, headers=HEADERS, json=payload, timeout=60)
        if response.status_code == 200:
            return True
        else:
            log(f"Failed to load: {response.status_code}")
            return False
    except Exception as e:
        log(f"Error loading text: {str(e)}")
        return False

def process_file(file_path, reload=False):
    """Process a single file and load its contents to the vector store"""
    collection_name = os.path.basename(file_path).split('.')[0]
    log(f"Loading file {file_path} to collection {collection_name}")
    
    # Clear the collection if requested
    if reload:
        if not clear_collection(collection_name):
            log(f"Skipping {file_path} due to clear error")
            return
    
    # Count lines and successful loads
    total_lines = 0
    successful_loads = 0
    
    # Read and process the file
    with open(file_path, 'r') as f:
        for i, line in enumerate(f, 1):
            text = line.strip()
            if not text or text.startswith('#'):
                continue
            
            # Skip state information for HA entities
            if collection_name == "ha_entities" and "has state" in text:
                log(f"Skipping line {i}: Contains state information")
                continue
            
            # For HA entities, transform entries to only include entity ID and domain
            if collection_name == "ha_entities" and text.startswith("Entity "):
                parts = text.split()
                if len(parts) >= 2:
                    entity_id = parts[1]
                    domain = entity_id.split('.')[0]
                    text = f"Entity {entity_id} in domain {domain}"
                    log(f"Transformed: {text}")
                
            total_lines += 1
            log(f"Loading line {i}: {text[:50]}...")
            
            # Load the line and add a delay
            if load_line(text, collection_name):
                successful_loads += 1
                log(f"Line {i} loaded successfully")
            else:
                log(f"Line {i} failed to load")
            
            # Add a delay between requests
            time.sleep(5)
    
    log(f"Completed {file_path}: {successful_loads}/{total_lines} lines loaded")

def main():
    # Check if specific files were requested
    if len(sys.argv) > 1:
        file_names = sys.argv[1:]
        files_to_process = [f for f in FILES if any(name in f for name in file_names)]
    else:
        files_to_process = FILES
    
    if not files_to_process:
        log("No matching files found")
        return
    
    log(f"Will process: {[os.path.basename(f) for f in files_to_process]}")
    
    # Process each file
    for file_path in files_to_process:
        if os.path.exists(file_path):
            process_file(file_path, reload=True)
        else:
            log(f"File not found: {file_path}")

if __name__ == "__main__":
    main() 