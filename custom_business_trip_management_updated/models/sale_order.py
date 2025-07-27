from odoo import models, fields, api
import werkzeug

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def start_trip_for_quotation(self):
        self.ensure_one()
        
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
            'title': f'Business Trip Form - {self.name}',
            'sale_order_id': self.id,
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web#active_id={form.id}&model=formio.form&view_type=formio_form&id={form.id}&cids=1',
            'target': 'self',
        } 