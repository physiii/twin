#!/usr/bin/env python3
"""
Setup script for Twin room integration
"""
import json
import os
import sys
from ...tools.ha_rooms import generate_room_mapping

def create_config_directory():
    """Create config directory if it doesn't exist"""
    os.makedirs('config', exist_ok=True)
    print("✅ Created config directory")

def setup_basic_configuration():
    """Create basic source location configuration"""
    print("\n🔧 Setting up basic configuration...")
    
    config = {
        "home_assistant": {
            "url": "http://homeassistant:8123",
            "token_env": "HA_TOKEN",
            "sync_rooms": True
        },
        "source_mappings": {},
        "room_aliases": {
            "media": ["media_room", "entertainment", "tv_room"],
            "living_room": ["living", "lounge", "family_room"],
            "master_bedroom": ["bedroom", "master"],
            "office": ["study", "den", "work_room"]
        },
        "non_ha_devices": {},
        "default_location": "office"
    }
    
    # Interactive setup
    print("\n📍 Let's configure your audio sources and rooms:")
    
    # Get Home Assistant URL
    ha_url = input(f"Home Assistant URL [{config['home_assistant']['url']}]: ").strip()
    if ha_url:
        config['home_assistant']['url'] = ha_url
    
    # Ask about HA integration
    sync_ha = input("Enable Home Assistant room sync? [Y/n]: ").strip().lower()
    config['home_assistant']['sync_rooms'] = sync_ha != 'n'
    
    # Configure audio sources
    print("\n🎙️  Configure audio source mappings:")
    while True:
        print("\nAvailable room presets: office, kitchen, living_room, bedroom, media")
        source = input("Audio source (RTSP URL, device name, or 'done' to finish): ").strip()
        if source.lower() == 'done' or not source:
            break
        
        room = input(f"Room for '{source}': ").strip()
        if room:
            config['source_mappings'][source] = room.lower().replace(' ', '_')
            print(f"✅ Added: {source} → {room}")
    
    # Default location
    default = input(f"Default location [{config['default_location']}]: ").strip()
    if default:
        config['default_location'] = default.lower().replace(' ', '_')
    
    return config

def setup_non_ha_devices(config):
    """Setup non-Home Assistant devices"""
    print("\n🔌 Configure non-HA devices (Philips Hue, AC units, etc.):")
    
    rooms = set(config['source_mappings'].values())
    rooms.add(config['default_location'])
    
    for room in sorted(rooms):
        print(f"\n📍 Configuring devices for room: {room}")
        
        # Philips Hue
        has_hue = input(f"Does {room} have Philips Hue lights? [y/N]: ").strip().lower()
        if has_hue == 'y':
            bridge_ip = input("Hue Bridge IP: ").strip()
            lights_input = input("Light IDs (comma-separated, e.g., 1,2,3): ").strip()
            
            if bridge_ip and lights_input:
                try:
                    light_ids = [int(x.strip()) for x in lights_input.split(',')]
                    if room not in config['non_ha_devices']:
                        config['non_ha_devices'][room] = {}
                    config['non_ha_devices'][room]['philips_hue'] = {
                        'bridge_ip': bridge_ip,
                        'lights': light_ids
                    }
                    print(f"✅ Added Hue lights for {room}")
                except ValueError:
                    print("❌ Invalid light IDs format")
        
        # AC/Climate
        has_ac = input(f"Does {room} have AC/climate control? [y/N]: ").strip().lower()
        if has_ac == 'y':
            ac_type = input("AC type (midea/generic) [midea]: ").strip() or "midea"
            ac_ip = input("AC IP address: ").strip()
            
            if ac_ip:
                if room not in config['non_ha_devices']:
                    config['non_ha_devices'][room] = {}
                config['non_ha_devices'][room][f'{ac_type}_ac'] = {
                    'ip': ac_ip,
                    'token': 'env:MIDEA_TOKEN',
                    'key': 'env:MIDEA_KEY'
                }
                print(f"✅ Added {ac_type} AC for {room}")
    
    return config

