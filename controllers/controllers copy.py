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

            # Show only forms titled "Organizzatore di viaggio"
            domain = [('name', 'ilike', 'Organizzatore di viaggio')]
            domain_encoded = urllib.parse.quote(json.dumps(domain))

            return werkzeug.utils.redirect(
                 f"/web#action={action.id}&model=formio.form&view_type=list&domain={domain_encoded}"
            )


        # Otherwise, redirect to the first available current public form
        builder = request.env['formio.builder'].sudo().search([
            ('state', '=', 'CURRENT')
        ], limit=1)


        if builder and builder.name:
            return werkzeug.utils.redirect(builder.portal_url)
        else:
            return request.not_found()

