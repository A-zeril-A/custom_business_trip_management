# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class AccompanyingPerson(models.Model):
    _name = 'accompanying.person'
    _description = 'Accompanying Person for Business Trip'
    _rec_name = 'full_name'

    business_trip_id = fields.Many2one('business.trip.data', string='Business Trip', required=True, ondelete='cascade')
    formio_form_id = fields.Many2one('formio.form', string='Formio Form Reference')
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
        return super().create(vals_list)

    def write(self, vals):
        _logger.info(f"[AccompanyingPerson_WRITE] Updating accompanying person {self.full_name} with values: {vals.get('full_name', 'N/A')}, Document changed: {'identity_document' in vals}")
        return super().write(vals)

    def unlink(self):
        for record in self:
            _logger.info(f"[AccompanyingPerson_UNLINK] Deleting accompanying person: {record.full_name}")
        return super().unlink() 