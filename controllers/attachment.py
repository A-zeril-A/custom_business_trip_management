# -*- coding: utf-8 -*-

import json
import logging
import base64
import magic
import hashlib
import mimetypes
from odoo import http, fields, tools
from odoo.http import request, Response
from odoo.exceptions import UserError
from datetime import datetime, timedelta, timezone

_logger = logging.getLogger(__name__)


class BusinessTripAttachmentController(http.Controller):
    """
    Secure and robust controller for handling asynchronous file uploads.
    """
    
    # Security settings
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    ALLOWED_EXTENSIONS = {'.pdf', '.jpg', '.jpeg', '.png', '.doc', '.docx', '.xls', '.xlsx'}
    ALLOWED_MIME_TYPES = {
        'application/pdf', 'image/jpeg', 'image/png', 
        'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    }
    MAX_UPLOADS_PER_HOUR = 50

    # --- Main Routes ---

    @http.route('/business_trip/upload_attachment', type='http', auth='user', methods=['POST'], csrf=False)
    def upload_attachment(self, **kwargs):
        """ Handles the secure upload of a file. """
        try:
            # 1. Rate Limiting
            if not self._is_rate_limit_ok(request):
                return self._error_response("Too many uploads. Try again later.", 429)

            # 2. File and Filename Validation
            uploaded_file = request.httprequest.files.get('file')
            if not uploaded_file or not uploaded_file.filename:
                return self._error_response("No file or filename provided.", 400)

            filename = uploaded_file.filename
            file_ext = '.' + filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
            if file_ext not in self.ALLOWED_EXTENSIONS:
                _logger.warning(f"User {request.env.user.login} uploaded file with disallowed extension: {file_ext}")
                return self._error_response("Invalid file type.", 400)

            # 3. File Content and Size Validation
            file_content = uploaded_file.read()
            file_size = len(file_content)

            if file_size > self.MAX_FILE_SIZE:
                return self._error_response("File is too large.", 413)
            if file_size == 0:
                return self._error_response("File is empty.", 400)

            # 4. Secure MIME and Duplicate Detection
            detected_mime = self._detect_mime_type(file_content, filename)
            if detected_mime not in self.ALLOWED_MIME_TYPES:
                _logger.warning(f"User {request.env.user.login} uploaded disallowed MIME: {detected_mime} for file {filename}")
                return self._error_response("Invalid file content.", 400)

            file_hash = hashlib.sha256(file_content).hexdigest()
            if self._is_duplicate(request, file_hash):
                return self._error_response("Duplicate file detected.", 409)

            # 5. Create Attachment
            attachment_vals = {
                'name': tools.ustr(filename),
                'datas': base64.b64encode(file_content),
                'res_model': 'business.trip.data',
                'res_id': 0,
                'mimetype': detected_mime,
                'checksum': file_hash,
                'public': False,
            }

            attachment = request.env['ir.attachment'].create(attachment_vals)
            _logger.info(f"User {request.env.user.login} uploaded attachment ID {attachment.id}: {filename}")

            # 6. Log upload and prepare success response
            self._log_upload_for_rate_limit(request)
            
            base_url = request.httprequest.host_url.rstrip('/')
            response_data = {
                'id': attachment.id,
                'name': filename,
                'size': file_size,
                'type': detected_mime,
                'url': f'{base_url}/web/content/{attachment.id}?access_token={attachment.access_token}',
                'storage': 'url',
                'attachment_id': attachment.id,
            }
            
            return self._success_response({'result': response_data})

        except UserError as e:
            return self._error_response(f"Upload failed: {e}", 400)
        except Exception as e:
            _logger.error(f"Unexpected error during upload: {str(e)}", exc_info=True)
            return self._error_response("Server error during upload.", 500)

    @http.route('/business_trip/delete_attachment/<int:attachment_id>', type='http', auth='user', methods=['DELETE'], csrf=False)
    def delete_attachment(self, attachment_id, **kwargs):
        """ Handles the secure deletion of a file. """
        try:
            attachment = request.env['ir.attachment'].browse(attachment_id).exists()
            if not attachment:
                return self._error_response("Attachment not found", 404)

            # Security checks: must be an unlinked attachment from this module, owned by the user
            if attachment.res_id != 0 or attachment.res_model != 'business.trip.data' or attachment.create_uid.id != request.env.user.id:
                _logger.warning(f"Forbidden attempt by user {request.env.user.login} to delete attachment {attachment_id}")
                return self._error_response("Permission denied", 403)

            filename = attachment.name
            attachment.unlink()
            _logger.info(f"User {request.env.user.login} deleted attachment {attachment_id}: {filename}")
            
            return self._success_response({"message": "File deleted successfully"})

        except Exception as e:
            _logger.error(f"Error deleting attachment {attachment_id}: {str(e)}", exc_info=True)
            return self._error_response("Delete failed", 500)

    @http.route(['/business_trip/upload_attachment', '/business_trip/delete_attachment/<int:attachment_id>'], type='http', auth='user', methods=['OPTIONS'], csrf=False)
    def options_handler(self, **kwargs):
        """ Handles CORS preflight requests. """
        return self._success_response({})

    # --- Helper Methods ---

    def _detect_mime_type(self, content, filename):
        """Detect MIME type using magic and fallback to mimetypes."""
        try:
            return magic.from_buffer(content, mime=True)
        except Exception:
            _logger.warning(f"MIME detection via magic failed for {filename}. Falling back to extension.")
            return mimetypes.guess_type(filename)[0] or 'application/octet-stream'

    def _is_duplicate(self, req, file_hash):
        """Check if the same file has been uploaded by the user recently."""
        domain = [
            ('checksum', '=', file_hash),
            ('create_uid', '=', req.env.user.id),
            ('res_model', '=', 'business.trip.data'),
            ('res_id', '=', 0),
            ('create_date', '>=', fields.Datetime.now() - timedelta(hours=24))
        ]
        return req.env['ir.attachment'].search_count(domain) > 0

    def _is_rate_limit_ok(self, req):
        """Check if user has exceeded upload rate limit. Read-only."""
        try:
            history = req.session.get('upload_history', [])
            now = datetime.now(timezone.utc)
            # Filter history to the last hour
            recent_uploads = [ts for ts in history if now - datetime.fromisoformat(ts) < timedelta(hours=1)]
            req.session['upload_history'] = recent_uploads # Clean up session
            
            if len(recent_uploads) >= self.MAX_UPLOADS_PER_HOUR:
                _logger.warning(f"Rate limit hit for user {req.env.user.login}")
                return False
            return True
        except Exception:
            return True # Fail open

    def _log_upload_for_rate_limit(self, req):
        """Log a new upload time for rate limiting."""
        try:
            history = req.session.get('upload_history', [])
            history.append(datetime.now(timezone.utc).isoformat())
            req.session['upload_history'] = history
        except Exception as e:
            _logger.warning(f"Could not log upload for rate limit: {e}")

    # --- Response Methods with CORS ---

    def _set_cors_headers(self, response):
        """Utility to set common CORS headers."""
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'POST, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-Requested-With'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Max-Age'] = '86400'

    def _error_response(self, message, status=400):
        """Return a JSON error response with CORS headers."""
        response = Response(
            json.dumps({'error': message}),
            status=status,
            content_type='application/json'
        )
        self._set_cors_headers(response)
        return response

    def _success_response(self, data, status=200):
        """Return a JSON success response with CORS headers."""
        response = Response(
            json.dumps(data),
            status=status,
            content_type='application/json'
        )
        self._set_cors_headers(response)
        return response