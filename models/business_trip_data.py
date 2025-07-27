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
    
    @classmethod
    def _valid_field_parameter(cls, field, name):
        # Add support for tracking parameter
        return name == 'tracking' or super()._valid_field_parameter(field, name)
    
    # Reference to formio.form
    form_id = fields.Many2one('formio.form', string='Form', ondelete='cascade', required=True, index=True)
    form_title = fields.Char(string='Form Title', compute='_compute_form_title', store=True)
    active = fields.Boolean(default=True)
    
    # Personal information fields
    first_name = fields.Char(string='First Name', compute='_compute_personal_info_from_submission', store=True, readonly=False)
    last_name = fields.Char(string='Last Name', compute='_compute_personal_info_from_submission', store=True, readonly=False)
    full_name = fields.Char(string='Full Name', compute='_compute_full_name', store=True)
    
    # Trip approval and type fields
    approving_colleague_name = fields.Char(string='Approving Colleague Name', tracking=True, 
                                          help="Name of the colleague who approved this trip")
    trip_duration_type = fields.Selection([
        ('days', 'Daily Trip'),
        ('weeks', 'Short Trip (Up to one week)'),
        ('short', 'Intermediate Trip (Up to three months)'),
        ('long', 'Long Trip (More than three months)')
    ], string='Trip Duration Type', tracking=True, help="Category that best fits the trip duration")

    trip_type = fields.Selection([
        ('oneWay', 'One Way'),
        ('twoWay', 'Two Way')
    ], string='Trip Type', tracking=True, help="Indicates if the trip is one-way or two-way")
    
    # Accommodation fields
    accommodation_needed = fields.Selection([
        ('yes', 'Yes'),
        ('no', 'No')
    ], string='Accommodation Needed', tracking=True, help="Indicates if accommodation arrangements are required for this trip")
    accommodation_number_of_people = fields.Integer(string='Number of People', tracking=True, help="Total number of people requiring accommodation")
    accommodation_residence_city = fields.Char(string='Residence City', tracking=True, help="City of residence of the traveler")
    accommodation_check_in_date = fields.Date(string='Check-in Date', tracking=True, help="Planned accommodation check-in date")
    accommodation_check_out_date = fields.Date(string='Check-out Date', tracking=True, help="Planned accommodation check-out date")
    accommodation_points_of_interest = fields.Text(string='Points of Interest', tracking=True, help="Points of interest or other information relevant for accommodation selection")
    accommodation_need_24h_reception = fields.Selection([
        ('yes', 'Yes'),
        ('no', 'No')
    ], string='Need 24h Reception', tracking=True, help="Indicates if 24-hour reception is required")
    
    # One2many field for accompanying persons
    accompanying_person_ids = fields.One2many('accompanying.person', 'business_trip_id', string='Accompanying Persons', tracking=True)
    
    # Transport means fields
    use_rental_car = fields.Boolean(string='Rental Car', default=False, tracking=True)
    use_company_car = fields.Boolean(string='Company Car', default=False, tracking=True)
    use_personal_car = fields.Boolean(string='Personal Car', default=False, tracking=True)
    use_train = fields.Boolean(string='Train', default=False, tracking=True)
    use_airplane = fields.Boolean(string='Airplane', default=False, tracking=True)
    use_bus = fields.Boolean(string='Bus', default=False, tracking=True)
    transport_means_json = fields.Text(string='Transport Means (JSON)', help="JSON representation of selected transport means")
    
    # Return transport means fields (for two-way trips)
    use_return_rental_car = fields.Boolean(string='Return Rental Car', default=False, tracking=True)
    use_return_company_car = fields.Boolean(string='Return Company Car', default=False, tracking=True)
    use_return_personal_car = fields.Boolean(string='Return Personal Car', default=False, tracking=True)
    use_return_train = fields.Boolean(string='Return Train', default=False, tracking=True)
    use_return_airplane = fields.Boolean(string='Return Airplane', default=False, tracking=True)
    use_return_bus = fields.Boolean(string='Return Bus', default=False, tracking=True)
    return_transport_means_json = fields.Text(string='Return Transport Means (JSON)', help="JSON representation of selected return transport means")
    
    # Rental car information fields
    rental_car_pickup_date = fields.Date(string='Rental Car Pickup Date', tracking=True)
    rental_car_pickup_flexible = fields.Boolean(string='Pickup Flexible', default=False, tracking=True)
    rental_car_pickup_point = fields.Char(string='Pickup Point', tracking=True)
    rental_car_dropoff_point = fields.Char(string='Dropoff Point', tracking=True)
    rental_car_dropoff_date = fields.Date(string='Rental Car Dropoff Date', tracking=True)
    rental_car_dropoff_flexible = fields.Boolean(string='Dropoff Flexible', default=False, tracking=True)
    rental_car_credit_card = fields.Selection([
        ('yes', 'Yes'),
        ('no', 'No')
    ], string='Credit Card Available', tracking=True)
    rental_car_type = fields.Selection([
        ('ncc', 'Rental with driver (NCC)'),
        ('self', 'You drive')
    ], string='Rental Type', tracking=True)
    rental_car_drivers_license = fields.Binary(string='Driver\'s License', attachment=True)
    rental_car_drivers_license_filename = fields.Char(string='Driver\'s License Filename')
    rental_car_kilometer_limit = fields.Integer(string='Kilometer Limit', tracking=True)
    rental_car_unlimited_km = fields.Boolean(string='Unlimited Kilometers', default=False, tracking=True)
    rental_car_preferences = fields.Text(string='Rental Car Preferences', tracking=True, 
                                       help="Additional preferences for rental car, such as pick-up time, car model, GPS, child seat, etc.")
    
    # Return rental car information fields
    return_rental_car_pickup_date = fields.Date(string='Return Rental Car Pickup Date', tracking=True)
    return_rental_car_pickup_flexible = fields.Boolean(string='Return Pickup Flexible', default=False, tracking=True)
    return_rental_car_pickup_point = fields.Char(string='Return Pickup Point', tracking=True)
    return_rental_car_dropoff_point = fields.Char(string='Return Dropoff Point', tracking=True)
    return_rental_car_dropoff_date = fields.Date(string='Return Rental Car Dropoff Date', tracking=True)
    return_rental_car_dropoff_flexible = fields.Boolean(string='Return Dropoff Flexible', default=False, tracking=True)
    return_rental_car_credit_card = fields.Selection([
        ('yes', 'Yes'),
        ('no', 'No')
    ], string='Return Credit Card Available', tracking=True)
    return_rental_car_type = fields.Selection([
        ('ncc', 'Rental with driver (NCC)'),
        ('self', 'You drive')
    ], string='Return Rental Type', tracking=True)
    return_rental_car_drivers_license = fields.Binary(string='Return Driver\'s License', attachment=True)
    return_rental_car_drivers_license_filename = fields.Char(string='Return Driver\'s License Filename')
    return_rental_car_kilometer_limit = fields.Integer(string='Return Kilometer Limit', tracking=True)
    return_rental_car_unlimited_km = fields.Boolean(string='Return Unlimited Kilometers', default=False, tracking=True)
    return_rental_car_preferences = fields.Text(string='Return Rental Car Preferences', tracking=True, 
                                            help="Additional preferences for return rental car, such as pick-up time, car model, GPS, child seat, etc.")
    
    # Train information fields
    train_departure_city = fields.Char(string='Train Departure City', tracking=True)
    train_departure_station = fields.Char(string='Train Departure Station', tracking=True)
    train_arrival_station = fields.Char(string='Train Arrival Station', tracking=True)
    train_departure_date = fields.Date(string='Train Departure Date', tracking=True)
    train_departure_flexible = fields.Boolean(string='Train Departure Flexible', default=False, tracking=True)
    train_arrival_date = fields.Date(string='Train Arrival Date', tracking=True)
    train_arrival_flexible = fields.Boolean(string='Train Arrival Flexible', default=False, tracking=True)
    
    # Return train information fields
    return_train_departure_city = fields.Char(string='Return Train Departure City', tracking=True)
    return_train_departure_station = fields.Char(string='Return Train Departure Station', tracking=True)
    return_train_arrival_station = fields.Char(string='Return Train Arrival Station', tracking=True)
    return_train_departure_date = fields.Date(string='Return Train Departure Date', tracking=True)
    return_train_departure_flexible = fields.Boolean(string='Return Train Departure Flexible', default=False, tracking=True)
    return_train_arrival_date = fields.Date(string='Return Train Arrival Date', tracking=True)
    return_train_arrival_flexible = fields.Boolean(string='Return Train Arrival Flexible', default=False, tracking=True)
    
    # Return airplane information fields
    return_airplane_departure_airport = fields.Char(string='Return Departure Airport', tracking=True)
    return_airplane_departure_date = fields.Date(string='Return Airplane Departure Date', tracking=True)
    return_airplane_departure_flexible = fields.Boolean(string='Return Airplane Departure Flexible', default=False, tracking=True)
    return_airplane_destination_airport = fields.Char(string='Return Destination Airport', tracking=True)
    return_airplane_destination_date = fields.Date(string='Return Airplane Destination Date', tracking=True)
    return_airplane_destination_flexible = fields.Boolean(string='Return Airplane Destination Flexible', default=False, tracking=True)
    return_airplane_baggage_type = fields.Selection([
        ('no', 'No baggage / Small Bag'),
        ('medium', 'Medium'),
        ('large', 'Large'),
        ('checked', 'Checked Baggage')
    ], string='Return Baggage Type', tracking=True)
    return_airplane_preferences = fields.Text(string='Return Airplane Preferences', tracking=True,
                                            help="Additional preferences for return airplane travel, such as seat preference, preferred time, etc.")
    
    # Return bus information fields
    return_bus_departure_city = fields.Char(string='Return Bus Departure City', tracking=True)
    return_bus_departure_station = fields.Char(string='Return Bus Departure Station', tracking=True)
    return_bus_arrival_station = fields.Char(string='Return Bus Arrival Station', tracking=True)
    return_bus_departure_date = fields.Date(string='Return Bus Departure Date', tracking=True)
    return_bus_departure_flexible = fields.Boolean(string='Return Bus Departure Flexible', default=False, tracking=True)
    return_bus_arrival_date = fields.Date(string='Return Bus Arrival Date', tracking=True)
    return_bus_arrival_flexible = fields.Boolean(string='Return Bus Arrival Flexible', default=False, tracking=True)
    
    # Bus information fields
    bus_departure_city = fields.Char(string='Bus Departure City', tracking=True)
    bus_departure_terminal = fields.Char(string='Bus Departure Terminal', tracking=True)
    bus_arrival_terminal = fields.Char(string='Bus Arrival Terminal', tracking=True)
    bus_departure_date = fields.Date(string='Bus Departure Date', tracking=True)
    bus_departure_flexible = fields.Boolean(string='Bus Departure Flexible', default=False, tracking=True)
    bus_arrival_date = fields.Date(string='Bus Arrival Date', tracking=True)
    bus_arrival_flexible = fields.Boolean(string='Bus Arrival Flexible', default=False, tracking=True)
    
    # Airplane information fields
    airplane_departure_airport = fields.Char(string='Departure Airport', tracking=True)
    airplane_departure_date = fields.Date(string='Airplane Departure Date', tracking=True)
    airplane_departure_flexible = fields.Boolean(string='Airplane Departure Flexible', default=False, tracking=True)
    airplane_arrival_airport = fields.Char(string='Arrival Airport', tracking=True)
    airplane_arrival_date = fields.Date(string='Airplane Arrival Date', tracking=True)
    airplane_arrival_flexible = fields.Boolean(string='Airplane Arrival Flexible', default=False, tracking=True)
    airplane_baggage_type = fields.Selection([
        ('no', 'No baggage / Small Bag'),
        ('medium', 'Medium'),
        ('large', 'Large'),
        ('checked', 'Checked Baggage')
    ], string='Baggage Type', tracking=True)
    airplane_preferences = fields.Text(string='Airplane Preferences', tracking=True,
                                      help="Additional preferences for airplane travel, such as seat preference, preferred time, etc.")
    
    # Basic trip information fields
    destination = fields.Char(string='Destination', tracking=True)
    purpose = fields.Char(string='Purpose of Trip', compute='_compute_purpose', store=True, tracking=True)
    travel_start_date = fields.Date(string='Start Date', tracking=True)
    travel_end_date = fields.Date(string='End Date', tracking=True)
    manual_travel_duration = fields.Float(string='Manual Travel Duration', tracking=True, help="Travel duration manually set from the trip details wizard")
    expected_cost = fields.Float(string='Expected Cost', tracking=True, help="Initial expected cost by employee")
    currency_id = fields.Many2one('res.currency', string='Currency', 
                                 default=lambda self: self.env.company.currency_id.id, tracking=True)
    
    @api.depends('form_id', 'form_id.sale_order_id', 'form_id.sale_order_id.name')
    def _compute_purpose(self):
        for record in self:
            if record.form_id and hasattr(record.form_id, 'sale_order_id') and record.form_id.sale_order_id:
                record.purpose = record.form_id.sale_order_id.name # type: ignore
                _logger.info(f"BTD_COMPUTE_PURPOSE: Purpose for BTD {record.id} set to Sale Order Name: {record.purpose} from Form {record.form_id.id}")
            else:
                record.purpose = "Standalone"
                _logger.info(f"BTD_COMPUTE_PURPOSE: Purpose for BTD {record.id} set to Standalone. Form ID: {record.form_id.id if record.form_id else 'N/A'}, SO on Form: {record.form_id.sale_order_id if record.form_id and hasattr(record.form_id, 'sale_order_id') else 'N/A'}")

    @api.depends('first_name', 'last_name')
    def _compute_full_name(self):
        for record in self:
            names = []
            if record.first_name:
                names.append(record.first_name)
            if record.last_name:
                names.append(record.last_name)
            record.full_name = ' '.join(names) if names else False
    
    @api.depends('form_id', 'form_id.title')
    def _compute_form_title(self):
        """Computes the form title from the related formio.form record."""
        for record in self:
            record.form_title = record.form_id.title if record.form_id else False
    
    def process_submission_data(self, submission_data):
        _logger.info(f"BTD_PROCESS: Starting process_submission_data for BusinessTripData ID: {self.id}, Form ID: {self.form_id.id if self.form_id else 'N/A'}")

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
        vals['approving_colleague_name'] = self._extract_field_value(data_root, nested_data, 'approving_colleague_name', 'approving_colleague_name', default_value="")

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
                
                if isinstance(accompanying_doc, list) and accompanying_doc:
                    # Take the first file if multiple are somehow uploaded
                    file_info = accompanying_doc[0]
                    if isinstance(file_info, dict):
                        # Handle both storage types: base64 stored in 'url' field or separate 'base64' field
                        if file_info.get('storage') == 'base64' and file_info.get('url'):
                            # Extract base64 data from data URL
                            url_data = file_info.get('url', '')
                            if url_data.startswith('data:'):
                                doc_base64 = url_data.split(',')[-1]
                            else:
                                doc_base64 = file_info.get('base64')
                        else:
                            doc_base64 = file_info.get('base64')
                        doc_filename = file_info.get('originalName') or file_info.get('name')
                        _logger.info(f"BTD_PROCESS: Found accompanying document: {doc_filename}, storage: {file_info.get('storage')}, has_base64: {bool(doc_base64)}, url_length: {len(file_info.get('url', ''))}")
                
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
                    if i == 0 and doc_base64 and doc_filename:
                        try:
                            person_vals['identity_document'] = doc_base64
                            person_vals['identity_document_filename'] = doc_filename
                            _logger.info(f"BTD_PROCESS: Added document '{doc_filename}' to accompanying person '{person_name}'")
                        except Exception as e:
                            _logger.error(f"BTD_PROCESS: Error processing document for accompanying person '{person_name}': {e}")
                    
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
                if isinstance(file_info, dict) and file_info.get('storage') == 'base64':
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
                else:
                    _logger.warning(f"BTD_PROCESS: Rental car license data found but not in expected format (dict with storage='base64'): {file_info}")
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
                if isinstance(file_info, dict) and file_info.get('storage') == 'base64':
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
                else:
                    _logger.warning(f"BTD_PROCESS: Return rental car license data found but not in expected format (dict with storage='base64'): {file_info}")

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
            _logger.warning("BTD_PROCESS: Manual travel duration not found in submission data. Using default value.")
            vals['manual_travel_duration'] = 0.0

        # Expected Cost
        expected_cost_val = self._extract_field_value(data_root, nested_data, 'expected_cost', 'expected_cost')
        if expected_cost_val is not None:
                vals['expected_cost'] = float(expected_cost_val)
        else:
            _logger.warning("BTD_PROCESS: Expected cost not found in submission data. Using default value.")
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
            _logger.warning("BTD_PROCESS: Currency not found in submission data. Using default currency.")
            vals['currency_id'] = self.env.company.currency_id.id

        _logger.info(f"BTD_PROCESS: Final vals before writing: {vals}")
        try:
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
                    # Handle "MM/DD/YYYY" and "YYYY-MM-DD"
                    parsed_date = None
                    try:
                        parsed_date = datetime.strptime(raw_value, '%m/%d/%Y').date()
                    except ValueError:
                        try:
                            parsed_date = datetime.strptime(raw_value, '%Y-%m-%d').date()
                        except ValueError:
                            _logger.warning(f"BTD_PROCESS_EXTRACT: Could not parse date '{raw_value}' for key '{root_key}'. Supported formats: MM/DD/YYYY, YYYY-MM-DD.")
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

    @api.model_create_multi
    def create(self, vals_list):
        records = super(BusinessTripData, self).create(vals_list)
        
        for record in records:
            if record.form_id:
                # Create a simple, clean HTML message
                message_body = f"""
                <div style="background-color: #EBF5FF; border: 1px solid #B3D4FF; border-radius: 5px; padding: 15px; margin: 10px 0; font-family: sans-serif;">
                    <div style="font-size: 16px; font-weight: bold; margin-bottom: 12px; color: #00529B;">
                        📝 Business Trip Request Created
                    </div>
                    <div style="color: #004085; font-size: 14px; line-height: 1.6; margin-bottom: 12px;">
                        A new business trip request has been initiated. Please fill out the form with the required details.
                    </div>
                    <div style="background-color: #DAE8FC; border-radius: 4px; padding: 10px; margin-top: 15px;">
                        <strong>Next steps:</strong>
                        <div style="font-size: 13px; margin-top: 5px;">
                            Complete the submission form with all travel details.
                        </div>
                    </div>
                    <div style="text-align: right; font-size: 12px; color: #004085; margin-top: 15px; border-top: 1px solid #B3D4FF; padding-top: 8px;">
                        <em>Posted by: {self.env.user.name}</em>
                    </div>
                </div>
                """

                # Post the initial message to the linked form's chatter
                record.form_id.message_post(
                    body=message_body,
                    message_type='comment',
                    subtype_xmlid='mail.mt_comment'
                )
                _logger.info(f"BTD_CREATE: Posted initial creation message to chatter for form {record.form_id.id}")

        return records