def sync_with_home_assistant(config):
    """Attempt to sync with Home Assistant"""
    if not config['home_assistant']['sync_rooms']:
        print("🏠 HA sync disabled, skipping...")
        return config
    
    print("\n🏠 Attempting to sync with Home Assistant...")
    
    # Check for HA token
    token_env = config['home_assistant']['token_env']
    if not os.getenv(token_env):
        print(f"⚠️  Environment variable {token_env} not set")
        print(f"   Please set it with your HA long-lived access token")
        return config
    
    try:
        from tools.ha_rooms import HomeAssistantRooms
        ha = HomeAssistantRooms()
        areas = ha.get_areas()
        
        if areas:
            print(f"✅ Found {len(areas)} HA areas: {list(areas.keys())}")
            # Auto-add any missing source mappings for HA rooms
            for area_name in areas.keys():
                if area_name not in config['source_mappings'].values():
                    print(f"   Note: HA room '{area_name}' has no audio source mapping")
        else:
            print("⚠️  No HA areas found (check connection/token)")
    
    except Exception as e:
        print(f"❌ Error connecting to HA: {e}")
    
    return config

def save_configuration(config):
    """Save configuration to file"""
    config_path = 'config/source_locations.json'
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
    print(f"✅ Configuration saved to {config_path}")

def print_setup_summary(config):
    """Print setup summary"""
    print("\n📋 Setup Summary")
    print("=" * 50)
    print(f"Home Assistant: {config['home_assistant']['url']}")
    print(f"HA Sync: {'Enabled' if config['home_assistant']['sync_rooms'] else 'Disabled'}")
    print(f"Default Location: {config['default_location']}")
    print(f"Audio Source Mappings: {len(config['source_mappings'])}")
    print(f"Non-HA Device Rooms: {len(config['non_ha_devices'])}")
    
    print("\n🎙️  Audio Sources:")
    for source, location in config['source_mappings'].items():
        print(f"  {source} → {location}")
    
    print("\n🔌 Non-HA Devices:")
    for room, devices in config['non_ha_devices'].items():
        print(f"  {room}: {list(devices.keys())}")

def create_environment_template():
    """Create environment variable template"""
    env_template = """# Twin Room Integration Environment Variables

# Home Assistant
HA_TOKEN=your_long_lived_access_token_here
HA_URL=http://homeassistant:8123

# Philips Hue (if using direct API)
HUE_BRIDGE_IP=192.168.1.XXX
HUE_USERNAME=your_hue_username

# Midea AC (if using)
MIDEA_TOKEN=your_midea_token
MIDEA_KEY=your_midea_key

# Other device credentials as needed
"""
    
    with open('.env.example', 'w') as f:
        f.write(env_template)
    print("✅ Created .env.example with environment variable template")

def main():
    """Main setup function"""
    print("🤖 Twin Room Integration Setup")
    print("=" * 40)
    print("This will help you configure room-aware voice control")
    print()
    
    # Check for existing config
    if os.path.exists('config/source_locations.json'):
        overwrite = input("Configuration exists. Overwrite? [y/N]: ").strip().lower()
        if overwrite != 'y':
            print("Setup cancelled.")
            return
    
    create_config_directory()
    config = setup_basic_configuration()
    config = setup_non_ha_devices(config)
    config = sync_with_home_assistant(config)
    save_configuration(config)
    create_environment_template()
    
    print_setup_summary(config)
    
    print("\n🎉 Setup Complete!")
    print()
    print("Next steps:")
    print("1. Copy .env.example to .env and fill in your credentials")
    print("2. Run 'python test_room_integration.py' to test the setup")
    print("3. Start Twin with your configured audio sources")
    print()
    print("💡 Voice commands will now be room-aware:")
    print("   - 'turn on the lights' → uses source location")
    print("   - 'turn on kitchen lights' → explicit room override")
    print("   - Commands are validated against room capabilities")

if __name__ == "__main__":
    main() 