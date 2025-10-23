from odoo import models, fields, api

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'
    
    require_finance_approval_for_trips = fields.Boolean(
        related='company_id.require_finance_approval_for_trips',
        readonly=False,
        string='Require Finance Approval for Business Trips',
        help='If checked, business trip requests will require finance department approval after manager approval.'
    ) 
    
    undo_expense_approval_days_limit = fields.Integer(
        related='company_id.undo_expense_approval_days_limit',
        readonly=False,
        string="Undo Expense Approval Deadline (Days)",
        help="Number of days after expense approval within which the approval can be undone. Set to 0 for no time limit."
    )
    
    # Expense submission reminder settings
    expense_reminder_interval = fields.Integer(
        related='company_id.expense_reminder_interval',
        readonly=False,
        string="Expense Reminder Interval",
        help="Interval for sending expense submission reminders to employees."
    )
    
    expense_reminder_interval_type = fields.Selection(
        related='company_id.expense_reminder_interval_type',
        readonly=False,
        string="Expense Reminder Interval Type",
        help="Unit type for expense reminder interval."
    ) 