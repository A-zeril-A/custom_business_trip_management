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
