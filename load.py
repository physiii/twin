# load.py

import os
import requests
import json

def get_collection_name(file_path):
    filename = os.path.basename(file_path)
    collection_name, _ = os.path.splitext(filename)
    return collection_name

def load_file_to_vectorstore(file_path, base_url):
    collection_name = get_collection_name(file_path)
    headers = {'Content-Type': 'application/json'}
    print(f"Processing file: {file_path}")
    print(f"Collection name: {collection_name}")

    # Read the file line by line
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
                    data = response.json()
                    print(f"Line {line_number}: Loaded successfully.")
                else:
                    print(f"Line {line_number}: Failed to load. Status code: {response.status_code}")
            except Exception as e:
                print(f"Line {line_number}: Exception occurred: {str(e)}")

def main():
    base_url = 'http://127.0.0.1:5000/vectorstore'  # Update if your API URL is different

    file_paths = [
        '/media/mass/scripts/twin/wake.txt',
        '/media/mass/scripts/twin/na.txt',
        '/media/mass/scripts/twin/amygdala.txt'
    ]

    for file_path in file_paths:
        load_file_to_vectorstore(file_path, base_url)

if __name__ == "__main__":
    main()
