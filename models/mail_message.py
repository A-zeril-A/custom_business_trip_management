from odoo import models, fields, api, tools
import logging

_logger = logging.getLogger(__name__)

class MailMessage(models.Model):
    _inherit = 'mail.message'
    
    confidential = fields.Boolean(string='Confidential', default=False, index=True)
    confidential_recipients = fields.Many2many(
        'res.partner', 
        'mail_message_confidential_res_partner_rel',
        'mail_message_id',
        'res_partner_id',
        string='Confidential Recipients'
    )
    
    def _format_for_notification(self):
        """Override to filter confidential messages"""
        _logger.info(f"---- Start _format_for_notification for user: {self.env.user.name} (partner_id: {self.env.user.partner_id.id}) ----")
        notifications = super(MailMessage, self)._format_for_notification()
        
        current_partner_id = self.env.user.partner_id.id
        
        filtered_notifications = []
        for i, notification_tuple in enumerate(notifications):
            if not isinstance(notification_tuple, (list, tuple)) or not notification_tuple:
                _logger.warning(f"Notification item {i} is not a valid tuple/list or is empty: {notification_tuple}")
                if notification_tuple:
                    filtered_notifications.append(notification_tuple)
                continue

            message = notification_tuple[0]
            
            _logger.info(f"Processing message ID: {message.id}, Subject: {message.subject}, Confidential: {message.confidential}")
            _logger.info(f"Confidential Recipients for message ID {message.id}: {message.confidential_recipients.ids}")

            if message.confidential:
                is_current_user_admin = self.env.user.has_group('base.group_system')
                is_current_user_recipient = current_partner_id in message.confidential_recipients.ids
                
                _logger.info(f"Message ID: {message.id} IS CONFIDENTIAL. Current user admin: {is_current_user_admin}, Current user in recipients: {is_current_user_recipient}")

                if not is_current_user_recipient and not is_current_user_admin:
                    _logger.info(f"SKIPPING confidential message ID: {message.id} for user: {self.env.user.name} (partner_id: {current_partner_id})")
                    continue
            
            filtered_notifications.append(notification_tuple)
        
        _logger.info(f"---- End _format_for_notification for user: {self.env.user.name}. Original notifications: {len(notifications)}, Filtered: {len(filtered_notifications)} ----")
        return filtered_notifications
        
    @api.model
    def _search(self, args, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
        """Override _search to filter out confidential messages that the user shouldn't see"""
        # Only apply filtering if we're not admin and not in superuser mode
        if not self.env.is_superuser() and not self.env.user.has_group('base.group_system'):
            partner_id = self.env.user.partner_id.id
            
            # Add condition to filter out confidential messages not intended for current user
            confidential_condition = [
                '|',
                ('confidential', '=', False),
                '&',
                ('confidential', '=', True),
                ('confidential_recipients', 'in', [partner_id])
            ]
            
            if args:
                args = ['&'] + args + confidential_condition
            else:
                args = confidential_condition
                
            _logger.info(f"Modified search args for mail.message to filter confidential messages: {args}")
            
        return super(MailMessage, self)._search(args, offset=offset, limit=limit, order=order, count=count, access_rights_uid=access_rights_uid)
        
    def _get_message_format_fields(self):
        """Add confidential fields to the message format fields"""
        return super(MailMessage, self)._get_message_format_fields() + ['confidential', 'confidential_recipients']
        
    def message_format(self):
        """Override message_format to filter out confidential messages"""
        messages = super(MailMessage, self).message_format()
        
        # If not admin, filter out confidential messages not for current user
        if not self.env.is_superuser() and not self.env.user.has_group('base.group_system'):
            partner_id = self.env.user.partner_id.id
            filtered_messages = []
            
            for message in messages:
                # Skip confidential messages not intended for current user
                if message.get('confidential') and partner_id not in message.get('confidential_recipients', []):
                    _logger.info(f"Filtering out confidential message ID {message.get('id')} from message_format for user {self.env.user.name}")
                    continue
                filtered_messages.append(message)
                
            return filtered_messages
            
        return messages