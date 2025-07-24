import requests
import logging
from typing import Optional, Dict, Tuple

logger = logging.getLogger(__name__)

class LocationService:
    """Service for handling location-related operations with Google Maps integration."""
    
    def __init__(self, config):
        self.config = config
        self.google_maps_api_key = getattr(config, 'GOOGLE_MAPS_API_KEY', None)
        
    def validate_api_key(self) -> bool:
        """Check if Google Maps API key is configured."""
        return bool(self.google_maps_api_key)
    
    def get_address_from_coordinates(self, latitude: float, longitude: float) -> Optional[str]:
        """Convert coordinates to human-readable address using Google Maps Geocoding API."""
        if not self.validate_api_key():
            logger.warning("Google Maps API key not configured")
            return None
            
        try:
            url = "https://maps.googleapis.com/maps/api/geocode/json"
            params = {
                'latlng': f"{latitude},{longitude}",
                'key': self.google_maps_api_key,
                'language': 'en'
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if data['status'] == 'OK' and data['results']:
                # Get the most detailed address (first result)
                formatted_address = data['results'][0]['formatted_address']
                logger.info(f"Successfully geocoded coordinates to: {formatted_address}")
                return formatted_address
            else:
                logger.warning(f"Geocoding failed: {data.get('status', 'Unknown error')}")
                return None
                
        except requests.RequestException as e:
            logger.error(f"Error calling Google Maps Geocoding API: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in geocoding: {e}")
            return None
    
    def get_coordinates_from_address(self, address: str) -> Optional[Tuple[float, float]]:
        """Convert address to coordinates using Google Maps Geocoding API."""
        if not self.validate_api_key():
            logger.warning("Google Maps API key not configured")
            return None
            
        try:
            url = "https://maps.googleapis.com/maps/api/geocode/json"
            params = {
                'address': address,
                'key': self.google_maps_api_key,
                'language': 'en'
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if data['status'] == 'OK' and data['results']:
                location = data['results'][0]['geometry']['location']
                latitude = location['lat']
                longitude = location['lng']
                logger.info(f"Successfully geocoded address to coordinates: {latitude}, {longitude}")
                return (latitude, longitude)
            else:
                logger.warning(f"Address geocoding failed: {data.get('status', 'Unknown error')}")
                return None
                
        except requests.RequestException as e:
            logger.error(f"Error calling Google Maps Geocoding API: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in address geocoding: {e}")
            return None
    
    def generate_maps_link(self, address: str) -> str:
        """Generate a Google Maps link for the given address."""
        import urllib.parse
        encoded_address = urllib.parse.quote(address)
        return f"https://maps.google.com/maps?q={encoded_address}"
    
    def generate_maps_link_from_coordinates(self, latitude: float, longitude: float) -> str:
        """Generate a Google Maps link from coordinates."""
        return f"https://maps.google.com/maps?q={latitude},{longitude}"
    
    def calculate_distance(self, origin_lat: float, origin_lng: float, 
                          dest_lat: float, dest_lng: float) -> Optional[Dict]:
        """Calculate distance and duration between two points using Google Maps Distance Matrix API."""
        if not self.validate_api_key():
            logger.warning("Google Maps API key not configured")
            return None
            
        try:
            url = "https://maps.googleapis.com/maps/api/distancematrix/json"
            params = {
                'origins': f"{origin_lat},{origin_lng}",
                'destinations': f"{dest_lat},{dest_lng}",
                'key': self.google_maps_api_key,
                'units': 'metric',
                'mode': 'driving'
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if data['status'] == 'OK' and data['rows']:
                element = data['rows'][0]['elements'][0]
                if element['status'] == 'OK':
                    return {
                        'distance': element['distance']['text'],
                        'duration': element['duration']['text'],
                        'distance_value': element['distance']['value'],  # in meters
                        'duration_value': element['duration']['value']   # in seconds
                    }
            
            logger.warning(f"Distance calculation failed: {data.get('status', 'Unknown error')}")
            return None
            
        except requests.RequestException as e:
            logger.error(f"Error calling Google Maps Distance Matrix API: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in distance calculation: {e}")
            return None
    
    def validate_location_format(self, location_data: Dict) -> bool:
        """Validate WhatsApp location message format."""
        required_fields = ['latitude', 'longitude']
        return all(field in location_data for field in required_fields)
    
    def format_location_info(self, latitude: float, longitude: float, 
                           address: Optional[str] = None) -> str:
        """Format location information for display."""
        if address:
            maps_link = self.generate_maps_link(address)
            return f"📍 Location: {address}\n🗺️ View on Maps: {maps_link}"
        else:
            maps_link = self.generate_maps_link_from_coordinates(latitude, longitude)
            return f"📍 Coordinates: {latitude}, {longitude}\n🗺️ View on Maps: {maps_link}"