from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    travel_approver_sale_order_user_id = fields.Many2one(
        related="company_id.business_trip_sale_order_approver_id",
        readonly=False,
        string="Travel Approver (Sale Order)",
        help=(
            "If set, sale-order travel requests go to this user. Leave empty "
            "to use each employee's direct manager. A requester is never "
            "assigned as their own approver."
        ),
    )

    travel_approver_standalone_user_id = fields.Many2one(
        related="company_id.business_trip_standalone_approver_id",
        readonly=False,
        string="Travel Approver (Standalone)",
        help="Default approver for standalone business trips.",
    )

    business_trip_organizer_ids = fields.Many2many(
        related="company_id.business_trip_organizer_ids",
        readonly=False,
        string="Business Trip Organizers",
        help=(
            "Users the Travel Approver can pick as trip organizer. Removing "
            "a user with open trips hands them over to the single remaining "
            "organizer, or requires explicit reassignment first."
        ),
    )

    business_trip_sale_order_expense_reviewer_id = fields.Many2one(
        related="company_id.business_trip_sale_order_expense_reviewer_id",
        readonly=False,
        string="Expense Reviewer (Sale Order)",
    )

    business_trip_standalone_expense_reviewer_id = fields.Many2one(
        related="company_id.business_trip_standalone_expense_reviewer_id",
        readonly=False,
        string="Expense Reviewer (Standalone)",
    )
    
    undo_expense_approval_days_limit = fields.Integer(
        related='company_id.undo_expense_approval_days_limit',
        readonly=False,
        string="Expense Approval Reopen Window (Days)",
        help="Number of days after expense approval during which an authorized user can reopen expense review. Set to 0 for no time limit."
    )
    
    # Expense submission reminder settings
    expense_reminder_interval = fields.Integer(
        related='company_id.expense_reminder_interval',
        readonly=False,
        string="Employee Reminder Repeat",
        help="How often each employee should receive grouped reminder emails while the expense is still unresolved. Set to 0 to disable recurring employee reminders after the first reminder."
    )
    
    expense_reminder_interval_type = fields.Selection(
        related='company_id.expense_reminder_interval_type',
        readonly=False,
        string="Employee Reminder Cadence Unit",
        help="Time unit used for the recurring employee reminder cadence."
    ) 

    employee_expense_reminder_delay = fields.Integer(
        related='company_id.employee_expense_reminder_delay',
        readonly=False,
        string="Employee First Reminder",
        help="How long after the trip ends the employee should receive the first grouped expense reminder email and To Do activity."
    )

    employee_expense_reminder_delay_type = fields.Selection(
        related='company_id.employee_expense_reminder_delay_type',
        readonly=False,
        string="Employee Expense Follow-up Delay Unit",
        help="Time unit used for the employee expense follow-up delay."
    )

    employee_expense_digest_send_hour = fields.Integer(
        related='company_id.employee_expense_digest_send_hour',
        readonly=False,
        string="Employee Reminder Time",
        help="Hour of day (0-23) when employee reminder emails and To Do items should become visible."
    )

    organizer_expense_escalation_delay = fields.Integer(
        related='company_id.organizer_expense_escalation_delay',
        readonly=False,
        string="Expense Reviewer Follow-up Starts",
        help="How long after the trip ends the configured expense reviewer should start receiving grouped reminders if the employee still has not clarified the trip expenses."
    )

    organizer_expense_escalation_delay_type = fields.Selection(
        related='company_id.organizer_expense_escalation_delay_type',
        readonly=False,
        string="Expense Reviewer Follow-up Delay Unit",
        help="Time unit used for the expense reviewer follow-up delay."
    )

    organizer_expense_digest_send_hour = fields.Integer(
        related='company_id.organizer_expense_digest_send_hour',
        readonly=False,
        string="Expense Reviewer Reminder Time",
        help="Hour of day (0-23) when expense reviewer follow-up reminders should be delivered."
    )

    organizer_expense_reminder_interval = fields.Integer(
        related='company_id.organizer_expense_reminder_interval',
        readonly=False,
        string="Expense Reviewer Reminder Repeat",
        help="How often the configured expense reviewer should receive grouped follow-up reminders while the expense is still unresolved. Set to 0 to disable recurring reviewer reminders after the first follow-up."
    )

    organizer_expense_reminder_interval_type = fields.Selection(
        related='company_id.organizer_expense_reminder_interval_type',
        readonly=False,
        string="Expense Reviewer Reminder Cadence Unit",
        help="Time unit used for the recurring expense reviewer follow-up cadence."
    )