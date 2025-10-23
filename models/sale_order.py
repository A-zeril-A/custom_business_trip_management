from odoo import models, fields, api
import werkzeug

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    business_trip_ids = fields.One2many('business.trip', 'sale_order_id', string='Business Trips')

    def start_trip_for_quotation(self):
        """
        Creates a new Business Trip record linked to this sales order and
        opens the associated form.
        """
        self.ensure_one()

        # Create the main business trip record
        trip = self.env['business.trip'].create({
            'user_id': self.env.user.id,
            'sale_order_id': self.id, # Assuming we will add this field to business.trip
        })

        # The formio.form is now created automatically via business.trip logic
        # (We will implement this in the next steps)
        # For now, we assume the trip record has a link to it.
        # We need to add the logic to create the form and link it.

        # Find the form associated with the trip.
        # This part will be completed in the next refactoring steps.
        # For now, we'll just return a placeholder or open the trip record.
        
        # Open the newly created business trip record
        return {
            'type': 'ir.actions.act_window',
            'name': 'Business Trip Request',
            'res_model': 'business.trip',
            'res_id': trip.id,
            'view_mode': 'form',
            'target': 'current',
        } 