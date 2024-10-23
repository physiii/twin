# hue_api.py
import requests
import logging
import sys
import os
import json
import colorsys
import time

CONFIG_PATH = os.path.expanduser("~/.hue_config.json")

# Define room to light ID mapping (now just for organization)
ROOMS = {
    "living_room": [1, 2],
    "bedroom": [3, 4],
    "kitchen": [5, 6],
}

# Enhanced color presets with specific hue and saturation values
POPULAR_COLORS = {
    "red": {"hue": 0, "sat": 254},
    "coral": {"hue": 2730, "sat": 254},
    "orange": {"hue": 5461, "sat": 254},
    "yellow": {"hue": 10922, "sat": 254},
    "lime": {"hue": 16384, "sat": 254},
    "green": {"hue": 25500, "sat": 254},
    "cyan": {"hue": 31655, "sat": 254},
    "blue": {"hue": 43690, "sat": 254},
    "purple": {"hue": 50000, "sat": 254},
    "pink": {"hue": 56100, "sat": 254},
    "white": {"ct": 366},
    "warm_white": {"ct": 500}
}

def rgb_to_hue(r, g, b):
    """
    Convert RGB values (0-255) to Hue color system values.
    Returns a tuple of (hue, saturation, brightness).
    """
    # Convert RGB (0-255) to RGB (0-1)
    r, g, b = r/255.0, g/255.0, b/255.0

    # Convert RGB to HSV
    h, s, v = colorsys.rgb_to_hsv(r, g, b)

    # Convert to Hue system values:
    # Hue: 0-65535 (instead of 0-1)
    # Saturation: 0-254 (instead of 0-1)
    # Brightness: 0-254 (instead of 0-1)
    hue = int(h * 65535)
    sat = int(s * 254)
    bri = int(v * 254)

    return (hue, sat, bri)

def parse_rgb(rgb_str):
    """
    Parse RGB string in format "r,g,b" to tuple of integers.
    """
    try:
        r, g, b = map(int, rgb_str.split(','))
        if not all(0 <= x <= 255 for x in (r, g, b)):
            raise ValueError
        return (r, g, b)
    except:
        raise ValueError("RGB values must be three integers between 0 and 255, separated by commas (e.g., '255,0,0')")

def get_all_lights(bridge_ip, username):
    """
    Get all available lights from the bridge.
    """
    url = f"http://{bridge_ip}/api/{username}/lights"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            lights = response.json()
            return {int(light_id): info for light_id, info in lights.items()}
        else:
            logging.error(f"Failed to get lights. Status code: {response.status_code}")
            return {}
    except requests.exceptions.RequestException as e:
        logging.error(f"Request exception: {e}")
        return {}

def get_light_ids(bridge_ip, username, room):
    """
    Retrieve light IDs based on the specified room, including dynamic discovery of all lights.
    """
    all_lights = get_all_lights(bridge_ip, username)

    if room.lower() == "all":
        return list(all_lights.keys())

    room = room.lower()
    if room in ROOMS:
        # Filter the room's lights to only include ones that actually exist
        return [lid for lid in ROOMS[room] if lid in all_lights]
    return []

def get_api_username(bridge_ip, max_retries=30, delay=2):
    """
    Get or register the username for the Hue API.
    """
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)
            username = config.get('username')
            if username:
                logging.info(f"Using existing username: {username}")
                return username
            else:
                logging.warning("Username not found in config. Proceeding to register a new user.")
    else:
        logging.info("Config file not found. Proceeding to register a new user.")

    # Attempt to register a new user
    logging.info("Registering new user. Please press the link button on the Hue Bridge.")
    url = f"http://{bridge_ip}/api"
    payload = {"devicetype": "my_hue_app#python_script"}

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(url, json=payload, timeout=5)
            data = response.json()

            if isinstance(data, list):
                if 'success' in data[0]:
                    username = data[0]['success']['username']
                    with open(CONFIG_PATH, 'w') as f:
                        json.dump({'username': username}, f)
                    logging.info(f"Username registered and saved to {CONFIG_PATH}")
                    return username
                elif 'error' in data[0]:
                    error = data[0]['error']
                    if error.get('type') == 101:
                        # Link button not pressed
                        logging.warning(f"Attempt {attempt}/{max_retries}: Link button not pressed. Waiting {delay} seconds before retrying...")
                    else:
                        logging.error(f"Error {error.get('type')}: {error.get('description')}")
                        sys.exit(1)
            else:
                logging.error("Unexpected response during user registration.")
                sys.exit(1)
        except requests.exceptions.RequestException as e:
            logging.error(f"Request exception: {e}")
            sys.exit(1)

        time.sleep(delay)

    logging.error("Failed to register new user. Ensure the link button was pressed.")
    sys.exit(1)

