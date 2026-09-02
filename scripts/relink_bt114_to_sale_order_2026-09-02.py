# -*- coding: utf-8 -*-
"""
Data fix: attach BT114 to sales order 130-25-OFF.ISALAB Rev.4 and route it to
the Travel Approver the sale-order rule resolves.

Context:
  Gholami Mehrdad and Joudi Javad travelled to Istanbul together for the
  Cerkezkoy-Kapikule ISA audit (31Aug26 - 04Sep26). Javad used the
  "With Quotation" path, so BT115 carries sale_order_id 130-25-OFF.ISALAB
  Rev.4 and went to his direct manager, Lewis Glyn.

  Mehrdad used the "Standalone" path instead, and in the project wizard he
  picked "ARMCO - Supplementary ISA Report for Cerkezkoy-Kapikule Signalling
  System (ISA) - 034-26-OFF.ISALAB Rev.1" - a different order covering the
  same physical ISA work. BT114 therefore carries no sales order at all, and
  standalone routing sent it to the approver configured in Business Trip
  Settings (Boustan Sara) instead of Mehrdad's direct manager. The request has
  been sitting in the wrong queue since 2026-08-28 while the travel window is
  already running.

Scope (deliberately minimal), one trip:
  * link the trip to its real sales order, so every downstream step (project,
    task, reporting) follows the order it belongs to;
  * drop the standalone project/task pointers that were only there because the
    trip was created as standalone, and archive the placeholder task the
    wizard created in the ARMCO project so that project keeps a truthful task
    list. The task is archived, never deleted, and only when it carries no
    timesheet entries;
  * re-resolve the approver through the ordinary sale-order rule rather than
    hardcoding a name, then notify them, because a submitted trip is sitting
    in someone's review queue right now;
  * record the reassignment in business.trip.assignment.history and leave a
    note on the trip, so Mehrdad and Sara both see why it moved.

  The trip stays in 'submitted': the correction changes who reviews it, not
  how far it has progressed. The name is refreshed so the label matches the
  sale-order convention ("SO-..." instead of "SA-...").

Idempotent: re-running finds the order already linked and the approver already
correct, and does nothing.

Usage (as unix user odoo):
  cd /opt/odoo/isalab18
  sudo -u odoo venv_isalab18/bin/python odoo-bin shell \
      -c config/myodoo18.cfg -d isalab --no-http --max-cron-threads=0 \
      < custom_addons/custom_business_trip_management/scripts/relink_bt114_to_sale_order_2026-09-02.py

Set BT_DRY_RUN=1 in the environment to preview without committing.
"""

import os

DRY_RUN = os.environ.get("BT_DRY_RUN") == "1"

TRIP_ID = 114
REQUESTER_LOGIN = "m.gholami@isalab.it"
SALE_ORDER_NAME = "130-25-OFF.ISALAB Rev.4"
EDITABLE_STATUSES = ("draft", "submitted", "returned")
REASON = (
    "BT114 was created as a standalone request against order 034-26 by "
    "mistake; relinked to sales order 130-25-OFF.ISALAB Rev.4, so the "
    "sale-order approver rule applies."
)

Trip = env["business.trip"].sudo()
History = env["business.trip.assignment.history"].sudo()
Users = env["res.users"].sudo()

trip = Trip.browse(TRIP_ID).exists()
if not trip:
    raise SystemExit("BT%s does not exist - nothing to do." % TRIP_ID)
if trip.user_id.login != REQUESTER_LOGIN:
    raise SystemExit(
        "BT%s belongs to %s, not %s - refusing to touch it."
        % (TRIP_ID, trip.user_id.login, REQUESTER_LOGIN)
    )
if trip.trip_status not in EDITABLE_STATUSES:
    raise SystemExit(
        "BT%s is in '%s'; its approver has already acted, so the request must "
        "be corrected by hand instead." % (TRIP_ID, trip.trip_status)
    )

sale_order = env["sale.order"].sudo().search(
    [("name", "=", SALE_ORDER_NAME)], limit=1
)
if not sale_order:
    raise SystemExit("Sales order %s not found." % SALE_ORDER_NAME)
if sale_order.company_id != trip.company_id:
    raise SystemExit(
        "Sales order %s belongs to %s but the trip belongs to %s."
        % (SALE_ORDER_NAME, sale_order.company_id.name, trip.company_id.name)
    )

print("BT%s  requester=%s  status=%s" % (trip.id, trip.user_id.name, trip.trip_status))
print("  current order   : %s" % (trip.sale_order_id.name or "-"))
print("  current project : %s" % (trip.selected_project_id.display_name or "-"))
print("  current approver: %s" % (trip.manager_id.name or "-"))
print("  target order    : %s (%s)" % (sale_order.name, sale_order.state))
print("")

