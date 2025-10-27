from odoo import http
from odoo.http import request
import werkzeug
import json
import urllib.parse
from odoo import fields
import logging

_logger = logging.getLogger(__name__)


class BusinessTripController(http.Controller):

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
        Creates a new business trip for the given quotation (sale.order)
        and redirects the user to the new form view to fill the details.
        """
        sale_order = request.env['sale.order'].sudo().browse(sale_order_id)
        if not sale_order.exists():
            return request.not_found()

        try:
            current_user = request.env.user
            travel_approver_id = request.env['res.users'].sudo().get_travel_approver_for_sale_order(current_user.id)

            trip_vals = {
                'user_id': current_user.id,
                'sale_order_id': sale_order.id,
                'manager_id': travel_approver_id,
                'purpose': f"Business trip request based on Opportunity: {sale_order.name}",
            }
            
            # The creation of business.trip.data is handled by the create method of business.trip
            business_trip = request.env['business.trip'].sudo().create(trip_vals)
            _logger.info(f"Created business trip {business_trip.id} for sale order {sale_order.id}")

            # Pre-fill some data in business_trip_data
            if business_trip.business_trip_data_id:
                partner = current_user.partner_id
                name_parts = partner.name.split(' ', 1) if partner.name else ['', '']
                last_name_val = name_parts[0]
                first_name_val = name_parts[1] if len(name_parts) > 1 else ''

                business_trip.business_trip_data_id.sudo().write({
                    'first_name': first_name_val,
                    'last_name': last_name_val,
                })

        except Exception as e:
            _logger.error(f"Error creating business trip: {e}", exc_info=True)
            return request.render('http_routing.http_error', {
                'status_code': 500,
                'status_message': 'Could not create the business trip request.'
            })

        # Redirect to the newly created business.trip record's form view
        action = request.env.ref('custom_business_trip_management.action_view_my_business_trip_forms')
        menu_id = request.env.ref('custom_business_trip_management.menu_view_my_business_trip_forms').id
        
        return werkzeug.utils.redirect(
            f"/web#action={action.id}&model=business.trip&view_type=form&id={business_trip.id}&menu_id={menu_id}"
        )
        
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


class BusinessTripApi(http.Controller):

    @http.route('/api/business_trip_data', type='json', auth='user', methods=['POST'])
    def get_business_trip_data(self, **kwargs):
        pass
