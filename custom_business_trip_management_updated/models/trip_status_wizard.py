from odoo import api, fields, models

class FormioFormTripStatusWizard(models.TransientModel):
    _name = 'formio.form.trip.status.wizard'
    _description = 'Wizard to change trip status'
    
    form_id = fields.Many2one('formio.form', string='Form', required=True)
    current_status = fields.Selection(related='form_id.trip_status', string='Current Status', readonly=True)
    new_status = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted for Approval'),
        ('manager_approved', 'Manager Approved'),
        ('rejected', 'Rejected'),
        ('approved', 'Approved'),
        ('in_progress', 'Trip In Progress'),
        ('returned', 'Returned from Trip'),
        ('expense_waiting', 'Expense Approval Pending'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled')
    ], string='New Status', required=True)
    
    def apply_status_change(self):
        """Apply the status change to the form"""
        self.ensure_one()
        if self.new_status != self.current_status:
            self.form_id.write({'trip_status': self.new_status})
            # Log the change in the chatter
            self.form_id.message_post(
                body=f"Status manually changed from '{self.current_status}' to '{self.new_status}' by {self.env.user.name}"
            )
        return {'type': 'ir.actions.act_window_close'} 