from odoo import models, fields, api

class BusinessTrip(models.Model):
    _name = 'custom_business_trip_management.business_trip'
    _description = 'Business Trip'

    name = fields.Char(string='Name', required=True)
    sale_order_id = fields.Many2one('sale.order', string='Sales Order')
    sale_order_name = fields.Char(string='Quotation Number', related='sale_order_id.name', store=True)
    partner_id = fields.Many2one('res.partner', string='Customer', related='sale_order_id.partner_id', store=True)
    # ... other fields
