from odoo import models, fields, api

class ResCompany(models.Model):
    _inherit = 'res.company'
    
    require_finance_approval_for_trips = fields.Boolean(
        string='Require Finance Approval for Business Trips',
        default=True,
        help='If checked, business trip requests will require finance department approval after manager approval.'
    ) 