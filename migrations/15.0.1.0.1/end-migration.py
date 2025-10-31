import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Run at the END of migration:
    Verify that formio-related columns are properly cleaned up (NULL values only)
    
    NOTE: We do NOT drop columns here! Odoo will handle that when fields are removed from models.
    This script just verifies that the cleanup was successful.
    """
    _logger.info("=== Running END-migration verification for version %s ===" % version)

    # List of columns to verify - these were related to formio which is now removed
    columns_to_verify = [
        ('business_trip_data', 'form_id'),
        ('business_trip', 'formio_form_id'),
        ('accompanying_person', 'formio_form_id'),
        ('planned_trip_accommodation_line', 'form_id'),
        ('planned_trip_transport_line', 'form_id'),
    ]

    for table_name, column_name in columns_to_verify:
        try:
            # Check if column exists
            cr.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name=%s AND column_name=%s
            """, (table_name, column_name))

            if not cr.fetchone():
                _logger.info("Column %s.%s does not exist (already removed)." % (table_name, column_name))
                continue

            # Check if column has any non-null values
            cr.execute("""
                SELECT COUNT(*)
                FROM %s
                WHERE %s IS NOT NULL
            """ % (table_name, column_name))

            non_null_count = cr.fetchone()[0]

            if non_null_count > 0:
                _logger.warning("Column %s.%s still has %s non-null values!"
                               % (table_name, column_name, non_null_count))
                _logger.warning("This should not happen. Manual intervention may be required.")
            else:
                _logger.info("Column %s.%s is clean (all NULL values). Will be removed when field is deleted from model."
                            % (table_name, column_name))

        except Exception as e:
            _logger.error("Error verifying column %s.%s: %s"
                          % (table_name, column_name, str(e)))
            # Don't raise - continue with other columns
            pass

    _logger.info("END-migration verification completed")

