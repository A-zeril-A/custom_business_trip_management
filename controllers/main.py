import requests
import json
from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)

class BusinessTripFormIOController(http.Controller):

    @http.route('/business_trip/api/geonames_cities', type='json', auth='user', methods=['GET', 'POST'], csrf=False)
    def fetch_geonames_cities(self, **kwargs):
        search_term = kwargs.get('search_term') or kwargs.get('query')
        
        _logger.info(f"BTD_CONTROLLER_API: Geonames city search. Search term from kwargs: {search_term}, All kwargs: {kwargs}")

        if not search_term:
            if request and hasattr(request, 'params'):
                search_term = request.params.get('search_term') or request.params.get('query')
                _logger.info(f"BTD_CONTROLLER_API: Search term from request.params: {search_term}")

        if not search_term:
            _logger.warning("BTD_CONTROLLER_API: No search_term provided in kwargs or request.params.")
            return []

        username = 'azerila' 
        api_url = "http://api.geonames.org/search?"
        geonames_params = {
            'name_startsWith': search_term,
            'maxRows': 15,
            'featureClass': 'P',
            'style': 'MEDIUM',
            'username': username,
        }
        
        results = []
        try:
            _logger.info(f"BTD_CONTROLLER_API: Requesting Geonames. URL: {api_url}, Params: {json.dumps(geonames_params)}")
            
            api_response = requests.get(api_url, params=geonames_params, timeout=10)
            api_response.raise_for_status()
            
            response_data = api_response.json()

            if 'status' in response_data and response_data.get('geonames') is None:
                error_message = response_data['status'].get('message', 'Unknown Geonames API error')
                error_value = response_data['status'].get('value', 'N/A')
                _logger.error(f"BTD_CONTROLLER_API: Geonames API returned an error. Value: {error_value}, Message: {error_message}")
            else:
                geonames_results = response_data.get('geonames', [])
                for item in geonames_results:
                    name = item.get('name')
                    country_name = item.get('countryName')
                    geoname_id = item.get('geonameId')

                    if name and geoname_id:
                        label_parts = [name]
                        if country_name:
                            label_parts.append(country_name)
                        
                        display_label = ", ".join(filter(None,label_parts))
                        
                        results.append({
                            'value': str(geoname_id), 
                            'label': display_label
                        })
                _logger.info(f"BTD_CONTROLLER_API: Processed {len(results)} results for search term '{search_term}'.")

        except requests.exceptions.Timeout:
            _logger.error(f"BTD_CONTROLLER_API: Timeout error fetching data from Geonames for term '{search_term}'.")
        except requests.exceptions.RequestException as e:
            _logger.error(f"BTD_CONTROLLER_API: Network or HTTP error for term '{search_term}': {str(e)}")
        except json.JSONDecodeError as e:
            _logger.error(f"BTD_CONTROLLER_API: Error decoding JSON response from Geonames for term '{search_term}': {str(e)}")
        except Exception as e:
            _logger.error(f"BTD_CONTROLLER_API: An unexpected error occurred for term '{search_term}': {type(e).__name__} - {str(e)}")
        
        return results 