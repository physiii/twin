#!/usr/bin/env python3
import requests
import json
import os
from typing import Dict, List, Optional

class HomeAssistantRooms:
    def __init__(self):
        self.ha_url = os.getenv('HA_URL', 'http://homeassistant:8123')
        self.ha_token = os.getenv('HA_TOKEN')
        self.headers = {
            'Authorization': f'Bearer {self.ha_token}',
            'Content-Type': 'application/json'
        }
    
    def get_areas(self) -> Dict[str, Dict]:
        """Get all areas/rooms from Home Assistant"""
        try:
            response = requests.get(f'{self.ha_url}/api/config/area_registry', headers=self.headers)
            response.raise_for_status()
            areas = response.json()
            
            # Convert to name-based lookup
            area_map = {}
            for area in areas:
                area_map[area['name'].lower()] = {
                    'id': area['area_id'],
                    'name': area['name'],
                    'aliases': area.get('aliases', [])
                }
            return area_map
        except Exception as e:
            print(f"Failed to get HA areas: {e}")
            return {}
    
    def get_devices_by_area(self, area_id: str) -> List[Dict]:
        """Get all devices in a specific area"""
        try:
            # Get device registry
            response = requests.get(f'{self.ha_url}/api/config/device_registry', headers=self.headers)
            response.raise_for_status()
            devices = response.json()
            
            return [d for d in devices if d.get('area_id') == area_id]
        except Exception as e:
            print(f"Failed to get devices for area {area_id}: {e}")
            return []
    
    def get_entities_by_area(self, area_name: str) -> Dict[str, List]:
        """Get all entities (lights, switches, etc.) in an area"""
        try:
            # Get all states
            response = requests.get(f'{self.ha_url}/api/states', headers=self.headers)
            response.raise_for_status()
            states = response.json()
            
            area_entities = {
                'lights': [],
                'switches': [], 
                'climate': [],
                'covers': [],
                'media_players': []
            }
            
            for state in states:
                entity_id = state['entity_id']
                attributes = state.get('attributes', {})
                
                # Check if entity belongs to this area
                if (attributes.get('area_id') == area_name or 
                    attributes.get('friendly_name', '').lower().startswith(area_name.lower())):
                    
                    domain = entity_id.split('.')[0]
                    if domain in area_entities:
                        area_entities[domain].append({
                            'entity_id': entity_id,
                            'name': attributes.get('friendly_name', entity_id),
                            'state': state['state']
                        })
            
            return area_entities
        except Exception as e:
            print(f"Failed to get entities for area {area_name}: {e}")
            return {}

def generate_room_mapping():
    """Generate comprehensive room mapping from HA + custom sources"""
    ha = HomeAssistantRooms()
    areas = ha.get_areas()
    
    # Base configuration structure
    config = {
        "home_assistant": {
            "url": os.getenv('HA_URL', 'http://homeassistant:8123'),
            "token_env": "HA_TOKEN"
        },
        "source_mappings": {},
        "room_entities": {},
        "non_ha_devices": {},
        "default_location": "office",
        "fallback_behavior": "use_default"
    }
    
    # Process each HA area
    for area_name, area_info in areas.items():
        print(f"Processing HA area: {area_name}")
        entities = ha.get_entities_by_area(area_info['id'])
        config["room_entities"][area_name] = entities
    
    return config, areas

if __name__ == "__main__":
    config, areas = generate_room_mapping()
    
    # Save to file
    os.makedirs('config', exist_ok=True)
    with open('config/ha_room_mapping.json', 'w') as f:
        json.dump(config, f, indent=2)
    
    print("Generated Home Assistant room mapping")
    print(f"Found {len(areas)} areas: {list(areas.keys())}") 