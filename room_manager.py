#!/usr/bin/env python3
import json
import os
import requests
import logging
from typing import Dict, List, Optional, Tuple
from pathlib import Path

logger = logging.getLogger("twin")

class RoomManager:
    def __init__(self, config_path: str = "config/source_locations.json"):
        self.config_path = config_path
        self.config = self._load_config()
        self.ha_rooms = {}
        self.refresh_ha_rooms()
    
    def _load_config(self) -> Dict:
        """Load room configuration"""
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load room config: {e}")
            return {"source_mappings": {}, "default_location": "office"}
    
    def refresh_ha_rooms(self):
        """Refresh Home Assistant room data"""
        if not self.config.get("home_assistant", {}).get("sync_rooms", False):
            logger.debug("HA room sync disabled")
            return
        
        try:
            ha_url = self.config["home_assistant"]["url"]
            token_env = self.config["home_assistant"]["token_env"]
            token = os.getenv(token_env)
            
            if not token:
                logger.warning(f"HA token not found in env var: {token_env}")
                return
            
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }
            
            # Get areas
            response = requests.get(f'{ha_url}/api/config/area_registry', headers=headers, timeout=5)
            response.raise_for_status()
            areas = response.json()
            
            for area in areas:
                area_name = area['name'].lower()
                self.ha_rooms[area_name] = {
                    'id': area['area_id'],
                    'name': area['name'],
                    'aliases': area.get('aliases', [])
                }
            
            logger.info(f"🏠 Refreshed {len(self.ha_rooms)} HA rooms: {list(self.ha_rooms.keys())}")
            
        except Exception as e:
            logger.error(f"Failed to refresh HA rooms: {e}")
    
    def get_location_from_source(self, audio_source: str) -> str:
        """Get room location based on audio source"""
        mappings = self.config.get("source_mappings", {})
        
        # Direct mapping lookup
        if audio_source in mappings:
            location = mappings[audio_source]
            logger.info(f"🎯 Direct source mapping: {audio_source} → {location}")
            return location
        
        # Partial matching for RTSP URLs
        for source_pattern, location in mappings.items():
            if audio_source and source_pattern in str(audio_source):
                logger.info(f"🎯 Pattern source mapping: {audio_source} → {location}")
                return location
        
        # Fallback to default
        default = self.config.get("default_location", "office")
        logger.warning(f"🎯 Using default location: {default} for source: {audio_source}")
        return default
    
    def resolve_room_from_transcript(self, transcript: str) -> Optional[str]:
        """Extract room name from transcription text"""
        transcript_lower = transcript.lower()
        
        # Check HA rooms first
        for room_name in self.ha_rooms.keys():
            if room_name in transcript_lower:
                logger.debug(f"🎯 Found HA room '{room_name}' in transcript: '{transcript}'")
                return room_name
        
        # Check aliases
        for room, aliases in self.config.get("room_aliases", {}).items():
            for alias in aliases:
                if alias.lower() in transcript_lower:
                    logger.debug(f"🎯 Found room '{room}' via alias '{alias}' in transcript: '{transcript}'")
                    return room
        
        # Check non-HA device rooms
        for room_name in self.config.get("non_ha_devices", {}).keys():
            if room_name.lower() in transcript_lower:
                logger.debug(f"🎯 Found non-HA room '{room_name}' in transcript: '{transcript}'")
                return room_name
        
        return None
    
    def get_room_capabilities(self, room: str) -> Dict:
        """Get what devices/capabilities are available in a room"""
        capabilities = {
            "ha_entities": {},
            "non_ha_devices": {},
            "available_commands": []
        }
        
        # HA entities (if room exists in HA)
        if room in self.ha_rooms:
            # This would be populated by querying HA for entities in this area
            # For now, we assume HA rooms have basic light/climate capabilities
            capabilities["ha_entities"] = {
                "lights": ["assumed_ha_lights"],
                "climate": ["assumed_ha_climate"]
            }
        
        # Non-HA devices
        non_ha = self.config.get("non_ha_devices", {}).get(room, {})
        capabilities["non_ha_devices"] = non_ha
        
        # Generate available commands based on devices
        if "philips_hue" in non_ha:
            capabilities["available_commands"].extend([
                f"lights --power on/off --room {room}",
                f"lights --brightness <0-100> --room {room}",
                f"lights --color <color> --room {room}"
            ])
        
        if "midea_ac" in non_ha:
            capabilities["available_commands"].extend([
                f"thermostat --set-temp <temp> --room {room}",
                f"thermostat --power on/off --room {room}"
            ])
        
        # Add HA-based commands if room exists in HA
        if room in self.ha_rooms:
            capabilities["available_commands"].extend([
                f"ha_service --entity light.{room}_* --service turn_on",
                f"ha_service --entity climate.{room}_* --service set_temperature"
            ])
        
        return capabilities
    
    def validate_room_command(self, command: str, room: str) -> Tuple[bool, str]:
        """Validate if a command can be executed in the specified room"""
        capabilities = self.get_room_capabilities(room)
        
        # Basic validation - check if room has relevant devices
        if "lights" in command:
            if ("philips_hue" in capabilities["non_ha_devices"] or 
                "lights" in capabilities.get("ha_entities", {}) or
                room in self.ha_rooms):
                return True, f"Lights available in {room}"
            else:
                return False, f"No lighting devices found in {room}"
        
        if "thermostat" in command:
            if ("midea_ac" in capabilities["non_ha_devices"] or
                "climate" in capabilities.get("ha_entities", {}) or
                room in self.ha_rooms):
                return True, f"Climate control available in {room}"
            else:
                return False, f"No climate devices found in {room}"
        
        # Allow other commands to pass through
        return True, "Command validation passed"
    
    def get_all_rooms(self) -> List[str]:
        """Get list of all available rooms"""
        rooms = set()
        
        # Add HA rooms
        rooms.update(self.ha_rooms.keys())
        
        # Add non-HA device rooms
        rooms.update(self.config.get("non_ha_devices", {}).keys())
        
        # Add source mapping rooms
        rooms.update(self.config.get("source_mappings", {}).values())
        
        return sorted(list(rooms))
    
    def get_room_info(self, room: str) -> Dict:
        """Get comprehensive information about a room"""
        info = {
            "name": room,
            "is_ha_room": room in self.ha_rooms,
            "capabilities": self.get_room_capabilities(room),
            "sources": []
        }
        
        # Find audio sources for this room
        for source, location in self.config.get("source_mappings", {}).items():
            if location == room:
                info["sources"].append(source)
        
        return info

# Global instance
room_manager = None

def get_room_manager() -> RoomManager:
    """Get singleton room manager instance"""
    global room_manager
    if room_manager is None:
        room_manager = RoomManager()
    return room_manager 