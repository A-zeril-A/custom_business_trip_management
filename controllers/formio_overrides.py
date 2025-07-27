import requests
import json
import logging
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

# Attempt to import the original Formio controllers
# These paths assume 'formio' is the technical name of the odoo-formio main module
try:
    from odoo.addons.formio.controllers.main import FormioController as OriginalFormioController
except ImportError:
    _logger.error("Failed to import OriginalFormioController from odoo.addons.formio.controllers.main. Using fallback.")
    # Fallback to a generic controller if the import fails, to prevent Odoo from crashing
    # This override will likely not work correctly if the import fails.
    class OriginalFormioController(http.Controller):
        def _api_get_data(self, builder_or_form_uuid_or_object, **kwargs): # pragma: no cover
            _logger.warning("OriginalFormioController._api_get_data could not be imported. Fallback called.")
            return json.dumps([])

try:
    from odoo.addons.formio.controllers.public import FormioPublicController as OriginalFormioPublicController
except ImportError:
    _logger.error("Failed to import OriginalFormioPublicController from odoo.addons.formio.controllers.public. Using fallback.")
    class OriginalFormioPublicController(http.Controller):
        def _api_get_data(self, builder, **kwargs): # pragma: no cover
            _logger.warning("OriginalFormioPublicController._api_get_data could not be imported. Fallback called.")
            return json.dumps([])

# --- ADDING IMPORT FOR PORTAL CONTROLLER ---
try:
    from odoo.addons.formio.controllers.portal import FormioCustomerPortal as OriginalFormioCustomerPortal
except ImportError:
    _logger.error("Failed to import OriginalFormioCustomerPortal from odoo.addons.formio.controllers.portal. Using fallback.")
    class OriginalFormioCustomerPortal(http.Controller):
        def _api_get_data(self, builder_name, **kwargs): return json.dumps([]) # pragma: no cover
# --- END ADDING IMPORT FOR PORTAL CONTROLLER ---

class GeonamesDataFetcher:
    """
    Helper class to encapsulate Geonames API interaction.
    """
    def _fetch_geonames_data_results(self, search_query, username='azerila'):
        """
        Fetches data from Geonames API based on the search query.

        :param search_query: The term to search for.
        :param username: Your Geonames username.
        :return: A list of dictionaries, where each dictionary has 'value' and 'label'.
        """
        if not search_query:
            _logger.info("GEONAMES_FETCHER: No search query provided.")
            return []

        api_url = "http://api.geonames.org/searchJSON"
        geonames_params = {
            'name_startsWith': search_query,
            'maxRows': 15,
            'featureClass': 'P',  # Populated places (cities, villages)
            'style': 'MEDIUM',
            'username': username,
        }
        
        results = []
        try:
            _logger.info(f"GEONAMES_FETCHER: Requesting Geonames. Params: {json.dumps(geonames_params)}")
            api_response = requests.get(api_url, params=geonames_params, timeout=10)
            api_response.raise_for_status()  # Raise an HTTPError for bad responses (4xx or 5xx)
            response_data = api_response.json()

            # Check if Geonames returned an error status within the JSON itself
            if 'status' in response_data and response_data.get('geonames') is None:
                error_message = response_data['status'].get('message', 'Unknown Geonames API error')
                _logger.error(f"GEONAMES_FETCHER: Geonames API returned an error. Message: {error_message}")
            else:
                geonames_entries = response_data.get('geonames', [])
                for item in geonames_entries:
                    name = item.get('name')
                    country_name = item.get('countryName')
                    geoname_id = item.get('geonameId')
                    
                    if name and geoname_id:
                        label_parts = [name]
                        if country_name:
                            label_parts.append(country_name)
                        display_label = ", ".join(filter(None, label_parts))
                        results.append({
                            'value': str(geoname_id), 
                            'label': display_label
                        })
                _logger.info(f"GEONAMES_FETCHER: Processed {len(results)} results for search term '{search_query}'.")
        
        except requests.exceptions.Timeout:
            _logger.error(f"GEONAMES_FETCHER: Timeout error fetching data from Geonames for term '{search_query}'.")
        except requests.exceptions.RequestException as e:
            _logger.error(f"GEONAMES_FETCHER: Network or HTTP error for term '{search_query}': {str(e)}")
        except json.JSONDecodeError as e:
            _logger.error(f"GEONAMES_FETCHER: Error decoding JSON response from Geonames for term '{search_query}': {str(e)}")
        except Exception as e:
            _logger.error(f"GEONAMES_FETCHER: An unexpected error occurred for term '{search_query}': {type(e).__name__} - {str(e)}")
        
        return results

