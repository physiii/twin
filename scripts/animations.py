# animations.py
import time
import logging
import requests

from hue_api import set_color, set_brightness, get_light_ids, POPULAR_COLORS

def sunrise(bridge_ip, username, room):
    """
    Simulates a sunrise by gradually increasing brightness and changing color from warm to bright white.
    """
    logging.info("Starting Sunrise Animation")
    steps = [
        {"ct": 500, "bri": 10, "transitiontime": 100},   # 10 seconds
        {"ct": 450, "bri": 30, "transitiontime": 100},
        {"ct": 400, "bri": 60, "transitiontime": 100},
        {"ct": 366, "bri": 100, "transitiontime": 100},  # White
    ]
    for step in steps:
        payload = step
        light_ids = get_light_ids(bridge_ip, username, room)
        for light_id in light_ids:
            url = f"http://{bridge_ip}/api/{username}/lights/{light_id}/state"
            # Adjust brightness to 0-254
            bri_value = int((payload['bri'] / 100.0) * 254)
            data = {"ct": payload["ct"], "bri": bri_value, "transitiontime": payload.get("transitiontime", 100)}
            requests.put(url, json=data)
        # Sleep for the duration of the transition
        time.sleep(payload.get("transitiontime", 100) / 10.0)
    logging.info("Sunrise Animation Completed")

def sunset(bridge_ip, username, room):
    """
    Simulates a sunset by gradually decreasing brightness and changing color from bright white to warm.
    """
    logging.info("Starting Sunset Animation")
    steps = [
        {"ct": 366, "bri": 100, "transitiontime": 100},  # White
        {"ct": 400, "bri": 60, "transitiontime": 100},
        {"ct": 450, "bri": 30, "transitiontime": 100},
        {"ct": 500, "bri": 10, "transitiontime": 100},
    ]
    for step in steps:
        payload = step
        light_ids = get_light_ids(bridge_ip, username, room)
        for light_id in light_ids:
            url = f"http://{bridge_ip}/api/{username}/lights/{light_id}/state"
            # Adjust brightness to 0-254
            bri_value = int((payload['bri'] / 100.0) * 254)
            data = {"ct": payload["ct"], "bri": bri_value, "transitiontime": payload.get("transitiontime", 100)}
            requests.put(url, json=data)
        # Sleep for the duration of the transition
        time.sleep(payload.get("transitiontime", 100) / 10.0)
    logging.info("Sunset Animation Completed")

def party(bridge_ip, username, room):
    """
    Creates a vibrant party atmosphere by cycling through bright colors.
    """
    logging.info("Starting Party Animation")
    colors = ["red", "orange", "yellow", "lime", "green", "cyan", "blue", "purple", "pink"]
    for _ in range(10):  # Repeat the cycle 10 times
        for color in colors:
            color_data = POPULAR_COLORS[color]
            payload = {"hue": color_data["hue"], "sat": color_data["sat"], "transitiontime": 5}
            light_ids = get_light_ids(bridge_ip, username, room)
            for light_id in light_ids:
                url = f"http://{bridge_ip}/api/{username}/lights/{light_id}/state"
                requests.put(url, json=payload)
            # Sleep for the duration of the transition
            time.sleep(payload.get("transitiontime", 5) / 10.0)
    logging.info("Party Animation Completed")

def relax(bridge_ip, username, room):
    """
    Sets a calm and relaxing ambiance with soft blue and green hues.
    """
    logging.info("Starting Relax Animation")
    colors = ["blue", "cyan", "green", "lime"]
    for _ in range(10):
        for color in colors:
            color_data = POPULAR_COLORS[color]
            # Set brightness to 50% for relaxing ambiance
            bri_value = int((50 / 100.0) * 254)
            payload = {"hue": color_data["hue"], "sat": color_data["sat"], "bri": bri_value, "transitiontime": 20}
            light_ids = get_light_ids(bridge_ip, username, room)
            for light_id in light_ids:
                url = f"http://{bridge_ip}/api/{username}/lights/{light_id}/state"
                requests.put(url, json=payload)
            time.sleep(payload.get("transitiontime", 20) / 10.0)
    logging.info("Relax Animation Completed")

def romantic(bridge_ip, username, room):
    """
    Creates a romantic setting with warm red and pink hues.
    """
    logging.info("Starting Romantic Animation")
    colors = ["red", "coral", "pink", "warm_white"]
    for _ in range(10):
        for color in colors:
            color_data = POPULAR_COLORS[color]
            # Set brightness to 80% for romantic ambiance
            bri_value = int((80 / 100.0) * 254)
            payload = {}
            if "hue" in color_data and "sat" in color_data:
                payload["hue"] = color_data["hue"]
                payload["sat"] = color_data["sat"]
            if "ct" in color_data:
                payload["ct"] = color_data["ct"]
            payload["bri"] = bri_value
            payload["transitiontime"] = 20
            light_ids = get_light_ids(bridge_ip, username, room)
            for light_id in light_ids:
                url = f"http://{bridge_ip}/api/{username}/lights/{light_id}/state"
                requests.put(url, json=payload)
            time.sleep(payload.get("transitiontime", 20) / 10.0)
    logging.info("Romantic Animation Completed")
