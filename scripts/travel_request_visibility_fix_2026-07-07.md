# Travel Request Visibility Fix — Organizer Handover (2026-07-07)

## Reported problem

Laura Brunetti (l.brunetti@isalab.eu):

> I don't see the Travel Requests anymore (it's correct).
> But the girl who should doesn't see it either (administration@isalab.it).
> I'm referring to the request of offer from Aldo Canzian for Reggio Emilia.

## Root cause (confirmed on a fresh copy of the production DB)

1. On **2026-07-03 (07:42–07:55 UTC)** user Sara Boustan (uid 24) moved the
   **Business Trip Organizer** group membership from Laura Brunetti (uid 17)
   to Berenice Di Croce / administration@isalab.it (uid 45).
   Organizer group is now: administration@isalab.it, m.ferraro@isalab.it,
   m.pompeo@zeta-lab.it.
2. Losing the group removed Laura's access to the managerial
   **"Assigned to Me"** menu (`menu_all_assigned_business_trip_forms`) —
   this is the intended part ("it's correct").
3. However, **existing trips were never reassigned**: 18 in-flight
   `business.trip` records still had `organizer_id = Laura`, including the
   reported one:
   - **BT103** `SO-029-26-OFF.ISALAB | Reggio Emilia, Italy | 28Jul26`,
     employee Aldo Canzian, status `pending_organization`,
     approved by Lewis Glyn on 2026-06-22 with Laura assigned as organizer.
4. The "Assigned to Me" action filters on `organizer_id = current user`
   (see `action_all_assigned_business_trip_forms` in
   `custom_business_trip_management/views/business_trip_action.xml`), so:
   - Laura no longer had the menu → could not see the trip.
   - Berenice had the menu but `organizer_id` still pointed to Laura →
     her list was empty (0 trips). **Nobody could see the request.**

This is a **data / process gap** (role handover without record handover),
not a code bug. No module code was changed.

## Affected records (before fix)

18 in-flight trips with `organizer_id = 17` (Laura):

| Status | Trips |
|---|---|
| `pending_organization` (organizer must act) | BT78 (Ankara, travel 10Mar26 — past), BT83 (Genoa, travel 01Feb26 — past), **BT103 (Reggio Emilia, travel 28Jul26)** |
| `expense_submitted` (expense reviewer acts) | BT79, BT84, BT86, BT88, BT91, BT92, BT93 |
| `completed_waiting_expense` (employee must submit expenses) | BT15, BT16, BT27, BT28, BT38, BT41, BT45, BT50 |

Trips in final statuses (`completed` / `rejected` / `cancelled`) were left
untouched as historical records.

## Fix applied (test DB `isalab`, refreshed from production 2026-07-07)

Script: `custom_addons/custom_business_trip_management/scripts/reassign_organizer_handover.py`
(idempotent, guarded; run via `odoo-bin shell`). For each of the 18 trips:

1. `organizer_id` → Berenice (tracked field → old/new value logged in chatter).
2. Berenice subscribed as follower of the trip.
3. Only for the 3 `pending_organization` trips (active organizer work):
   Berenice subscribed to the trip's project/task and task assignee swapped
   Laura → Berenice.

### Verification result (simulating the real action domain per user)

- `administration@isalab.it`: management menu visible, **"Assigned to Me" = 18
  trips including BT103 (Reggio Emilia)**.
- `l.brunetti@isalab.eu`: management menu **not** visible (unchanged, as
  desired).
- Remaining in-flight trips assigned to Laura: **0**.
- Chatter audit entry on BT103: `Trip Organizer: Brunetti Laura → Di Croce
  Berenice`.
- Side effects: exactly 3 `mail.mail` records ("You have been assigned to
  task …" addressed to Berenice, one per pending trip task). They were
  **cancelled on the test DB** to avoid sending from the test server. On
  production these notifications are expected and harmless (they inform
  Berenice of her new tasks).

## How to apply on PRODUCTION

1. Deploy the updated `custom_business_trip_management` module (or copy
   `custom_addons/custom_business_trip_management/scripts/reassign_organizer_handover.py`)
   to the production server. No module upgrade is needed; the script is not
   loaded by Odoo, it is only fed to `odoo-bin shell`.
2. Run as the unix user that owns Odoo (adjust paths/config to production):

```bash
cd /opt/odoo/<production_dir>
<venv>/bin/python3 odoo-bin shell -c <production_config>.cfg -d <production_db> \
    --no-http < custom_addons/custom_business_trip_management/scripts/reassign_organizer_handover.py
```

- The running Odoo service does **not** need to be stopped.
- The script prints the trips it hands over, commits once, then prints a
  per-user verification of the "Assigned to Me" list. Re-running it is safe
  ("Nothing to hand over - already migrated.").

## Follow-up recommendations (no action taken)

1. **BT78 (Ankara) and BT83 (Genoa)** are still `pending_organization` but
   their travel dates are months in the past. They are now visible to
   Berenice; the business should decide whether to complete or cancel them.
2. Process note: when the Business Trip Organizer role changes hands in
   Settings → Users, in-flight trips must be reassigned too. If this happens
   again, consider a small module enhancement that warns about (or migrates)
   open trips when a user leaves the organizer group — intentionally **not**
   implemented now to avoid unrequested logic changes.
