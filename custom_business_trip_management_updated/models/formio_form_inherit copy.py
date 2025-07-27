from odoo import models, fields

class FormioForm(models.Model):
    _inherit = 'formio.form'

    # Travel-specific status field (used only for business trip forms)
    trip_status = fields.Selection([
        ('to_be_started', 'To be Started'),
        ('ongoing', 'Ongoing'),
        ('finalised', 'Finalised'),
        ('blocked', 'Blocked'),
    ], string="Travel Status", default='to_be_started')

    # Final total cost of the business trip
    final_total_cost = fields.Monetary(string="Final Total Cost")

    # Currency of the trip cost
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        default=lambda self: self.env.company.currency_id.id
    )


