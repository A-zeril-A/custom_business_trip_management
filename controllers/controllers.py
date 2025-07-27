from odoo import http
from odoo.http import request
import werkzeug
import json
import urllib.parse
from odoo import fields
import logging

_logger = logging.getLogger(__name__)

# Import from formio base controller
from odoo.addons.formio.controllers.main import FormioController, FORM_STATE_COMPLETE

class BusinessTripRedirect(FormioController):

    @http.route('/business_trip/entry', type='http', auth='user')
    def redirect_user_by_role(self, **kwargs):
        """
        Redirects the user to the appropriate business trip form list view 
        based on their access level.

        - If the user belongs to the system administrator group, they are 
        redirected to a global list of business trip forms filtered to show 
        only those containing "Organizzatore di viaggio" in the name.
        - Otherwise, the user is redirected to a personalized list of their 
        own submitted forms.

        The redirection targets specific actions and menu items within the 
        Odoo web client, preserving contextual UI behavior.

        Parameters:
            **kwargs: Optional keyword arguments passed from the route (unused).

        Returns:
            werkzeug.wrappers.Response: A 302 redirect response to the target view.
        """
        user = request.env.user

        if user.has_group('base.group_system'):
            # Admin users: redirect to internal list of all business trip forms
            action = request.env.ref('custom_business_trip_management.action_view_business_trip_forms')
            menu = request.env.ref('custom_business_trip_management.menu_view_business_trip_forms')

            domain = [('name', 'ilike', 'Organizzatore di viaggio')]
        else:
            # Regular users: redirect to their own forms
            action = request.env.ref('custom_business_trip_management.action_view_my_business_trip_forms')
            menu = request.env.ref('custom_business_trip_management.menu_view_my_business_trip_forms')

            domain = [('user_id', '=', user.id)]

        domain_encoded = urllib.parse.quote(json.dumps(domain))

        return werkzeug.utils.redirect(
            f"/web#action={action.id}&model=formio.form&view_type=list&domain={domain_encoded}&menu_id={menu.id}"
        )


        
    @http.route('/business_trip/quotation_list', type='http', auth='user')
    def redirect_to_quotation_list(self, **kwargs):
        """
        Redirects the current user to a customized list view of quotations 
        within the business trip workflow.

        This view is tailored to display quotations relevant for travel planning 
        and is linked to a specific menu and action to maintain context within 
        the Odoo web client. The target list view may include custom JavaScript 
        behavior for row interactions (e.g., redirection on row click).
        """
        action = request.env.ref('custom_business_trip_management.action_sale_order_trip_custom')
        menu = request.env.ref('custom_business_trip_management.menu_select_quotation_for_trip')
        return werkzeug.utils.redirect(
            f"/web#action={action.id}&model=sale.order&view_type=list&menu_id={menu.id}"
        )

    """ 
    This route may be deprecated if only one form per quotation is allowed.
    Consider removing unless multiple forms per sale.order are required.
    """
    # @http.route('/business_trip/start/<int:sale_order_id>', type='http', auth='user')
    # def start_trip_for_quotation(self, sale_order_id, **kwargs):
    #     # Get the target quotation
    #     sale_order = request.env['sale.order'].sudo().browse(sale_order_id)
    #     if not sale_order.exists():
    #         return request.not_found()

    #     # Get the builder first
    #     builder = request.env['formio.builder'].sudo().search([
    #         ('state', '=', 'CURRENT'),
    #         ('res_model_id.model', '=', 'sale.order')
    #     ], limit=1)

    #     if not builder:
    #         return request.not_found('custom_business_trip_management.template_no_builder')

    #     # Check if a form is already created for this quotation
    #     form = request.env['formio.form'].sudo().search([
    #         ('sale_order_id', '=', sale_order.id)
    #     ], limit=1)

    #     # If no form exists, create one
    #     if not form:
    #         form = request.env['formio.form'].sudo().create({
    #             'builder_id': builder.id,
    #             'title': builder.title,
    #             'user_id': request.env.user.id,
    #             'sale_order_id': sale_order.id,
    #             'res_id': sale_order.id,
    #             'res_model_id': request.env.ref('sale.model_sale_order').id,
    #             'res_name': sale_order.name,
    #             'res_partner_id': sale_order.partner_id.id,
    #         })

    #     # Redirect to the formio.form record (form view)
    #     return werkzeug.utils.redirect(
    #         f"/web#action=formio.action_formio_form&active_id={form.id}&model=formio.form&view_type=formio_form&id={form.id}&cids=1"
    #     )
        
    @http.route('/business_trip/new/<int:sale_order_id>', type='http', auth='user')
    def create_new_trip_form(self, sale_order_id, **kwargs):
        """
        Forcefully creates a new business trip form for the given quotation (sale.order),
        regardless of whether any previous form already exists.

        This route bypasses duplication checks and is intended for cases where multiple
        trip forms per quotation are allowed or explicitly required.
        
        Note: After creating the form, we explicitly call after_submit() to ensure
        that form data is properly processed and extracted to business.trip.data model.
        This fixes issues with missing data in fields like 'Requester Name' and 'Approving Colleague'.
        
        Args:
            sale_order_id (int): The ID of the related sale.order (quotation).
            **kwargs: Optional keyword arguments (unused).

        Returns:
            werkzeug.wrappers.Response: A redirect to the newly created form's form view.
        """
        # Fetch the target quotation
        sale_order = request.env['sale.order'].sudo().browse(sale_order_id)
        if not sale_order.exists():
            return request.not_found()

        # Fetch the CURRENT builder configured for the sale.order model
        builder = request.env['formio.builder'].sudo().search([
            ('state', '=', 'CURRENT'),
            ('res_model_id.model', '=', 'sale.order')
        ], limit=1)

        if not builder:
            return request.not_found('custom_business_trip_management.template_no_builder')

        # Create a new form without checking for existing forms
        form_vals = {
            'builder_id': builder.id,
            'title': f'New Business Trip Form - {sale_order.name}',
            'user_id': request.env.user.id,
            'sale_order_id': sale_order.id,
            'res_id': sale_order.id,
            'res_model_id': request.env.ref('sale.model_sale_order').id,
            'res_name': sale_order.name,
            'res_partner_id': sale_order.partner_id.id,
            'state': 'DRAFT',
        }
        form = request.env['formio.form'].sudo().create(form_vals)
        
        # Ensure the business.trip.data record is created
        # Create the business.trip.data record and process initial data
        try:
            import logging
            _logger = logging.getLogger(__name__)
            
            # Check if the business.trip.data record was created during form creation
            trip_data = request.env['business.trip.data'].sudo().search([('form_id', '=', form.id)], limit=1)
            if not trip_data:
                # Create the record if not exists
                trip_data = request.env['business.trip.data'].sudo().create({
                    'form_id': form.id,
                })
                _logger.info(f"Created business.trip.data record for form {form.id} during controller execution")
            
            # Create initial submission_data structure with user information
            # This helps after_submit to properly extract basic data even before user fills the form
            current_user = request.env.user
            if current_user and trip_data:
                # Get user's partner record which contains name information
                partner = current_user.partner_id
                if partner:
                    # Split name into first and last name
                    name_parts = partner.name.split(' ', 1) if partner.name else ['', '']
                    # Corrected assignment based on "LastName FirstName" convention
                    last_name_val = name_parts[0]
                    first_name_val = name_parts[1] if len(name_parts) > 1 else ''
                    
                    # Determine the approving colleague's name (manager if available)
                    approving_colleague_name_val = partner.name # Default to user's own name
                    employee = request.env['hr.employee'].sudo().search([('user_id', '=', current_user.id)], limit=1)
                    if employee and employee.parent_id:
                        manager_employee = employee.parent_id
                        if manager_employee.user_id and manager_employee.user_id.partner_id:
                            approving_colleague_name_val = manager_employee.user_id.partner_id.name
                        elif manager_employee.name: # Fallback to employee name if user_id or partner_id is not set on manager
                            approving_colleague_name_val = manager_employee.name
                        _logger.info(f"Manager found for user {current_user.name}: {approving_colleague_name_val}")
                    else:
                        _logger.info(f"No manager found for user {current_user.name}, defaulting approving colleague to user themselves.")

                    initial_data = {
                        "first_name": first_name_val,
                        "last_name": last_name_val,
                        "approving_colleague_name": approving_colleague_name_val,
                        "trip_basis_text": f"Business trip request based on Opportunity: {sale_order.name}",
                        "data": {}
                    }
                    
                    # Log the data structure for debugging
                    _logger.info(f"Creating initial submission_data with flat structure: {initial_data}")
                    
                    # Update form with initial submission data
                    form.sudo().write({
                        'submission_data': json.dumps(initial_data)
                    })
                    
                    # Explicitly call after_submit to process the initial data
                    form.sudo().after_submit()
                    
                    # DIRECT UPDATE: Also update the business.trip.data record directly to ensure values are set
                    # This section is now removed as form.after_submit() should handle BTD population
                    # from the initial_data structure set on the form.
                    # if trip_data:
                    #     try:
                    #         # Get all available fields from the model
                    #         business_trip_data_model = request.env['business.trip.data'].sudo()
                    #         available_fields = business_trip_data_model._fields.keys()
                            
                    #         # Try direct update with proper error handling
                    #         direct_update_vals = {}
                            
                    #         if 'first_name' in available_fields:
                    #             direct_update_vals['first_name'] = first_name
                            
                    #         if 'last_name' in available_fields:
                    #             direct_update_vals['last_name'] = last_name
                            
                    #         if 'approving_colleague_name' in available_fields:
                    #             direct_update_vals['approving_colleague_name'] = partner.name
                            
                    #         if 'travel_start_date' in available_fields:
                    #             direct_update_vals['travel_start_date'] = fields.Date.today()
                            
                    #         if 'is_hourly_trip' in available_fields:
                    #             direct_update_vals['is_hourly_trip'] = False
                                
                    #         # Include common trip fields
                    #         if 'destination' in available_fields:
                    #             direct_update_vals['destination'] = ""  # Empty placeholder to be filled by user
                                
                    #         if 'purpose' in available_fields:
                    #             direct_update_vals['purpose'] = ""  # Empty placeholder to be filled by user
                            
                    #         # Log what we're about to do
                    #         _logger.info(f"About to update business.trip.data record {trip_data.id} with values: {direct_update_vals}")
                            
                    #         # Directly update the record with sudo permissions
                    #         if direct_update_vals:
                    #             # Update the record with a new cr.commit() to ensure it's saved
                    #             trip_data.sudo().write(direct_update_vals)
                    #             request.env.cr.commit()
                    #             _logger.info(f"Successfully updated business.trip.data record {trip_data.id}")
                                
                    #             # Double-check that the values were actually set
                    #             trip_data_refreshed = request.env['business.trip.data'].sudo().browse(trip_data.id)
                    #             _logger.info(f"Verification after update - first_name: {trip_data_refreshed.first_name}, last_name: {trip_data_refreshed.last_name}")
                    #         else:
                    #             _logger.warning(f"No valid fields found to update business.trip.data record {trip_data.id}")
                    #     except Exception as e:
                    #         _logger.error(f"Error updating business.trip.data record: {e}")
                    #         # Continue execution even if the direct update fails
                    
                    _logger.info(f"Initialized form {form.id} with basic submission data and called after_submit()")
            
        except Exception as e:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.error(f"Error processing business.trip.data record: {e}")

        # Redirect to the "My Business Trip Forms" list, with the new form selected.
        action = request.env.ref('custom_business_trip_management.action_view_my_business_trip_forms')
        menu_id = request.env.ref('custom_business_trip_management.menu_view_my_business_trip_forms').id
        company_id = request.env.company.id
        cids_param = f"&cids={company_id}" if company_id else ""

        redirect_url = (
            f"/web#action={action.id}"
            f"&model=formio.form"
            f"&view_type=form"  # Initially display the form in form view
            f"&id={form.id}"
            f"&menu_id={menu_id}{cids_param}"
        )
        return werkzeug.utils.redirect(redirect_url)

        
    @http.route('/business_trip/create_standalone', type='http', auth='user')
    def create_standalone_trip_form(self, **kwargs):
        """
        Creates a business trip form without a link to a quotation.
        
        Note: After creating the form, we ensure business.trip.data record is created
        to fix issues with missing data in fields like 'Requester Name' and 'Approving Colleague'.
        This is necessary because the regular formio submit handler that calls after_submit() 
        is not triggered during form creation via this route.
        """
        builder = request.env['formio.builder'].sudo().search([
            ('state', '=', 'CURRENT'),
            ('res_model_id.model', '=', 'sale.order') 
        ], limit=1)

        if not builder:
            return request.not_found('custom_business_trip_management.template_no_builder')

        form_vals = {
            'builder_id': builder.id,
            'title': f'Standalone Business Trip Form - {request.env.user.name}',
            'user_id': request.env.user.id,
            'state': 'DRAFT',
        }
        form = request.env['formio.form'].sudo().create(form_vals)

        # Ensure the business.trip.data record is created
        # Create the business.trip.data record and process initial data
        try:
            import logging
            _logger = logging.getLogger(__name__)
            
            # Check if the business.trip.data record was created during form creation
            trip_data = request.env['business.trip.data'].sudo().search([('form_id', '=', form.id)], limit=1)
            if not trip_data:
                # Create the record if not exists
                trip_data = request.env['business.trip.data'].sudo().create({
                    'form_id': form.id,
                })
                _logger.info(f"Created business.trip.data record for form {form.id} during controller execution")
            
            # Create initial submission_data structure with user information
            # This helps after_submit to properly extract basic data even before user fills the form
            current_user = request.env.user
            if current_user and trip_data:
                # Get user's partner record which contains name information
                partner = current_user.partner_id
                if partner:
                    # Split name into first and last name
                    name_parts = partner.name.split(' ', 1) if partner.name else ['', '']
                    # Corrected assignment based on "LastName FirstName" convention
                    last_name_val = name_parts[0]
                    first_name_val = name_parts[1] if len(name_parts) > 1 else ''
                    
                    # Determine the approving colleague's name (manager if available)
                    approving_colleague_name_val = partner.name # Default to user's own name
                    employee = request.env['hr.employee'].sudo().search([('user_id', '=', current_user.id)], limit=1)
                    if employee and employee.parent_id:
                        manager_employee = employee.parent_id
                        if manager_employee.user_id and manager_employee.user_id.partner_id:
                            approving_colleague_name_val = manager_employee.user_id.partner_id.name
                        elif manager_employee.name: # Fallback to employee name if user_id or partner_id is not set on manager
                            approving_colleague_name_val = manager_employee.name
                        _logger.info(f"Manager found for user {current_user.name}: {approving_colleague_name_val}")
                    else:
                        _logger.info(f"No manager found for user {current_user.name}, defaulting approving colleague to user themselves.")

                    initial_data = {
                        "first_name": first_name_val,
                        "last_name": last_name_val,
                        "approving_colleague_name": approving_colleague_name_val,
                        "trip_basis_text": "Standalone business trip request",
                        "data": {}
                    }
                    
                    # Log the data structure for debugging
                    _logger.info(f"Creating initial submission_data with flat structure: {initial_data}")
                    
                    # Update form with initial submission data
                    form.sudo().write({
                        'submission_data': json.dumps(initial_data)
                    })
                    
                    # Explicitly call after_submit to process the initial data
                    form.sudo().after_submit()
                    
                    # DIRECT UPDATE: Also update the business.trip.data record directly to ensure values are set
                    # This section is now removed as form.after_submit() should handle BTD population
                    # from the initial_data structure set on the form.
                    # if trip_data:
                    #     try:
                    #         # Get all available fields from the model
                    #         business_trip_data_model = request.env['business.trip.data'].sudo()
                    #         available_fields = business_trip_data_model._fields.keys()
                            
                    #         # Try direct update with proper error handling
                    #         direct_update_vals = {}
                            
                    #         if 'first_name' in available_fields:
                    #             direct_update_vals['first_name'] = first_name
                            
                    #         if 'last_name' in available_fields:
                    #             direct_update_vals['last_name'] = last_name
                            
                    #         if 'approving_colleague_name' in available_fields:
                    #             direct_update_vals['approving_colleague_name'] = partner.name
                            
                    #         if 'travel_start_date' in available_fields:
                    #             direct_update_vals['travel_start_date'] = fields.Date.today()
                            
                    #         if 'is_hourly_trip' in available_fields:
                    #             direct_update_vals['is_hourly_trip'] = False
                                
                    #         # Include common trip fields
                    #         if 'destination' in available_fields:
                    #             direct_update_vals['destination'] = ""  # Empty placeholder to be filled by user
                                
                    #         if 'purpose' in available_fields:
                    #             direct_update_vals['purpose'] = ""  # Empty placeholder to be filled by user
                            
                    #         # Log what we're about to do
                    #         _logger.info(f"About to update business.trip.data record {trip_data.id} with values: {direct_update_vals}")
                            
                    #         # Directly update the record with sudo permissions
                    #         if direct_update_vals:
                    #             # Update the record with a new cr.commit() to ensure it's saved
                    #             trip_data.sudo().write(direct_update_vals)
                    #             request.env.cr.commit()
                    #             _logger.info(f"Successfully updated business.trip.data record {trip_data.id}")
                                
                    #             # Double-check that the values were actually set
                    #             trip_data_refreshed = request.env['business.trip.data'].sudo().browse(trip_data.id)
                    #             _logger.info(f"Verification after update - first_name: {trip_data_refreshed.first_name}, last_name: {trip_data_refreshed.last_name}")
                    #         else:
                    #             _logger.warning(f"No valid fields found to update business.trip.data record {trip_data.id}")
                    #     except Exception as e:
                    #         _logger.error(f"Error updating business.trip.data record: {e}")
                    #         # Continue execution even if the direct update fails
                    
                    _logger.info(f"Initialized form {form.id} with basic submission data and called after_submit()")
            
        except Exception as e:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.error(f"Error processing business.trip.data record: {e}")

        # Redirect to the "My Business Trip Forms" list, with the new form selected.
        action = request.env.ref('custom_business_trip_management.action_view_my_business_trip_forms')
        menu_id = request.env.ref('custom_business_trip_management.menu_view_my_business_trip_forms').id
        company_id = request.env.company.id
        cids_param = f"&cids={company_id}" if company_id else ""

        redirect_url = (
            f"/web#action={action.id}"
            f"&model=formio.form"
            f"&view_type=form" 
            f"&id={form.id}"
            f"&menu_id={menu_id}{cids_param}"
        )
        return werkzeug.utils.redirect(redirect_url)

    @http.route('/formio/form/<string:uuid>/submit', type='json', auth='user', website=True)
    def submit(self, uuid, **kwargs):
        """Submit handler. Override to add additional logging and processing."""
        _logger.info("====================== START /formio/form/submit ======================")
        _logger.info(f"Form UUID: {uuid}")
        _logger.info(f"Current user: {request.env.user.name}")
        _logger.info(f"Kwargs: {list(kwargs.keys())}")
        
        form = self._get_form(uuid, 'write')
        if not form:
            _logger.error(f"Form with UUID {uuid} not found or no write access")
            return {'success': False, 'message': 'Form not found or access denied'}
            
        # Get the data from kwargs.get('data')
        if not kwargs.get('data'):
            _logger.error(f"No data found in form submission for form {form.id}")
            
        # Log detailed submission data for debugging
        submission_data = kwargs.get('data')
        _logger.info(f"Submission data type: {type(submission_data)}")
        
        # Call the parent controller method - using form_submit to match parent method name
        result = super(BusinessTripRedirect, self).form_submit(uuid, **kwargs)
        
        try:
            # We want to update the trip_status to 'submitted' if form was submitted
            if form.state == FORM_STATE_COMPLETE and form.trip_status == 'draft':
                _logger.info(f"Form {form.id} state is COMPLETE and trip_status is draft, updating to 'submitted'")
                form.sudo().write({'trip_status': 'submitted'})
                _logger.info(f"Updated trip_status to 'submitted' for form {form.id}")
                
            # For returned forms, handle if this is a resubmission
            if form.state == FORM_STATE_COMPLETE and form.trip_status == 'returned':
                # Check if form was being edited in returned state
                if form.edit_in_returned_state:
                    _logger.info(f"Form {form.id} was edited in returned state, resetting flag")
                    form.sudo().write({'edit_in_returned_state': False})
                    _logger.info(f"Reset edit_in_returned_state flag for form {form.id}")
                
            # The form.after_submit() method (called by super().form_submit() above)
            # is already responsible for calling trip_data.process_submission_data().
            # So, the explicit call here is redundant and has been removed.
            # trip_data = request.env['business.trip.data'].sudo().search([('form_id', '=', form.id)], limit=1)
            # if trip_data:
            #     _logger.info(f"Found business.trip.data record {trip_data.id} for form {form.id}")
            #     try:
            #         # Parse the data from kwargs (not from form.submission_data which might not be updated yet)
            #         if submission_data: # submission_data was defined as kwargs.get('data') earlier
            #             _logger.info(f"Processing submission data for business.trip.data {trip_data.id}")
            #             trip_data.process_submission_data(submission_data)
            #     except Exception as e:
            #         _logger.error(f"Error processing business.trip.data from submitted data: {e}")
        except Exception as e:
            _logger.error(f"Error in business trip form submit handler: {e}")
            
        _logger.info("====================== END /formio/form/submit ======================")
        return result
