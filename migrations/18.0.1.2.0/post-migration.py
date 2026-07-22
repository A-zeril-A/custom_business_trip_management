# -*- coding: utf-8 -*-
"""Move the single active organizer to the multi-organizer pool."""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _logger.info(
        "Starting custom_business_trip_management 18.0.1.2.0 organizer pool migration"
    )

    cr.execute(
        """
        SELECT column_name
          FROM information_schema.columns
         WHERE table_name = 'res_company'
           AND column_name = 'business_trip_organizer_id'
        """
    )
    if not cr.fetchone():
        _logger.info("Legacy organizer column not found; nothing to migrate.")
        return

    cr.execute(
        """
        SELECT id, business_trip_organizer_id
          FROM res_company
         WHERE business_trip_organizer_id IS NOT NULL
        """
    )
    for company_id, user_id in cr.fetchall():
        company = env["res.company"].browse(company_id)
        user = env["res.users"].browse(user_id)
        if not user.exists():
            continue
        company.with_context(skip_business_trip_role_sync=True).write(
            {"business_trip_organizer_ids": [(4, user.id)]}
        )
        company._sync_business_trip_organizer_pool_group(env["res.users"])
        _logger.info(
            "Seeded organizer pool of %s with %s", company.name, user.login
        )

    _remove_stale_organizer_group_members(env)

    _logger.info(
        "Finished custom_business_trip_management 18.0.1.2.0 organizer pool migration"
    )


def _remove_stale_organizer_group_members(env):
    """Drop the technical organizer group from users in no company pool.

    The organizer group is managed exclusively by the company organizer
    setting; membership left over from earlier manual grants keeps the
    management menus visible to ex-organizers.
    """
    group = env.ref(
        "custom_business_trip_management.group_business_trip_organizer",
        raise_if_not_found=False,
    )
    if not group:
        return
    pooled_user_ids = set(
        env["res.company"]
        .sudo()
        .search([])
        .mapped("business_trip_organizer_ids")
        .ids
    )
    stale_users = group.users.filtered(
        lambda user: user.id not in pooled_user_ids
    )
    if stale_users:
        _logger.info(
            "Removing stale organizer group membership from: %s",
            stale_users.mapped("login"),
        )
        stale_users.sudo().write({"groups_id": [(3, group.id)]})
