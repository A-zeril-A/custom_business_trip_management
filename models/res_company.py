from odoo import models, fields, api

class ResCompany(models.Model):
    _inherit = 'res.company'
    
    require_finance_approval_for_trips = fields.Boolean(
        string='Require Finance Approval for Business Trips',
        default=True,
        help='If checked, business trip requests will require finance department approval after manager approval.'
    )
    
    undo_expense_approval_days_limit = fields.Integer(
        string="Undo Expense Approval Deadline (Days)",
        default=7,
        help="Number of days after expense approval within which the approval can be undone. Set to 0 for no time limit."
    )
    
    # Expense submission reminder settings
    expense_reminder_interval = fields.Integer(
        string="Expense Reminder Interval",
        default=7,
        help="Interval for sending expense submission reminders to employees."
    )
    
    expense_reminder_interval_type = fields.Selection([
        ('minutes', 'Minutes'),
        ('days', 'Days')
    ], string="Expense Reminder Interval Type", default='days',
       help="Unit type for expense reminder interval.") 