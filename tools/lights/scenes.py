import requests
import logging
import time

# Scene color palettes (Hue, Saturation, Brightness)
SCENES = {
    'tropical': [
        (1000, 254, 254),  # Warm Coral
        (5000, 254, 254),  # Tropical Green
        (9000, 254, 254),  # Ocean Blue
        (2000, 254, 254),  # Sunset Orange
        (7000, 254, 254),  # Turquoise
        (12000, 254, 254), # Purple Orchid
        (4000, 254, 254),  # Yellow Palm
        (10000, 254, 254), # Deep Sea Blue
        (15000, 254, 254)  # Pink Hibiscus
    ],
    'autumn': [
        (5000, 200, 254),  # Forest Green
        (8000, 240, 254),  # Auburn
        (2500, 220, 254),  # Golden Yellow
        (10000, 180, 254), # Deep Burgundy
        (4000, 230, 254),  # Warm Orange
        (6000, 210, 254),  # Olive Green
        (9000, 200, 254),  # Rich Brown
        (3000, 225, 254),  # Harvest Gold
        (7000, 215, 254)   # Moss Green
    ],
    'winter': [
        (45000, 200, 254), # Ice Blue
        (47000, 150, 254), # Cool White
        (43000, 220, 254), # Glacial Blue
        (46000, 180, 254), # Frost
        (42000, 190, 254), # Arctic Blue
        (44000, 160, 254), # Winter Sky
        (48000, 170, 254), # Snow
        (41000, 210, 254), # Deep Ice
        (49000, 140, 254)  # Crystal
    ],
    'sunset': [
        (2000, 254, 254),  # Sunset Orange
        (1500, 240, 254),  # Warm Gold
        (3000, 220, 254),  # Rose Pink
        (500, 200, 254),   # Amber
        (4000, 230, 254),  # Peach
        (1000, 245, 254),  # Deep Orange
        (2500, 235, 254),  # Coral
        (3500, 225, 254),  # Blush Pink
        (1800, 250, 254)   # Crimson
    ],
    'forest': [
        (25500, 254, 254), # Deep Green
        (23000, 230, 254), # Pine
        (28000, 240, 254), # Emerald
        (21000, 220, 254), # Sage
        (26000, 235, 254), # Forest Green
        (24000, 245, 254), # Moss
        (27000, 225, 254), # Fern
        (22000, 250, 254), # Jungle Green
        (29000, 215, 254)  # Leaf Green
    ]
}

def get_available_lights(bridge_ip, username):
    """
    Get all available lights from the bridge
    """
    url = f"http://{bridge_ip}/api/{username}/lights"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return list(response.json().keys())
        return []
    except requests.exceptions.RequestException:
        return []

def detect_scene(lights_status):
    """
    Detect which scene is currently active based on light settings
    
    Args:
        lights_status (list): List of dictionaries containing light status information
        
    Returns:
        str: Name of the detected scene or None if no match
    """
    if not lights_status:
        return None
        
    # Extract current light settings
    current_settings = [(light.get('hue', 0), light.get('sat', 0), light.get('bri', 0)) 
                       for light in lights_status]
    
    # Helper function to check if two colors are similar
    def colors_match(c1, c2, hue_tolerance=500, sat_tolerance=20, bri_tolerance=20):
        hue1, sat1, bri1 = c1
        hue2, sat2, bri2 = c2
        
        # Handle hue wraparound
        hue_diff = min(abs(hue1 - hue2), abs(hue1 - hue2 + 65535), abs(hue1 - hue2 - 65535))
        
        return (hue_diff <= hue_tolerance and
                abs(sat1 - sat2) <= sat_tolerance and
                abs(bri1 - bri2) <= bri_tolerance)
    
    # Check each scene
    for scene_name, scene_colors in SCENES.items():
        matches = 0
        total_lights = min(len(current_settings), len(scene_colors))
        
        # Count how many lights match the scene definition
        for current, scene in zip(current_settings, scene_colors):
            if colors_match(current, scene):
                matches += 1
        
        # If most lights match (allowing for some tolerance), consider it a match
        if matches >= total_lights * 0.7:  # 70% threshold for matching
            return scene_name
    
    return None

def set_scene(bridge_ip, username, room, scene_name):
    """
    Set a predefined scene for all lights in the specified room
    """
    if scene_name not in SCENES:
        logging.error(f"Scene '{scene_name}' not found. Available scenes: {', '.join(SCENES.keys())}")
        return False

    # Get all available lights
    available_lights = get_available_lights(bridge_ip, username)
    if not available_lights:
        logging.error("No lights found on the bridge")
        return False

    scene_colors = SCENES[scene_name]
    
    # Set each light to its corresponding color in the scene
    for light_id, colors in zip(available_lights, scene_colors):
        hue, saturation, brightness = colors
        url = f"http://{bridge_ip}/api/{username}/lights/{light_id}/state"
        
        state = {
            "on": True,
            "hue": int(hue),
            "sat": int(saturation),
            "bri": int(brightness)
        }
        
        try:
            response = requests.put(url, json=state)
            if not response.ok:
                logging.error(f"Failed to set scene color for light {light_id}")
                return False
            
            # Small delay to prevent overwhelming the bridge
            time.sleep(0.1)
            
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to communicate with light {light_id}: {str(e)}")
            return False
    
    logging.info(f"Successfully set scene: {scene_name}")
    return True