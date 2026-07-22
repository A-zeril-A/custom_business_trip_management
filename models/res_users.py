import logging

from odoo import models, api, fields
from odoo.exceptions import ValidationError

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
        """Return the current company's fallback sale-order approver."""
        return self.env.company.sudo().business_trip_sale_order_approver_id

    @api.model
    def get_default_travel_approver_standalone(self):
        """Return the current company's standalone approver."""
        return self.env.company.sudo().business_trip_standalone_approver_id

    @api.model
    def get_travel_approver_for_sale_order(self, user_id=None):
        """
        Get Travel Approver for Sale Order related trips.
        Priority: 1) Direct manager  2) Travel Approver (Sale Order)  3) Admin
        """
        if not user_id:
            user_id = self.env.user.id

        employee = self.env['hr.employee'].sudo().search([
            ('user_id', '=', user_id),
            ('company_id', '=', self.env.company.id),
            ('active', '=', True),
        ], limit=1)

        # First priority: employee's direct manager
        if (
            employee
            and employee.parent_id
            and employee.parent_id.user_id
            and employee.parent_id.user_id.active
            and self.env.company in employee.parent_id.user_id.company_ids
        ):
            return employee.parent_id.user_id.id

        # Second priority: designated Travel Approver (Sale Order)
        default_approver = self.get_default_travel_approver_sale_order()
        if default_approver:
            return default_approver.id

        return None

    @api.model
    def get_travel_approver_for_standalone(self, user_id=None):
        """
        Get Travel Approver for Standalone trips.
        Only the user with is_travel_approver_standalone=True (or group member
        as fallback) is allowed.  Raises if nobody is configured.
        """
        default_approver = self.get_default_travel_approver_standalone()
        if default_approver:
            return default_approver.id

        raise ValidationError(
            "No Travel Approver (Standalone) is configured. "
            "Please assign at least one user to the "
            "'Travel Approver (Standalone)' role."
        )
