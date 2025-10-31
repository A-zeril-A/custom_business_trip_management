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


def post_init_hook(cr, registry):
    """
    Post-install hook to:
    1. Migrate the legacy form completion status.
    2. Create the 'Business Trip Requester' group.
    3. Add this group to the 'Internal User' group.
    4. Migrate existing trip data to the new line models.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    _create_business_trip_requester_group(env)
    _assign_group_to_internal_users(env)
    _migrate_trip_data_to_new_models(env) 