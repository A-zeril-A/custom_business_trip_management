# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class BusinessTripExpenseLine(models.Model):
    _name = 'business.trip.expense.line'
    _description = 'Business Trip Expense Line Item'
    _order = 'date desc, id desc'

    trip_id = fields.Many2one('business.trip', string='Business Trip', required=True, ondelete='cascade', index=True)
    
    name = fields.Char(string='Description', required=True)
    date = fields.Date(string='Date', required=True, default=fields.Date.context_today)
    
    # Using product_id allows for categorization and accounting integration
    product_id = fields.Many2one('product.product', string='Category', required=True,
                                 domain="[('can_be_expensed', '=', True)]")

    # This allows for detailed cost calculation, e.g., 2 nights * 150 EUR/night
    quantity = fields.Float(string='Quantity', required=True, digits='Product Unit of Measure', default=1.0)
    unit_amount = fields.Monetary(string='Unit Price', required=True, currency_field='currency_id')
    
    # The total amount is computed
    total_amount = fields.Monetary(string='Total Amount', currency_field='currency_id',
                                   compute='_compute_total_amount', store=True, readonly=True)

    currency_id = fields.Many2one('res.currency', string='Currency', related='trip_id.currency_id', readonly=True)

    attachment_ids = fields.Many2many(
        'ir.attachment',
        'business_trip_expense_line_ir_attachments_rel',
        'expense_line_id', 'attachment_id',
        string='Receipts',
        help="Attach receipts or other documents related to this expense."
    )
    
    notes = fields.Text(string='Notes')

    @api.depends('quantity', 'unit_amount')
    def _compute_total_amount(self):
        """Computes the total amount from quantity and unit price."""
        for line in self:
            line.total_amount = line.quantity * line.unit_amount

    @api.constrains('quantity', 'unit_amount')
    def _check_amounts(self):
        """Ensure that expense amounts are positive."""
        for record in self:
            if record.quantity <= 0:
                raise ValidationError(_("Quantity must be positive."))
            if record.unit_amount < 0:
                raise ValidationError(_("Unit price cannot be negative."))
                
    @api.onchange('product_id')
    def _onchange_product_id(self):
        """
        When the product (category) is changed, update the description
        and unit price with the product's default values.
        """
        if self.product_id:
            if not self.name:
                self.name = self.product_id.display_name
            self.unit_amount = self.product_id.standard_price 