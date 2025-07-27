# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import logging
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)

class BusinessTripCleanup(models.AbstractModel):
    _name = 'business.trip.cleanup'
    _description = 'Automated Cleanup for Business Trip Attachments'

    def _cron_cleanup_orphaned_attachments(self, older_than_hours=24):
        """
        Finds and deletes unlinked ir.attachment records created by the
        business trip upload controller that are older than a given time.
        """
        _logger.info("Starting orphaned business trip attachments cleanup cron job...")
        
        # Define the cutoff time
        cutoff_date = datetime.now() - timedelta(hours=older_than_hours)
        
        # Define the domain to find orphaned attachments:
        # - Created for our specific model
        # - Not linked to any record (res_id is 0)
        # - Older than our cutoff date
        domain = [
            ('res_model', '=', 'business.trip.data'),
            ('res_id', '=', 0),
            ('create_date', '<', fields.Datetime.to_string(cutoff_date))
        ]
        
        orphaned_attachments = self.env['ir.attachment'].search(domain)
        
        if orphaned_attachments:
            count = len(orphaned_attachments)
            _logger.info(f"Found {count} orphaned attachments to delete for business trip module.")
            try:
                orphaned_attachments.unlink()
                _logger.info(f"Successfully deleted {count} orphaned attachments.")
            except Exception as e:
                _logger.error(f"Error during orphaned attachment deletion: {e}", exc_info=True)
        else:
            _logger.info("No orphaned business trip attachments found to delete.")
            
        return True 