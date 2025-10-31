# Migration 15.0.1.0.1

## Purpose
This migration handles the removal of the `formio` module dependency from the Business Trip Management module.

## What it does

### 1. pre-migration.py (BEFORE schema update)
- **Removes foreign key constraints** to formio tables
- **Drops NOT NULL constraints** on formio-related columns
- **Sets all formio-related fields to NULL**
- This prevents foreign key errors during the update

**Tables affected:**
- `business_trip_data.form_id`
- `business_trip.formio_form_id`
- `accompanying_person.formio_form_id`
- `planned_trip_accommodation_line.form_id`
- `planned_trip_transport_line.form_id`

### 2. post-migration.py (AFTER schema update)
- **Migrates form_completion_status** based on business logic
- Sets status to:
  - `cancelled` if trip is cancelled
  - `form_completed` if trip is beyond draft status
  - `form_completed` if submission_date exists
  - `awaiting_completion` otherwise

### 3. end-migration.py (AT THE END)
- **Safely removes empty formio-related columns**
- Only drops columns that are completely NULL
- Provides warnings if any data still exists

## Why is this necessary?

When removing a module dependency (formio), PostgreSQL foreign key constraints prevent the update from completing. The migration automatically handles:

1.  Removing constraints
2.  Cleaning up data
3.  Migrating to new structure
4.  Removing obsolete columns

## Manual alternative (NOT RECOMMENDED)

Before this migration, you had to manually run:
```sql
ALTER TABLE business_trip_data ALTER COLUMN form_id DROP NOT NULL;
UPDATE business_trip_data SET form_id = NULL;
```

Now it's automatic! 

## Execution order

```
pre-migration.py    → Drop constraints, NULL values
      ↓
Schema Update       → Odoo updates tables
      ↓
post-migration.py   → Migrate form_completion_status
      ↓
end-migration.py    → Drop empty columns
```

## Safety

All migrations include:
-  Existence checks before operations
-  Error handling with logging
-  Non-null value checks before dropping
-  Detailed logging for debugging

## A_zeril_A
Migration created to handle formio dependency removal
Date: October 2025

