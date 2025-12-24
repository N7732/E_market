# mapping_service.py
import requests
import googlemaps
import polyline
import folium
from geopy.distance import geodesic
from django.conf import settings
from typing import Dict, List, Tuple, Optional
import json
from datetime import datetime

class MappingService:
    def __init__(self):
        # Initialize Google Maps client
        self.gmaps = googlemaps.Client(key=settings.GOOGLE_MAPS_API_KEY)
        
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
        
        # Method 3: Fallback - OSMnx (offline routing)
        try:
            osmnx_result = self._osmnx_distance(origin, destination, mode)
            results['osmnx'] = osmnx_result
        except Exception as e:
            print(f"OSMnx error: {e}")
        
        # Choose best result
        best_result = self._select_best_distance(results)
        
        # Add map visualization
        best_result['map_url'] = self.generate_map_url(origin, destination)
        best_result['static_map'] = self.generate_static_map(origin, destination)
        
        return best_result
    
    def _google_maps_distance(self, origin: Tuple[float, float], 
                             destination: Tuple[float, float], 
                             mode: str) -> Dict:
        """Calculate distance using Google Maps API"""
        result = self.gmaps.distance_matrix(
            origins=[origin],
            destinations=[destination],
            mode=mode,
            units='metric',
            departure_time=datetime.now()
        )
        
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
        
        data = response.json()
        
        return {
            'distance_meters': data['features'][0]['properties']['summary']['distance'],
            'duration_seconds': data['features'][0]['properties']['summary']['duration'],
            'route_geojson': data['features'][0]['geometry'],
            'source': 'openroute',
            'status': 'OK'
        }
    
    def _osmnx_distance(self, origin: Tuple[float, float], 
                       destination: Tuple[float, float], 
                       mode: str) -> Dict:
        """Calculate distance using OSMnx (offline)"""
        try:
            import osmnx as ox
            import networkx as nx
            
            # Get graph for the area
            north = max(origin[0], destination[0]) + 0.1
            south = min(origin[0], destination[0]) - 0.1
            east = max(origin[1], destination[1]) + 0.1
            west = min(origin[1], destination[1]) - 0.1
            
            # Download street network
            graph = ox.graph_from_bbox(north, south, east, west, network_type=mode)
            
            # Find nearest nodes
            orig_node = ox.distance.nearest_nodes(graph, origin[1], origin[0])
            dest_node = ox.distance.nearest_nodes(graph, destination[1], destination[0])
            
            # Calculate shortest path
            route = nx.shortest_path(graph, orig_node, dest_node, weight='length')
            
            # Calculate route distance
            route_distance = sum(
                ox.utils_graph.get_route_edge_attributes(graph, route, 'length')
            )
            
            # Estimate time (simplified)
            speed_kmh = 30 if mode == 'driving' else 5
            duration_hours = route_distance / 1000 / speed_kmh
            
            return {
                'distance_meters': route_distance,
                'duration_seconds': duration_hours * 3600,
                'route_nodes': route,
                'source': 'osmnx',
                'status': 'OK'
            }
        except Exception as e:
            raise Exception(f"OSMnx error: {e}")
    
    def _get_route_polyline(self, origin: Tuple[float, float], 
                           destination: Tuple[float, float], 
                           mode: str) -> str:
        """Get route polyline from Google Directions API"""
        directions = self.gmaps.directions(
            origin=origin,
            destination=destination,
            mode=mode
        )
        
        if directions:
            return directions[0]['overview_polyline']['points']
        return ""
    
    def _select_best_distance(self, results: Dict) -> Dict:
        """Select the most reliable distance result"""
        # Prefer Google Maps, then OpenRoute, then OSMnx
        for source in ['google_maps', 'openroute', 'osmnx']:
            if source in results and results[source]['status'] == 'OK':
                return results[source]
        
        # Fallback to straight line distance
        straight_distance = geodesic(origin, destination).km * 1000
        return {
            'distance_meters': straight_distance,
            'distance_text': f"{straight_distance/1000:.1f} km",
            'duration_seconds': straight_distance / 1000 * 3600 / 30,  # 30 km/h
            'duration_text': "Estimated",
            'source': 'fallback',
            'status': 'OK'
        }
    
    def generate_map_url(self, origin: Tuple[float, float], 
                        destination: Tuple[float, float]) -> str:
        """Generate Google Maps URL for visualization"""
        base_url = "https://www.google.com/maps/dir/"
        origin_str = f"{origin[0]},{origin[1]}"
        dest_str = f"{destination[0]},{destination[1]}"
        return f"{base_url}{origin_str}/{dest_str}"
    
    def generate_static_map(self, origin: Tuple[float, float], 
                           destination: Tuple[float, float],
                           width: int = 600, height: int = 400) -> str:
        """Generate static map image URL"""
        markers = [
            f"color:red|label:S|{origin[0]},{origin[1]}",
            f"color:green|label:E|{destination[0]},{destination[1]}"
        ]
        
        markers_str = "&".join([f"markers={m}" for m in markers])
        
        return (
            f"https://maps.googleapis.com/maps/api/staticmap?"
            f"size={width}x{height}&{markers_str}"
            f"&path=color:0x0000ff|weight:5{self._get_route_polyline(origin, destination)}"
            f"&key={settings.GOOGLE_MAPS_API_KEY}"
        )
    
    def find_nearby_places(self, location: Tuple[float, float], 
                          place_type: str, radius: int = 1000) -> List[Dict]:
        """Find nearby places using Google Places API"""
        places_result = self.gmaps.places_nearby(
            location=location,
            radius=radius,
            type=place_type
        )
        
        places = []
        for place in places_result.get('results', [])[:10]:
            places.append({
                'name': place['name'],
                'address': place.get('vicinity', ''),
                'location': place['geometry']['location'],
                'rating': place.get('rating', 0),
                'types': place.get('types', []),
                'place_id': place['place_id']
            })
        
        return places
    
    def geocode_address(self, address: str) -> Optional[Dict]:
        """Convert address to coordinates"""
        try:
            result = self.gmaps.geocode(address)
            if result:
                location = result[0]['geometry']['location']
                return {
                    'latitude': location['lat'],
                    'longitude': location['lng'],
                    'formatted_address': result[0]['formatted_address']
                }
        except Exception as e:
            print(f"Geocoding error: {e}")
        
        return None
    
    def reverse_geocode(self, lat: float, lng: float) -> Optional[Dict]:
        """Convert coordinates to address"""
        try:
            result = self.gmaps.reverse_geocode((lat, lng))
            if result:
                return {
                    'address': result[0]['formatted_address'],
                    'components': result[0]['address_components']
                }
        except Exception as e:
            print(f"Reverse geocoding error: {e}")
        
        return None

# Singleton instance
mapping_service = MappingService()