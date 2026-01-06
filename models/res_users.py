from odoo import models, api, fields
from odoo.exceptions import ValidationError

class ResUsers(models.Model):
    _inherit = 'res.users'

    # Deprecated fields - kept for migration compatibility
    is_travel_approver = fields.Boolean(
        string='Travel Approver (Sale Order)',
        default=False,
        help="Enable this user as the active Travel Approver for sale order related trips. Only one user can be active at a time."
    )
    is_business_trip_organizer = fields.Boolean(
        string='Business Trip Organizer',
        default=False,
        help="Enable this user as a Business Trip Organizer. Multiple users can have this role."
    )
    
    # Travel Approver for Standalone trips
    is_travel_approver_standalone = fields.Boolean(
        string='Travel Approver (Standalone)',
        default=False,
        help="Enable this user as the active Travel Approver for standalone trips. Only one user can be active at a time."
    )

    def write(self, vals):
        """Override write to handle Travel Approver group management for both Sale Order and Standalone groups"""
        # Get both Travel Approver groups
        travel_approver_sale_group = self.env.ref('custom_business_trip_management.group_business_trip_manager_sale_order')
        travel_approver_standalone_group = self.env.ref('custom_business_trip_management.group_business_trip_manager_standalone')
        
        # Helper function to clear a group and set boolean field to False
        def clear_group_and_boolean(group, boolean_field):
            all_users_in_group = self.search([
                ('groups_id', 'in', [group.id])
            ])
            
            if all_users_in_group:
                # Remove group from all users using direct SQL
                self._cr.execute("""
                    DELETE FROM res_groups_users_rel 
                    WHERE gid = %s AND uid IN %s
                """, (group.id, tuple(all_users_in_group.ids)))
                
                # Set boolean field to False for all users
                super(ResUsers, all_users_in_group).write({boolean_field: False})
        
        # Helper function to add user to group
        def add_user_to_group(user_id, group):
            self._cr.execute("""
                INSERT INTO res_groups_users_rel (gid, uid) 
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
            """, (group.id, user_id))
        
        # Check Sale Order Travel Approver group operations
        # 1. Check in_group_XXX for Sale Order
        if f'in_group_{travel_approver_sale_group.id}' in vals and vals[f'in_group_{travel_approver_sale_group.id}']:
            clear_group_and_boolean(travel_approver_sale_group, 'is_travel_approver')
            result = super(ResUsers, self).write(vals)
            super(ResUsers, self).write({'is_travel_approver': True})
            return result
        
        # 2. Check groups_id operations for Sale Order  
        if 'groups_id' in vals:
            for operation in vals['groups_id']:
                if (len(operation) == 2 and operation[0] == 4 and 
                    operation[1] == travel_approver_sale_group.id):
                    clear_group_and_boolean(travel_approver_sale_group, 'is_travel_approver')
                    result = super(ResUsers, self).write(vals)
                    super(ResUsers, self).write({'is_travel_approver': True})
                    return result
                elif (len(operation) == 2 and operation[0] == 4 and 
                    operation[1] == travel_approver_standalone_group.id):
                    clear_group_and_boolean(travel_approver_standalone_group, 'is_travel_approver_standalone')
                    result = super(ResUsers, self).write(vals)
                    super(ResUsers, self).write({'is_travel_approver_standalone': True})
                    return result
        
        # 3. Check is_travel_approver boolean field for Sale Order
        if 'is_travel_approver' in vals and vals['is_travel_approver']:
            clear_group_and_boolean(travel_approver_sale_group, 'is_travel_approver')
            result = super(ResUsers, self).write(vals)
            for user in self:
                add_user_to_group(user.id, travel_approver_sale_group)
            return result
        
        # Check Standalone Travel Approver group operations
        # 1. Check in_group_XXX for Standalone
        if f'in_group_{travel_approver_standalone_group.id}' in vals and vals[f'in_group_{travel_approver_standalone_group.id}']:
            clear_group_and_boolean(travel_approver_standalone_group, 'is_travel_approver_standalone')
            result = super(ResUsers, self).write(vals)
            super(ResUsers, self).write({'is_travel_approver_standalone': True})
            return result
        
        # 2. Check is_travel_approver_standalone boolean field
        if 'is_travel_approver_standalone' in vals and vals['is_travel_approver_standalone']:
            clear_group_and_boolean(travel_approver_standalone_group, 'is_travel_approver_standalone')
            result = super(ResUsers, self).write(vals)
            for user in self:
                add_user_to_group(user.id, travel_approver_standalone_group)
            return result
        
        return super(ResUsers, self).write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        requester_group = self.env.ref('custom_business_trip_management.group_business_trip_requester', raise_if_not_found=False)
        if requester_group:
            for user in users:
                # Check if the new user belongs to the 'Internal User' group
                if user.has_group('base.group_user'):
                    # Add the 'Business Trip Requester' group if not already assigned
                    if requester_group not in user.groups_id:
                        user.write({'groups_id': [(4, requester_group.id)]})
        return users

    @api.model
    def get_default_travel_approver_sale_order(self):
        """Get the Travel Approver user for Sale Order trips directly from the group."""
        approver_group = self.env.ref('custom_business_trip_management.group_business_trip_manager_sale_order', raise_if_not_found=False)
        if not approver_group:
            return self.env['res.users']
        
        # Return the first user found in that group
        return self.search([('groups_id', 'in', approver_group.id)], limit=1)

    @api.model
    def get_default_travel_approver_standalone(self):
        """Get the Travel Approver user for Standalone trips directly from the group."""
        approver_group = self.env.ref('custom_business_trip_management.group_business_trip_manager_standalone', raise_if_not_found=False)
        if not approver_group:
            return self.env['res.users']
        
        # Return the first user found in that group
        return self.search([('groups_id', 'in', approver_group.id)], limit=1)

    @api.model
    def get_travel_approver_for_sale_order(self, user_id=None):
        """
        Get Travel Approver for Sale Order related trips.
        Priority: 1) Direct manager 2) Travel Approver (Sale Order) group 3) Admin
        """
        if not user_id:
            user_id = self.env.user.id
            
        # Find employee for the user
        employee = self.env['hr.employee'].sudo().search([('user_id', '=', user_id)], limit=1)
        
        # First priority: employee's direct manager
        if employee and employee.parent_id and employee.parent_id.user_id:
            return employee.parent_id.user_id.id
        
        # Second priority: any user with Travel Approver (Sale Order) group
        default_approver = self.get_default_travel_approver_sale_order()
        if default_approver:
            return default_approver.id
            
        # Third priority: admin
        admin_user = self.search([('groups_id.name', '=', 'Administration / Settings')], limit=1)
        if admin_user:
            return admin_user.id
            
        return None

    @api.model
    def get_travel_approver_for_standalone(self, user_id=None):
        """
        Get Travel Approver for Standalone trips.
        Only allowed approver is a user in Travel Approver (Standalone) group.
        If no such user exists, raise a clear error.
        """
        # Ignore user_id; selection is group-based only per new policy
        default_approver = self.get_default_travel_approver_standalone()
        if default_approver:
            return default_approver.id

        # No approver configured -> raise error
        raise ValidationError(
            "No Travel Approver (Standalone) is configured. Please assign at least one user to the 'Travel Approver (Standalone)' group."
        )
