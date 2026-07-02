import logging

from odoo import models, api, fields
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    is_travel_approver = fields.Boolean(
        string='Travel Approver (Sale Order)',
        default=False,
        help="Enable this user as the active Travel Approver for sale order related trips. Only one user can be active at a time."
    )
    is_business_trip_organizer = fields.Boolean(
        string='Business Trip Organizer',
        default=False,
        help="Enable this user as a Business Trip Organizer. Multiple users can have this role."
    )

    is_travel_approver_standalone = fields.Boolean(
        string='Travel Approver (Standalone)',
        default=False,
        help="Enable this user as the active Travel Approver for standalone trips. Only one user can be active at a time."
    )

    # ------------------------------------------------------------------
    # Helpers for single-active-approver enforcement
    # ------------------------------------------------------------------

    def _ensure_single_approver(self, group_xmlid, boolean_field):
        """
        Guarantee that only the current recordset (``self``) holds the
        given approver role.  Every *other* user who previously held the
        role loses the group membership **and** the boolean flag.

        All mutations go through the ORM so the registry cache stays in
        sync – the old raw-SQL approach caused stale group memberships
        that led to the wrong approver being selected.
        """
        group = self.env.ref(group_xmlid, raise_if_not_found=False)
        if not group:
            return

        # Users who currently carry the group but are NOT in ``self``
        stale_users = self.search([
            ('groups_id', 'in', [group.id]),
            ('id', 'not in', self.ids),
        ])
        if stale_users:
            _logger.info(
                "Removing %s from group %s (single-approver enforcement)",
                stale_users.mapped('login'), group_xmlid,
            )
            # ORM write → cache stays valid
            super(ResUsers, stale_users).write({
                boolean_field: False,
                'groups_id': [(3, group.id)],
            })

        # Also reset the boolean for any user who has it True but is not ``self``
        stale_boolean_users = self.search([
            (boolean_field, '=', True),
            ('id', 'not in', self.ids),
        ])
        if stale_boolean_users:
            super(ResUsers, stale_boolean_users).write({boolean_field: False})

        # Make sure ``self`` is in the group and has the boolean
        for user in self:
            if group not in user.groups_id:
                super(ResUsers, user).write({'groups_id': [(4, group.id)]})
            if not user[boolean_field]:
                super(ResUsers, user).write({boolean_field: True})

    # ------------------------------------------------------------------
    # Detect which approver role is being activated in ``vals``
    # ------------------------------------------------------------------

    def _is_activating_approver(self, vals, group, boolean_field):
        """
        Return True when *vals* is attempting to grant the approver role
        to the current recordset – via the boolean flag, the virtual
        ``in_group_XX`` field, or a ``groups_id`` command.
        """
        # 1) Boolean field set to True
        if vals.get(boolean_field):
            return True

        # 2) Virtual in_group_XX field (used by the Settings / Users form)
        virt_field = f'in_group_{group.id}'
        if vals.get(virt_field):
            return True

        # 3) Explicit groups_id command  [(4, gid)] or [(6, 0, [... gid ...])]
        for cmd in (vals.get('groups_id') or []):
            if len(cmd) >= 2 and cmd[0] == 4 and cmd[1] == group.id:
                return True
            if len(cmd) >= 3 and cmd[0] == 6 and group.id in (cmd[2] or []):
                return True

        return False

    # ------------------------------------------------------------------
    # write / create
    # ------------------------------------------------------------------

    def write(self, vals):
        """
        Intercept writes that activate an approver role and enforce the
        single-active-approver invariant.
        """
        sale_group = self.env.ref(
            'custom_business_trip_management.group_business_trip_manager_sale_order',
            raise_if_not_found=False,
        )
        standalone_group = self.env.ref(
            'custom_business_trip_management.group_business_trip_manager_standalone',
            raise_if_not_found=False,
        )

        activating_sale = (
            sale_group
            and self._is_activating_approver(vals, sale_group, 'is_travel_approver')
        )
        activating_standalone = (
            standalone_group
            and self._is_activating_approver(vals, standalone_group, 'is_travel_approver_standalone')
        )

        result = super(ResUsers, self).write(vals)

        if activating_sale:
            self._ensure_single_approver(
                'custom_business_trip_management.group_business_trip_manager_sale_order',
                'is_travel_approver',
            )
        if activating_standalone:
            self._ensure_single_approver(
                'custom_business_trip_management.group_business_trip_manager_standalone',
                'is_travel_approver_standalone',
            )

        return result

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        requester_group = self.env.ref(
            'custom_business_trip_management.group_business_trip_requester',
            raise_if_not_found=False,
        )
        if requester_group:
            for user in users:
                if user.has_group('base.group_user'):
                    if requester_group not in user.groups_id:
                        user.write({'groups_id': [(4, requester_group.id)]})
        return users

    # ------------------------------------------------------------------
    # Approver look-up helpers
    # ------------------------------------------------------------------

    @api.model
    def get_default_travel_approver_sale_order(self):
        """Return the single active Travel Approver for Sale Order trips.

        The boolean field is the authoritative source of truth.
        Falls back to group membership for resilience.
        """
        approver = self.search([('is_travel_approver', '=', True)], limit=1)
        if approver:
            return approver

        # Fallback: check group membership (covers edge cases)
        group = self.env.ref(
            'custom_business_trip_management.group_business_trip_manager_sale_order',
            raise_if_not_found=False,
        )
        if group:
            return self.search([('groups_id', 'in', group.id)], limit=1)

        return self.env['res.users']

    @api.model
    def get_default_travel_approver_standalone(self):
        """Return the single active Travel Approver for Standalone trips.

        The boolean field is the authoritative source of truth.
        Falls back to group membership for resilience.
        """
        approver = self.search([('is_travel_approver_standalone', '=', True)], limit=1)
        if approver:
            return approver

        # Fallback: check group membership (covers edge cases)
        group = self.env.ref(
            'custom_business_trip_management.group_business_trip_manager_standalone',
            raise_if_not_found=False,
        )
        if group:
            return self.search([('groups_id', 'in', group.id)], limit=1)

        return self.env['res.users']

    @api.model
    def get_travel_approver_for_sale_order(self, user_id=None):
        """
        Get Travel Approver for Sale Order related trips.
        Priority: 1) Direct manager  2) Travel Approver (Sale Order)  3) Admin
        """
        if not user_id:
            user_id = self.env.user.id

        employee = self.env['hr.employee'].sudo().search(
            [('user_id', '=', user_id)], limit=1,
        )

        # First priority: employee's direct manager
        if employee and employee.parent_id and employee.parent_id.user_id:
            return employee.parent_id.user_id.id

        # Second priority: designated Travel Approver (Sale Order)
        default_approver = self.get_default_travel_approver_sale_order()
        if default_approver:
            return default_approver.id

        # Third priority: admin
        admin_user = self.search(
            [('groups_id.name', '=', 'Administration / Settings')], limit=1,
        )
        if admin_user:
            return admin_user.id

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
