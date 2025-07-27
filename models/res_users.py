from odoo import models, api

class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model
    def create(self, vals):
        user = super().create(vals)
        requester_group = self.env.ref('custom_business_trip_management.group_business_trip_requester', raise_if_not_found=False)
        if requester_group:
            # Check if the new user belongs to the 'Internal User' group
            if user.has_group('base.group_user'):
                # Add the 'Business Trip Requester' group if not already assigned
                if requester_group not in user.groups_id:
                    user.write({'groups_id': [(4, requester_group.id)]})
        return user
