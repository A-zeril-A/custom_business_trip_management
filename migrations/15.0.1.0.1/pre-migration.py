import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Run BEFORE module update (before schema changes):
    - Remove foreign key constraints to formio tables
    - Clean up dependencies before formio module is removed
    """
    _logger.info("=== Running PRE-migration script for version %s ===" % version)
    
    # Step 1: Drop foreign key constraints related to formio
    # This is necessary because we're removing the formio dependency
    
    tables_and_columns = [
        ('business_trip_data', 'form_id'),
        ('business_trip', 'formio_form_id'),
        ('accompanying_person', 'formio_form_id'),
        ('planned_trip_accommodation_line', 'form_id'),
        ('planned_trip_transport_line', 'form_id'),
    ]
    
    for table_name, column_name in tables_and_columns:
        try:
            # Check if column exists
            cr.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name=%s AND column_name=%s
            """, (table_name, column_name))
            
            if not cr.fetchone():
                continue
            
            _logger.info("Processing %s.%s..." % (table_name, column_name))
            
            # Find and drop all foreign key constraints on this column
            cr.execute("""
                SELECT con.conname
                FROM pg_constraint con
                JOIN pg_class rel ON rel.oid = con.conrelid
                JOIN pg_attribute att ON att.attnum = ANY(con.conkey) AND att.attrelid = con.conrelid
                WHERE rel.relname = %s 
                AND att.attname = %s
                AND con.contype = 'f'
            """, (table_name, column_name))
            
            constraints = cr.fetchall()
            for (constraint_name,) in constraints:
                _logger.info("Dropping foreign key constraint: %s" % constraint_name)
                cr.execute("ALTER TABLE %s DROP CONSTRAINT IF EXISTS %s" % (table_name, constraint_name))
            
            # Drop NOT NULL constraint if exists
            _logger.info("Removing NOT NULL constraint from %s.%s" % (table_name, column_name))
            cr.execute("ALTER TABLE %s ALTER COLUMN %s DROP NOT NULL" % (table_name, column_name))
            
            # Set all values to NULL
            _logger.info("Setting %s.%s to NULL" % (table_name, column_name))
            cr.execute("UPDATE %s SET %s = NULL" % (table_name, column_name))
            
            _logger.info("Successfully cleaned up %s.%s" % (table_name, column_name))
            
        except Exception as e:
            _logger.warning("Error processing %s.%s: %s" % (table_name, column_name, str(e)))
            # Continue with other columns
            pass
    
    _logger.info("Pre-migration cleanup completed successfully")