def list_lights(bridge_ip, username, room):
    """
    List all connected Hue lights in the specified room.
    """
    light_ids = get_light_ids(bridge_ip, username, room)
    if not light_ids:
        logging.error(f"No lights found for room '{room}'.")
        sys.exit(1)

    for light_id in light_ids:
        url = f"http://{bridge_ip}/api/{username}/lights/{light_id}"
        response = requests.get(url)
        if response.status_code != 200:
            logging.error(f"Failed to retrieve light {light_id}. Status code: {response.status_code}")
            continue
        light = response.json()
        name = light.get('name', 'Unknown')
        state = light.get('state', {}).get('on', False)
        brightness = light.get('state', {}).get('bri', 'N/A')
        hue = light.get('state', {}).get('hue', 'N/A')
        saturation = light.get('state', {}).get('sat', 'N/A')
        colormode = light.get('state', {}).get('colormode', 'N/A')
        xy = light.get('state', {}).get('xy', 'N/A')
        ct = light.get('state', {}).get('ct', 'N/A')
        logging.info(f"ID: {light_id}, Name: {name}, State: {'On' if state else 'Off'}, Brightness: {brightness}, Hue: {hue}, Saturation: {saturation}, Colormode: {colormode}, XY: {xy}, CT: {ct}")

def turn_power(bridge_ip, username, room, power_state):
    """
    Turn on/off the lights in the specified room.
    """
    light_ids = get_light_ids(bridge_ip, username, room)
    if not light_ids:
        logging.error(f"No lights found for room '{room}'.")
        sys.exit(1)

    payload = {"on": power_state}
    for light_id in light_ids:
        url = f"http://{bridge_ip}/api/{username}/lights/{light_id}/state"
        response = requests.put(url, json=payload)
        if response.status_code == 200:
            logging.info(f"Light {light_id} turned {'on' if power_state else 'off'}.")
        else:
            logging.error(f"Failed to turn {'on' if power_state else 'off'} light {light_id}. Status code: {response.status_code}")

def set_brightness(bridge_ip, username, room, brightness):
    """
    Set brightness of the lights in the specified room (0-100%).
    """
    if not (0 <= brightness <= 100):
        logging.error("Brightness must be between 0 and 100.")
        sys.exit(1)

    # Convert brightness percentage to 0-254 scale
    bri_value = int((brightness / 100.0) * 254)

    light_ids = get_light_ids(bridge_ip, username, room)
    if not light_ids:
        logging.error(f"No lights found for room '{room}'.")
        sys.exit(1)

    payload = {"bri": bri_value}
    for light_id in light_ids:
        url = f"http://{bridge_ip}/api/{username}/lights/{light_id}/state"
        response = requests.put(url, json=payload)
        if response.status_code == 200:
            logging.info(f"Brightness of light {light_id} set to {brightness}%.")
        else:
            logging.error(f"Failed to set brightness for light {light_id}. Status code: {response.status_code}")

def set_color(bridge_ip, username, room, color_name=None, hue=None, saturation=None, xy=None, ct=None):
    """
    Set color of the lights in the specified room using color name or hue, saturation, and optionally xy and ct values.
    """
    if color_name and color_name in POPULAR_COLORS:
        color_data = POPULAR_COLORS[color_name]
        hue = color_data.get("hue")
        saturation = color_data.get("sat")
        ct = color_data.get("ct")

    if hue is not None and not (0 <= hue <= 65535):
        logging.error("Hue must be between 0 and 65535.")
        sys.exit(1)
    if saturation is not None and not (0 <= saturation <= 254):
        logging.error("Saturation must be between 0 and 254.")
        sys.exit(1)

    light_ids = get_light_ids(bridge_ip, username, room)
    if not light_ids:
        logging.error(f"No lights found for room '{room}'.")
        sys.exit(1)

    payload = {}
    if hue is not None and saturation is not None:
        payload["hue"] = hue
        payload["sat"] = saturation
    if xy:
        payload["xy"] = xy
    if ct:
        payload["ct"] = ct

    for light_id in light_ids:
        url = f"http://{bridge_ip}/api/{username}/lights/{light_id}/state"
        response = requests.put(url, json=payload)
        if response.status_code == 200:
            logging.info(f"Color of light {light_id} set.")
        else:
            logging.error(f"Failed to set color for light {light_id}. Status code: {response.status_code}")
