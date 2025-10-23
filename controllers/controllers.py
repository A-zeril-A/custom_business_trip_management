from odoo import http
from odoo.http import request
import werkzeug
import json
import urllib.parse
from odoo import fields
import logging

_logger = logging.getLogger(__name__)

# Import from formio base controller
try:
    from odoo.addons.formio.controllers.main import FormioController, FORM_STATE_COMPLETE
except ImportError:
    # Fallback if formio module is not available
    from odoo import http
    FormioController = http.Controller
    FORM_STATE_COMPLETE = 'COMPLETE'

class BusinessTripRedirect(FormioController):

    @http.route('/business_trip/entry', type='http', auth='user')
    def redirect_user_by_role(self, **kwargs):
        """
        Redirects users to appropriate business trip views based on their role.

        Routing logic:
        1. System Admin → "Assigned to Me" view with all business trips
        2. Manager/Organizer → "Assigned to Me" view with trips assigned to them
        3. Regular User → "My Business Trip Forms" view with only their own trips
        
        This provides role-appropriate entry points while maintaining proper access control.

        Parameters:
            **kwargs: Optional keyword arguments passed from the route (unused).

        Returns:
            werkzeug.wrappers.Response: A 302 redirect response to the appropriate view.
        """
        user = request.env.user

        # Admin and Manager/Organizer go to "Assigned to Me", regular users go to "My Business Trip Forms"
        if user.has_group('base.group_system'):
            # Admin users: go to "Assigned to Me" and show all business trips
            action = request.env.ref('custom_business_trip_management.action_all_assigned_business_trip_forms')
            menu = request.env.ref('custom_business_trip_management.menu_all_assigned_business_trip_forms')
            domain = []
        elif user.has_group('custom_business_trip_management.group_business_trip_manager') or user.has_group('custom_business_trip_management.group_business_trip_organizer'):
            # Manager/Organizer users: go to "Assigned to Me" and show trips assigned to them
            action = request.env.ref('custom_business_trip_management.action_all_assigned_business_trip_forms')
            menu = request.env.ref('custom_business_trip_management.menu_all_assigned_business_trip_forms')
            domain = [
                '|', 
                ('user_id', '=', user.id), 
                '|',
                '&', ('manager_id', '=', user.id), ('trip_status', '!=', 'draft'),
                ('organizer_id', '=', user.id)
            ]
        else:
            # Regular users: go to "My Business Trip Forms" and show only their own trips
            action = request.env.ref('custom_business_trip_management.action_view_my_business_trip_forms')
            menu = request.env.ref('custom_business_trip_management.menu_view_my_business_trip_forms')
            domain = [('user_id', '=', user.id)]

        domain_encoded = urllib.parse.quote(json.dumps(domain))

        # All actions now use business.trip model for consistency
        model = 'business.trip'
            
        return werkzeug.utils.redirect(
            f"/web#action={action.id}&model={model}&view_type=list&domain={domain_encoded}&menu_id={menu.id}"
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
        Creates a new business trip for the given quotation (sale.order).
        This will automatically create the associated formio.form and business.trip.data records.
        """
        # Fetch the target quotation
        sale_order = request.env['sale.order'].sudo().browse(sale_order_id)
        if not sale_order.exists():
            return request.not_found()

        try:
            # Create the business.trip record - this will automatically create formio.form and business.trip.data
            business_trip = request.env['business.trip'].sudo().create({
                'user_id': request.env.user.id,
                'sale_order_id': sale_order.id,
            })
            
            # Get the automatically created form
            form = business_trip.formio_form_id
            if not form:
                raise Exception("Form was not created automatically by business.trip")
                
            _logger.info(f"Created business trip {business_trip.id} with form {form.id}")
            
            # Set initial submission data with user information
            current_user = request.env.user
            partner = current_user.partner_id
            if partner:
                # Split name into first and last name
                name_parts = partner.name.split(' ', 1) if partner.name else ['', '']
                last_name_val = name_parts[0]
                first_name_val = name_parts[1] if len(name_parts) > 1 else ''
                
                # Determine the Travel Approver for Sale Order related trips
                travel_approver_id = request.env['res.users'].sudo().get_travel_approver_for_sale_order(current_user.id)
                _logger.info(f"Selected Travel Approver for sale order: {travel_approver_id}")

                # Get Travel Approver name for formio field
                travel_approver_name = ""
                if travel_approver_id:
                    travel_approver_user = request.env['res.users'].sudo().browse(travel_approver_id)
                    if travel_approver_user:
                        travel_approver_name = travel_approver_user.name

                        # Add user to Business Trip Manager group if not already a member
                        manager_group = request.env.ref('custom_business_trip_management.group_business_trip_manager', raise_if_not_found=False)
                        if manager_group and not travel_approver_user.has_group('custom_business_trip_management.group_business_trip_manager'):
                            travel_approver_user.sudo().write({'groups_id': [(4, manager_group.id)]})

                initial_data = {
                    "first_name": first_name_val,
                    "last_name": last_name_val,
                    "trip_basis_text": f"Business trip request based on Opportunity: {sale_order.name}",
                    "approving_colleague_name": travel_approver_name,
                    "data": {}
                }
                
                # Update form with initial submission data
                form.sudo().write({
                    'submission_data': json.dumps(initial_data)
                })
                
                # Process the initial data
                form.sudo().after_submit()
                _logger.info(f"Initialized form {form.id} with basic submission data")
                
                # Set the Travel Approver on the business trip record
                if travel_approver_id:
                    business_trip = request.env['business.trip'].sudo().search([('formio_form_id', '=', form.id)], limit=1)
                    if business_trip:
                        business_trip.sudo().write({'manager_id': travel_approver_id})
                        _logger.info(f"Set Travel Approver {travel_approver_id} for business trip {business_trip.id}")
                else:
                    _logger.warning(f"No Travel Approver found for user {current_user.id}")
            
        except Exception as e:
            _logger.error(f"Error creating business trip: {e}")
            return request.not_found()

        # Redirect to the newly created business.trip record's form view
        action = request.env.ref('custom_business_trip_management.action_view_my_business_trip_forms')
        menu_id = request.env.ref('custom_business_trip_management.menu_view_my_business_trip_forms').id
        company_id = request.env.company.id
        cids_param = f"&cids={company_id}" if company_id else ""

        redirect_url = (
            f"/web#action={action.id}"
            f"&model=business.trip"
            f"&view_type=form"
            f"&id={business_trip.id}"
            f"&menu_id={menu_id}{cids_param}"
        )
        return werkzeug.utils.redirect(redirect_url)

        
    @http.route('/business_trip/create_standalone', type='http', auth='user')
    def create_standalone_trip_form(self, **kwargs):
        """
        Redirects to project selection wizard for standalone business trips.
        """
        try:
            # Create and open the project selection wizard
            wizard = request.env['business.trip.project.selection.wizard'].sudo().create({})
            
            action = request.env.ref('custom_business_trip_management.action_business_trip_project_selection_wizard')
            menu_id = request.env.ref('custom_business_trip_management.menu_view_my_business_trip_forms').id
            company_id = request.env.company.id
            cids_param = f"&cids={company_id}" if company_id else ""

            redirect_url = (
                f"/web#action={action.id}"
                f"&model=business.trip.project.selection.wizard"
                f"&view_type=form" 
                f"&id={wizard.id}"
                f"&menu_id={menu_id}{cids_param}"
            )
            return werkzeug.utils.redirect(redirect_url)
            
        except Exception as e:
            _logger.error(f"Error creating project selection wizard: {e}")
            return request.not_found()

    @http.route('/formio/form/<string:uuid>/submit', type='json', auth="user", methods=['POST'], website=True, csrf=False)
    def form_submit(self, uuid, **post):
        """
        Overrides the base formio controller's submission method.
        This version is declared as type='json' to match the client-side request,
        resolving the 'http' vs 'json' type mismatch error.

        1. Calls the data-saving logic from the parent class.
        2. Fetches the computed redirect URL from the form record.
        3. Returns a Python dictionary, which Odoo automatically converts to a JSON response.
        """
        _logger.info(f"CUSTOM JSON form_submit: Intercepting submission for form UUID {uuid}.")

        # The base controller's `form_submit` handles the data writing.
        super(BusinessTripRedirect, self).form_submit(uuid, **post)
        _logger.info("CUSTOM JSON form_submit: Original data submission logic executed.")

        # Fetch the form again to get the computed redirect URL.
        form = request.env['formio.form'].sudo().search([('uuid', '=', uuid)], limit=1)
        if not form:
            _logger.warning(f"CUSTOM JSON form_submit: Could not find form with UUID {uuid} after submission.")
            return {'error': 'form_not_found'}

        # Get the redirect URL from the computed field.
        redirect_url = form.redirect_after_submit
        _logger.info(f"CUSTOM JSON form_submit: Computed redirect URL is: {redirect_url}")

        response_data = {}
        if redirect_url:
            response_data['redirect'] = redirect_url
            _logger.info(f"CUSTOM JSON form_submit: Returning JSON response with redirect: {json.dumps(response_data)}")
        else:
            _logger.warning("CUSTOM JSON form_submit: No redirect URL found. Returning success status.")
            response_data['status'] = 'OK'

        # For a 'json' route, we simply return the dictionary.
        return response_data


class BusinessTripApi(http.Controller):

    @http.route('/api/business_trip_data', type='json', auth='user', methods=['POST'])
    def get_business_trip_data(self, **kwargs):
        pass