# ---------------------------------------------------------------------------
# 1. Link the sales order and retire the standalone project/task pointers.
# ---------------------------------------------------------------------------
stray_task = trip.selected_project_task_id or trip.business_trip_task_id
if trip.sale_order_id == sale_order:
    print("Order already linked - skipping.")
else:
    print("Linking order %s (was standalone)." % sale_order.name)
    if not DRY_RUN:
        trip.with_context(
            authorized_business_trip_assignment=True,
            force_name_refresh=True,
        ).write({
            "sale_order_id": sale_order.id,
            "selected_project_id": False,
            "selected_project_task_id": False,
            "business_trip_project_id": False,
            "business_trip_task_id": False,
        })

# ---------------------------------------------------------------------------
# 2. Refresh the generated name so the label matches the sale-order convention.
#     _compute_name keeps the stored name for trips past 'draft'/'returned',
#     and the recompute itself has to run in an environment carrying
#     force_name_refresh, hence add_to_compute instead of a plain write.
# ---------------------------------------------------------------------------
refreshing = trip.with_context(force_name_refresh=True)
if DRY_RUN and not trip.sale_order_id:
    print("Name: regenerated once the order link is written.")
else:
    expected_name = refreshing._build_generated_trip_name()
    if trip.name == expected_name:
        print("Name already up to date - skipping.")
    else:
        print("Name '%s' -> '%s'" % (trip.name, expected_name))
        if not DRY_RUN:
            refreshing.env.add_to_compute(trip._fields["name"], refreshing)
            refreshing.flush_recordset(["name"])

if stray_task:
    timesheets = env["account.analytic.line"].sudo().search_count([
        ("task_id", "=", stray_task.id),
    ])
    if timesheets:
        print(
            "Placeholder task %s carries %s timesheet line(s) - left in place "
            "for review." % (stray_task.id, timesheets)
        )
    elif not stray_task.active:
        print("Placeholder task %s already archived - skipping." % stray_task.id)
    else:
        print(
            "Archiving placeholder task %s in project '%s'."
            % (stray_task.id, stray_task.project_id.display_name)
        )
        if not DRY_RUN:
            stray_task.write({"active": False})

# ---------------------------------------------------------------------------
# 3. Re-resolve the approver through the ordinary sale-order rule.
# ---------------------------------------------------------------------------
previous_approver = trip.manager_id
approver_id = Users.with_company(trip.company_id).get_travel_approver_for_sale_order(
    trip.user_id.id
)
approver = Users.browse(approver_id) if approver_id else Users.browse()

if not approver:
    print("")
    print(
        "No sale-order approver resolvable for %s - approver left as %s."
        % (trip.user_id.name, previous_approver.name or "-")
    )
elif approver == previous_approver:
    print("")
    print("Approver already %s - skipping." % approver.name)
else:
    print("")
    print("Approver %s -> %s" % (previous_approver.name or "-", approver.name))
    if not DRY_RUN:
        approver.ensure_business_trip_approver_capability()
        trip.with_context(
            authorized_business_trip_assignment=True,
        ).write({"manager_id": approver.id})
        History.create({
            "trip_id": trip.id,
            "role": "approver",
            "previous_user_id": previous_approver.id or False,
            "new_user_id": approver.id,
            "reason": REASON,
        })
        trip.message_subscribe(partner_ids=approver.partner_id.ids)
        trip._post_message_with_record_link(
            body=(
                "Business trip request submitted by %s is now assigned to you "
                "for review. It was originally created as a standalone request "
                "against the wrong order and has been relinked to %s."
                % (trip.user_id.name, sale_order.name)
            ),
            partner_ids=[approver.partner_id.id],
            subtype_xmlid="mail.mt_comment",
        )
        if previous_approver:
            trip._post_message_with_record_link(
                body=(
                    "This request was relinked to sales order %s and reassigned "
                    "from %s to %s, the Travel Approver for sale-order trips."
                    % (sale_order.name, previous_approver.name, approver.name)
                ),
                subtype_xmlid="mail.mt_note",
            )
            previous_approver.cleanup_business_trip_capability_groups()

if DRY_RUN:
    print("")
    print("DRY RUN - nothing committed.")
else:
    env.cr.commit()
    print("")
    print("Committed.")

# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------
trip.invalidate_recordset()
print("")
print("Verification")
print("  name    : %s" % trip.name)
print("  order   : %s" % (trip.sale_order_id.name or "-"))
print("  approver: %s" % (trip.manager_id.name or "-"))
print("  status  : %s" % trip.trip_status)
print("  project : %s" % (trip.business_trip_project_id.display_name or "-"))
