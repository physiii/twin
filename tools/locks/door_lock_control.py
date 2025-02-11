#!/usr/bin/env python3
import paho.mqtt.client as mqtt
import json
import time
import sys

# Configuration variables
MQTT_BROKER = "localhost"      # Change this if your broker is remote
MQTT_PORT = 1883               # Default MQTT port
LOCK_TOPIC = "zigbee2mqtt/door_lock"   # Base topic for your lock device
LOCK_COMMAND_TOPIC = f"{LOCK_TOPIC}/set"  # Command topic

def on_connect(client, userdata, flags, rc):
    print("Connected with result code:", rc)
    # Subscribe to the topic that publishes the lock state
    client.subscribe(LOCK_TOPIC)

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
    except json.JSONDecodeError:
        payload = msg.payload.decode()
    print(f"Received message on topic '{msg.topic}': {payload}")

def send_lock_command(command):
    # Command payload is assumed to be a JSON dict with a key "state"
    payload = {"state": command}
    client.publish(LOCK_COMMAND_TOPIC, json.dumps(payload))
    print(f"Sent command: {command}")

# Create an MQTT client instance and set callback functions
client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

# Connect to the MQTT broker
client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)

# Start the network loop in a background thread
client.loop_start()

if len(sys.argv) > 1:
    # If a command argument is provided, send it immediately
    cmd = sys.argv[1].strip().upper()
    if cmd in ["LOCK", "UNLOCK"]:
        send_lock_command(cmd)
    else:
        print("Invalid command. Use 'LOCK' or 'UNLOCK'.")
else:
    print("Monitoring door lock state. Press Ctrl+C to exit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Exiting monitoring mode.")

# Stop the loop and disconnect cleanly
client.loop_stop()
client.disconnect()
