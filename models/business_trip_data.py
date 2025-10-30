# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from datetime import datetime, date, timedelta
from odoo.exceptions import ValidationError, UserError
import logging
import json

_logger = logging.getLogger(__name__)

class BusinessTripData(models.Model):
    _name = 'business.trip.data'
    _description = 'Business Trip Form Data'
    _rec_name = 'full_name'
    
    # Link back to the main business trip model
    form_id = fields.Many2one('business.trip', string='Business Trip Form', ondelete='cascade', index=True)
    form_title = fields.Char(string='Form Title', related='form_id.name', store=True, readonly=True)
    active = fields.Boolean(default=True)
    
    # Personal information fields
    # Modified by A_zeril_A, 2025-10-20: Changed from compute fields to regular fields after formio removal
    first_name = fields.Char(string='First Name')
    last_name = fields.Char(string='Last Name')
    full_name = fields.Char(string='Full Name', compute='_compute_full_name', store=True)
    
        # Trip approval and type fields
    trip_duration_type = fields.Selection([
        ('days', 'Daily Trip'),
        ('weeks', 'Short Trip (Up to one week)'),
        ('short', 'Intermediate Trip (Up to three months)'),
        ('long', 'Long Trip (More than three months)')
    ], string='Trip Duration Type', help="Category that best fits the trip duration")

    trip_type = fields.Selection([
        ('oneWay', 'One Way'),
        ('twoWay', 'Two Way')
    ], string='Trip Type', default='oneWay', help="Indicates if the trip is one-way or two-way")
    
    # Accommodation fields
    accommodation_needed = fields.Selection([
        ('yes', 'Yes'),
        ('no', 'No')
    ], string='Accommodation Needed', default='no', help="Indicates if accommodation arrangements are required for this trip")
    accommodation_number_of_people = fields.Integer(string='Number of People', help="Total number of people requiring accommodation")
    accommodation_residence_city = fields.Char(string='Residence City', help="City of residence of the traveler")
    accommodation_check_in_date = fields.Date(string='Check-in Date', help="Planned accommodation check-in date")
    accommodation_check_out_date = fields.Date(string='Check-out Date', help="Planned accommodation check-out date")
    accommodation_points_of_interest = fields.Text(string='Points of Interest', help="Points of interest or other information relevant for accommodation selection")
    accommodation_need_24h_reception = fields.Selection([
        ('yes', 'Yes'),
        ('no', 'No')
    ], string='Need 24h Reception', help="Indicates if 24-hour reception is required")
    
    # One2many field for accompanying persons
    accompanying_person_ids = fields.One2many('accompanying.person', 'business_trip_id', string='Accompanying Persons')
    
    # Transport means fields
    use_rental_car = fields.Boolean(string='Rental Car', default=False)
    use_company_car = fields.Boolean(string='Company Car', default=False)
    use_personal_car = fields.Boolean(string='Personal Car', default=False)
    use_train = fields.Boolean(string='Train', default=False)
    use_airplane = fields.Boolean(string='Airplane', default=False)
    use_bus = fields.Boolean(string='Bus', default=False)
    transport_means_json = fields.Text(string='Transport Means (JSON)', help="JSON representation of selected transport means")
    
    # Return transport means fields (for two-way trips)
    use_return_rental_car = fields.Boolean(string='Return Rental Car', default=False)
    use_return_company_car = fields.Boolean(string='Return Company Car', default=False)
    use_return_personal_car = fields.Boolean(string='Return Personal Car', default=False)
    use_return_train = fields.Boolean(string='Return Train', default=False)
    use_return_airplane = fields.Boolean(string='Return Airplane', default=False)
    use_return_bus = fields.Boolean(string='Return Bus', default=False)
    return_transport_means_json = fields.Text(string='Return Transport Means (JSON)', help="JSON representation of selected return transport means")
    
    # Rental car information fields
    rental_car_pickup_date = fields.Date(string='Rental Car Pickup Date')
    rental_car_pickup_flexible = fields.Boolean(string='Pickup Flexible', default=False)
    rental_car_pickup_point = fields.Char(string='Pickup Point')
    rental_car_dropoff_point = fields.Char(string='Dropoff Point')
    rental_car_dropoff_date = fields.Date(string='Rental Car Dropoff Date')
    rental_car_dropoff_flexible = fields.Boolean(string='Dropoff Flexible', default=False)
    rental_car_credit_card = fields.Selection([
        ('yes', 'Yes'),
        ('no', 'No')
    ], string='Credit Card Available')
    rental_car_type = fields.Selection([
        ('ncc', 'Rental with driver (NCC)'),
        ('self', 'You drive')
    ], string='Rental Type')
    rental_car_drivers_license = fields.Binary(string='Driver\'s License', attachment=True)
    rental_car_drivers_license_filename = fields.Char(string='Driver\'s License Filename')
    rental_car_drivers_license_attachment_id = fields.Many2one('ir.attachment', string='Driver\'s License Attachment')
    rental_car_kilometer_limit = fields.Integer(string='Kilometer Limit')
    rental_car_unlimited_km = fields.Boolean(string='Unlimited Kilometers', default=False)
    rental_car_preferences = fields.Text(string='Rental Car Preferences', 
                                       help="Additional preferences for rental car, such as pick-up time, car model, GPS, child seat, etc.")
    
    # Return rental car information fields
    return_rental_car_pickup_date = fields.Date(string='Return Rental Car Pickup Date')
    return_rental_car_pickup_flexible = fields.Boolean(string='Return Pickup Flexible', default=False)
    return_rental_car_pickup_point = fields.Char(string='Return Pickup Point')
    return_rental_car_dropoff_point = fields.Char(string='Return Dropoff Point')
    return_rental_car_dropoff_date = fields.Date(string='Return Rental Car Dropoff Date')
    return_rental_car_dropoff_flexible = fields.Boolean(string='Return Dropoff Flexible', default=False)
    return_rental_car_credit_card = fields.Selection([
        ('yes', 'Yes'),
        ('no', 'No')
    ], string='Return Credit Card Available')
    return_rental_car_type = fields.Selection([
        ('ncc', 'Rental with driver (NCC)'),
        ('self', 'You drive')
    ], string='Return Rental Type')
    return_rental_car_drivers_license = fields.Binary(string='Return Driver\'s License', attachment=True)
    return_rental_car_drivers_license_filename = fields.Char(string='Return Driver\'s License Filename')
    return_rental_car_drivers_license_attachment_id = fields.Many2one('ir.attachment', string='Return Driver\'s License Attachment')
    return_rental_car_kilometer_limit = fields.Integer(string='Return Kilometer Limit')
    return_rental_car_unlimited_km = fields.Boolean(string='Return Unlimited Kilometers', default=False)
    return_rental_car_preferences = fields.Text(string='Return Rental Car Preferences', 
                                            help="Additional preferences for return rental car, such as pick-up time, car model, GPS, child seat, etc.")
    
    # Download URLs for driver's licenses
    rental_car_drivers_license_download_url = fields.Char(string="Driver's License URL (Technical)", compute='_compute_download_urls')
    return_rental_car_drivers_license_download_url = fields.Char(string="Return Driver's License URL (Technical)", compute='_compute_download_urls')
    
    # HTML link for driver's licenses
    rental_car_drivers_license_download_link_html = fields.Html(string="Driver's License Download", compute='_compute_download_link_html', sanitize=False)
    return_rental_car_drivers_license_download_link_html = fields.Html(string="Return Driver's License Download", compute='_compute_download_link_html', sanitize=False)

    # HTML for accompanying persons
    accompanying_persons_html = fields.Html(string="Accompanying Persons List", compute='_compute_accompanying_persons_html', sanitize=False)

    # Train information fields
    train_departure_city = fields.Char(string='Train Departure City')
    train_departure_station = fields.Char(string='Train Departure Station')
    train_arrival_station = fields.Char(string='Train Arrival Station')
    train_departure_date = fields.Date(string='Train Departure Date')
    train_departure_flexible = fields.Boolean(string='Train Departure Flexible', default=False)
    train_arrival_date = fields.Date(string='Train Arrival Date')
    train_arrival_flexible = fields.Boolean(string='Train Arrival Flexible', default=False)
    
    # Return train information fields
    return_train_departure_city = fields.Char(string='Return Train Departure City')
    return_train_departure_station = fields.Char(string='Return Train Departure Station')
    return_train_arrival_station = fields.Char(string='Return Train Arrival Station')
    return_train_departure_date = fields.Date(string='Return Train Departure Date')
    return_train_departure_flexible = fields.Boolean(string='Return Train Departure Flexible', default=False)
    return_train_arrival_date = fields.Date(string='Return Train Arrival Date')
    return_train_arrival_flexible = fields.Boolean(string='Return Train Arrival Flexible', default=False)
    
    # Return airplane information fields
    return_airplane_departure_airport = fields.Char(string='Return Departure Airport')
    return_airplane_departure_date = fields.Date(string='Return Airplane Departure Date')
    return_airplane_departure_flexible = fields.Boolean(string='Return Airplane Departure Flexible', default=False)
    return_airplane_destination_airport = fields.Char(string='Return Destination Airport')
    return_airplane_destination_date = fields.Date(string='Return Airplane Destination Date')
    return_airplane_destination_flexible = fields.Boolean(string='Return Airplane Destination Flexible', default=False)
    return_airplane_baggage_type = fields.Selection([
        ('no', 'No baggage / Small Bag'),
        ('medium', 'Medium'),
        ('large', 'Large'),
        ('checked', 'Checked Baggage')
    ], string='Return Baggage Type')
    return_airplane_preferences = fields.Text(string='Return Airplane Preferences',
                                            help="Additional preferences for return airplane travel, such as seat preference, preferred time, etc.")
    
    # Return bus information fields
    return_bus_departure_city = fields.Char(string='Return Bus Departure City')
    return_bus_departure_station = fields.Char(string='Return Bus Departure Station')
    return_bus_arrival_station = fields.Char(string='Return Bus Arrival Station')
    return_bus_departure_date = fields.Date(string='Return Bus Departure Date')
    return_bus_departure_flexible = fields.Boolean(string='Return Bus Departure Flexible', default=False)
    return_bus_arrival_date = fields.Date(string='Return Bus Arrival Date')
    return_bus_arrival_flexible = fields.Boolean(string='Return Bus Arrival Flexible', default=False)
    
    # Bus information fields
    bus_departure_city = fields.Char(string='Bus Departure City')
    bus_departure_terminal = fields.Char(string='Bus Departure Terminal')
    bus_arrival_terminal = fields.Char(string='Bus Arrival Terminal')
    bus_departure_date = fields.Date(string='Bus Departure Date')
    bus_departure_flexible = fields.Boolean(string='Bus Departure Flexible', default=False)
    bus_arrival_date = fields.Date(string='Bus Arrival Date')
    bus_arrival_flexible = fields.Boolean(string='Bus Arrival Flexible', default=False)
    
    # Airplane information fields
    airplane_departure_airport = fields.Char(string='Departure Airport')
    airplane_departure_date = fields.Date(string='Airplane Departure Date')
    airplane_departure_flexible = fields.Boolean(string='Airplane Departure Flexible', default=False)
    airplane_arrival_airport = fields.Char(string='Arrival Airport')
    airplane_arrival_date = fields.Date(string='Airplane Arrival Date')
    airplane_arrival_flexible = fields.Boolean(string='Airplane Arrival Flexible', default=False)
    airplane_baggage_type = fields.Selection([
        ('no', 'No baggage / Small Bag'),
        ('medium', 'Medium'),
        ('large', 'Large'),
        ('checked', 'Checked Baggage')
    ], string='Baggage Type')
    airplane_preferences = fields.Text(string='Airplane Preferences',
                                      help="Additional preferences for airplane travel, such as seat preference, preferred time, etc.")
    
    # Basic trip information fields
    destination = fields.Char(string='Destination')
    purpose = fields.Char(string='Purpose of Trip') # Removed compute='_compute_purpose', store=True
    travel_start_date = fields.Date(string='Start Date')
    travel_end_date = fields.Date(string='End Date')
    manual_travel_duration = fields.Float(string='Manual Travel Duration', help="Travel duration manually set from the trip details wizard")
    expected_cost = fields.Float(string='Expected Cost', help="Initial expected cost by employee")
    currency_id = fields.Many2one('res.currency', string='Currency', 
                                 default=lambda self: self.env.company.currency_id.id)
    
    @api.depends('rental_car_drivers_license_attachment_id', 'return_rental_car_drivers_license_attachment_id')
    def _compute_download_urls(self):
        for record in self:
            base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
            if record.rental_car_drivers_license_attachment_id:
                record.rental_car_drivers_license_download_url = f"{base_url}/web/content/{record.rental_car_drivers_license_attachment_id.id}?download=true"
            else:
                record.rental_car_drivers_license_download_url = False
            
            if record.return_rental_car_drivers_license_attachment_id:
                record.return_rental_car_drivers_license_download_url = f"{base_url}/web/content/{record.return_rental_car_drivers_license_attachment_id.id}?download=true"
            else:
                record.return_rental_car_drivers_license_download_url = False

    @api.depends('rental_car_drivers_license_download_url', 'return_rental_car_drivers_license_download_url')
    def _compute_download_link_html(self):
        for record in self:
            if record.rental_car_drivers_license_download_url:
                record.rental_car_drivers_license_download_link_html = f'<a href="{record.rental_car_drivers_license_download_url}" title="Download"><i class="fa fa-download"></i></a>'
            else:
                record.rental_car_drivers_license_download_link_html = False
            
            if record.return_rental_car_drivers_license_download_url:
                record.return_rental_car_drivers_license_download_link_html = f'<a href="{record.return_rental_car_drivers_license_download_url}" title="Download"><i class="fa fa-download"></i></a>'
            else:
                record.return_rental_car_drivers_license_download_link_html = False

    def _compute_accompanying_persons_html(self):
        for record in self:
            if not record.accompanying_person_ids:
                record.accompanying_persons_html = False
                continue

            html_parts = []
            for i, person in enumerate(record.accompanying_person_ids, 1):
                person_name = person.full_name or ''
                download_link = person.identity_document_download_link_html or ''

                # Using a structure that mimics a group of two fields
                person_block = (
                    f'<div style="display: contents;">'
                    f'    <div class="o_form_label" style="font-weight: bold;">Person {i}</div>'
                    f'    <div style="padding-top: 4px; padding-bottom: 4px;">{person_name}</div>'
                    f'    <div class="o_form_label">Identity Document</div>'
                    f'    <div style="padding-top: 4px; padding-bottom: 4px;">{download_link or "No document"}</div>'
                    f'</div>'
                )
                html_parts.append(person_block)
            
            # The outer element is a grid container that mimics Odoo's form group layout
            record.accompanying_persons_html = (
                '<div style="display: grid; grid-template-columns: max-content 1fr; gap: 1px 8px; align-items: center;">'
                f'{"".join(html_parts)}</div>'
            )

    @api.depends('first_name', 'last_name')
    def _compute_full_name(self):
        for record in self:
            names = []
            if record.first_name:
                names.append(record.first_name)
            if record.last_name:
                names.append(record.last_name)
            record.full_name = ' '.join(names) if names else False
    
    def process_submission_data(self, submission_data):
        _logger.info(f"BTD_PROCESS: Starting process_submission_data for BusinessTripData ID: {self.id}")

        if not submission_data or not isinstance(submission_data, dict):
            _logger.warning(f"BTD_PROCESS: No submission data provided or not a dict for BTD ID: {self.id}. Type: {type(submission_data)}")
            return False

        data_root = submission_data
        nested_data = submission_data.get('data', {})

        # initial, empty call and should not be processed.
        # We check if there are any keys other than the defaults to decide if it's a real submission.
        meaningful_keys = [k for k in data_root if k not in ['data', 'submit', 'form_id', 'state']]
        if not meaningful_keys:
            _logger.info(f"BTD_PROCESS: Skipping processing for BTD ID: {self.id}. "
                         f"No meaningful submission data found. "
                         f"Assuming initial call during creation. Data: {submission_data}")
            return False
        
        vals = {}
        # The entire submission_data is the root
         # Get the nested 'data' object, if it exists

        _logger.info(f"BTD_PROCESS: Root keys: {list(data_root.keys())}")
        if 'data' in data_root:
            _logger.info(f"BTD_PROCESS: Nested 'data' keys: {list(nested_data.keys())}")
        else:
            _logger.info("BTD_PROCESS: No nested 'data' key in submission_data.")

        # Personal Information - Prioritize root, then nested 'data'
        vals['first_name'] = self._extract_field_value(data_root, nested_data, 'first_name', 'first_name', default_value="")
        vals['last_name'] = self._extract_field_value(data_root, nested_data, 'last_name', 'last_name', default_value="")


        # Trip approval and type fields - Prioritize root, then nested 'data'
        vals['trip_duration_type'] = self._extract_field_value(data_root, nested_data, 'trip_duration_type', 'trip_duration_type')
        vals['trip_type'] = self._extract_field_value(data_root, nested_data, 'trip_type', 'trip_type')
        
        # Basic Trip Information - Now extracting from Form.io submission
        _logger.info("BTD_PROCESS: Extracting destination and travel dates from Form.io submission data.")
        
        # Destination - using the new field key from form
        vals['destination'] = self._extract_field_value(data_root, nested_data, 'trip_destination_portal_query_params', 'trip_destination_portal_query_params', default_value="")
        
        # Purpose - No longer extracted directly from Form.io, it's computed.
        # vals['purpose'] = self._extract_field_value(data_root, nested_data, 'trip_purpose', 'trip_purpose', default_value="") # MODIFIED: Commented out/Removed
        
        # Travel dates - using the new field keys from form
        vals['travel_start_date'] = self._extract_field_value(data_root, nested_data, 'trip_start_date', 'trip_start_date', is_date=True)
        vals['travel_end_date'] = self._extract_field_value(data_root, nested_data, 'trip_end_date', 'trip_end_date', is_date=True)
        
        # Accommodation fields - Prioritize root, then nested 'data'
        vals['accommodation_needed'] = self._extract_field_value(data_root, nested_data, 'accommodation_needed', 'accommodation_needed')
        # Use the extracted value for the condition directly
        accommodation_is_needed = vals['accommodation_needed'] == 'yes'

        if accommodation_is_needed:
            _logger.info(f"BTD_PROCESS: Accommodation is needed. Extracting details based on extracted value.")
            vals['accommodation_number_of_people'] = self._extract_field_value(data_root, nested_data, 'number_of_people', 'number_of_people', is_integer=True) # Corrected key from form
            vals['accommodation_residence_city'] = self._extract_field_value(data_root, nested_data, 'residence_city', 'residence_city') # Corrected key from form
            vals['accommodation_check_in_date'] = self._extract_field_value(data_root, nested_data, 'check_in_date', 'check_in_date', is_date=True) # Corrected key from form
            vals['accommodation_check_out_date'] = self._extract_field_value(data_root, nested_data, 'check_out_date', 'check_out_date', is_date=True) # Corrected key from form
            vals['accommodation_points_of_interest'] = self._extract_field_value(data_root, nested_data, 'points_of_interest', 'points_of_interest') # Corrected key from form
            vals['accommodation_need_24h_reception'] = self._extract_field_value(data_root, nested_data, 'need_24h_reception', 'need_24h_reception') # Corrected key from form
        else:
            _logger.info(f"BTD_PROCESS: Accommodation is NOT needed or value is '{vals.get('accommodation_needed')}'. Skipping accommodation detail extraction.")
            # Clear accommodation details if accommodation_needed is 'no' or not set
            vals['accommodation_number_of_people'] = 0
            vals['accommodation_residence_city'] = ""
            vals['accommodation_check_in_date'] = None
            vals['accommodation_check_out_date'] = None
            vals['accommodation_points_of_interest'] = ""
            vals['accommodation_need_24h_reception'] = ""

        # Accompanying Persons
        # Check for different possible structures:
        # 1. Array of person objects: 'accompanying_persons_panel': [{'full_name_acc': 'Name', 'accompanying_identity_document_acc': 'base64data', 'accompanying_identity_document_acc_filename': 'name.pdf'}, ...]
        # 2. Simple structure with number_of_people and accompanying_identity_document
        
        accompanying_persons_data = None
        possible_keys = ['accompanying_persons_panel', 'accompanyingPersons', 'accompanying_persons']
        for key in possible_keys:
            if key in data_root and isinstance(data_root[key], list):
                accompanying_persons_data = data_root[key]
                _logger.info(f"BTD_PROCESS: Found accompanying persons data under root key '{key}'. Count: {len(accompanying_persons_data)}")
                break
            elif key in nested_data and isinstance(nested_data[key], list): # Fallback to nested if not in root
                accompanying_persons_data = nested_data[key]
                _logger.info(f"BTD_PROCESS: Found accompanying persons data under nested key 'data.{key}'. Count: {len(accompanying_persons_data)}")
                break
        
        # Clear existing persons before adding new ones to avoid duplicates on re-submission
        self.accompanying_person_ids.unlink()
        persons_to_create = []
        
        if accompanying_persons_data:
            # Process array of person objects
            for person_data in accompanying_persons_data:
                if not isinstance(person_data, dict):
                    _logger.warning(f"BTD_PROCESS: Skipping accompanying person item, not a dict: {person_data}")
                    continue

                full_name = person_data.get('full_name_acc') or person_data.get('fullName')
                doc_data_field = person_data.get('accompanying_identity_document_acc') # This is the form.io file field name
                doc_filename_field = person_data.get('accompanying_identity_document_acc_filename') # This is the derived filename field

                # If the file field itself contains a list of file info dicts (common for Form.io file components)
                doc_base64 = None
                doc_filename = None

                if isinstance(doc_data_field, list) and doc_data_field:
                    # Take the first file if multiple are somehow uploaded to a single component instance
                    file_info = doc_data_field[0]
                    if isinstance(file_info, dict):
                        doc_base64 = file_info.get('storage') == 'base64' and file_info.get('base64', '').split(',')[-1]
                        doc_filename = file_info.get('name')
                elif isinstance(doc_data_field, str) and doc_data_field.startswith('data:'): # Direct base64 string
                     doc_base64 = doc_data_field.split(',')[-1]
                     doc_filename = doc_filename_field # Use the separate filename field if main field is direct base64

                if full_name:
                    person_vals = {
                        'full_name': full_name,
                    }
                    if doc_base64 and doc_filename:
                        try:
                            person_vals['identity_document'] = doc_base64
                            person_vals['identity_document_filename'] = doc_filename
                            _logger.info(f"BTD_PROCESS: Prepared accompanying person '{full_name}' with document '{doc_filename}'.")
                        except Exception as e:
                             _logger.error(f"BTD_PROCESS: Error decoding base64 for accompanying person '{full_name}', document '{doc_filename}': {e}")
                    else:
                        _logger.info(f"BTD_PROCESS: Prepared accompanying person '{full_name}' without document (data missing or not base64).")
                    
                    persons_to_create.append((0, 0, person_vals))
        else:
            # Check for simple structure with number_of_people and accompanying_identity_document
            number_of_people = self._extract_field_value(data_root, nested_data, 'number_of_people', 'number_of_people', is_integer=True)
            accompanying_doc = self._extract_field_value(data_root, nested_data, 'accompanying_identity_document', 'accompanying_identity_document')
            
            if number_of_people and number_of_people > 1:  # More than 1 person means there are accompanying persons
                _logger.info(f"BTD_PROCESS: Found {number_of_people} people in trip, creating {number_of_people - 1} accompanying persons")
                
                # Process accompanying document if exists
                doc_base64 = None
                doc_filename = None
                attachment_id = None
                
                # The extracted value can be a string representation of a JSON list, so we need to parse it.
                accompanying_doc_list = []
                if isinstance(accompanying_doc, str):
                    try:
                        accompanying_doc_list = json.loads(accompanying_doc)
                    except json.JSONDecodeError:
                        _logger.warning(f"Could not decode JSON from accompanying_identity_document: {accompanying_doc}")
                elif isinstance(accompanying_doc, list):
                    accompanying_doc_list = accompanying_doc

                if accompanying_doc_list and accompanying_doc_list[0]:
                    file_info = accompanying_doc_list[0]
                    if isinstance(file_info, dict):
                        doc_filename = file_info.get('originalName') or file_info.get('name')
                        storage_type = file_info.get('storage')

                        # We no longer need to read the base64 data, just get the attachment_id
                        if storage_type == 'url':
                            attachment_id = file_info.get('data', {}).get('result', {}).get('attachment_id')
                        
                        _logger.info(f"BTD_PROCESS: Found accompanying document: {doc_filename}, storage: {storage_type}, attachment_id: {attachment_id}")

                # Extract accompanying person's name from JSON
                # In the JSON structure, full_name appears to be the accompanying person's name
                # while first_name and last_name are for the main traveler
                accompanying_full_name = self._extract_field_value(data_root, nested_data, 'full_name', 'full_name')
                _logger.info(f"BTD_PROCESS: Extracted accompanying person full_name: '{accompanying_full_name}'")
                
                # Create accompanying persons (number_of_people - 1, excluding the main traveler)
                for i in range(number_of_people - 1):
                    # Use the extracted name if available, otherwise use a default name
                    person_name = accompanying_full_name if accompanying_full_name else f'Accompanying Person {i + 1}'
                    _logger.info(f"BTD_PROCESS: Creating accompanying person {i + 1} with name: '{person_name}'")
                    
                    person_vals = {
                        'full_name': person_name,
                    }
                    
                    # Add document to the first accompanying person if available
                    if i == 0 and doc_filename:
                        if attachment_id:
                            person_vals['identity_document_attachment_id'] = attachment_id
                        person_vals['identity_document_filename'] = doc_filename
                        _logger.info(f"BTD_PROCESS: Added document '{doc_filename}' to accompanying person '{person_name}'")
                    
                    persons_to_create.append((0, 0, person_vals))
                    
        if persons_to_create:
            vals['accompanying_person_ids'] = persons_to_create
            _logger.info(f"BTD_PROCESS: Creating/updating {len(persons_to_create)} accompanying persons.")
        else:
            _logger.info("BTD_PROCESS: No accompanying persons data found in submission.")


        # Transport Means - Expected at root, e.g., 'means_of_transport': {'train': true, 'airplane': false}
        # Or direct boolean flags like 'use_train', 'use_airplane'
        transport_means_val = None
        if 'means_of_transport' in data_root and isinstance(data_root['means_of_transport'], dict):
            transport_means_val = data_root['means_of_transport']
            _logger.info(f"BTD_PROCESS: Found 'means_of_transport' (dict) at root: {transport_means_val}")
        elif 'means_of_transport' in nested_data and isinstance(nested_data['means_of_transport'], dict): # Fallback
            transport_means_val = nested_data['means_of_transport']
            _logger.info(f"BTD_PROCESS: Found 'means_of_transport' (dict) in nested 'data': {transport_means_val}")

        if transport_means_val:
            vals['use_rental_car'] = bool(transport_means_val.get('rental_car', False))
            vals['use_company_car'] = bool(transport_means_val.get('company_car', False))
            vals['use_personal_car'] = bool(transport_means_val.get('personal_car', False))
            vals['use_train'] = bool(transport_means_val.get('train', False))
            vals['use_airplane'] = bool(transport_means_val.get('airplane', False))
            vals['use_bus'] = bool(transport_means_val.get('bus', False))
            vals['transport_means_json'] = json.dumps(transport_means_val)
        else: # Check for individual boolean flags if 'means_of_transport' dict is not found
            _logger.info("BTD_PROCESS: 'means_of_transport' (dict) not found. Checking for individual boolean transport flags (e.g., 'airplane', 'train') at root/nested.")
            direct_transport_flags = {}
            possible_transport_keys = ['airplane', 'train', 'bus', 'rental_car', 'company_car', 'personal_car']
            found_direct_flags = False
            for key in possible_transport_keys:
                val = self._extract_field_value(data_root, nested_data, key, key, is_boolean=True, default_value=False)
                # self._extract_field_value returns the value, not a dict.
                # We need to check if this value indicates selection.
                # Assuming if the key exists and is true-ish, it's selected.
                # The default_value=False handles cases where key isn't present.
                if key in data_root or key in nested_data: # Check if key was present to avoid adding all as False
                     direct_transport_flags[key] = val # val here will be True if selected, False otherwise
                     if val:
                         found_direct_flags = True
            
            if found_direct_flags:
                _logger.info(f"BTD_PROCESS: Found individual transport flags: {direct_transport_flags}")
                vals['use_rental_car'] = bool(direct_transport_flags.get('rental_car', False))
                vals['use_company_car'] = bool(direct_transport_flags.get('company_car', False))
                vals['use_personal_car'] = bool(direct_transport_flags.get('personal_car', False))
                vals['use_train'] = bool(direct_transport_flags.get('train', False))
                vals['use_airplane'] = bool(direct_transport_flags.get('airplane', False))
                vals['use_bus'] = bool(direct_transport_flags.get('bus', False))
                vals['transport_means_json'] = json.dumps(direct_transport_flags) # Store the collected flags
            else:
                _logger.info("BTD_PROCESS: No individual transport flags found either.")
                # Ensure fields are reset if no data found
                vals['use_rental_car'] = False
                vals['use_company_car'] = False
                vals['use_personal_car'] = False
                vals['use_train'] = False
                vals['use_airplane'] = False
                vals['use_bus'] = False
                vals['transport_means_json'] = "{}"


        # Return Transport Means - Expected at root, e.g., 'return_means_of_transport': {'train': true}
        # Or direct boolean flags like 'use_return_train'
        return_transport_means_val = None
        if 'return_means_of_transport' in data_root and isinstance(data_root['return_means_of_transport'], dict):
            return_transport_means_val = data_root['return_means_of_transport']
            _logger.info(f"BTD_PROCESS: Found 'return_means_of_transport' (dict) at root: {return_transport_means_val}")
        elif 'return_means_of_transport' in nested_data and isinstance(nested_data['return_means_of_transport'], dict): # Fallback
            return_transport_means_val = nested_data['return_means_of_transport']
            _logger.info(f"BTD_PROCESS: Found 'return_means_of_transport' (dict) in nested 'data': {return_transport_means_val}")

        if return_transport_means_val:
            vals['use_return_rental_car'] = bool(return_transport_means_val.get('rental_car', False))
            vals['use_return_company_car'] = bool(return_transport_means_val.get('company_car', False))
            vals['use_return_personal_car'] = bool(return_transport_means_val.get('personal_car', False))
            vals['use_return_train'] = bool(return_transport_means_val.get('train', False))
            vals['use_return_airplane'] = bool(return_transport_means_val.get('airplane', False))
            vals['use_return_bus'] = bool(return_transport_means_val.get('bus', False))
            vals['return_transport_means_json'] = json.dumps(return_transport_means_val)
        else: # Check for individual boolean flags for return trip
            _logger.info("BTD_PROCESS: 'return_means_of_transport' (dict) not found. Checking for individual boolean return transport flags (e.g., 'return_airplane') at root/nested.")
            direct_return_transport_flags = {}
            possible_return_transport_keys = ['return_airplane', 'return_train', 'return_bus', 'return_rental_car', 'return_company_car', 'return_personal_car']
            found_direct_return_flags = False
            for key in possible_return_transport_keys:
                # The key in form (e.g., 'return_airplane') maps to a field in BTD (e.g., use_return_airplane)
                # We need to map the form key to the dict key for json_dumps
                simple_key = key.replace('return_', '') # 'airplane', 'train', etc.
                
                val = self._extract_field_value(data_root, nested_data, key, key, is_boolean=True, default_value=False)
                if key in data_root or key in nested_data: # Check if key was present
                    direct_return_transport_flags[simple_key] = val # Use simple_key for the JSON structure
                    if val:
                        found_direct_return_flags = True
            
            if found_direct_return_flags:
                _logger.info(f"BTD_PROCESS: Found individual return transport flags: {direct_return_transport_flags}")
                vals['use_return_rental_car'] = bool(direct_return_transport_flags.get('rental_car', False))
                vals['use_return_company_car'] = bool(direct_return_transport_flags.get('company_car', False))
                vals['use_return_personal_car'] = bool(direct_return_transport_flags.get('personal_car', False))
                vals['use_return_train'] = bool(direct_return_transport_flags.get('train', False))
                vals['use_return_airplane'] = bool(direct_return_transport_flags.get('airplane', False))
                vals['use_return_bus'] = bool(direct_return_transport_flags.get('bus', False))
                vals['return_transport_means_json'] = json.dumps(direct_return_transport_flags) # Store the collected flags
            else:
                _logger.info("BTD_PROCESS: No individual return transport flags found either.")
                # Ensure fields are reset if no data found
                vals['use_return_rental_car'] = False
                vals['use_return_company_car'] = False
                vals['use_return_personal_car'] = False
                vals['use_return_train'] = False
                vals['use_return_airplane'] = False
                vals['use_return_bus'] = False
                vals['return_transport_means_json'] = "{}"

        # Rental Car Information - Prioritize root, then nested 'data'
        if vals.get('use_rental_car'):
            _logger.info("BTD_PROCESS: Rental car is selected. Extracting details.")
            vals.update({
                'rental_car_pickup_date': self._extract_field_value(data_root, nested_data, 'pickup_date', 'pickup_date', is_date=True),
                'rental_car_pickup_flexible': self._extract_field_value(data_root, nested_data, 'pickup_flexible', 'pickup_flexible', is_boolean=True),
                'rental_car_pickup_point': self._extract_field_value(data_root, nested_data, 'pickup_point', 'pickup_point'),
                'rental_car_dropoff_point': self._extract_field_value(data_root, nested_data, 'dropoff_point', 'dropoff_point'),
                'rental_car_dropoff_date': self._extract_field_value(data_root, nested_data, 'dropoff_date', 'dropoff_date', is_date=True),
                'rental_car_dropoff_flexible': self._extract_field_value(data_root, nested_data, 'dropoff_flexible', 'dropoff_flexible', is_boolean=True),
                'rental_car_credit_card': self._extract_field_value(data_root, nested_data, 'credit_card_available', 'credit_card_available'),
                'rental_car_type': self._extract_field_value(data_root, nested_data, 'rental_type', 'rental_type'),
                'rental_car_kilometer_limit': self._extract_field_value(data_root, nested_data, 'kilometer_limit', 'kilometer_limit', is_integer=True),
                'rental_car_unlimited_km': self._extract_field_value(data_root, nested_data, 'unlimited_km', 'unlimited_km', is_boolean=True),
                'rental_car_preferences': self._extract_field_value(data_root, nested_data, 'car_additional_preferences', 'car_additional_preferences'),
            })

            # Handle driver's license file upload for rental car
            # The form uses 'drivers_license_file' as per the component JSON provided by the user
            license_data = self._extract_field_value(data_root, nested_data, 'drivers_license_file', 'drivers_license_file')
            if not license_data:
                # Fallback for other possible naming conventions
                _logger.info("BTD_PROCESS: 'drivers_license_file' not found, trying fallback 'drivers_license'.")
                license_data = self._extract_field_value(data_root, nested_data, 'drivers_license', 'drivers_license')
            if not license_data:
                 # Fallback for older form versions
                _logger.info("BTD_PROCESS: 'drivers_license' not found, trying fallback 'rental_car_drivers_license'.")
                license_data = self._extract_field_value(data_root, nested_data, 'rental_car_drivers_license', 'rental_car_drivers_license')

            if license_data and isinstance(license_data, list) and license_data[0]:
                file_info = license_data[0]
                if isinstance(file_info, dict):
                    if file_info.get('storage') == 'base64':
                        base64_data = None
                        # The base64 data can be in 'base64' key or in 'url' key for formio
                        if file_info.get('url') and file_info['url'].startswith('data:'):
                            base64_data = file_info['url'].split(',')[-1]
                        elif file_info.get('base64'):
                            base64_data = file_info['base64'].split(',')[-1]
                        
                        if base64_data:
                            vals['rental_car_drivers_license'] = base64_data
                            vals['rental_car_drivers_license_filename'] = file_info.get('originalName') or file_info.get('name')
                            _logger.info(f"BTD_PROCESS: Successfully extracted rental car drivers license: {vals['rental_car_drivers_license_filename']}")
                        else:
                            _logger.warning(f"BTD_PROCESS: Rental car license data found, but no base64 string in 'url' or 'base64' keys: {file_info}")
                    elif file_info.get('storage') == 'url':
                        # Handle URL-based uploads from our custom attachment controller
                        attachment_id = None
                        filename = None
                        
                        # Extract attachment_id from the data.result structure
                        if file_info.get('data', {}).get('result', {}).get('attachment_id'):
                            attachment_id = file_info['data']['result']['attachment_id']
                            filename = file_info.get('originalName') or file_info.get('name') or file_info['data']['result'].get('name')
                        
                        if attachment_id:
                            # Link to the existing attachment instead of storing base64 data
                            vals['rental_car_drivers_license_attachment_id'] = attachment_id
                            vals['rental_car_drivers_license_filename'] = filename
                            _logger.info(f"BTD_PROCESS: Successfully linked rental car drivers license attachment {attachment_id}: {filename}")
                        else:
                            _logger.warning(f"BTD_PROCESS: Rental car license with storage='url' found but no attachment_id: {file_info}")
                    else:
                        _logger.warning(f"BTD_PROCESS: Rental car license data found but unsupported storage type '{file_info.get('storage')}': {file_info}")
        else:
            _logger.info("BTD_PROCESS: Rental car is not selected. Skipping rental car detail extraction.")
            # Clear rental car fields if use_rental_car is False
            vals['rental_car_pickup_date'] = None
            vals['rental_car_pickup_flexible'] = False
            vals['rental_car_pickup_point'] = None
            vals['rental_car_dropoff_point'] = None
            vals['rental_car_dropoff_date'] = None
            vals['rental_car_dropoff_flexible'] = False
            vals['rental_car_credit_card'] = None
            vals['rental_car_type'] = None
            vals['rental_car_drivers_license'] = None
            vals['rental_car_drivers_license_filename'] = None
            vals['rental_car_drivers_license_attachment_id'] = None
            vals['rental_car_kilometer_limit'] = 0
            vals['rental_car_unlimited_km'] = False
            vals['rental_car_preferences'] = ""

        # Return Rental Car Information - Prioritize root, then nested 'data'
        if vals.get('use_return_rental_car'): # Only process if return rental car is selected
            _logger.info(f"BTD_PROCESS: Return rental car is selected. Extracting details.")
            vals['return_rental_car_pickup_date'] = self._extract_field_value(data_root, nested_data, 'return_rental_car_pickup_date', 'return_rental_car_pickup_date', is_date=True)
            vals['return_rental_car_pickup_flexible'] = self._extract_field_value(data_root, nested_data, 'return_rental_car_pickup_flexible', 'return_rental_car_pickup_flexible', is_boolean=True)
            vals['return_rental_car_pickup_point'] = self._extract_field_value(data_root, nested_data, 'return_rental_car_pickup_point', 'return_rental_car_pickup_point')
            vals['return_rental_car_dropoff_point'] = self._extract_field_value(data_root, nested_data, 'return_rental_car_dropoff_point', 'return_rental_car_dropoff_point')
            vals['return_rental_car_dropoff_date'] = self._extract_field_value(data_root, nested_data, 'return_rental_car_dropoff_date', 'return_rental_car_dropoff_date', is_date=True)
            vals['return_rental_car_dropoff_flexible'] = self._extract_field_value(data_root, nested_data, 'return_rental_car_dropoff_flexible', 'return_rental_car_dropoff_flexible', is_boolean=True)
            vals['return_rental_car_credit_card'] = self._extract_field_value(data_root, nested_data, 'return_rental_car_credit_card', 'return_rental_car_credit_card')
            vals['return_rental_car_type'] = self._extract_field_value(data_root, nested_data, 'return_rental_car_type', 'return_rental_car_type')
            
            # Handle driver's license file upload for return rental car
            return_license_data = self._extract_field_value(data_root, nested_data, 'return_rental_car_drivers_license', 'return_rental_car_drivers_license')
            
            if return_license_data and isinstance(return_license_data, list) and return_license_data[0]:
                file_info = return_license_data[0]
                if isinstance(file_info, dict):
                    if file_info.get('storage') == 'base64':
                        base64_data = None
                        if file_info.get('url') and file_info['url'].startswith('data:'):
                            base64_data = file_info['url'].split(',')[-1]
                        elif file_info.get('base64'):
                            base64_data = file_info['base64'].split(',')[-1]

                        if base64_data:
                            vals['return_rental_car_drivers_license'] = base64_data
                            vals['return_rental_car_drivers_license_filename'] = file_info.get('originalName') or file_info.get('name')
                            _logger.info(f"BTD_PROCESS: Successfully extracted return rental car drivers license: {vals['return_rental_car_drivers_license_filename']}")
                        else:
                            _logger.warning(f"BTD_PROCESS: Return rental car license data found, but no base64 string in 'url' or 'base64' keys: {file_info}")
                    elif file_info.get('storage') == 'url':
                        # Handle URL-based uploads from our custom attachment controller
                        attachment_id = None
                        filename = None
                        
                        # Extract attachment_id from the data.result structure
                        if file_info.get('data', {}).get('result', {}).get('attachment_id'):
                            attachment_id = file_info['data']['result']['attachment_id']
                            filename = file_info.get('originalName') or file_info.get('name') or file_info['data']['result'].get('name')
                        
                        if attachment_id:
                            # Link to the existing attachment instead of storing base64 data
                            vals['return_rental_car_drivers_license_attachment_id'] = attachment_id
                            vals['return_rental_car_drivers_license_filename'] = filename
                            _logger.info(f"BTD_PROCESS: Successfully linked return rental car drivers license attachment {attachment_id}: {filename}")
                        else:
                            _logger.warning(f"BTD_PROCESS: Return rental car license with storage='url' found but no attachment_id: {file_info}")
                    else:
                        _logger.warning(f"BTD_PROCESS: Return rental car license data found but unsupported storage type '{file_info.get('storage')}': {file_info}")

            vals['return_rental_car_kilometer_limit'] = self._extract_field_value(data_root, nested_data, 'return_rental_car_kilometer_limit', 'return_rental_car_kilometer_limit', is_integer=True)
            vals['return_rental_car_unlimited_km'] = self._extract_field_value(data_root, nested_data, 'return_rental_car_unlimited_km', 'return_rental_car_unlimited_km', is_boolean=True)
            vals['return_rental_car_preferences'] = self._extract_field_value(data_root, nested_data, 'return_rental_car_preferences', 'return_rental_car_preferences')
        else:
            _logger.info("BTD_PROCESS: Return rental car is not selected. Skipping return rental car detail extraction.")
            # Clear return rental car fields if use_return_rental_car is False
            vals['return_rental_car_pickup_date'] = None
            vals['return_rental_car_pickup_flexible'] = False
            vals['return_rental_car_pickup_point'] = None
            vals['return_rental_car_dropoff_point'] = None
            vals['return_rental_car_dropoff_date'] = None
            vals['return_rental_car_dropoff_flexible'] = False
            vals['return_rental_car_credit_card'] = None
            vals['return_rental_car_type'] = None
            vals['return_rental_car_drivers_license'] = None
            vals['return_rental_car_drivers_license_filename'] = None
            vals['return_rental_car_drivers_license_attachment_id'] = None
            vals['return_rental_car_kilometer_limit'] = 0
            vals['return_rental_car_unlimited_km'] = False
            vals['return_rental_car_preferences'] = ""

        # Train Information - Prioritize root, then nested 'data'
        if vals.get('use_train'): # Only process if train is selected
            _logger.info(f"BTD_PROCESS: Train is selected. Extracting details.")
            vals['train_departure_city'] = self._extract_field_value(data_root, nested_data, 'departure_city', 'departure_city_train') # Form might use departure_city for multiple, or a specific one like departure_city_train
            vals['train_departure_station'] = self._extract_field_value(data_root, nested_data, 'departure_station', 'departure_station_train')
            vals['train_arrival_station'] = self._extract_field_value(data_root, nested_data, 'arrival_station', 'arrival_station_train')
            vals['train_departure_date'] = self._extract_field_value(data_root, nested_data, 'departure_date_train', 'departure_date_train', is_date=True)
            vals['train_departure_flexible'] = self._extract_field_value(data_root, nested_data, 'departure_flexible_train', 'departure_flexible_train', is_boolean=True)
            vals['train_arrival_date'] = self._extract_field_value(data_root, nested_data, 'arrival_date', 'arrival_date_train', is_date=True) # Form might use arrival_date for multiple
            vals['train_arrival_flexible'] = self._extract_field_value(data_root, nested_data, 'arrival_flexible_train', 'arrival_flexible_train', is_boolean=True)
        else:
            _logger.info("BTD_PROCESS: Train is not selected. Skipping train detail extraction.")
            # Clear train fields if use_train is False
            vals['train_departure_city'] = None
            vals['train_departure_station'] = None
            vals['train_arrival_station'] = None
            vals['train_departure_date'] = None
            vals['train_departure_flexible'] = False
            vals['train_arrival_date'] = None
            vals['train_arrival_flexible'] = False

        # Return Train Information - Prioritize root, then nested 'data'
        if vals.get('use_return_train'): # Only process if return train is selected
            _logger.info(f"BTD_PROCESS: Return train is selected. Extracting details.")
            vals['return_train_departure_city'] = self._extract_field_value(data_root, nested_data, 'return_train_departure_city', 'return_train_departure_city')
            vals['return_train_departure_station'] = self._extract_field_value(data_root, nested_data, 'return_train_departure_station', 'return_train_departure_station')
            vals['return_train_arrival_station'] = self._extract_field_value(data_root, nested_data, 'return_train_arrival_station', 'return_train_arrival_station')
            vals['return_train_departure_date'] = self._extract_field_value(data_root, nested_data, 'return_train_departure_date', 'return_train_departure_date', is_date=True)
            vals['return_train_departure_flexible'] = self._extract_field_value(data_root, nested_data, 'return_train_departure_flexible', 'return_train_departure_flexible', is_boolean=True)
            vals['return_train_arrival_date'] = self._extract_field_value(data_root, nested_data, 'return_train_arrival_date', 'return_train_arrival_date', is_date=True)
            vals['return_train_arrival_flexible'] = self._extract_field_value(data_root, nested_data, 'return_train_arrival_flexible', 'return_train_arrival_flexible', is_boolean=True)
        else:
            _logger.info("BTD_PROCESS: Return train is not selected. Skipping return train detail extraction.")
            # Clear return train fields if use_return_train is False
            vals['return_train_departure_city'] = None
            vals['return_train_departure_station'] = None
            vals['return_train_arrival_station'] = None
            vals['return_train_departure_date'] = None
            vals['return_train_departure_flexible'] = False
            vals['return_train_arrival_date'] = None
            vals['return_train_arrival_flexible'] = False

        # Airplane Information - Prioritize root, then nested 'data'
        if vals.get('use_airplane'): # Only process if airplane is selected
            _logger.info(f"BTD_PROCESS: Airplane is selected. Extracting details.")
            vals['airplane_departure_airport'] = self._extract_field_value(data_root, nested_data, 'departure_airport', 'departure_airport') 
            vals['airplane_departure_date'] = self._extract_field_value(data_root, nested_data, 'departure_date_airplane', 'departure_date_airplane', is_date=True) 
            vals['airplane_departure_flexible'] = self._extract_field_value(data_root, nested_data, 'departure_flexible_airplane', 'departure_flexible_airplane', is_boolean=True)
            vals['airplane_arrival_airport'] = self._extract_field_value(data_root, nested_data, 'arrival_airport', 'arrival_airport')
            vals['airplane_arrival_date'] = self._extract_field_value(data_root, nested_data, 'arrival_date_airplane', 'arrival_date_airplane', is_date=True)
            vals['airplane_arrival_flexible'] = self._extract_field_value(data_root, nested_data, 'arrival_flexible_airplane', 'arrival_flexible_airplane', is_boolean=True)
            vals['airplane_baggage_type'] = self._extract_field_value(data_root, nested_data, 'baggage', 'baggage')
            vals['airplane_preferences'] = self._extract_field_value(data_root, nested_data, 'airplane_additional_preferences', 'airplane_additional_preferences')
        else:
            _logger.info("BTD_PROCESS: Airplane is not selected. Skipping airplane detail extraction.")
            # Clear airplane fields if use_airplane is False
            vals['airplane_departure_airport'] = None
            vals['airplane_departure_date'] = None
            vals['airplane_arrival_airport'] = None
            vals['airplane_arrival_date'] = None
            vals['airplane_arrival_flexible'] = False
            vals['airplane_baggage_type'] = None
            vals['airplane_preferences'] = ""

        # Return Airplane Information - Prioritize root, then nested 'data'
        if vals.get('use_return_airplane'): # Only process if return airplane is selected
            _logger.info(f"BTD_PROCESS: Return airplane is selected. Extracting details.")
            vals['return_airplane_departure_airport'] = self._extract_field_value(data_root, nested_data, 'return_departure_airport', 'return_departure_airport')
            vals['return_airplane_departure_date'] = self._extract_field_value(data_root, nested_data, 'return_departure_date', 'return_departure_date', is_date=True) # Form key 'return_departure_date'
            vals['return_airplane_departure_flexible'] = self._extract_field_value(data_root, nested_data, 'return_departure_flexible', 'return_departure_flexible', is_boolean=True) # Added
            vals['return_airplane_destination_airport'] = self._extract_field_value(data_root, nested_data, 'return_destination_airport', 'return_destination_airport')
            vals['return_airplane_destination_date'] = self._extract_field_value(data_root, nested_data, 'return_destination_date', 'return_destination_date', is_date=True)
            vals['return_airplane_destination_flexible'] = self._extract_field_value(data_root, nested_data, 'return_destination_flexible', 'return_destination_flexible', is_boolean=True)
            vals['return_airplane_baggage_type'] = self._extract_field_value(data_root, nested_data, 'return_baggage', 'return_baggage')
            vals['return_airplane_preferences'] = self._extract_field_value(data_root, nested_data, 'return_other_details', 'return_other_details')
        else:
            _logger.info("BTD_PROCESS: Return airplane is not selected. Skipping return airplane detail extraction.")
            # Clear return airplane fields if use_return_airplane is False
            vals['return_airplane_departure_airport'] = None
            vals['return_airplane_departure_date'] = None
            vals['return_airplane_destination_airport'] = None
            vals['return_airplane_destination_date'] = None
            vals['return_airplane_destination_flexible'] = False
            vals['return_airplane_baggage_type'] = None
            vals['return_airplane_preferences'] = ""

        # Bus Information - Prioritize root, then nested 'data'
        if vals.get('use_bus'): # Only process if bus is selected
            _logger.info(f"BTD_PROCESS: Bus is selected. Extracting details.")
            vals['bus_departure_city'] = self._extract_field_value(data_root, nested_data, 'bus_departure_city', 'bus_departure_city')
            vals['bus_departure_terminal'] = self._extract_field_value(data_root, nested_data, 'bus_departure_terminal', 'bus_departure_terminal')
            vals['bus_arrival_terminal'] = self._extract_field_value(data_root, nested_data, 'bus_arrival_terminal', 'bus_arrival_terminal')
            vals['bus_departure_date'] = self._extract_field_value(data_root, nested_data, 'bus_departure_date', 'bus_departure_date', is_date=True)
            vals['bus_departure_flexible'] = self._extract_field_value(data_root, nested_data, 'bus_departure_flexible', 'bus_departure_flexible', is_boolean=True)
            vals['bus_arrival_date'] = self._extract_field_value(data_root, nested_data, 'bus_arrival_date', 'bus_arrival_date', is_date=True)
            vals['bus_arrival_flexible'] = self._extract_field_value(data_root, nested_data, 'bus_arrival_flexible', 'bus_arrival_flexible', is_boolean=True)
        else:
            _logger.info("BTD_PROCESS: Bus is not selected. Skipping bus detail extraction.")
            # Clear bus fields if use_bus is False
            vals['bus_departure_city'] = None
            vals['bus_departure_terminal'] = None
            vals['bus_arrival_terminal'] = None
            vals['bus_departure_date'] = None
            vals['bus_departure_flexible'] = False
            vals['bus_arrival_date'] = None
            vals['bus_arrival_flexible'] = False

        # Return Bus Information - Prioritize root, then nested 'data'
        if vals.get('use_return_bus'): # Only process if return bus is selected
            _logger.info(f"BTD_PROCESS: Return bus is selected. Extracting details.")
            vals['return_bus_departure_city'] = self._extract_field_value(data_root, nested_data, 'return_bus_departure_city', 'return_bus_departure_city')
            vals['return_bus_departure_station'] = self._extract_field_value(data_root, nested_data, 'return_bus_departure_station', 'return_bus_departure_station') # Corrected from terminal
            vals['return_bus_arrival_station'] = self._extract_field_value(data_root, nested_data, 'return_bus_arrival_station', 'return_bus_arrival_station')
            vals['return_bus_departure_date'] = self._extract_field_value(data_root, nested_data, 'return_bus_departure_date', 'return_bus_departure_date', is_date=True)
            vals['return_bus_departure_flexible'] = self._extract_field_value(data_root, nested_data, 'return_bus_departure_flexible', 'return_bus_departure_flexible', is_boolean=True)
            vals['return_bus_arrival_date'] = self._extract_field_value(data_root, nested_data, 'return_bus_arrival_date', 'return_bus_arrival_date', is_date=True)
            vals['return_bus_arrival_flexible'] = self._extract_field_value(data_root, nested_data, 'return_bus_arrival_flexible', 'return_bus_arrival_flexible', is_boolean=True)
        else:
            _logger.info("BTD_PROCESS: Return bus is not selected. Skipping return bus detail extraction.")
            # Clear return bus fields if use_return_bus is False
            vals['return_bus_departure_city'] = None
            vals['return_bus_departure_station'] = None
            vals['return_bus_arrival_station'] = None
            vals['return_bus_departure_date'] = None
            vals['return_bus_departure_flexible'] = False
            vals['return_bus_arrival_date'] = None
            vals['return_bus_arrival_flexible'] = False

        # Manual Travel Duration
        manual_travel_duration_val = self._extract_field_value(data_root, nested_data, 'manual_travel_duration', 'manual_travel_duration')
        if manual_travel_duration_val is not None:
                vals['manual_travel_duration'] = float(manual_travel_duration_val)
        else:
            _logger.info("BTD_PROCESS: Manual travel duration not found in submission data. Using default value.")
            vals['manual_travel_duration'] = 0.0

        # Expected Cost
        expected_cost_val = self._extract_field_value(data_root, nested_data, 'expected_cost', 'expected_cost')
        if expected_cost_val is not None:
                vals['expected_cost'] = float(expected_cost_val)
        else:
            _logger.info("BTD_PROCESS: Expected cost not found in submission data. Using default value.")
            vals['expected_cost'] = 0.0

        # Currency
        currency_id_val_str = self._extract_field_value(data_root, nested_data, 'currency', 'currency')
        if currency_id_val_str:
            # Attempt to find currency by name (if string) or ID (if int)
            currency_obj = None
            if isinstance(currency_id_val_str, str):
                currency_obj = self.env['res.currency'].search([('name', '=', currency_id_val_str)], limit=1)
            elif isinstance(currency_id_val_str, int):
                currency_obj = self.env['res.currency'].browse(currency_id_val_str) # browse if ID is provided

            if currency_obj and currency_obj.exists():
                vals['currency_id'] = currency_obj.id
            else:
                _logger.warning(f"BTD_PROCESS: Currency '{currency_id_val_str}' not found or invalid. Using default currency.")
                vals['currency_id'] = self.env.company.currency_id.id
        else:
            _logger.info("BTD_PROCESS: Currency not found in submission data. Using default currency.")
            vals['currency_id'] = self.env.company.currency_id.id

        _logger.info(f"BTD_PROCESS: Final vals before writing...")
        try:
            # Prepare a clean version of vals for logging to avoid large base64 strings
            log_vals = vals.copy()
            if log_vals.get('rental_car_drivers_license'):
                log_vals['rental_car_drivers_license'] = '<base64_data>'
            if log_vals.get('return_rental_car_drivers_license'):
                log_vals['return_rental_car_drivers_license'] = '<base64_data>'
            
            # Also clean up the accompanying person data if it exists
            if 'accompanying_person_ids' in log_vals and log_vals['accompanying_person_ids']:
                cleaned_persons = []
                for cmd, rec_id, person_vals in log_vals['accompanying_person_ids']:
                    if 'identity_document' in person_vals:
                        person_vals['identity_document'] = '<base64_data>'
                    cleaned_persons.append((cmd, rec_id, person_vals))
                log_vals['accompanying_person_ids'] = cleaned_persons

            _logger.info(f"BTD_PROCESS: Cleaned vals for logging: {log_vals}")

            # Disable tracking for automated field updates to avoid individual log entries
            self.with_context(tracking_disable=True).write(vals)
            _logger.info(f"BTD_PROCESS: Successfully updated BusinessTripData record {self.id}.")

        except Exception as e:
            _logger.error(f"BTD_PROCESS: Error updating BusinessTripData record {self.id}: {e}", exc_info=True)
            raise

        _logger.info("BTD_PROCESS: process_submission_data completed successfully.")
        return True

    def _extract_field_value(self, data_root, nested_data, root_key, nested_key, is_boolean=False, is_integer=False, is_float=False, is_date=False, default_value=None):
        """
        Helper to extract value: checks root first for the full key, then the nested 'data' object
        for the partial key. This supports both flat and nested structures.
        """
        # Set appropriate default value for dates to avoid invalid dates
        if is_date and default_value is None:
            default_value = None  # Use None for date fields
            
        raw_value = default_value
        source = "default"

        # 1. Prioritize root-level key (e.g., 'rental_car_pickup_date')
        if root_key in data_root and data_root[root_key] is not None and data_root[root_key] != '':
            raw_value = data_root[root_key]
            source = f"root ('{root_key}')"
        # 2. Fallback to nested key inside 'data' object (e.g., 'data.rental_car.pickup_date')
        elif nested_data and nested_key in nested_data and nested_data[nested_key] is not None and nested_data[nested_key] != '':
            raw_value = nested_data[nested_key]
            source = f"nested ('data.{nested_key}')"

        if raw_value is None or raw_value == '':
             _logger.info(f"BTD_PROCESS_EXTRACT: Field '{root_key}' (or 'data.{nested_key}') not found or empty. Returning default: {default_value}")
             return default_value

        try:
            if is_boolean:
                # Handles "true", "false", true, false, 1, 0, "on", "off"
                if isinstance(raw_value, str):
                    val_lower = raw_value.lower()
                    if val_lower in ["true", "on", "yes", "1"]: return True
                    if val_lower in ["false", "off", "no", "0"]: return False
                return bool(raw_value) # Fallback to standard bool conversion
            elif is_integer:
                return int(raw_value)
            elif is_float:
                return float(raw_value)
            elif is_date:
                # Attempt to parse date from common formats
                if isinstance(raw_value, str):
                    # Skip empty or whitespace-only strings
                    if not raw_value.strip():
                        _logger.info(f"BTD_PROCESS_EXTRACT: Date field '{root_key}' is empty string. Returning default: {default_value}")
                        return default_value
                        
                    # Handle "DD/MM/YYYY" (dayFirst), "MM/DD/YYYY" and "YYYY-MM-DD"
                    parsed_date = None
                    try:
                        # Try DD/MM/YYYY format first (dayFirst: true)
                        parsed_date = datetime.strptime(raw_value.strip(), '%d/%m/%Y').date()
                    except ValueError:
                        try:
                            # Fallback to MM/DD/YYYY format
                            parsed_date = datetime.strptime(raw_value.strip(), '%m/%d/%Y').date()
                        except ValueError:
                            try:
                                # Fallback to ISO format YYYY-MM-DD
                                parsed_date = datetime.strptime(raw_value.strip(), '%Y-%m-%d').date()
                            except ValueError:
                                _logger.warning(f"BTD_PROCESS_EXTRACT: Could not parse date '{raw_value}' for key '{root_key}'. Supported formats: DD/MM/YYYY, MM/DD/YYYY, YYYY-MM-DD. Returning default: {default_value}")
                                return default_value
                    
                    # Validate that the parsed date is reasonable (not too far in past/future)
                    if parsed_date and parsed_date.year < 1900:
                        _logger.warning(f"BTD_PROCESS_EXTRACT: Parsed date '{parsed_date}' for key '{root_key}' has invalid year ({parsed_date.year}). Returning default: {default_value}")
                        return default_value
                        
                    _logger.info(f"BTD_PROCESS_EXTRACT: Field '{root_key}' from {source} with raw value '{raw_value}' parsed to date: {parsed_date}")
                    return parsed_date
                elif isinstance(raw_value, date): # Already a date object
                     _logger.info(f"BTD_PROCESS_EXTRACT: Field '{root_key}' from {source} with raw value '{raw_value}' is already date type.")
                     return raw_value
                else:
                    _logger.warning(f"BTD_PROCESS_EXTRACT: Date field '{root_key}' from {source} is not a string or date object: {raw_value} (type: {type(raw_value)}).")
                    return default_value
            else: # String or other
                _logger.info(f"BTD_PROCESS_EXTRACT: Field '{root_key}' from {source} with raw value '{raw_value}' extracted as string/original type.")
                return raw_value
        except (ValueError, TypeError) as e:
            _logger.warning(f"BTD_PROCESS_EXTRACT: Could not parse value '{raw_value}' for field '{root_key}' from source '{source}'. Error: {e}. Using default value: {default_value}")
            return default_value

    def _cleanup_false_date_fields(self, vals):
        """Set date fields to None if they are False."""
        for field_name, field in self._fields.items():
            if field.type == 'date' and field_name in vals and vals[field_name] is False:
                vals[field_name] = None
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._cleanup_false_date_fields(vals)
        records = super(BusinessTripData, self).create(vals_list)
        # Update attachment IDs after creation
        for record in records:
            record._update_attachment_ids()
        return records

    def write(self, vals):
        self._cleanup_false_date_fields(vals)
        result = super(BusinessTripData, self).write(vals)
        # Update attachment IDs after write if binary fields were changed
        if any(field in vals for field in ['rental_car_drivers_license', 'return_rental_car_drivers_license']):
            self._update_attachment_ids()
        return result
    
    def _update_attachment_ids(self):
        """
        Update attachment_id fields by finding the attachments for binary fields.
        This is needed because when a binary field with attachment=True is saved,
        Odoo automatically creates an attachment, but we need to link it explicitly
        to use it for download links.
        """
        for record in self:
            # Find attachment for rental car driver's license
            if record.rental_car_drivers_license:
                attachment = self.env['ir.attachment'].search([
                    ('res_model', '=', 'business.trip.data'),
                    ('res_id', '=', record.id),
                    ('res_field', '=', 'rental_car_drivers_license')
                ], limit=1, order='id desc')
                current_attachment_id = record.rental_car_drivers_license_attachment_id.id if record.rental_car_drivers_license_attachment_id else False
                if attachment and attachment.id != current_attachment_id:
                    # Use sudo().write() to avoid triggering write method again
                    record.sudo().write({
                        'rental_car_drivers_license_attachment_id': attachment.id,
                        'rental_car_drivers_license_filename': record.rental_car_drivers_license_filename or attachment.name
                    })
            
            # Find attachment for return rental car driver's license
            if record.return_rental_car_drivers_license:
                attachment = self.env['ir.attachment'].search([
                    ('res_model', '=', 'business.trip.data'),
                    ('res_id', '=', record.id),
                    ('res_field', '=', 'return_rental_car_drivers_license')
                ], limit=1, order='id desc')
                current_attachment_id = record.return_rental_car_drivers_license_attachment_id.id if record.return_rental_car_drivers_license_attachment_id else False
                if attachment and attachment.id != current_attachment_id:
                    # Use sudo().write() to avoid triggering write method again
                    record.sudo().write({
                        'return_rental_car_drivers_license_attachment_id': attachment.id,
                        'return_rental_car_drivers_license_filename': record.return_rental_car_drivers_license_filename or attachment.name
                    })

