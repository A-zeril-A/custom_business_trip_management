import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Run AFTER module update (after schema changes):
    Set form_completion_status based on submission_date and trip_status
    """
    _logger.info("=== Running POST-migration script for version %s ===" % version)
    
    # Check if form_completion_status column exists
    cr.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='business_trip' 
        AND column_name='form_completion_status'
    """)
    
    if not cr.fetchone():
        _logger.info("Column 'form_completion_status' does not exist yet. Skipping migration.")
        return
    
    try:
        _logger.info("Starting form completion status migration based on submission_date and trip_status...")
        
        # Set form_completion_status based on business logic:
        # 1. If trip is cancelled -> 'cancelled'
        # 2. If trip_status is NOT 'draft' (moved beyond Awaiting Submission) -> 'form_completed'
        # 3. If submission_date is set -> 'form_completed'
        # 4. Otherwise -> 'awaiting_completion'
        cr.execute("""
            UPDATE business_trip
            SET form_completion_status = 
                CASE 
                    WHEN trip_status = 'cancelled' THEN 'cancelled'
                    WHEN trip_status != 'draft' THEN 'form_completed'
                    WHEN submission_date IS NOT NULL THEN 'form_completed'
                    ELSE 'awaiting_completion'
                END
            WHERE form_completion_status = 'awaiting_completion'
               OR form_completion_status IS NULL;
        """)
        
        migrated_count = cr.rowcount
        _logger.info("Successfully migrated form completion status for %s business trips." % migrated_count)
        
        # Log statistics
        cr.execute("""
            SELECT form_completion_status, COUNT(*) 
            FROM business_trip 
            GROUP BY form_completion_status
        """)
        stats = cr.fetchall()
        _logger.info("Form completion status distribution after migration:")
        for status, count in stats:
            _logger.info("  - %s: %s records" % (status, count))
            
    except Exception as e:
        _logger.error("Unexpected error during migration: %s" % str(e))
        raise

