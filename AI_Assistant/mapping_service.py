# mapping_service.py
import requests
from django.conf import settings
from typing import Dict, List, Tuple, Optional
import json
from datetime import datetime

# Optional imports
try:
    import googlemaps
except ImportError:
    googlemaps = None

try:
    import polyline
except ImportError:
    polyline = None

try:
    import folium
except ImportError:
    folium = None

try:
    from geopy.distance import geodesic
except ImportError:
    geodesic = None

class MappingService:
    def __init__(self):
        # Initialize Google Maps client safely
        self.gmaps = None
        api_key = getattr(settings, 'GOOGLE_MAPS_API_KEY', None)
        if googlemaps and api_key:
            try:
                self.gmaps = googlemaps.Client(key=api_key)
            except Exception as e:
                print(f"Failed to init Google Maps: {e}")
        
        # Initialize OpenRouteService (free alternative)
        self.ors_key = getattr(settings, 'OPENROUTE_SERVICE_API_KEY', None)
        self.ors_base_url = "https://api.openrouteservice.org/v2"
    
    def calculate_road_distance(self, origin: Tuple[float, float], 
                               destination: Tuple[float, float],
                               mode: str = 'driving') -> Dict:
        """
        Calculate accurate road distance using multiple APIs
        """
        results = {}
        
        # Method 1: Google Maps API (most accurate)
        if self.gmaps:
            try:
                gmaps_result = self._google_maps_distance(origin, destination, mode)
                results['google_maps'] = gmaps_result
            except Exception as e:
                print(f"Google Maps error: {e}")
        
        # Method 2: OpenRouteService (free alternative)
        if self.ors_key:
            try:
                ors_result = self._openroute_distance(origin, destination, mode)
                results['openroute'] = ors_result
            except Exception as e:
                print(f"OpenRoute error: {e}")

        # Choose best result
        best_result = self._select_best_distance(results, origin, destination)
        
        return best_result
    
    def _google_maps_distance(self, origin: Tuple[float, float], 
                             destination: Tuple[float, float], 
                             mode: str) -> Dict:
        """Calculate distance using Google Maps API"""
        if not self.gmaps: return {}
        
        result = self.gmaps.distance_matrix(
            origins=[origin],
            destinations=[destination],
            mode=mode,
            units='metric',
            departure_time=datetime.now()
        )
        
        if not result['rows']: return {}
        element = result['rows'][0]['elements'][0]
        
        return {
            'distance_meters': element['distance']['value'],
            'distance_text': element['distance']['text'],
            'duration_seconds': element['duration']['value'],
            'duration_text': element['duration']['text'],
            'route_polyline': self._get_route_polyline(origin, destination, mode),
            'source': 'google_maps',
            'status': element.get('status', 'OK')
        }
    
    def _openroute_distance(self, origin: Tuple[float, float], 
                           destination: Tuple[float, float], 
                           mode: str) -> Dict:
        """Calculate distance using OpenRouteService"""
        ors_mode = {
            'driving': 'driving-car',
            'walking': 'foot-walking',
            'cycling': 'cycling-regular'
        }.get(mode, 'driving-car')
        
        headers = {
            'Authorization': self.ors_key,
            'Content-Type': 'application/json'
        }
        
        body = {
            "coordinates": [
                [origin[1], origin[0]],  # ORS uses [lng, lat]
                [destination[1], destination[0]]
            ],
            "instructions": False,
            "units": "m"
        }
        
        response = requests.post(
            f"{self.ors_base_url}/directions/{ors_mode}/geojson",
            headers=headers,
            json=body
        )
        
        if response.status_code != 200:
             raise Exception(f"ORS Error: {response.text}")

        data = response.json()
        
        return {
            'distance_meters': data['features'][0]['properties']['summary']['distance'],
            'duration_seconds': data['features'][0]['properties']['summary']['duration'],
            'route_geojson': data['features'][0]['geometry'],
            'source': 'openroute',
            'status': 'OK'
        }
    
    def _get_route_polyline(self, origin: Tuple[float, float], 
                           destination: Tuple[float, float], 
                           mode: str) -> str:
        """Get route polyline from Google Directions API"""
        if not self.gmaps: return ""
        
        directions = self.gmaps.directions(
            origin=origin,
            destination=destination,
            mode=mode
        )
        
        if directions:
            return directions[0]['overview_polyline']['points']
        return ""
    
    def _select_best_distance(self, results: Dict, origin, destination) -> Dict:
        """Select the most reliable distance result"""
        # Prefer Google Maps, then OpenRoute
        for source in ['google_maps', 'openroute']:
            if source in results and results[source].get('status') == 'OK':
                return results[source]
        
        # Fallback to straight line distance
        dist = 0
        if geodesic:
             dist = geodesic(origin, destination).km * 1000
        else:
             # simple pythagorean approx for fallback (very rough) with conversion factor
             # lat/111km, lng/111km at equator
             import math
             dx = (origin[0]-destination[0]) * 111000
             dy = (origin[1]-destination[1]) * 111000
             dist = math.sqrt(dx*dx + dy*dy)

        return {
            'distance_meters': dist,
            'distance_text': f"{dist/1000:.1f} km",
            'duration_seconds': dist / 1000 * 3600 / 30,  # 30 km/h
            'duration_text': "Estimated",
            'source': 'fallback',
            'status': 'OK'
        }

# Singleton instance
mapping_service = MappingService()