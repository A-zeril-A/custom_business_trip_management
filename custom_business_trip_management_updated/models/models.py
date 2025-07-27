from odoo import models, fields, api

class BusinessTrip(models.Model):
    _name = 'custom_business_trip_management.business_trip'
    _description = 'Business Trip'

    name = fields.Char(string='Name', required=True)
    sale_order_id = fields.Many2one('sale.order', string='Sales Order')
    sale_order_name = fields.Char(string='Quotation Number', related='sale_order_id.name', store=True)
    partner_id = fields.Many2one('res.partner', string='Customer', related='sale_order_id.partner_id', store=True)
    # ... other fields

class ResCompany(models.Model):
    _inherit = 'res.company'
    
    require_finance_approval_for_trips = fields.Boolean(
        string="Require Finance Approval for Business Trips",
        default=True,
        help="If enabled, business trip requests will require approval from finance department after manager approval"
    )
    
    
class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'
    
    require_finance_approval_for_trips = fields.Boolean(
        related='company_id.require_finance_approval_for_trips', 
        readonly=False,
        string="Require Finance Approval for Business Trips",
        help="If enabled, business trip requests will require approval from finance department after manager approval"
    )
