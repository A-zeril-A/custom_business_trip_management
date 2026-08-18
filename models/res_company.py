from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError

class ResCompany(models.Model):
    _inherit = 'res.company'

    business_trip_sale_order_approver_id = fields.Many2one(
        "res.users",
        string="Travel Approver (Sale Order)",
        domain="[('active', '=', True), ('share', '=', False), ('company_ids', 'in', id)]",
        help=(
            "If set, sale-order travel requests go to this user. Leave empty "
            "to use each employee's direct manager. A requester is never "
            "assigned as their own approver."
        ),
    )
    business_trip_standalone_approver_id = fields.Many2one(
        "res.users",
        string="Travel Approver (Standalone)",
        domain="[('active', '=', True), ('share', '=', False), ('company_ids', 'in', id)]",
        help="Default approver for standalone business trips.",
    )
    business_trip_organizer_ids = fields.Many2many(
        "res.users",
        "res_company_business_trip_organizer_rel",
        "company_id",
        "user_id",
        string="Business Trip Organizers",
        domain="[('active', '=', True), ('share', '=', False), ('company_ids', 'in', id)]",
        help=(
            "Users the Travel Approver can pick as trip organizer for this "
            "company. Removing a user who still has open trips hands them "
            "over to the single remaining organizer, or requires explicit "
            "reassignment first."
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
        "business_trip_organizer_ids",
        "business_trip_sale_order_expense_reviewer_id",
        "business_trip_standalone_expense_reviewer_id",
    )
    def _check_business_trip_role_users(self):
        role_fields = (
            "business_trip_sale_order_approver_id",
            "business_trip_standalone_approver_id",
            "business_trip_organizer_ids",
            "business_trip_sale_order_expense_reviewer_id",
            "business_trip_standalone_expense_reviewer_id",
        )
        for company in self:
            for field_name in role_fields:
                for user in company[field_name]:
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

    def _handle_business_trip_organizer_pool_change(self, previous_pool):
        """Hand over or block when organizers with open trips leave the pool."""
        self.ensure_one()
        current_pool = self.business_trip_organizer_ids
        removed_users = previous_pool - current_pool

        final_statuses = ("completed", "rejected", "cancelled")
        Trip = self.env["business.trip"].sudo().with_context(active_test=False)
        for user in removed_users:
            open_trips = Trip.search([
                ("company_id", "=", self.id),
                ("organizer_id", "=", user.id),
                ("trip_status", "not in", final_statuses),
            ])
            if not open_trips:
                continue
            if len(current_pool) == 1:
                open_trips._handover_organizer(
                    current_pool,
                    reason=f"Organizer pool changed for {self.name}.",
                    changed_by=self.env.user,
                )
            else:
                raise ValidationError(
                    f"{user.name} still organizes {len(open_trips)} open "
                    f"trip(s) in {self.name}. Reassign those trips to another "
                    "organizer before removing this user, or leave exactly "
                    "one organizer in the list to hand them over "
                    "automatically."
                )

    def _sync_business_trip_organizer_pool_group(self, previous_pool):
        """Keep organizer group membership aligned with all company pools."""
        self.ensure_one()
        group = self.env.ref(
            "custom_business_trip_management.group_business_trip_organizer",
            raise_if_not_found=False,
        )
        if not group:
            return

        current_pool = self.business_trip_organizer_ids
        for user in current_pool:
            if group not in user.groups_id:
                user.sudo().write({"groups_id": [(4, group.id)]})

        for user in previous_pool - current_pool:
            still_in_a_pool = self.sudo().search_count([
                ("business_trip_organizer_ids", "in", user.id),
            ])
            if not still_in_a_pool and group in user.groups_id:
                user.sudo().write({"groups_id": [(3, group.id)]})

    def write(self, vals):
        role_groups = {
            "business_trip_sale_order_approver_id": (
                "custom_business_trip_management.group_business_trip_manager_sale_order"
            ),
            "business_trip_standalone_approver_id": (
                "custom_business_trip_management.group_business_trip_manager_standalone"
            ),
            "business_trip_sale_order_expense_reviewer_id": (
                "custom_business_trip_management.group_business_trip_expense_reviewer"
            ),
            "business_trip_standalone_expense_reviewer_id": (
                "custom_business_trip_management.group_business_trip_expense_reviewer"
            ),
        }
        changed_fields = tuple(field for field in role_groups if field in vals)
        organizer_pool_changed = "business_trip_organizer_ids" in vals
        previous_users = {
            (company.id, field): company[field]
            for company in self
            for field in changed_fields
        }
        previous_pools = {
            company.id: company.business_trip_organizer_ids
            for company in self
        } if organizer_pool_changed else {}

        result = super().write(vals)
        if self.env.context.get("skip_business_trip_role_sync"):
            return result

        for company in self:
            if organizer_pool_changed:
                company._handle_business_trip_organizer_pool_change(
                    previous_pools[company.id]
                )
                company._sync_business_trip_organizer_pool_group(
                    previous_pools[company.id]
                )

            for field_name in changed_fields:
                previous_user = previous_users[(company.id, field_name)]
                company._sync_business_trip_role_group(
                    field_name,
                    role_groups[field_name],
                    previous_user,
                )
                if previous_user and previous_user != company[field_name]:
                    previous_user.sudo().cleanup_business_trip_capability_groups()

        return result