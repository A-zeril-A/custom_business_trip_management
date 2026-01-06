# -*- coding: utf-8 -*-
from odoo import models, fields, api, SUPERUSER_ID

class MailMessage(models.Model):
    _inherit = 'mail.message'

    confidential = fields.Boolean(string='Confidential', default=False, help="Whether this message is confidential and should only be visible to specific recipients.")
    confidential_recipients = fields.Many2many('res.partner', 'mail_message_res_partner_confidential_rel', string='Confidential Recipients', help="Partners who can view this confidential message.")

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None):
        """
        Override the search method to filter out confidential messages for users who are not in the recipient list.
        Note: In Odoo 18, the 'access_rights_uid' parameter was removed from _search method.
        The filtering logic remains exactly the same as Odoo 17.
        """
        # If the user is a superuser or has admin/manager/organizer rights, bypass the confidential filter.
        # This ensures they can always see all messages for administrative purposes.
        is_privileged_user = self.env.user.has_group('base.group_system') or \
                             self.env.user.has_group('custom_business_trip_management.group_trip_organizer')
        
        if not is_privileged_user:
            # For non-privileged users, add a domain to filter confidential messages.
            # A message is visible if:
            # 1. It is not confidential.
            # OR
            # 2. It is confidential, AND the current user's partner is in the list of confidential recipients.
            confidential_domain = [
                '|',
                ('confidential', '=', False),
                '&',
                ('confidential', '=', True),
                ('confidential_recipients', 'in', [self.env.user.partner_id.id])
            ]
            domain = list(domain) + confidential_domain

        return super(MailMessage, self)._search(domain, offset=offset, limit=limit, order=order)