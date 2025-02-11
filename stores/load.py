# load.py
#!/usr/bin/env python3

import os
import requests
import json
import argparse

def get_collection_name(file_path):
    """Extracts collection name from the file name."""
    filename = os.path.basename(file_path)
    collection_name, _ = os.path.splitext(filename)
    return collection_name

def clear_collection(base_url, collection_name):
    """Clears the specified collection."""
    headers = {'Content-Type': 'application/json'}
    clear_payload = {
        "type": "clear",
        "collection": collection_name
    }
    
    print(f"Clearing collection: {collection_name}")
    
    try:
        response = requests.post(base_url, headers=headers, data=json.dumps(clear_payload))
        if response.status_code == 200:
            print(f"Collection '{collection_name}' cleared successfully.")
        else:
            print(f"Failed to clear collection '{collection_name}'. Status code: {response.status_code}")
    except Exception as e:
        print(f"Exception occurred while clearing collection '{collection_name}': {str(e)}")

def load_file_to_vectorstore(file_path, base_url, reload_collection):
    """Loads data from the file to the vector store, with optional collection clearing."""
    collection_name = get_collection_name(file_path)
    headers = {'Content-Type': 'application/json'}
    print(f"Processing file: {file_path}")
    print(f"Collection name: {collection_name}")

    # Clear the collection if --reload is set
    if reload_collection:
        clear_collection(base_url, collection_name)

    # Read the file line by line and load it into the collection
    with open(file_path, 'r', encoding='utf-8') as file:
        for line_number, line in enumerate(file, start=1):
            text = line.strip()
            if not text:
                continue  # Skip empty lines

            load_payload = {
                "type": "load",
                "text": text,
                "collection": collection_name
            }

            try:
                response = requests.post(base_url, headers=headers, data=json.dumps(load_payload))
                if response.status_code == 200:
                    print(f"Line {line_number}: Loaded successfully.")
                else:
                    print(f"Line {line_number}: Failed to load. Status code: {response.status_code}")
            except Exception as e:
                print(f"Line {line_number}: Exception occurred: {str(e)}")

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Load data into a vectorstore with optional collection clearing.")
    parser.add_argument('--reload', action='store_true', help="Clear the collection before loading new data.")
    args = parser.parse_args()

    base_url = 'http://127.0.0.1:5000/vectorstore'  # Update if your API URL is different

    file_paths = [
        '/media/mass/scripts/twin/stores/wake.txt',
        '/media/mass/scripts/twin/stores/na.txt',
        '/media/mass/scripts/twin/stores/amygdala.txt',
        '/media/mass/scripts/twin/stores/modes.txt',
        '/media/mass/scripts/twin/stores/conditions.txt',
        '/media/mass/scripts/twin/stores/tools.txt'
    ]

    for file_path in file_paths:
        load_file_to_vectorstore(file_path, base_url, args.reload)

if __name__ == "__main__":
    main()
