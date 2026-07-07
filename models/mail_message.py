# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools, SUPERUSER_ID

class MailMessage(models.Model):
    _inherit = 'mail.message'

    confidential = fields.Boolean(string='Confidential', default=False, help="Whether this message is confidential and should only be visible to specific recipients.")
    confidential_recipients = fields.Many2many('res.partner', 'mail_message_res_partner_confidential_rel', string='Confidential Recipients', help="Partners who can view this confidential message.")

    def init(self):
        super().init()
        # Confidential messages are a tiny fraction of mail_message (hundreds
        # out of tens of thousands), but the _search override below appends a
        # domain on `confidential` to EVERY mail.message search of every
        # non-privileged user. A partial index keeps the confidential=True
        # branch cheap regardless of table growth, at near-zero write cost.
        tools.create_index(
            self._cr,
            'mail_message_confidential_true_idx',
            self._table,
            ['id'],
            where='confidential IS TRUE',
        )

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
            #
            # NOTE: this is the minimal equivalent form of the historical
            # domain ['|', (confidential, =, False),
            #         '&', (confidential, =, True), (recipients, in, [pid])]:
            # for confidential rows the first leg is false so visibility is
            # exactly "partner is a recipient"; for non-confidential rows the
            # first leg already matches. Dropping the redundant
            # (confidential, =, True) qual keeps the result set identical
            # while generating one less condition in every chatter query.
            confidential_domain = [
                '|',
                ('confidential', '!=', True),
                ('confidential_recipients', 'in', [self.env.user.partner_id.id])
            ]
            domain = list(domain) + confidential_domain

        return super(MailMessage, self)._search(domain, offset=offset, limit=limit, order=order)