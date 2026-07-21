from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError

class ResCompany(models.Model):
    _inherit = 'res.company'

    business_trip_sale_order_approver_id = fields.Many2one(
        "res.users",
        string="Fallback Travel Approver (Sale Order)",
        domain="[('active', '=', True), ('share', '=', False), ('company_ids', 'in', id)]",
        help=(
            "Fallback approver for sale-order trips when the employee has no "
            "direct manager."
        ),
    )
    business_trip_standalone_approver_id = fields.Many2one(
        "res.users",
        string="Travel Approver (Standalone)",
        domain="[('active', '=', True), ('share', '=', False), ('company_ids', 'in', id)]",
        help="Default approver for standalone business trips.",
    )
    business_trip_organizer_id = fields.Many2one(
        "res.users",
        string="Active Business Trip Organizer",
        domain="[('active', '=', True), ('share', '=', False), ('company_ids', 'in', id)]",
        help=(
            "The active organizer for this company. Changing this user safely "
            "hands over all non-final trips."
        ),
    )
    business_trip_sale_order_expense_reviewer_id = fields.Many2one(
        "res.users",
        string="Expense Reviewer (Sale Order)",
        domain="[('active', '=', True), ('share', '=', False), ('company_ids', 'in', id)]",
        help="Expense reviewer for sale-order business trips.",
    )
    business_trip_standalone_expense_reviewer_id = fields.Many2one(
        "res.users",
        string="Expense Reviewer (Standalone)",
        domain="[('active', '=', True), ('share', '=', False), ('company_ids', 'in', id)]",
        help="Expense reviewer for standalone business trips.",
    )

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
        help="How long after the trip ends the employee should receive the first grouped expense reminder email and To Do activity."
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
        help="How long after the trip ends the configured expense reviewer should start receiving grouped reminders if the employee still has not clarified the trip expenses."
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

    @api.constrains(
        "business_trip_sale_order_approver_id",
        "business_trip_standalone_approver_id",
        "business_trip_organizer_id",
        "business_trip_sale_order_expense_reviewer_id",
        "business_trip_standalone_expense_reviewer_id",
    )
    def _check_business_trip_role_users(self):
        role_fields = (
            "business_trip_sale_order_approver_id",
            "business_trip_standalone_approver_id",
            "business_trip_organizer_id",
            "business_trip_sale_order_expense_reviewer_id",
            "business_trip_standalone_expense_reviewer_id",
        )
        for company in self:
            for field_name in role_fields:
                user = company[field_name]
                if not user:
                    continue
                if not user.active or user.share:
                    raise ValidationError(
                        f"{user.name} must be an active internal user."
                    )
                if company not in user.company_ids:
                    raise ValidationError(
                        f"{user.name} is not allowed to access {company.name}."
                    )

    def _sync_business_trip_role_group(
        self,
        field_name,
        group_xmlid,
        previous_user,
    ):
        self.ensure_one()
        group = self.env.ref(group_xmlid, raise_if_not_found=False)
        if not group:
            return

        current_user = self[field_name]
        if current_user and group not in current_user.groups_id:
            current_user.sudo().write({"groups_id": [(4, group.id)]})

        if not previous_user or previous_user == current_user:
            return

        if group_xmlid.endswith("group_business_trip_expense_reviewer"):
            still_configured = self.sudo().search_count([
                "|",
                (
                    "business_trip_sale_order_expense_reviewer_id",
                    "=",
                    previous_user.id,
                ),
                (
                    "business_trip_standalone_expense_reviewer_id",
                    "=",
                    previous_user.id,
                ),
            ])
            still_configured = still_configured or self.env[
                "business.trip"
            ].sudo().search_count([
                ("expense_reviewer_id", "=", previous_user.id),
                (
                    "trip_status",
                    "not in",
                    ("completed", "rejected", "cancelled"),
                ),
            ])
        else:
            still_configured = self.sudo().search_count([
                (field_name, "=", previous_user.id),
            ])
        if not still_configured and group in previous_user.groups_id:
            previous_user.sudo().write({"groups_id": [(3, group.id)]})

    def _handover_business_trip_organizer(self, previous_user):
        self.ensure_one()
        current_user = self.business_trip_organizer_id
        if not previous_user or previous_user == current_user:
            return

        final_statuses = ("completed", "rejected", "cancelled")
        trips = self.env["business.trip"].sudo().with_context(
            active_test=False,
        ).search([
            ("company_id", "=", self.id),
            ("organizer_id", "=", previous_user.id),
            ("trip_status", "not in", final_statuses),
        ])

        if not current_user and trips:
            raise ValidationError(
                "Select a replacement organizer before removing the active "
                "organizer while non-final trips are still assigned."
            )

        if trips:
            trips._handover_organizer(
                current_user,
                reason=f"Active organizer changed for {self.name}.",
                changed_by=self.env.user,
            )

    def write(self, vals):
        role_groups = {
            "business_trip_sale_order_approver_id": (
                "custom_business_trip_management.group_business_trip_manager_sale_order"
            ),
            "business_trip_standalone_approver_id": (
                "custom_business_trip_management.group_business_trip_manager_standalone"
            ),
            "business_trip_organizer_id": (
                "custom_business_trip_management.group_business_trip_organizer"
            ),
            "business_trip_sale_order_expense_reviewer_id": (
                "custom_business_trip_management.group_business_trip_expense_reviewer"
            ),
            "business_trip_standalone_expense_reviewer_id": (
                "custom_business_trip_management.group_business_trip_expense_reviewer"
            ),
        }
        changed_fields = tuple(field for field in role_groups if field in vals)
        previous_users = {
            (company.id, field): company[field]
            for company in self
            for field in changed_fields
        }

        result = super().write(vals)
        if self.env.context.get("skip_business_trip_role_sync"):
            return result

        for company in self:
            if "business_trip_organizer_id" in changed_fields:
                company._handover_business_trip_organizer(
                    previous_users[(company.id, "business_trip_organizer_id")]
                )
                company._sync_business_trip_role_group(
                    "business_trip_organizer_id",
                    role_groups["business_trip_organizer_id"],
                    previous_users[(company.id, "business_trip_organizer_id")],
                )

            for field_name in changed_fields:
                if field_name == "business_trip_organizer_id":
                    continue
                company._sync_business_trip_role_group(
                    field_name,
                    role_groups[field_name],
                    previous_users[(company.id, field_name)],
                )

        return result