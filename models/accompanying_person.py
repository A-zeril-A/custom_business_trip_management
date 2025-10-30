# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class AccompanyingPerson(models.Model):
    _name = 'accompanying.person'
    _description = 'Accompanying Person for Business Trip'
    _rec_name = 'full_name'

    business_trip_id = fields.Many2one('business.trip.data', string='Business Trip', required=True, ondelete='cascade')
    # Modified by A_zeril_A, 2025-10-20: Removed formio dependency
    # formio_form_id = fields.Many2one('formio.form', string='Formio Form Reference')
    full_name = fields.Char(string='Full Name', required=True, tracking=True)
    identity_document = fields.Binary(string='Identity Document', attachment=True, tracking=True)
    identity_document_filename = fields.Char(string='Identity Document Filename')
    identity_document_attachment_id = fields.Many2one('ir.attachment', string="Identity Document Attachment", store=True)
    identity_document_download_url = fields.Char(string="Download URL", compute='_compute_download_url', store=False)
    identity_document_download_link_html = fields.Html(string="Document", compute='_compute_download_link_html', sanitize=False)

    @api.depends('identity_document_attachment_id')
    def _compute_download_url(self):
        for record in self:
            if record.identity_document_attachment_id:
                base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
                record.identity_document_download_url = f"{base_url}/web/content/{record.identity_document_attachment_id.id}?download=true"
            else:
                record.identity_document_download_url = False

    @api.depends('identity_document_download_url')
    def _compute_download_link_html(self):
        for record in self:
            if record.identity_document_download_url:
                record.identity_document_download_link_html = f'<a href="{record.identity_document_download_url}" title="Download Document"><i class="fa fa-download"></i></a>'
            else:
                record.identity_document_download_link_html = False

    @classmethod
    def _valid_field_parameter(cls, field, name):
        return name == 'tracking' or super()._valid_field_parameter(field, name)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            _logger.info(f"[AccompanyingPerson_CREATE] Creating accompanying person with values: {vals.get('full_name', 'N/A')}")
        records = super().create(vals_list)
        # Update attachment IDs after creation
        for record in records:
            record._update_attachment_id()
        return records

    def write(self, vals):
        # Log for each record in the recordset
        for record in self:
            _logger.info(f"[AccompanyingPerson_WRITE] Updating accompanying person {record.full_name} with values: {vals.get('full_name', 'N/A')}, Document changed: {'identity_document' in vals}")
        result = super().write(vals)
        # Update attachment ID after write if document was changed
        if 'identity_document' in vals:
            self._update_attachment_id()
        return result
    
    def _update_attachment_id(self):
        """
        Update identity_document_attachment_id by finding the attachment for the binary field.
        This is needed because when a binary field with attachment=True is saved,
        Odoo automatically creates an attachment, but we need to link it explicitly
        to use it for download links.
        """
        for record in self:
            if record.identity_document:
                attachment = self.env['ir.attachment'].search([
                    ('res_model', '=', 'accompanying.person'),
                    ('res_id', '=', record.id),
                    ('res_field', '=', 'identity_document')
                ], limit=1, order='id desc')
                current_attachment_id = record.identity_document_attachment_id.id if record.identity_document_attachment_id else False
                if attachment and attachment.id != current_attachment_id:
                    # Use sudo().write() to avoid triggering write method again
                    record.sudo().write({
                        'identity_document_attachment_id': attachment.id,
                        'identity_document_filename': record.identity_document_filename or attachment.name
                    })
                    _logger.info(f"[AccompanyingPerson] Linked attachment {attachment.id} ({attachment.name}) to person {record.full_name}")

    def unlink(self):
        for record in self:
            _logger.info(f"[AccompanyingPerson_UNLINK] Deleting accompanying person: {record.full_name}")
        return super().unlink() 