class CustomFormioControllerOverride(OriginalFormioController, GeonamesDataFetcher):
    """
    Overrides the FormioController to handle custom Geonames API requests.
    This controller is typically used for authenticated users.
    """

    def _api_get_data(self, builder_or_form_uuid_or_object, **kwargs):
        """
        Overrides the method responsible for fetching data for Formio components.
        If a specific set of parameters indicates a Geonames request, it fetches data
        from Geonames API. Otherwise, it calls the original method.

        The signature of this method MUST match the original method in FormioController.
        The parameter `builder_or_form_uuid_or_object` can vary based on odoo-formio version
        (it could be a builder object, a form UUID string, or a form object).
        """
        args = request.httprequest.args
        _logger.info(f"CUSTOM_FORMIO_OVERRIDE (Main): _api_get_data called. Args: {args}")

        # Check for our custom parameters to identify a Geonames request
        if args.get('model') == 'custom.geonames.api' and args.get('geonames_request') == 'true':
            search_query = args.get('search_query_param') # Parameter name defined in Form.io component's data.url
            _logger.info(f"CUSTOM_FORMIO_OVERRIDE (Main): Geonames request identified. Search query: {search_query}")
            
            geonames_results = self._fetch_geonames_data_results(search_query)
            return json.dumps(geonames_results) # Must return a JSON string
        else:
            _logger.info("CUSTOM_FORMIO_OVERRIDE (Main): Not a Geonames request, calling super().")
            # Call the original _api_get_data method
            # The way to call super depends on how OriginalFormioController was imported and its MRO
            try:
                # This super call assumes that 'builder_or_form_uuid_or_object' is the correct first argument
                # for the original _api_get_data method. This needs careful verification against odoo-formio's code.
                res = super(CustomFormioControllerOverride, self)._api_get_data(builder_or_form_uuid_or_object, **kwargs)
                return res if res is not None else json.dumps([])
            except Exception as e:
                _logger.error(f"CUSTOM_FORMIO_OVERRIDE (Main): Error calling super()._api_get_data: {e}. Args were: {builder_or_form_uuid_or_object}, {kwargs}")
                return json.dumps([])


class CustomFormioPublicControllerOverride(OriginalFormioPublicController, GeonamesDataFetcher):
    """
    Overrides the FormioPublicController for public-facing forms.
    """

    def _api_get_data(self, builder, **kwargs):
        """
        Overrides the method for public forms.
        The signature of this method MUST match the original method in FormioPublicController.
        The original FormioPublicController._api_get_data often takes `builder` as the first argument.
        """
        args = request.httprequest.args
        _logger.info(f"CUSTOM_FORMIO_OVERRIDE (Public): _api_get_data called. Args: {args}, Builder ID: {builder.id if builder else 'N/A'}")
        
        if args.get('model') == 'custom.geonames.api' and args.get('geonames_request') == 'true':
            search_query = args.get('search_query_param')
            _logger.info(f"CUSTOM_FORMIO_OVERRIDE (Public): Geonames request identified. Search query: {search_query}")
            geonames_results = self._fetch_geonames_data_results(search_query)
            return json.dumps(geonames_results)
        else:
            _logger.info("CUSTOM_FORMIO_OVERRIDE (Public): Not a Geonames request, calling super().")
            try:
                # This super call assumes `builder` is the correct first argument.
                res = super(CustomFormioPublicControllerOverride, self)._api_get_data(builder, **kwargs)
                return res if res is not None else json.dumps([])
            except Exception as e:
                _logger.error(f"CUSTOM_FORMIO_OVERRIDE (Public): Error calling super()._api_get_data: {e}. Args were: {builder}, {kwargs}")
                return json.dumps([]) 

# --- ADDING PORTAL CONTROLLER OVERRIDE ---
class CustomFormioCustomerPortalOverride(OriginalFormioCustomerPortal, GeonamesDataFetcher):
    """
    Overrides the FormioCustomerPortal to handle custom Geonames API requests for portal forms.
    """
    def _api_get_data(self, builder_name, **kwargs): # Signature matches the original from portal.py
        """
        Overrides the method responsible for fetching data for Formio components in the portal.
        If a specific set of parameters indicates a Geonames request, it fetches data
        from Geonames API. Otherwise, it calls the original method.
        """
        args = request.httprequest.args
        _logger.info(f"CUSTOM_OVERRIDE (Portal): _api_get_data called. Builder Name: {builder_name}, Args: {args}")

        if args.get('model') == 'custom.geonames.api' and args.get('geonames_request') == 'true':
            search_query = args.get('search_query_param')
            _logger.info(f"CUSTOM_OVERRIDE (Portal): Geonames request identified. Search Query: {search_query}")
            geonames_results = self._fetch_geonames_data_results(search_query)
            return json.dumps(geonames_results) # Must return a JSON string
        else:
            _logger.info("CUSTOM_OVERRIDE (Portal): Not a Geonames request, calling super().")
            try:
                # Call the original _api_get_data method from FormioCustomerPortal
                res = super(CustomFormioCustomerPortalOverride, self)._api_get_data(builder_name, **kwargs)
                return res if res is not None else json.dumps([])
            except Exception as e:
                _logger.error(f"CUSTOM_OVERRIDE (Portal): Error calling super()._api_get_data: {e}. Args were: builder_name={builder_name}, kwargs={kwargs}")
                return json.dumps([])
# --- END ADDING PORTAL CONTROLLER OVERRIDE --- 