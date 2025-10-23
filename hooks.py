from odoo import api, SUPERUSER_ID
import logging
import json
from odoo import fields

_logger = logging.getLogger(__name__)


def _create_business_trip_requester_group(env):
    """
    Creates the 'Business Trip Requester' group and its corresponding XML ID.

    This function is idempotent and can be safely run multiple times.
    """
    group_xml_id = 'custom_business_trip_management.group_business_trip_requester'
    group = env.ref(group_xml_id, raise_if_not_found=False)

    if not group:
        category = env.ref('base.module_category_human_resources_employees')
        group = env['res.groups'].create({
            'name': 'Business Trip Requester',
            'category_id': category.id,
            'comment': 'Users in this group can request business trips and view all sale orders for selection.',
        })

        env['ir.model.data'].create({
            'name': 'group_business_trip_requester',
            'module': 'custom_business_trip_management',
            'model': 'res.groups',
            'res_id': group.id,
            'noupdate': True,
        })


def _assign_group_to_internal_users(env):
    """Assigns the 'Business Trip Requester' group to 'Internal User' implied groups."""
    group_user = env.ref('base.group_user', raise_if_not_found=False)
    group_requester = env.ref('custom_business_trip_management.group_business_trip_requester', raise_if_not_found=False)

    if group_user and group_requester and group_requester.id not in group_user.implied_ids.ids:
        group_user.write({
            'implied_ids': [(4, group_requester.id)]
        })


def _migrate_trip_data_to_new_models(env):
    """
    Migrates data from old text/json fields in business.trip to the new
    business.trip.plan.line and business.trip.expense.line models.
    This hook is designed to be run once after the models are created.
    """
    _logger.info("Starting data migration for business trips to new line models...")
    
    BusinessTrip = env['business.trip']
    PlanLine = env['business.trip.plan.line']
    
    # Find all trips that have JSON data but no plan lines yet
    trips_to_migrate = BusinessTrip.search([
        ('structured_plan_items_json', '!=', False),
        ('structured_plan_items_json', '!=', '[]'),
        ('plan_line_ids', '=', False)
    ])
    
    _logger.info(f"Found {len(trips_to_migrate)} business trips to migrate plan items for.")
    
    for trip in trips_to_migrate:
        try:
            plan_items_data = json.loads(trip.structured_plan_items_json)
            if not isinstance(plan_items_data, list):
                _logger.warning(f"Skipping trip ID {trip.id}: structured_plan_items_json is not a list.")
                continue

            plan_lines_vals = []
            for item_data in plan_items_data:
                # Map old data keys to new model fields "one-to-one"
                vals = {
                    'trip_id': trip.id,
                    'item_type': item_data.get('item_type'),
                    'custom_type': item_data.get('custom_type'),
                    'direction': item_data.get('direction'),
                    'description': item_data.get('description'),
                    'item_date': item_data.get('item_date'),
                    'from_location': item_data.get('from_location'),
                    'to_location': item_data.get('to_location'),
                    'carrier': item_data.get('carrier'),
                    'reference_number': item_data.get('reference_number'),
                    'departure_time': item_data.get('departure_time'),
                    'arrival_time': item_data.get('arrival_time'),
                    'travel_class': item_data.get('travel_class'),
                    'nights': item_data.get('nights'),
                    'accommodation_type': item_data.get('accommodation_type'),
                    'planned_cost': item_data.get('cost', 0.0),  # Note the field name change
                    'cost_status': item_data.get('cost_status'),
                    'is_reimbursable': item_data.get('is_reimbursable', True),
                    'payment_method': item_data.get('payment_method'),
                    'notes': item_data.get('notes'),
                    'item_data_json': item_data.get('item_data_json')
                }
                plan_lines_vals.append(vals)
            
            if plan_lines_vals:
                PlanLine.create(plan_lines_vals)
                _logger.info(f"Successfully migrated {len(plan_lines_vals)} plan items for trip ID {trip.id}.")

        except json.JSONDecodeError:
            _logger.error(f"Could not migrate plan items for trip ID {trip.id}: Invalid JSON in structured_plan_items_json.")
        except Exception as e:
            _logger.error(f"An unexpected error occurred during migration for trip ID {trip.id}: {e}")

    # --- Expense Data Migration ---
    # ExpenseLine = env['business.trip.expense.line']
    
    # # Find a default "expensable" product to be used as a category for migrated expenses.
    # # This makes the migrated data compatible with the new model's constraints.
    # default_expense_product = env['product.product'].search([('can_be_expensed', '=', True)], limit=1)
    # if not default_expense_product:
    #     _logger.warning("Data migration for expenses skipped: Could not find a default product that can be expensed.")
    # else:
    #     # Find all trips that have an expense total but no expense lines yet
    #     trips_for_expense_migration = BusinessTrip.search([
    #         ('expense_total', '>', 0),
    #         ('expense_line_ids', '=', False)
    #     ])

    #     _logger.info(f"Found {len(trips_for_expense_migration)} business trips to migrate legacy expenses for.")

    #     for trip in trips_for_expense_migration:
    #         try:
    #             expense_vals = {
    #                 'trip_id': trip.id,
    #                 'name': 'Imported Legacy Expense',
    #                 'date': trip.actual_expense_submission_date.date() if trip.actual_expense_submission_date else fields.Date.today(),
    #                 'product_id': default_expense_product.id,
    #                 'quantity': 1,
    #                 'unit_amount': trip.expense_total,
    #                 'total_amount': trip.expense_total, # Set directly as compute is not triggered in create
    #                 'notes': trip.expense_comments,
    #                 'attachment_ids': [(6, 0, trip.expense_attachment_ids.ids)]
    #             }
    #             ExpenseLine.create(expense_vals)
    #             _logger.info(f"Successfully migrated legacy expense for trip ID {trip.id}.")
    #         except Exception as e:
    #             _logger.error(f"An unexpected error occurred during expense migration for trip ID {trip.id}: {e}")
    
    _logger.info("Data migration for business trips finished.")


def post_init_hook(cr, registry):
    """
    Post-install hook to:
    1. Create the 'Business Trip Requester' group.
    2. Add this group to the 'Internal User' group.
    3. Migrate existing trip data to the new line models.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    _create_business_trip_requester_group(env)
    _assign_group_to_internal_users(env)
    _migrate_trip_data_to_new_models(env) 