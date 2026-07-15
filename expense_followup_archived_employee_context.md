# Archived Employee Expense Follow-up

## Goal

Prevent pending business trips owned by archived employees from appearing in
employee or expense-reviewer reminder digests. Remove the module-owned expense
follow-up To Do activities for those trips without changing their workflow
status or historical data.

## Business Rules

- A trip is eligible for expense follow-up only when its owner has both:
  - an active `res.users` account; and
  - an active `hr.employee` record in the trip's effective company.
- An archived employee's pending trip remains unchanged and available for
  historical or manual financial closure.
- Reactivating both the employee and user makes an unresolved trip eligible
  again.
- Employee and reviewer emails, reminder timestamps, and follow-up activities
  must all use the same eligibility rule.

## Architecture

`business.trip._filter_expense_followup_eligible_trips()` is the single
eligibility boundary. It performs one batched employee query for all candidate
users and companies, then matches exact `(user_id, company_id)` pairs.

The check uses `sudo()` only to read employee lifecycle state consistently
during system reminder processing. It does not expose employee data or bypass
access rules for trip content.

The cron filters candidates once, removes stale module-owned activities from
ineligible trips, and passes only prechecked trips to the downstream employee
and reviewer digest flows. The downstream private methods still check
eligibility by default when called independently.

## Exact Codebase State

- Reminder implementation:
  `models/business_trip.py`
- Cron:
  `data/cron_jobs.xml`,
  `business.trip._cron_send_expense_submission_reminders()`
- Digest cadence state:
  `models/business_trip_reminder_digest_state.py`
- Regression tests:
  `tests/test_expense_followup_employee_eligibility.py`
- Module version:
  `18.0.1.0.2`

## Verified Incident Data

The staging database contains archived employee `Luceri Gabriele` linked to an
inactive user and three unresolved trips. Those trips had reviewer reminder
timestamps and three stale `Clarify Expense Status` activities. This confirms
that the previous cron selected trips solely by workflow status.

## Completed Work

- Added lifecycle-aware, company-aware batched eligibility filtering.
- Applied the rule to employee digests, reviewer digests, and activity sync.
- Updated the cron to avoid repeated eligibility queries.
- Updated the module in the `isalab` staging database.
- Removed four stale follow-up activities from currently ineligible trips,
  including the three activities belonging to Luceri Gabriele's open trips.
- Added regression coverage for:
  - an active employee and user;
  - an archived employee whose user remains active;
  - an inactive user;
  - employee digest contents and timestamps;
  - reviewer digest contents and timestamps; and
  - stale To Do cleanup.
- Passed the complete module test suite: 7 tests, 0 failures, 0 errors.

## Next Steps

1. Restart or start the normal staging Odoo service when the environment is
   ready to resume scheduled jobs.
2. Verify the next reviewer digest contains no archived employees.
