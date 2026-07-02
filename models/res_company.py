from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError

class ResCompany(models.Model):
    _inherit = 'res.company'

    undo_expense_approval_days_limit = fields.Integer(
        string="Expense Approval Reopen Window (Days)",
        default=7,
        help="Number of days after expense approval during which an authorized user can reopen expense review. Set to 0 for no time limit."
    )

    # Expense submission reminder settings
    expense_reminder_interval = fields.Integer(
        string="Employee Reminder Repeat",
        default=7,
        help="How often each employee should receive grouped reminder emails while the expense is still unresolved. Set to 0 to disable recurring employee reminders after the first reminder."
    )

    expense_reminder_interval_type = fields.Selection([
        ('minutes', 'Minutes'),
        ('days', 'Days')
    ], string="Employee Reminder Cadence Unit", default='days',
       help="Time unit used for the recurring employee reminder cadence.")

    employee_expense_reminder_delay = fields.Integer(
        string="Employee First Reminder",
        default=1,
        help="How long after planning is finalized the employee should receive the first grouped expense reminder email and To Do activity."
    )

    employee_expense_reminder_delay_type = fields.Selection([
        ('minutes', 'Minutes'),
        ('days', 'Days')
    ], string="Employee Expense Follow-up Delay Unit", default='days',
       help="Time unit used for the employee expense follow-up delay.")

    employee_expense_digest_send_hour = fields.Integer(
        string="Employee Reminder Time",
        default=9,
        help="Hour of day (0-23) when employee reminder emails and To Do items should become visible."
    )

    organizer_expense_escalation_delay = fields.Integer(
        string="Expense Reviewer Follow-up Starts",
        default=14,
        help="How long after planning is finalized the configured expense reviewer should start receiving grouped reminders if the employee still has not clarified the trip expenses."
    )

    organizer_expense_escalation_delay_type = fields.Selection([
        ('minutes', 'Minutes'),
        ('days', 'Days')
    ], string="Expense Reviewer Follow-up Delay Unit", default='days',
       help="Time unit used for the expense reviewer follow-up delay.")

    organizer_expense_digest_send_hour = fields.Integer(
        string="Expense Reviewer Reminder Time",
        default=9,
        help="Hour of day (0-23) when expense reviewer follow-up reminders should be delivered."
    )

    organizer_expense_reminder_interval = fields.Integer(
        string="Expense Reviewer Reminder Repeat",
        default=7,
        help="How often the configured expense reviewer should receive grouped follow-up reminders while the expense is still unresolved. Set to 0 to disable recurring reviewer reminders after the first follow-up."
    )

    organizer_expense_reminder_interval_type = fields.Selection([
        ('minutes', 'Minutes'),
        ('days', 'Days')
    ], string="Expense Reviewer Reminder Cadence Unit", default='days',
       help="Time unit used for the recurring expense reviewer follow-up cadence.")

    @api.model
    def _reminder_delta(self, interval, interval_type):
        interval = max(interval or 0, 0)
        if interval_type == 'minutes':
            return timedelta(minutes=interval)
        return timedelta(days=interval)

    @api.constrains('employee_expense_digest_send_hour', 'organizer_expense_digest_send_hour')
    def _check_digest_send_hours(self):
        for company in self:
            for field_name, label in (
                ('employee_expense_digest_send_hour', 'Employee digest send hour'),
                ('organizer_expense_digest_send_hour', 'Organizer digest send hour'),
            ):
                hour = company[field_name]
                if hour is False:
                    continue
                if hour < 0 or hour > 23:
                    raise ValidationError(f"{label} must be between 0 and 23.")

    @api.constrains(
        'employee_expense_reminder_delay',
        'employee_expense_reminder_delay_type',
        'organizer_expense_escalation_delay',
        'organizer_expense_escalation_delay_type',
    )
    def _check_organizer_escalation_delay(self):
        for company in self:
            employee_delta = company._reminder_delta(
                company.employee_expense_reminder_delay,
                company.employee_expense_reminder_delay_type,
            )
            organizer_delta = company._reminder_delta(
                company.organizer_expense_escalation_delay,
                company.organizer_expense_escalation_delay_type,
            )
            if organizer_delta < employee_delta:
                raise ValidationError(
                    "Expense reviewer follow-up delay must be greater than or equal to the employee expense follow-up delay."
                )