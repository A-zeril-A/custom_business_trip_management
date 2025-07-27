from odoo import models, fields, api

class BusinessTripForm(models.Model):
    _name = 'business.trip.form'
    _description = 'Business Trip Form Management'

    def create_trip_form(self, sale_order_ids=None):
        if not sale_order_ids:
            return False
            
        sale_order_id = sale_order_ids[0] if isinstance(sale_order_ids, list) else sale_order_ids
        sale_order = self.env['sale.order'].browse(sale_order_id)
        
        # Find or create formio.builder
        builder = self.env['formio.builder'].search([('name', '=', 'Business Trip Form')], limit=1)
        if not builder:
            builder = self.env['formio.builder'].create({
                'name': 'Business Trip Form',
                'title': 'Business Trip Form',
                'display': 'form',
                'components': [],
            })

        # Create formio.form
        form = self.env['formio.form'].create({
            'builder_id': builder.id,
            'title': f'Business Trip Form - {sale_order.name}',
            'sale_order_id': sale_order.id,
            'state': 'DRAFT',
            'user_id': self.env.user.id,
            'res_model_id': self.env.ref('sale.model_sale_order').id,
            'res_id': sale_order.id,
            'res_name': sale_order.name,
            'res_partner_id': sale_order.partner_id.id,
        })

        return {
            'type': 'ir.actions.act_window',
            'name': 'Business Trip Form',
            'res_model': 'formio.form',
            'res_id': form.id,
            'view_mode': 'formio_form',
            'view_id': False,
            'target': 'current',
        }