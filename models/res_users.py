import logging

from odoo import models, api, fields

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    is_travel_approver = fields.Boolean(
        string='Travel Approver (Sale Order)',
        default=False,
        readonly=True,
        help=(
            "Legacy compatibility flag. Configure the fallback approver in "
            "Business Trip Settings."
        ),
    )
    is_business_trip_organizer = fields.Boolean(
        string='Business Trip Organizer',
        default=False,
        readonly=True,
        help=(
            "Legacy compatibility flag. Configure the active organizer in "
            "Business Trip Settings."
        ),
    )

    is_travel_approver_standalone = fields.Boolean(
        string='Travel Approver (Standalone)',
        default=False,
        readonly=True,
        help=(
            "Legacy compatibility flag. Configure the standalone approver in "
            "Business Trip Settings."
        ),
    )

    def ensure_business_trip_approver_capability(self):
        group = self.env.ref(
            "custom_business_trip_management.group_business_trip_approver",
            raise_if_not_found=False,
        )
        if not group:
            return
        for user in self.filtered(lambda record: record.active and not record.share):
            if group not in user.groups_id:
                user.sudo().write({"groups_id": [(4, group.id)]})

    def ensure_business_trip_expense_reviewer_capability(self):
        group = self.env.ref(
            "custom_business_trip_management.group_business_trip_expense_reviewer",
            raise_if_not_found=False,
        )
        if not group:
            return
        for user in self.filtered(lambda record: record.active and not record.share):
            if group not in user.groups_id:
                user.sudo().write({"groups_id": [(4, group.id)]})

    def cleanup_business_trip_capability_groups(self):
        """Revoke approver/reviewer capability that is no longer justified.

        A user keeps the capability group only while they are configured in
        any company's Business Trip Settings or still hold the matching role
        on a non-final trip. Called when trips reach a final status and when
        company role settings change, so ex-role-holders lose the management
        menus instead of keeping them forever.
        """
        final_statuses = ("completed", "rejected", "cancelled")
        approver_group = self.env.ref(
            "custom_business_trip_management.group_business_trip_approver",
            raise_if_not_found=False,
        )
        sale_group = self.env.ref(
            "custom_business_trip_management.group_business_trip_manager_sale_order",
            raise_if_not_found=False,
        )
        standalone_group = self.env.ref(
            "custom_business_trip_management.group_business_trip_manager_standalone",
            raise_if_not_found=False,
        )
        reviewer_group = self.env.ref(
            "custom_business_trip_management.group_business_trip_expense_reviewer",
            raise_if_not_found=False,
        )
        Trip = self.env["business.trip"].sudo()
        Company = self.env["res.company"].sudo()

        for user in self:
            commands = []

            if approver_group and approver_group in user.groups_id:
                approver_needed = Company.search_count([
                    "|",
                    ("business_trip_sale_order_approver_id", "=", user.id),
                    ("business_trip_standalone_approver_id", "=", user.id),
                ]) or Trip.search_count([
                    ("manager_id", "=", user.id),
                    ("trip_status", "not in", final_statuses),
                ])
                if not approver_needed:
                    commands.append((3, approver_group.id))
                    if (
                        sale_group
                        and sale_group in user.groups_id
                        and not Company.search_count([
                            ("business_trip_sale_order_approver_id", "=", user.id),
                        ])
                    ):
                        commands.append((3, sale_group.id))
                    if (
                        standalone_group
                        and standalone_group in user.groups_id
                        and not Company.search_count([
                            ("business_trip_standalone_approver_id", "=", user.id),
                        ])
                    ):
                        commands.append((3, standalone_group.id))

            if reviewer_group and reviewer_group in user.groups_id:
                reviewer_needed = Company.search_count([
                    "|",
                    ("business_trip_sale_order_expense_reviewer_id", "=", user.id),
                    ("business_trip_standalone_expense_reviewer_id", "=", user.id),
                ]) or Trip.search_count([
                    ("expense_reviewer_id", "=", user.id),
                    ("trip_status", "not in", final_statuses),
                ])
                if not reviewer_needed:
                    commands.append((3, reviewer_group.id))

            if commands:
                _logger.info(
                    "Revoking stale business trip capability groups from %s",
                    user.login,
                )
                user.sudo().write({"groups_id": commands})

    # ------------------------------------------------------------------
    # Approver look-up helpers
    # ------------------------------------------------------------------

    @api.model
    def get_default_travel_approver_sale_order(self):
        """Return the current company's configured sale-order approver."""
        return self.env.company.sudo().business_trip_sale_order_approver_id

    @api.model
    def get_default_travel_approver_standalone(self):
        """Return the current company's standalone approver."""
        return self.env.company.sudo().business_trip_standalone_approver_id

    def _get_usable_travel_approver(self, user, requester_id):
        """Return user if they can approve someone else's trip in this company."""
        if (
            user
            and user.active
            and not user.share
            and user.id != requester_id
            and self.env.company in user.company_ids
        ):
            return user
        return self.env["res.users"]

    def _get_employee_manager_user(self, user_id):
        """Return the requester's direct manager user when it is usable."""
        employee = self.env["hr.employee"].sudo().search([
            ("user_id", "=", user_id),
            ("company_id", "=", self.env.company.id),
            ("active", "=", True),
        ], limit=1)
        manager_user = employee.parent_id.user_id if employee else self.env["res.users"]
        return self._get_usable_travel_approver(manager_user, user_id)

    def _is_top_of_hierarchy(self, user_id):
        """Return True when nobody in this company sits above the requester.

        Requiring at least one subordinate is deliberate: an employee record
        that simply never got a manager assigned must not silently gain the
        right to approve their own trips.
        """
        Employee = self.env["hr.employee"].sudo()
        employee = Employee.search([
            ("user_id", "=", user_id),
            ("company_id", "=", self.env.company.id),
            ("active", "=", True),
        ], limit=1)
        if not employee or employee.parent_id:
            return False
        return bool(Employee.search_count([
            ("parent_id", "=", employee.id),
            ("active", "=", True),
        ]))

    def _get_top_of_hierarchy_approver(self, user_id):
        """Return the requester themselves when there is nobody above them.

        Routing the request to anyone else would hand it to one of their own
        subordinates, so the top of the hierarchy approves their own trips.
        """
        if not self._is_top_of_hierarchy(user_id):
            return self.env["res.users"]
        user = self.browse(user_id)
        if (
            user.active
            and not user.share
            and self.env.company in user.company_ids
        ):
            return user
        return self.env["res.users"]

    @api.model
    def get_travel_approver_for_sale_order(self, user_id=None):
        """Return the sale-order travel approver for a requester.

        Sale-order trips are approved by the employee's own direct manager.
        A requester at the top of the hierarchy approves their own trip, since
        every other candidate reports to them. The approver configured in
        Settings is only a fallback, used when the requester has no usable
        direct manager and is not at the top of the hierarchy.

        Returns None when nobody can be resolved; every caller turns that
        into a user-facing message, so an unconfigured role never breaks the
        request form itself.
        """
        if not user_id:
            user_id = self.env.user.id

        manager_user = self._get_employee_manager_user(user_id)
        if manager_user:
            return manager_user.id

        top_user = self._get_top_of_hierarchy_approver(user_id)
        if top_user:
            return top_user.id

        configured = self._get_usable_travel_approver(
            self.get_default_travel_approver_sale_order(),
            user_id,
        )
        if configured:
            return configured.id

        return None

    @api.model
    def get_travel_approver_for_standalone(self, user_id=None):
        """Return the standalone travel approver for a requester.

        A requester at the top of the hierarchy approves their own trip, since
        the configured approver reports to them. For everyone else Settings
        are the source of truth when a company approver is set, and the
        employee's direct manager is used only when Settings is empty, when
        the configured approver can no longer approve in this company, or
        when using Settings would assign the requester as their own approver.

        Returns None when nobody can be resolved; every caller turns that
        into a user-facing message, so an unconfigured role never breaks the
        request form itself.
        """
        if not user_id:
            user_id = self.env.user.id

        top_user = self._get_top_of_hierarchy_approver(user_id)
        if top_user:
            return top_user.id

        configured = self._get_usable_travel_approver(
            self.get_default_travel_approver_standalone(),
            user_id,
        )
        if configured:
            return configured.id

        manager_user = self._get_employee_manager_user(user_id)
        if manager_user:
            return manager_user.id

        return None
