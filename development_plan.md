# Business Trip Security and Notification Redesign

## Goal

Redesign business trip authorization, role handover, read-only audit access,
and post-travel expense reminders so that the module is secure at the ORM
layer, company-aware, auditable, and safe to operate with multiple workers.

## Implemented Architecture

### Authorization Layers

1. Capability groups define what a user may do.
2. Company settings define the currently active default duty holders.
3. `business.trip` fields define responsibility for a specific record.
4. Tracked assignment history records role handovers.

### Roles

- Business Trip Requester: create and maintain own requests.
- Business Trip Approver: access trips where `manager_id` is the user.
- Business Trip Organizer: read the company organizer workspace and modify
  only trips where `organizer_id` is the user.
- Business Trip Expense Reviewer: access trips where
  `expense_reviewer_id` is the user.
- Business Trip Auditor: read all trips in allowed companies without write,
  create, or delete permission.
- Business Trip Administrator: company-wide configuration and workflow
  override.
- System Administrator: unrestricted technical administration.

Technical default-approver and active-organizer groups are managed from
company settings and are not meant for direct day-to-day editing on the Users
access-rights form.

### Organizer Pool and Handover

- `res.company.business_trip_organizer_ids` is the pool of organizers per
  company; the Travel Approver picks any pool member when assigning a trip.
- Pool members automatically receive the technical organizer group; users in
  no company pool automatically lose it (and the management menus).
- Removing a pool member who still has non-final trips:
  - hands those trips over automatically when exactly one organizer remains;
  - is blocked with a validation error otherwise, until the trips are
    reassigned explicitly.
- Trip followers, task assignees, task followers, and pending activities are
  synchronized on handover.
- Final trips retain their historical `organizer_id`.
- Every reassignment creates a structured history entry and tracked chatter
  change.
- Migration `18.0.1.2.0` seeds the pool from the legacy single-organizer
  column and removes stale organizer group memberships.

### Expense Follow-up

- Organizer confirmation moves a trip to `organization_done`.
- No actual travel dates or expense follow-up timestamp are written during
  planning confirmation.
- The scheduled job moves `organization_done` trips to
  `completed_waiting_expense` only after their `travel_end_date`.
- The stable reminder anchor is midnight immediately after the trip end in
  the company timezone, stored as UTC.
- Missing end dates never trigger expense reminders.
- Employee and expense-reviewer due dates use the same post-travel anchor.
- The cron runs hourly.
- Digest processing uses a transaction-scoped advisory lock per
  user/company/digest key.
- Activity records are only written when their values actually change.

## Current State

- Architecture implemented in module code.
- Migration `18.0.1.1.0` repairs company links, role settings, premature
  expense statuses, fake actual dates, and cron interval.
- Focused tests cover security, organizer handover, and expense timing.
- Module update + test run required on the staging database.
