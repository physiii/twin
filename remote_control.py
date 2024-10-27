#!/usr/bin/python
import sys
import requests
import json

def send_command(ip, command):
    url = f"http://{ip}:8454/command"
    headers = {"Content-Type": "application/json"}
    payload = {"text": command}
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        if response.status_code == 200:
            print("Command sent successfully!")
        else:
            print(f"Failed to send command. Status code: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"Error sending command: {e}")

def main():
    # Default IP address if none is specified
    default_ip = "127.0.0.1"
    
    # Parse arguments
    if len(sys.argv) == 3:
        ip = sys.argv[1]
        command = sys.argv[2]
    elif len(sys.argv) == 2:
        ip = default_ip
        command = sys.argv[1]
    else:
        print("Usage:")
        print("python remote_control.py <IP> <command>")
        print("or")
        print("python remote_control.py <command> (uses 127.0.0.1 as default IP)")
        sys.exit(1)
    
    send_command(ip, command)

if __name__ == "__main__":
    main()
