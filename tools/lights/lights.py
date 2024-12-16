#!/usr/bin/env python3
import argparse, sys, json, asyncio, concurrent.futures
from phue import Bridge

# Define rooms and scenes as examples (adjust as needed)
ROOMS = {
    "kitchen": "Kitchen",
    "office": "Office",
    "living_room": "Living room",
    "bedroom": "Bedroom"
}

POPULAR_COLORS = {
    "red": {"hue":0,"sat":254},
    "orange":{"hue":5461,"sat":254},
    "yellow":{"hue":10922,"sat":254},
    "green":{"hue":25500,"sat":254},
    "blue":{"hue":43690,"sat":254},
    "purple":{"hue":50000,"sat":254},
    "pink":{"hue":56100,"sat":254},
    "white":{"ct":366},
    "warm_white":{"ct":500}
}

SCENES = {
    "tropical": [{"hue":10000,"sat":200}, {"hue":20000,"sat":254}],
    "autumn":   [{"hue":6000,"sat":254}, {"hue":7000,"sat":200}],
    "winter":   [{"hue":40000,"sat":100},{"hue":45000,"sat":150}],
    "sunset":   [{"hue":50000,"sat":180},{"hue":60000,"sat":254}],
    "forest":   [{"hue":25000,"sat":254},{"hue":30000,"sat":200}]
}

def rgb_to_hue(r,g,b):
    # Convert to Hue HSV space
    import colorsys
    h,s,v = colorsys.rgb_to_hsv(r/255.0,g/255.0,b/255.0)
    return int(h*65535), int(s*254), int(v*254)

def parse_rgb(rgb_str):
    r,g,b = map(int,rgb_str.split(','))
    if not all(0<=x<=255 for x in [r,g,b]):
        raise ValueError("RGB values must be between 0 and 255")
    return r,g,b

def get_room_lights(bridge, room):
    if room == "all":
        return bridge.lights
    room_name = ROOMS.get(room.lower())
    if not room_name:
        return []
    group = bridge.get_group(room_name)
    light_ids = group.get('lights', [])
    # Convert to Light objects
    return [l for l in bridge.lights if str(l.light_id) in light_ids]

def set_scene(bridge, room, scene):
    # Set predefined scene colors (just sets colors for lights in room)
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

async def get_light_state(light):
    # Return state dict of a single light
    return {
        "id": light.light_id,
        "name": light.name,
        "on": light.on,
        "bri": light.brightness,
        "hue": getattr(light, 'hue', None),
        "sat": getattr(light, 'saturation', None),
        "ct": getattr(light, 'colortemp', None)
    }

async def list_lights_async(bridge, room):
    # Get states of all lights in parallel
    lights = get_room_lights(bridge, room)
    loop = asyncio.get_running_loop()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        results = await asyncio.gather(*[loop.run_in_executor(pool, lambda l=l: {
            "id": l.light_id,
            "name": l.name,
            "on": l.on,
            "bri": l.brightness,
            "hue": getattr(l, 'hue', None),
            "sat": getattr(l, 'saturation', None),
            "ct": getattr(l, 'colortemp', None)
        }) for l in lights])
    return results

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
    bridge = Bridge(args.bridge_ip)
    bridge.connect()

    if args.status:
        states = asyncio.run(list_lights_async(bridge, args.room))
        print(json.dumps(states, indent=2))
        sys.exit(0)

    lights = get_room_lights(bridge, args.room)
    if not lights:
        print("No lights found for room:", args.room)
        sys.exit(1)

    if args.power:
        state = True if args.power == 'on' else False
        for l in lights:
            l.on = state

    elif args.brightness is not None:
        bri = int((args.brightness/100)*254)
        for l in lights:
            l.on = True
            l.brightness = bri

    elif args.color:
        c = POPULAR_COLORS[args.color]
        for l in lights:
            l.on = True
            if 'hue' in c: l.hue = c['hue']
            if 'sat' in c: l.saturation = c['sat']
            if 'ct' in c: l.colortemp = c['ct']

    elif args.manual_color:
        hue, sat = map(int, args.manual_color)
        for l in lights:
            l.on = True
            l.hue = hue
            l.saturation = sat

    elif args.rgb:
        r,g,b = parse_rgb(args.rgb)
        hue, sat, bri = rgb_to_hue(r,g,b)
        for l in lights:
            l.on = True
            l.hue = hue
            l.saturation = sat
            l.brightness = bri

    elif args.scene:
        set_scene(bridge, args.room, args.scene)

    # After actions, print final state
    states = [ {
        "id": l.light_id,
        "name": l.name,
        "on": l.on,
        "bri": l.brightness,
        "hue": getattr(l, 'hue', None),
        "sat": getattr(l, 'saturation', None),
        "ct": getattr(l, 'colortemp', None)
    } for l in lights]
    print(json.dumps(states, indent=2))

if __name__ == "__main__":
    main()
