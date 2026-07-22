# -*- coding: utf-8 -*-
"""Secure authorization and post-travel expense follow-up migration."""

import logging
from datetime import timedelta

import pytz

from odoo import SUPERUSER_ID, api, fields

_logger = logging.getLogger(__name__)

FINAL_STATUSES = ("completed", "rejected", "cancelled")


def _populate_company_and_links(env):
    Trip = env["business.trip"].sudo().with_context(active_test=False)
    trips = Trip.search([])
    for trip in trips:
        vals = {}
        if not trip.company_id:
            company = (
                trip.sale_order_id.company_id
                or trip.user_id.company_id
                or env.company
            )
            vals["company_id"] = company.id
        if trip.business_trip_data_id and not trip.business_trip_data_id.form_id:
            trip.business_trip_data_id.write({"form_id": trip.id})
        if vals:
            trip.with_context(
                mail_notrack=True,
                system_edit=True,
                skip_business_trip_role_sync=True,
            ).write(vals)


def _configure_company_roles(env):
    Users = env["res.users"].sudo()
    for company in env["res.company"].sudo().search([]):
        vals = {}
        if not company.business_trip_sale_order_approver_id:
            sale_group = env.ref(
                "custom_business_trip_management.group_business_trip_manager_sale_order",
                raise_if_not_found=False,
            )
            sale_user = Users.search(
                [
                    ("is_travel_approver", "=", True),
                    ("company_ids", "in", company.id),
                    ("active", "=", True),
                    ("share", "=", False),
                ],
                limit=1,
            )
            if not sale_user and sale_group:
                sale_user = Users.search(
                    [
                        ("groups_id", "in", sale_group.id),
                        ("company_ids", "in", company.id),
                        ("active", "=", True),
                        ("share", "=", False),
                    ],
                    limit=1,
                )
            if sale_user:
                vals["business_trip_sale_order_approver_id"] = sale_user.id

        if not company.business_trip_standalone_approver_id:
            standalone_group = env.ref(
                "custom_business_trip_management.group_business_trip_manager_standalone",
                raise_if_not_found=False,
            )
            standalone_user = Users.search(
                [
                    ("is_travel_approver_standalone", "=", True),
                    ("company_ids", "in", company.id),
                    ("active", "=", True),
                    ("share", "=", False),
                ],
                limit=1,
            )
            if not standalone_user and standalone_group:
                standalone_user = Users.search(
                    [
                        ("groups_id", "in", standalone_group.id),
                        ("company_ids", "in", company.id),
                        ("active", "=", True),
                        ("share", "=", False),
                    ],
                    limit=1,
                )
            if standalone_user:
                vals["business_trip_standalone_approver_id"] = standalone_user.id

        if not company.business_trip_organizer_ids:
            organizer_group = env.ref(
                "custom_business_trip_management.group_business_trip_organizer",
                raise_if_not_found=False,
            )
            organizers = Users.search(
                [
                    ("groups_id", "in", organizer_group.id),
                    ("company_ids", "in", company.id),
                    ("active", "=", True),
                    ("share", "=", False),
                ]
            ) if organizer_group else Users
            if organizers:
                vals["business_trip_organizer_ids"] = [(6, 0, organizers.ids)]

        if vals:
            company.with_context(skip_business_trip_role_sync=True).write(vals)
            for field_name, group_xmlid in (
                (
                    "business_trip_sale_order_approver_id",
                    "custom_business_trip_management.group_business_trip_manager_sale_order",
                ),
                (
                    "business_trip_standalone_approver_id",
                    "custom_business_trip_management.group_business_trip_manager_standalone",
                ),
            ):
                if field_name in vals:
                    company._sync_business_trip_role_group(
                        field_name,
                        group_xmlid,
                        previous_user=env["res.users"],
                    )
            if "business_trip_organizer_ids" in vals:
                company._sync_business_trip_organizer_pool_group(
                    env["res.users"]
                )


