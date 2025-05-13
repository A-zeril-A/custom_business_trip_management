from odoo import api, fields, models
from odoo.exceptions import ValidationError

class FormioFormRequiredFieldsWizard(models.TransientModel):
    _name = 'formio.form.required.fields.wizard'
    _description = 'Wizard to edit required fields for business trip forms'
    
    form_id = fields.Many2one('formio.form', string='Form', required=True)
    destination = fields.Char(string='Destination', required=True)
    purpose = fields.Text(string='Purpose of Trip', required=True)
    travel_start_date = fields.Date(string='Start Date', required=True)
    travel_end_date = fields.Date(string='End Date', required=True)
    expected_cost = fields.Float(string='Expected Cost', required=True)
    
    @api.constrains('travel_start_date', 'travel_end_date')
    def _check_dates(self):
        for wizard in self:
            if wizard.travel_start_date and wizard.travel_end_date and wizard.travel_start_date > wizard.travel_end_date:
                raise ValidationError("The travel end date must be after the travel start date.")
    
    def apply_changes(self):
        """Apply changes to the form"""
        self.ensure_one()
        self.form_id.write({
            'destination': self.destination,
            'purpose': self.purpose,
            'travel_start_date': self.travel_start_date,
            'travel_end_date': self.travel_end_date,
            'expected_cost': self.expected_cost,
        })
        # Log the changes
        self.form_id.message_post(body="Required fields were updated manually.")
        return {'type': 'ir.actions.act_window_close'} 