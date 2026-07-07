# -*- coding: utf-8 -*-
"""
Data fix: hand over ALL in-flight business trips from the former organizer
(Laura Brunetti) to the current organizer (Berenice Di Croce,
administration@isalab.it).

Context:
  On 2026-07-03 the "Business Trip Organizer" group membership was moved from
  Laura to Berenice, but existing trips kept organizer_id = Laura. The
  "Assigned to Me" list filters on organizer_id = current user, so every
  in-flight trip organized by Laura became invisible to both users
  (reported case: BT103 "SO-029-26-OFF.ISALAB | Reggio Emilia").

Scope (deliberately minimal, mirroring the standard assignment flow):
  * Trips with organizer_id = Laura and trip_status NOT in
    completed / rejected / cancelled:
      1. organizer_id -> Berenice (tracked field, audited in chatter)
      2. Berenice subscribed as follower of the trip
  * Only for trips still in 'pending_organization' (active organizer work):
      3. Berenice subscribed as follower of the trip's project and task
      4. Task assignees: replace Laura with Berenice
  * Finished trips (completed/rejected/cancelled) are left untouched as
    historical records.

Guarded and idempotent: safe to re-run (e.g. on production via odoo-bin shell).

Usage (as unix user odoo):
  cd /opt/odoo/isalab18
  venv_isalab18/bin/python3 odoo-bin shell -c config/myodoo18.cfg -d isalab \
      --no-http < custom_addons/custom_business_trip_management/scripts/reassign_organizer_handover.py
"""

OLD_ORGANIZER_LOGIN = "l.brunetti@isalab.eu"
NEW_ORGANIZER_LOGIN = "administration@isalab.it"
FINAL_STATUSES = ("completed", "rejected", "cancelled")

Users = env["res.users"]
old_org = Users.search([("login", "=", OLD_ORGANIZER_LOGIN)], limit=1)
new_org = Users.search([("login", "=", NEW_ORGANIZER_LOGIN)], limit=1)
assert old_org and new_org, "Expected users not found; aborting."

organizer_group = env.ref(
    "custom_business_trip_management.group_business_trip_organizer")
assert new_org in organizer_group.users, (
    "%s is not in the Business Trip Organizer group; aborting." % new_org.login)

trips = env["business.trip"].search([
    ("organizer_id", "=", old_org.id),
    ("trip_status", "not in", list(FINAL_STATUSES)),
])
print("Trips to hand over: %s" % len(trips))
for trip in trips:
    print("  BT%-4s status=%-25s %s" % (trip.id, trip.trip_status, trip.name))

for trip in trips:
    trip.write({"organizer_id": new_org.id})
    trip.message_subscribe(partner_ids=new_org.partner_id.ids)

    if trip.trip_status == "pending_organization":
        if trip.business_trip_project_id:
            trip.business_trip_project_id.message_subscribe(
                partner_ids=new_org.partner_id.ids)
        task = trip.business_trip_task_id
        if task:
            task.message_subscribe(partner_ids=new_org.partner_id.ids)
            task.write({"user_ids": [(3, old_org.id), (4, new_org.id)]})

if trips:
    env.cr.commit()
    print("Committed handover of %s trips to %s." % (len(trips), new_org.login))
else:
    print("Nothing to hand over - already migrated.")

# ---------------------------------------------------------------------------
# Verification: simulate what each user sees in the "Assigned to Me" list
# (same domain as action_all_assigned_business_trip_forms).
# ---------------------------------------------------------------------------
def assigned_to_me_domain(uid):
    return [
        "|", "|",
        "&", ("manager_id", "=", uid), ("trip_status", "!=", "draft"),
        ("organizer_id", "=", uid),
        "&", ("expense_reviewer_id", "=", uid),
             ("trip_status", "=", "expense_submitted"),
    ]

MANAGEMENT_GROUPS = [
    "custom_business_trip_management.group_business_trip_manager",
    "custom_business_trip_management.group_business_trip_organizer",
    "custom_business_trip_management.group_business_trip_manager_sale_order",
    "custom_business_trip_management.group_business_trip_manager_standalone",
]

for user in (new_org, old_org):
    sees_menu = any(user.has_group(g) for g in MANAGEMENT_GROUPS)
    visible = env["business.trip"].with_user(user).search(
        assigned_to_me_domain(user.id))
    print("%s: management menu visible=%s | 'Assigned to Me' count=%s"
          % (user.login, sees_menu, len(visible)))
    for trip in visible:
        print("    BT%-4s status=%-25s %s" % (trip.id, trip.trip_status, trip.name))

leftover = env["business.trip"].search_count([
    ("organizer_id", "=", old_org.id),
    ("trip_status", "not in", list(FINAL_STATUSES)),
])
print("Remaining in-flight trips still assigned to %s: %s"
      % (old_org.login, leftover))
