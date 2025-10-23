# -*- coding: utf-8 -*-
from odoo import models
import logging

_logger = logging.getLogger(__name__)

class MailTemplateMixin(models.AbstractModel):
    """
    A mixin to provide a standardized method for posting styled messages to the chatter.
    This helps in creating consistent, theme-based messages (info, success, warning, etc.)
    by using a central QWeb template.
    """
    _name = 'mail.template.mixin'
    _description = 'Mixin for posting styled chatter messages'

    def _post_styled_message(self, card_type, icon, title, template_xml_id=None, body_html=None, render_context=None, is_internal_note=True, confidential=False, recipient_partner_ids=None):
        """
        Renders the generic message card template and posts it to the chatter.

        :param self: The record to post the message on (must be a mail.thread subtype).
        :param card_type: (str) 'info', 'success', 'warning', 'danger', or 'default'.
        :param icon: (str) An emoji or icon for the message header.
        :param title: (str) The title of the message.
        :param template_xml_id: (str, optional) The XML ID of a QWeb template to render for the body.
        :param body_html: (str, optional) The main HTML body of the message. Ignored if template_xml_id is provided.
        :param render_context: (dict, optional) A dictionary of context values to pass to the QWeb template.
        :param is_internal_note: (bool) If True, posts as an internal note (mail.mt_note). If False, posts as a public comment (mail.mt_comment).
        :param confidential: (bool) If True, marks the message as confidential.
        :param recipient_partner_ids: (list, optional) List of partner IDs who can view the confidential message.
        """
        self.ensure_one()
        
        final_body_html = body_html
        if template_xml_id:
            try:
                body_template = self.env.ref(template_xml_id)
                final_body_html = body_template._render(render_context or {}, engine='ir.qweb')
            except Exception as e:
                _logger.error(f"Failed to render QWeb template {template_xml_id}: {e}", exc_info=True)
                final_body_html = f"<p>Error rendering template: {template_xml_id}</p>"

        card_template = self.env.ref('custom_business_trip_management.chatter_message_card')
        
        message_body = card_template._render({
            'card_type': card_type,
            'icon': icon,
            'title': title,
            'body_html': final_body_html,
            'submitted_by': self.env.user.name
        }, engine='ir.qweb')

        post_vals = {
            'body': message_body,
            'subtype_id': self.env.ref('mail.mt_note' if is_internal_note else 'mail.mt_comment').id
        }

        if confidential:
            post_vals['confidential'] = True
            if recipient_partner_ids:
                post_vals['confidential_recipients'] = [(6, 0, recipient_partner_ids)]
        
        self.message_post(**post_vals)
        
        return True 