def _backfill_reviewers_and_capabilities(env):
    Trip = env["business.trip"].sudo().with_context(active_test=False)
    for trip in Trip.search([]):
        vals = {}
        if not trip.expense_reviewer_id:
            reviewer = trip._resolve_expense_review_user()
            if reviewer:
                vals["expense_reviewer_id"] = reviewer.id
                reviewer_group = env.ref(
                    "custom_business_trip_management.group_business_trip_expense_reviewer",
                    raise_if_not_found=False,
                )
                if reviewer_group and reviewer_group not in reviewer.groups_id:
                    reviewer.write({"groups_id": [(4, reviewer_group.id)]})
        if trip.manager_id:
            trip.manager_id.ensure_business_trip_approver_capability()
        if vals:
            trip.with_context(
                mail_notrack=True,
                system_edit=True,
            ).write(vals)


def _repair_expense_followup(env):
    Trip = env["business.trip"].sudo().with_context(active_test=False)
    utc_now = pytz.UTC.localize(fields.Datetime.now())

    for company in env["res.company"].sudo().search([]):
        timezone_name = (
            company.resource_calendar_id.tz
            or company.partner_id.tz
            or "UTC"
        )
        local_today = utc_now.astimezone(pytz.timezone(timezone_name)).date()

        premature = Trip.search(
            [
                ("company_id", "=", company.id),
                ("trip_status", "=", "completed_waiting_expense"),
                "|",
                ("travel_end_date", "=", False),
                ("travel_end_date", ">=", local_today),
            ]
        )
        if premature:
            premature.with_context(
                mail_notrack=True,
                system_edit=True,
            ).write(
                {
                    "trip_status": "organization_done",
                    "expense_followup_start_date": False,
                    "employee_expense_reminder_sent_date": False,
                    "last_expense_reminder_date": False,
                }
            )
            premature._clear_employee_expense_followup_activities()

        planned_with_fake_actuals = Trip.search(
            [
                ("company_id", "=", company.id),
                ("organization_done_date", "!=", False),
                ("actual_start_date", "!=", False),
                ("actual_end_date", "!=", False),
            ]
        )
        for trip in planned_with_fake_actuals:
            confirmation = trip.organization_done_date
            if (
                trip.actual_start_date == confirmation
                and trip.actual_end_date == confirmation
            ):
                trip.with_context(
                    mail_notrack=True,
                    system_edit=True,
                ).write(
                    {
                        "actual_start_date": False,
                        "actual_end_date": False,
                    }
                )

        past_open = Trip.search(
            [
                ("company_id", "=", company.id),
                ("trip_status", "in", ("organization_done", "completed_waiting_expense")),
                ("travel_end_date", "!=", False),
                ("travel_end_date", "<", local_today),
            ]
        )
        for trip in past_open:
            anchor = trip._get_post_travel_expense_anchor()
            trip.with_context(
                mail_notrack=True,
                system_edit=True,
            ).write(
                {
                    "trip_status": "completed_waiting_expense",
                    "expense_followup_start_date": anchor,
                }
            )


def _force_hourly_expense_cron(env):
    cron = env.ref(
        "custom_business_trip_management.ir_cron_send_expense_reminders",
        raise_if_not_found=False,
    )
    if not cron:
        return
    nextcall = fields.Datetime.now() + timedelta(hours=1)
    cron.write(
        {
            "interval_number": 1,
            "interval_type": "hours",
            "active": True,
            "nextcall": nextcall.replace(minute=0, second=0, microsecond=0),
        }
    )


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _logger.info(
        "Starting custom_business_trip_management 18.0.1.1.0 security/follow-up migration"
    )
    _populate_company_and_links(env)
    _configure_company_roles(env)
    _backfill_reviewers_and_capabilities(env)
    _repair_expense_followup(env)
    _force_hourly_expense_cron(env)
    _logger.info(
        "Finished custom_business_trip_management 18.0.1.1.0 security/follow-up migration"
    )
