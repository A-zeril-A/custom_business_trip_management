from odoo import http
from odoo.http import request
import werkzeug
import json
import urllib.parse

class BusinessTripRedirect(http.Controller):

    @http.route('/business_trip/entry', type='http', auth='user')
    def redirect_user_by_role(self, **kwargs):
        user = request.env.user

        # Admin users → internal list of business trip forms
        if user.has_group('base.group_system'):
            action = request.env.ref('custom_business_trip_management.action_view_business_trip_forms')
            menu = request.env.ref('custom_business_trip_management.menu_view_business_trip_forms')

            domain = [('name', 'ilike', 'Organizzatore di viaggio')]
            domain_encoded = urllib.parse.quote(json.dumps(domain))

            return werkzeug.utils.redirect(
                f"/web#action={action.id}&model=formio.form&view_type=list&domain={domain_encoded}&menu_id={menu.id}"
            )

        # Regular users → go to Quotations list (Sales Orders)
        action = request.env.ref('custom_business_trip_management.action_sale_order_trip_custom')
        menu = request.env.ref('custom_business_trip_management.menu_select_quotation_for_trip')
        return werkzeug.utils.redirect(
            f"/web#action={action.id}&model=sale.order&view_type=list&menu_id={menu.id}"
        )

    @http.route('/business_trip/start/<int:sale_order_id>', type='http', auth='user')
    def start_trip_for_quotation(self, sale_order_id, **kwargs):
        # Get the target quotation
        sale_order = request.env['sale.order'].sudo().browse(sale_order_id)
        if not sale_order.exists():
            return request.not_found()

        # Get the builder first
        builder = request.env['formio.builder'].sudo().search([
            ('state', '=', 'CURRENT'),
            ('res_model_id.model', '=', 'sale.order')
        ], limit=1)

        if not builder:
            return request.not_found('custom_business_trip_management.template_no_builder')

        # Debug logs
        _logger = request.env['ir.logging'].sudo()
        _logger.create({
            'name': 'Business Trip Debug',
            'type': 'server',
            'dbname': request.env.cr.dbname,
            'level': 'INFO',
            'message': f'Builder Info: ID={builder.id}, Name={builder.name}, Portal URL={builder.portal_url}',
            'path': 'controllers/controllers.py',
            'func': 'start_trip_for_quotation',
            'line': '50'
        })

        # Check if a form is already created for this quotation
        form = request.env['formio.form'].sudo().search([
            ('sale_order_id', '=', sale_order.id)
        ], limit=1)

        # If no form exists, create one
        if not form:
            form = request.env['formio.form'].sudo().create({
                'builder_id': builder.id,
                'title': builder.title,
                'user_id': request.env.user.id,
                'sale_order_id': sale_order.id,
                'res_id': sale_order.id,
                'res_model_id': request.env.ref('sale.model_sale_order').id,
                'res_name': sale_order.name,
                'res_partner_id': sale_order.partner_id.id,
            })

        # Redirect to the formio.form record (form view)
        return werkzeug.utils.redirect(
            f"/web#action=formio.action_formio_form&active_id={form.id}&model=formio.form&view_type=formio_form&id={form.id}&cids=1"
        )