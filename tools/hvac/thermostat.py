#!/home/andy/venv/bin/python
import os
import subprocess
import json
import logging
import argparse
import sys

# Configure logging to output to stderr
logger = logging.getLogger("midea")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stderr)
formatter = logging.Formatter('%(levelname)s:%(name)s:%(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Load credentials from environment variables
ACCOUNT_EMAIL = os.getenv('MIDEA_EMAIL')
PASSWORD = os.getenv('MIDEA_PASSWORD')
MIDEA_IP = os.getenv('MIDEA_IP')
MIDEA_TOKEN = os.getenv('MIDEA_TOKEN')
MIDEA_KEY = os.getenv('MIDEA_KEY')

# Define a list of default rooms if none is specified
DEFAULT_ROOMS = ["living_room", "bedroom", "office", "kitchen"]


def run_cli_command(command):
    """Run a command in the shell and return the output."""
    try:
        result = subprocess.run(
            command, shell=True, check=True, capture_output=True, text=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed: {command}\nError: {e}")
        return None


def parse_output(output):
    """Parse the CLI output into a dictionary."""
    data = {}
    lines = output.splitlines()
    for line in lines:
        line = line.strip()
        if '=' in line:
            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip()
            data[key] = value
    return data


def discover_device():
    """Discover the Midea AC device and extract the IP, token, and key."""
    command = f"midea-beautiful-air-cli discover --account {ACCOUNT_EMAIL} --password {PASSWORD} --credentials"
    output = run_cli_command(command)

    if output:
        data = parse_output(output)
        appliance_info = {
            'ip': data.get('addr'),
            'token': data.get('token'),
            'key': data.get('key')
        }

        if all(appliance_info.values()):
            return appliance_info
        else:
            logger.error("Incomplete appliance information discovered.")
            return None
    else:
        logger.error("Failed to discover device.")
        return None


def get_status(appliance_info, room):
    """Get the current status of the AC unit and include room information."""
    command = f"midea-beautiful-air-cli status --ip {appliance_info['ip']} --token {appliance_info['token']} --key {appliance_info['key']}"
    output = run_cli_command(command)
    if output:
        status = parse_output(output)
        status['room'] = room
        return status
    else:
        logger.error("Failed to retrieve status.")
        return None


def execute_command(appliance_info, args):
    """Execute command based on the arguments."""
    command = f"midea-beautiful-air-cli set --ip {appliance_info['ip']} --token {appliance_info['token']} --key {appliance_info['key']}"

    if args.power:
        if args.power == 'on':
            command += " --running 1"
        elif args.power == 'off':
            command += " --running 0"

    if args.set_temp is not None:
        # Make sure the AC is powered on before setting the temperature
        power_command = f"midea-beautiful-air-cli set --ip {appliance_info['ip']} --token {appliance_info['token']} --key {appliance_info['key']} --running 1"
        run_cli_command(power_command)

        # Convert Fahrenheit to Celsius
        temp_celsius = (args.set_temp - 32) * 5.0 / 9.0
        command += f" --target-temperature {temp_celsius:.1f}"

    if args.mode:
        mode_map = {
            'auto': 1,
            'cool': 2,
            'dry': 3,
            'heat': 4,
            'fan_only': 5
        }
        mode_value = mode_map.get(args.mode)
        if mode_value:
            command += f" --mode {mode_value}"

    if args.fan_speed:
        fan_speed_map = {
            'auto': 102,
            'low': 40,
            'medium': 60,
            'high': 80
        }
        fan_speed_value = fan_speed_map.get(args.fan_speed)
        if fan_speed_value:
            command += f" --fan-speed {fan_speed_value}"

    run_cli_command(command)


def main():
    parser = argparse.ArgumentParser(description='Control Midea AC units.')
    parser.add_argument('--room', help='Room name (optional). If omitted with --status, all rooms are shown.')

    parser.add_argument('--status', action='store_true', help='Retrieve the current status of the AC unit')
    parser.add_argument('--power', choices=['on', 'off'], help='Turn power on/off')
    parser.add_argument('--set-temp', type=float, help='Set target temperature in Fahrenheit')
    parser.add_argument('--mode', choices=['auto', 'cool', 'dry', 'heat', 'fan_only'], help='Set operation mode')
    parser.add_argument('--fan-speed', choices=['auto', 'low', 'medium', 'high'], help='Set fan speed')

    args = parser.parse_args()

    if not (ACCOUNT_EMAIL and PASSWORD):
        logger.error("MIDEA_EMAIL and MIDEA_PASSWORD environment variables must be set.")
        sys.exit(1)

    appliance_info = {
        'ip': MIDEA_IP,
        'token': MIDEA_TOKEN,
        'key': MIDEA_KEY
    }

    if not all(appliance_info.values()):
        logger.info("Discovering device information...")
        appliance_info = discover_device()
        if not appliance_info:
            logger.error("Could not retrieve appliance information.")
            sys.exit(1)
        else:
            os.environ['MIDEA_IP'] = appliance_info['ip']
            os.environ['MIDEA_TOKEN'] = appliance_info['token']
            os.environ['MIDEA_KEY'] = appliance_info['key']
            logger.info("Device information discovered and environment variables set.")

    control_performed = False
    if any([args.power, args.set_temp, args.mode, args.fan_speed]):
        room = args.room if args.room else "default_room"
        execute_command(appliance_info, args)
        control_performed = True

    if args.status or control_performed:
        if args.status and not args.room:
            # Retrieve status for all known rooms, but deduplicate by device ID
            unique_devices = {}
            for r in DEFAULT_ROOMS:
                s = get_status(appliance_info, r)
                if s:
                    device_id = s.get('id')
                    if device_id not in unique_devices:
                        # Add device and start a rooms list
                        s['rooms'] = [s.pop('room')]
                        unique_devices[device_id] = s
                    else:
                        # Append the new room to existing device
                        unique_devices[device_id]['rooms'].append(s['room'])
            # Convert to a list
            all_statuses = list(unique_devices.values())
            print(json.dumps(all_statuses, indent=2))
        else:
            # Retrieve status for the specified room
            room = args.room if args.room else "default_room"
            status = get_status(appliance_info, room)
            if status:
                print(json.dumps(status, indent=2))
            else:
                sys.exit(1)
    else:
        logger.error("No operation specified. Use --status to retrieve status or provide control arguments.")
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
