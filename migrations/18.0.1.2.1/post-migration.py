# -*- coding: utf-8 -*-
"""One-time sweep of stale approver/reviewer capability memberships.

Historically the approver and expense-reviewer capability groups were only
ever granted, never revoked, so users kept the management menus after their
last assignment closed. Revocation is now event-driven (settings changes and
trip finalization); this migration applies the same rule once to existing
members.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    members = env["res.users"]
    for group_xmlid in (
        "custom_business_trip_management.group_business_trip_approver",
        "custom_business_trip_management.group_business_trip_expense_reviewer",
    ):
        group = env.ref(group_xmlid, raise_if_not_found=False)
        if group:
            members |= group.users
    if not members:
        return
    _logger.info(
        "Re-evaluating business trip capability groups for %s user(s)",
        len(members),
    )
    members.cleanup_business_trip_capability_groups()
