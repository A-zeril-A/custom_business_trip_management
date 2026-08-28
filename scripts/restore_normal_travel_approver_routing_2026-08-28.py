# -*- coding: utf-8 -*-
"""
Data fix: end the August 2026 temporary approval coverage and return
in-flight business trips to their normal Travel Approver.

Context:
  On 2026-08-18 an admin recorded a temporary handover ("Temporary handover
  until end of August: Technical Director Glyn approves all travel requests
  while Scofano/Sara are unavailable.") and moved BT110 and BT111 to Glyn.
  Only the sale-order approver setting was switched to Glyn, so standalone
  requests kept going to Sara. BT114 (Gholami Mehrdad, standalone) was
  therefore routed to an absent approver and Glyn was never notified.

  Sara is back, so routing returns to normal:
    * sale-order trips  -> the employee's direct manager, Settings only as
      fallback when there is no usable direct manager
    * standalone trips  -> the approver configured in Settings (Sara)

Scope (deliberately minimal), one rule:
  Realign a trip's approver only when the approver has NOT acted on it yet,
  i.e. trip_status in draft / submitted / returned, and the stored approver
  differs from what the current rules resolve.

  * Trips already actioned by their approver keep them, so the audit trail
    stays truthful. BT111 is in 'pending_organization' (Glyn already assigned
    the organizer and budget) and is therefore left alone.
  * Draft trips are included because the approver is pre-assigned when the
    project is picked; a draft carrying a stale approver would notify the
    wrong person the moment the employee submits it.
  * The incoming approver is notified only for 'submitted' trips, which are
    the ones actually waiting on a review right now.
  * Every change is written through the authorized assignment context and is
    recorded in business.trip.assignment.history.

Trips whose approver has already acted are reported, never modified.

Idempotent: re-running finds nothing left to move.

Usage (as unix user odoo):
  cd /opt/odoo/isalab18
  sudo -u odoo venv_isalab18/bin/python odoo-bin shell \
      -c config/myodoo18.cfg -d isalab --no-http --max-cron-threads=0 \
      < custom_addons/custom_business_trip_management/scripts/restore_normal_travel_approver_routing_2026-08-28.py

Set BT_DRY_RUN=1 in the environment to preview without committing.
"""

import os

DRY_RUN = os.environ.get("BT_DRY_RUN") == "1"
HANDOVER_REASON_PREFIX = "Temporary handover until end of August"
AWAITING_APPROVER_STATUSES = ("draft", "submitted", "returned")
FINAL_STATUSES = ("completed", "rejected", "cancelled")
REASON = (
    "August 2026 coverage ended: returning the request to the normal "
    "Travel Approver."
)

Trip = env["business.trip"].sudo()
History = env["business.trip.assignment.history"].sudo()


def normal_approver_for(trip):
    """Resolve the approver the standard workflow would pick today."""
    users = env["res.users"].sudo().with_company(trip.company_id)
    if trip.sale_order_id:
        approver_id = users.get_travel_approver_for_sale_order(trip.user_id.id)
    else:
        approver_id = users.get_travel_approver_for_standalone(trip.user_id.id)
    return env["res.users"].sudo().browse(approver_id) if approver_id else None


handover_rows = History.search([
    ("role", "=", "approver"),
    ("reason", "=like", HANDOVER_REASON_PREFIX + "%"),
])
print("Temporary-handover rows found: %s (trips: %s)"
      % (len(handover_rows),
         ", ".join("BT%s" % t.id for t in handover_rows.mapped("trip_id")) or "-"))
print("")

candidates = Trip.search(
    [("trip_status", "in", list(AWAITING_APPROVER_STATUSES))], order="id"
)
print("Trips still awaiting an approver decision: %s" % len(candidates))

moved = 0
for trip in candidates:
    target = normal_approver_for(trip)
    current = trip.manager_id
    if not target:
        print("  BT%-4s SKIP - no approver resolvable (status=%s)"
              % (trip.id, trip.trip_status))
        continue
    if target == current:
        continue

    print("  BT%-4s %-10s %s -> %s"
          % (trip.id, trip.trip_status, current.name or "-", target.name))
    if DRY_RUN:
        continue

    target.ensure_business_trip_approver_capability()
    trip.with_context(
        authorized_business_trip_assignment=True,
    ).write({"manager_id": target.id})
    History.create({
        "trip_id": trip.id,
        "role": "approver",
        "previous_user_id": current.id or False,
        "new_user_id": target.id,
        "reason": REASON,
    })

    # Only a submitted trip is actually sitting in someone's review queue.
    if trip.trip_status == "submitted":
        trip.message_subscribe(partner_ids=target.partner_id.ids)
        trip._post_message_with_record_link(
            body=(
                "Business trip request submitted by %s is now assigned to you "
                "for review." % trip.user_id.name
            ),
            partner_ids=[target.partner_id.id],
            subtype_xmlid="mail.mt_comment",
        )
    if current:
        current.sudo().cleanup_business_trip_capability_groups()
    moved += 1

if moved and not DRY_RUN:
    env.cr.commit()
    print("Committed %s approver restoration(s)." % moved)
elif DRY_RUN:
    print("DRY RUN - nothing committed.")
else:
    print("Nothing to restore - already normal.")

# ---------------------------------------------------------------------------
# Report: every open trip whose stored approver differs from what the current
# rules would pick. Reported only; in-flight trips are never silently rewritten.
# ---------------------------------------------------------------------------
print("")
print("Remaining open trips whose approver differs from the current rules")
print("(left untouched on purpose - their approver has already acted):")
drifted = 0
for trip in Trip.search([("trip_status", "not in", list(FINAL_STATUSES))], order="id"):
    target = normal_approver_for(trip)
    if target and target != trip.manager_id:
        drifted += 1
        print("  BT%-4s status=%-24s stored=%-18s rules=%-18s %s"
              % (trip.id, trip.trip_status, trip.manager_id.name or "-",
                 target.name, "SALE-ORDER" if trip.sale_order_id else "STANDALONE"))
print("  total: %s" % drifted)

still_awaiting = [
    t for t in Trip.search([("trip_status", "in", list(AWAITING_APPROVER_STATUSES))])
    if normal_approver_for(t) and normal_approver_for(t) != t.manager_id
]
print("")
print("Verification - trips awaiting a decision with a wrong approver: %s"
      % len(still_awaiting))
