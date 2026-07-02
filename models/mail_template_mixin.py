# -*- coding: utf-8 -*-
from odoo import models
from markupsafe import Markup
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

    def _render_styled_message_card(self, card_type, icon, title, body_html=None, next_steps=None, submitted_by=None, icon_class=None):
        rendered_message = self.env['ir.qweb']._render('custom_business_trip_management.chatter_message_card', {
            'card_type': card_type,
            'icon': icon,
            'icon_class': icon_class,
            'title': title,
            'body_html': body_html,
            'next_steps': next_steps,
            'submitted_by': submitted_by,
        })
        return Markup(rendered_message.decode('utf-8') if isinstance(rendered_message, bytes) else rendered_message)

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
                # Odoo 18: Use ir.qweb._render() instead of view._render()
                rendered = self.env['ir.qweb']._render(template_xml_id, render_context or {})
                # Convert bytes to string if necessary and wrap in Markup for Odoo 18
                final_body_html = Markup(rendered.decode('utf-8') if isinstance(rendered, bytes) else rendered)
            except Exception as e:
                _logger.error(f"Failed to render QWeb template {template_xml_id}: {e}", exc_info=True)
                final_body_html = Markup(f"<p>Error rendering template: {template_xml_id}</p>")
        elif body_html:
            # Wrap plain HTML in Markup for Odoo 18
            final_body_html = Markup(body_html)

        if final_body_html and hasattr(self, '_append_record_reference_to_body_html'):
            final_body_html = self._append_record_reference_to_body_html(final_body_html)

        message_body = self._render_styled_message_card(
            card_type=card_type,
            icon=icon,
            title=title,
            body_html=final_body_html,
            submitted_by=self.env.user.name,
        )

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