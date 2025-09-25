#!/usr/bin/env python3
import argparse
import sys
import json
import asyncio
import concurrent.futures
from phue import Bridge

POPULAR_COLORS = {
    "red": {"hue": 0, "sat": 254},
    "orange": {"hue": 5461, "sat": 254},
    "yellow": {"hue": 10922, "sat": 254},
    "green": {"hue": 25500, "sat": 254},
    "blue": {"hue": 43690, "sat": 254},
    "purple": {"hue": 50000, "sat": 254},
    "pink": {"hue": 56100, "sat": 254},
    "white": {"ct": 366},
    "warm_white": {"ct": 500}
}

SCENES = {
    "tropical": [{"hue": 10000, "sat": 200}, {"hue": 20000, "sat": 254}],
    "autumn":   [{"hue": 6000,  "sat": 254}, {"hue": 7000,  "sat": 200}],
    "winter":   [{"hue": 40000, "sat": 100}, {"hue": 45000, "sat": 150}],
    "sunset":   [{"hue": 50000, "sat": 180}, {"hue": 60000, "sat": 254}],
    "forest":   [{"hue": 25000, "sat": 254}, {"hue": 30000, "sat": 200}]
}

def load_rooms():
    """
    Load room definitions from rooms.json.
    """
    with open('tools/lights/rooms.json', 'r') as f:
        data = json.load(f)
    return data.get("rooms", [])

def get_room_lights(bridge, room):
    """
    Return a list of Light objects for the specified room.
    If "all", return all lights on the bridge.
    """
    if room.lower() == "all":
        return bridge.lights

    rooms = load_rooms()
    matched_room = next(
        (r for r in rooms if r["name"].lower() == room.lower()), 
        None
    )
    if not matched_room:
        return []

    room_light_ids = matched_room.get("lights", [])
    return [light for light in bridge.lights if light.light_id in room_light_ids]

def rgb_to_hue(r, g, b):
    """
    Convert (R, G, B) (0-255) to (hue, sat, bri) in Hue space.
    """
    import colorsys
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    return int(h * 65535), int(s * 254), int(v * 254)

def parse_rgb(rgb_str):
    """
    Parse a string like "R,G,B" into integers.
    """
    r, g, b = map(int, rgb_str.split(','))
    if not all(0 <= x <= 255 for x in [r, g, b]):
        raise ValueError("RGB values must be between 0 and 255")
    return r, g, b

def set_scene(bridge, room, scene):
    """
    Apply a predefined scene to all lights in the given room.
    """
    lights = get_room_lights(bridge, room)
    colors = SCENES.get(scene, [])
    for i, light in enumerate(lights):
        c = colors[i % len(colors)]
        if 'hue' in c and 'sat' in c:
            light.hue = c['hue']
            light.saturation = c['sat']
        if 'ct' in c:
            light.colortemp = c['ct']
        light.on = True

async def list_lights_async(bridge, room):
    """
    Return the state of all lights in the specified room, asynchronously.
    """
    lights = get_room_lights(bridge, room)
    loop = asyncio.get_running_loop()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        results = await asyncio.gather(*[
            loop.run_in_executor(pool, lambda l=l: {
                "id": l.light_id,
                "name": l.name,
                "on": l.on,
                "bri": l.brightness,
                "hue": getattr(l, 'hue', None),
                "sat": getattr(l, 'saturation', None),
                "ct": getattr(l, 'colortemp', None)
            }) for l in lights
        ])
    return results

def print_lights_single_line(states):
    """
    Print a JSON array of lights, each on a single line.
    """
    print("[")
    for i, st in enumerate(states):
        # separators=(',', ':') removes extra spaces in the JSON
        line = json.dumps(st, separators=(',', ':'))
        if i < len(states) - 1:
            line += ","
        print(f"  {line}")
    print("]")

def main():
    parser = argparse.ArgumentParser(description='Philips Hue Control using phue')
    parser.add_argument('--bridge-ip', type=str, help='Hue Bridge IP', default='192.168.1.129')
    parser.add_argument('--room', type=str, help='Room name or "all"', default='all')

    group = parser.add_mutually_exclusive_group()
    group.add_argument('--status', action='store_true')
    group.add_argument('--power', choices=['on','off'])
    group.add_argument('--brightness', type=int)
    group.add_argument('--color', type=str, choices=POPULAR_COLORS.keys())
    group.add_argument('--manual-color', nargs=2, metavar=('HUE','SAT'))
    group.add_argument('--rgb', type=str)
    group.add_argument('--scene', choices=SCENES.keys())

    args = parser.parse_args()

    # Connect to the bridge
    bridge = Bridge(args.bridge_ip)
    bridge.connect()

    # If we're just listing the status
    if args.status:
        states = asyncio.run(list_lights_async(bridge, args.room))
        print_lights_single_line(states)
        sys.exit(0)

    # Otherwise, get lights
    lights = get_room_lights(bridge, args.room)
    if not lights:
        print("No lights found for room:", args.room)
        sys.exit(1)

    # Handle commands
    if args.power:
        state = (args.power == 'on')
        for l in lights:
            l.on = state

    elif args.brightness is not None:
        bri = int((args.brightness / 100) * 254)
        for l in lights:
            l.on = True
            l.brightness = bri

    elif args.color:
        c = POPULAR_COLORS[args.color]
        for l in lights:
            l.on = True
            if 'hue' in c:
                l.hue = c['hue']
            if 'sat' in c:
                l.saturation = c['sat']
            if 'ct' in c:
                l.colortemp = c['ct']

    elif args.manual_color:
        hue, sat = map(int, args.manual_color)
        for l in lights:
            l.on = True
            l.hue = hue
            l.saturation = sat

    elif args.rgb:
        r, g, b = parse_rgb(args.rgb)
        hue, sat, bri = rgb_to_hue(r, g, b)
        for l in lights:
            l.on = True
            l.hue = hue
            l.saturation = sat
            l.brightness = bri

    elif args.scene:
        set_scene(bridge, args.room, args.scene)

    # Print the final state of the lights after handling any commands
    final_states = [{
        "id": l.light_id,
        "name": l.name,
        "on": l.on,
        "bri": l.brightness,
        "hue": getattr(l, 'hue', None),
        "sat": getattr(l, 'saturation', None),
        "ct": getattr(l, 'colortemp', None)
    } for l in lights]

    print_lights_single_line(final_states)

if __name__ == "__main__":
    main()
