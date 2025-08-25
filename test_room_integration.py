#!/usr/bin/env python3
"""
Test script for the enhanced room management system
"""
import json
import sys
import os
from room_manager import RoomManager, get_room_manager
from tools.ha_rooms import generate_room_mapping

def test_source_mapping():
    """Test source-to-location mapping"""
    print("🔍 Testing Source-to-Location Mapping")
    print("=" * 50)
    
    room_manager = get_room_manager()
    
    test_sources = [
        "rtsp://192.168.1.100:554/audio",
        "rtsp://192.168.1.101:554/audio", 
        "device_13",
        "pulse",
        "unknown_source"
    ]
    
    for source in test_sources:
        location = room_manager.get_location_from_source(source)
        print(f"Source: {source:<35} → Location: {location}")
    
    print()

def test_transcript_room_detection():
    """Test room detection from voice commands"""
    print("🎯 Testing Transcript Room Detection")
    print("=" * 50)
    
    room_manager = get_room_manager()
    
    test_transcripts = [
        "turn on the kitchen lights",
        "set the bedroom temperature to 72",
        "turn off the office lights please",
        "turn on lights in the living room",
        "turn on the AC in media room",
        "just turn on the lights"  # No explicit room
    ]
    
    for transcript in test_transcripts:
        detected_room = room_manager.resolve_room_from_transcript(transcript)
        print(f"Transcript: '{transcript:<35}' → Room: {detected_room or 'None'}")
    
    print()

def test_room_capabilities():
    """Test room capability detection"""
    print("🏠 Testing Room Capabilities")
    print("=" * 50)
    
    room_manager = get_room_manager()
    rooms = room_manager.get_all_rooms()
    
    for room in rooms[:5]:  # Limit to first 5 rooms
        print(f"\n📍 Room: {room}")
        capabilities = room_manager.get_room_capabilities(room)
        print(f"  HA Room: {room in room_manager.ha_rooms}")
        print(f"  Non-HA Devices: {list(capabilities['non_ha_devices'].keys())}")
        print(f"  Available Commands: {len(capabilities['available_commands'])}")
        for cmd in capabilities['available_commands'][:3]:  # Show first 3 commands
            print(f"    - {cmd}")

def test_command_validation():
    """Test command validation against room capabilities"""
    print("✅ Testing Command Validation")
    print("=" * 50)
    
    room_manager = get_room_manager()
    
    test_cases = [
        ("lights --power on", "office"),
        ("lights --power on", "nonexistent_room"),
        ("thermostat --set-temp 72", "office"),
        ("thermostat --set-temp 72", "kitchen"),
        ("player --play", "office")  # Should pass (not validated)
    ]
    
    for command, room in test_cases:
        valid, message = room_manager.validate_room_command(command, room)
        status = "✅ VALID" if valid else "❌ INVALID"
        print(f"{status:<10} | Room: {room:<15} | Command: {command:<25} | {message}")
    
    print()

def test_ha_integration():
    """Test Home Assistant integration"""
    print("🏡 Testing Home Assistant Integration")
    print("=" * 50)
    
    try:
        room_manager = get_room_manager()
        room_manager.refresh_ha_rooms()
        
        if room_manager.ha_rooms:
            print(f"✅ HA Integration Working - Found {len(room_manager.ha_rooms)} rooms:")
            for room_name, room_info in list(room_manager.ha_rooms.items())[:5]:
                print(f"  - {room_name} (ID: {room_info['id']})")
        else:
            print("⚠️  No HA rooms found (check HA_TOKEN and connection)")
    except Exception as e:
        print(f"❌ HA Integration Error: {e}")
    
    print()

def test_full_integration():
    """Test the complete integration workflow"""
    print("🔄 Testing Full Integration Workflow")
    print("=" * 50)
    
    room_manager = get_room_manager()
    
    # Simulate various scenarios
    scenarios = [
        {
            "source": "rtsp://192.168.1.100:554/audio",
            "transcript": "turn on the lights",
            "expected_room": "office"
        },
        {
            "source": "device_14", 
            "transcript": "turn on the kitchen lights",
            "expected_room": "kitchen"  # Explicit in transcript
        },
        {
            "source": "unknown_source",
            "transcript": "set bedroom temperature to 70",
            "expected_room": "bedroom"  # Explicit in transcript
        }
    ]
    
    for i, scenario in enumerate(scenarios, 1):
        print(f"\n🔬 Scenario {i}:")
        print(f"  Source: {scenario['source']}")
        print(f"  Transcript: '{scenario['transcript']}'")
        
        # Get source location
        source_location = room_manager.get_location_from_source(scenario['source'])
        print(f"  Source Location: {source_location}")
        
        # Get transcript room
        transcript_room = room_manager.resolve_room_from_transcript(scenario['transcript'])
        print(f"  Transcript Room: {transcript_room or 'None'}")
        
        # Final room selection logic (mirrors command.py)
        final_room = transcript_room or source_location
        print(f"  Final Room: {final_room}")
        print(f"  Expected: {scenario['expected_room']}")
        
        # Validate
        if "lights" in scenario['transcript'] or "temperature" in scenario['transcript']:
            command_type = "lights" if "lights" in scenario['transcript'] else "thermostat"
            valid, message = room_manager.validate_room_command(f"{command_type} --test", final_room)
            status = "✅" if valid else "❌"
            print(f"  Validation: {status} {message}")

def print_configuration_summary():
    """Print current configuration summary"""
    print("📋 Configuration Summary")
    print("=" * 50)
    
    try:
        with open('config/source_locations.json', 'r') as f:
            config = json.load(f)
        
        print(f"HA Integration: {'✅ Enabled' if config.get('home_assistant', {}).get('sync_rooms') else '❌ Disabled'}")
        print(f"Source Mappings: {len(config.get('source_mappings', {}))}")
        print(f"Non-HA Device Rooms: {len(config.get('non_ha_devices', {}))}")
        print(f"Default Location: {config.get('default_location', 'Not set')}")
        print()
        
        # Show mappings
        print("🎙️  Source Mappings:")
        for source, location in config.get('source_mappings', {}).items():
            print(f"  {source:<35} → {location}")
        
        print()
    except Exception as e:
        print(f"❌ Error reading configuration: {e}")

def main():
    """Run all tests"""
    print("🤖 Twin Room Integration Test Suite")
    print("=" * 60)
    print()
    
    # Check if config exists
    if not os.path.exists('config/source_locations.json'):
        print("❌ Configuration file not found: config/source_locations.json")
        print("   Please ensure the configuration is set up first.")
        return
    
    print_configuration_summary()
    test_source_mapping()
    test_transcript_room_detection()
    test_room_capabilities()
    test_command_validation()
    test_ha_integration()
    test_full_integration()
    
    print("🏁 Testing Complete!")
    print()
    print("💡 Tips:")
    print("   - Set HA_TOKEN environment variable for HA integration")
    print("   - Update config/source_locations.json for your setup")
    print("   - Check logs for detailed room detection info")

if __name__ == "__main__":
    main() 