#!/home/andy/venv/bin/python
import argparse
import sys
import os
import time
import logging
import threading
import colorsys

# Import shared functions and variables
from hue_api import (
    get_api_username,
    list_lights,
    turn_power,
    set_brightness,
    set_color,
    parse_rgb,
    rgb_to_hue,
    POPULAR_COLORS,
    get_light_ids,
    ROOMS
)
import animations

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def main():
    parser = argparse.ArgumentParser(
        description='Philips Hue Lights Control Script with Animations',
        formatter_class=argparse.RawTextHelpFormatter
    )

    # Existing arguments
    parser.add_argument('--bridge-ip', type=str, help='IP address of the Philips Hue Bridge')
    parser.add_argument('--room', type=str, help=f'Room name ({", ".join(ROOMS.keys())}) or "all" for all lights')

    # Define mutually exclusive group for actions
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--status', action='store_true', help='Retrieve the current status of the lights in the specified room')
    group.add_argument('--power', choices=['on', 'off'], help='Turn power on/off for the lights in the specified room')
    group.add_argument('--brightness', type=int, help='Set brightness of the lights in the specified room (0-100%)')
    group.add_argument('--color', type=str, help=f'Set color of the lights using predefined color names: {", ".join(POPULAR_COLORS.keys())}')
    group.add_argument('--manual-color', nargs=2, metavar=('HUE', 'SATURATION'),
                       help='Set color manually using HUE (0-65535) and SATURATION (0-254)')
    group.add_argument('--rgb', type=str, metavar='R,G,B',
                       help='Set color using RGB values (0-255) separated by commas (e.g., "255,0,0" for red)')
    # New animate argument
    group.add_argument('--animate', type=str, choices=['sunrise', 'sunset', 'party', 'relax', 'romantic'],
                       help='Set a predefined animation: sunrise, sunset, party, relax, romantic')

    args = parser.parse_args()

    bridge_ip = args.bridge_ip or "192.168.1.129"  # Default IP if not provided
    room = args.room or "all"  # Default to all rooms if not provided

    username = get_api_username(bridge_ip)

    if args.status:
        list_lights(bridge_ip, username, room)
    elif args.power:
        power_state = True if args.power == 'on' else False
        turn_power(bridge_ip, username, room, power_state)
    elif args.brightness is not None:
        if 0 <= args.brightness <= 100:
            set_brightness(bridge_ip, username, room, args.brightness)
        else:
            logging.error("Brightness must be between 0 and 100.")
            sys.exit(1)
    elif args.color:
        color_name = args.color.lower()
        if color_name not in POPULAR_COLORS:
            logging.error(f"Invalid color name. Available colors: {', '.join(POPULAR_COLORS.keys())}")
            sys.exit(1)
        set_color(bridge_ip, username, room, color_name=color_name)
    elif args.manual_color:
        try:
            hue = float(args.manual_color[0])
            saturation = float(args.manual_color[1])
            set_color(bridge_ip, username, room, hue=hue, saturation=saturation)
        except ValueError:
            logging.error("Invalid hue or saturation values. Must be numbers.")
            sys.exit(1)
    elif args.rgb:
        try:
            r, g, b = parse_rgb(args.rgb)
            hue, saturation, brightness = rgb_to_hue(r, g, b)
            set_color(bridge_ip, username, room, hue=hue, saturation=saturation)
            # Map brightness from 0-254 to 0-100%
            brightness_percent = int((brightness / 254.0) * 100)
            set_brightness(bridge_ip, username, room, brightness=brightness_percent)
        except ValueError as ve:
            logging.error(str(ve))
            sys.exit(1)
    elif args.animate:
        animation = args.animate.lower()
        animation_functions = {
            'sunrise': animations.sunrise,
            'sunset': animations.sunset,
            'party': animations.party,
            'relax': animations.relax,
            'romantic': animations.romantic
        }
        animation_func = animation_functions.get(animation)
        if animation_func:
            # Run the animation in a separate thread to avoid blocking
            anim_thread = threading.Thread(target=animation_func, args=(bridge_ip, username, room))
            anim_thread.start()
        else:
            logging.error("Selected animation is not defined.")
            sys.exit(1)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
