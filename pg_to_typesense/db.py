import psycopg
from psycopg.rows import dict_row
from .utils import normalize_document_for_typesense, apply_column_aliases, remove_unmapped_fields, is_view

def get_db_connection(db_config):
    """Establishes and validates a connection to the PostgreSQL database."""
    try:
        conn = psycopg.connect(**db_config  )
        
        # Test connection with a simple query
        with conn.cursor() as cur:
            cur.execute("SELECT version();")
            version = cur.fetchone()[0]
            print(f"✓ Connected to PostgreSQL: {version.split(',')[0]}")
        
        return conn
        
    except psycopg.Error as e:
        print(f"✗ Failed to connect to PostgreSQL: {e}")
        raise
    except Exception as e:
        print(f"✗ Unexpected error connecting to database: {e}")
        raise

def setup_database_objects(conn, tables):
    """Validates database objects and creates only sync infrastructure with enhanced error handling."""
    with conn.cursor() as cur:
        try:
            # First, validate that all source tables exist
            missing_tables = []
            missing_reference_tables = []
            
            for table in tables:
                table_name = table['name']
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name = %s
                    );
                """, (table_name,))
                table_exists = cur.fetchone()[0]
                
                if not table_exists:
                    missing_tables.append(table_name)
                else:
                    # Check if it's a view
                    if is_view(conn, table_name):
                        print(f"✓ Source view '{table_name}' exists")
                        # Validate reference_table is specified for views
                        if 'reference_table' not in table:
                            raise Exception(f"View '{table_name}' requires 'reference_table' field in config")
                    else:
                        print(f"✓ Source table '{table_name}' exists")
                
                # Validate reference_table if specified
                if 'reference_table' in table:
                    ref_table = table['reference_table']
                    cur.execute("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_schema = 'public' 
                            AND table_name = %s
                        );
                    """, (ref_table,))
                    ref_exists = cur.fetchone()[0]
                    
                    if not ref_exists:
                        missing_reference_tables.append(f"{table_name} -> {ref_table}")
                    else:
                        print(f"✓ Reference table '{ref_table}' exists for '{table_name}'")
            
            if missing_tables:
                print(f"✗ Missing source tables: {', '.join(missing_tables)}")
                print("Please create these tables before running setup.")
                raise Exception(f"Source tables do not exist: {', '.join(missing_tables)}")
            
            if missing_reference_tables:
                print(f"✗ Missing reference tables: {', '.join(missing_reference_tables)}")
                raise Exception(f"Reference tables do not exist: {', '.join(missing_reference_tables)}")
            
            # Check if queue table exists and create if not
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'typesense_sync_queue'
                );
            """)
            table_exists = cur.fetchone()[0]
            
            if not table_exists:
                print("Creating typesense_sync_queue table...")
                cur.execute("""
                    CREATE TABLE typesense_sync_queue (
                        id BIGSERIAL PRIMARY KEY, 
                        record_id TEXT NOT NULL, 
                        table_name TEXT NOT NULL, 
                        operation_type VARCHAR(10) NOT NULL, 
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                print("✓ Queue table created")
            else:
                print("✓ Queue table already exists")
            
            # Check if trigger function exists and create/replace
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM pg_proc 
                    WHERE proname = 'log_changes_for_typesense'
                );
            """)
            function_exists = cur.fetchone()[0]
            
            print("Creating/updating trigger function...")
            cur.execute("""
                CREATE OR REPLACE FUNCTION log_changes_for_typesense() 
                RETURNS TRIGGER AS $$ 
                BEGIN 
                    IF (TG_OP = 'DELETE') THEN 
                        INSERT INTO typesense_sync_queue (record_id, table_name, operation_type) 
                        VALUES (OLD.id::TEXT, TG_TABLE_NAME, 'DELETE'); 
                        RETURN OLD; 
                    ELSE 
                        INSERT INTO typesense_sync_queue (record_id, table_name, operation_type) 
                        VALUES (NEW.id::TEXT, TG_TABLE_NAME, TG_OP); 
                        RETURN NEW; 
                    END IF; 
                END; 
                $$ LANGUAGE plpgsql;
            """)
            print("✓ Trigger function created/updated")
            
            # Create trigger function with custom table name for view support
            cur.execute("""
                CREATE OR REPLACE FUNCTION log_changes_for_typesense_with_name() 
                RETURNS TRIGGER AS $$ 
                DECLARE
                    target_table_name TEXT;
                BEGIN 
                    -- Get the table name from trigger arguments
                    target_table_name := TG_ARGV[0];
                    
                    IF (TG_OP = 'DELETE') THEN 
                        INSERT INTO typesense_sync_queue (record_id, table_name, operation_type) 
                        VALUES (OLD.id::TEXT, target_table_name, 'DELETE'); 
                        RETURN OLD; 
                    ELSE 
                        INSERT INTO typesense_sync_queue (record_id, table_name, operation_type) 
                        VALUES (NEW.id::TEXT, target_table_name, TG_OP); 
                        RETURN NEW; 
                    END IF; 
                END; 
                $$ LANGUAGE plpgsql;
            """)
            print("✓ View-aware trigger function created/updated")
            
            # Setup triggers for each table (we've already validated all tables exist)
            for table in tables:
                table_name = table['name']
                
                # For views, attach trigger to reference_table instead
                if 'reference_table' in table:
                    ref_table = table['reference_table']
                    trigger_name = f"trigger_{ref_table}_to_{table_name}_typesense"
                    target_table = ref_table
                    print(f"Setting up trigger for view '{table_name}' via reference table '{ref_table}'...")
                    trigger_function = f"log_changes_for_typesense_with_name('{table_name}')"
                else:
                    trigger_name = f"trigger_{table_name}_to_typesense"
                    target_table = table_name
                    trigger_function = "log_changes_for_typesense()"
                
                # Check if trigger already exists
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM pg_trigger 
                        WHERE tgname = %s 
                        AND tgrelid = %s::regclass
                    );
                """, (trigger_name, target_table))
                trigger_exists = cur.fetchone()[0]
                
                if not trigger_exists:
                    print(f"Creating trigger on '{target_table}'...")
                    cur.execute(f"""
                        CREATE TRIGGER {trigger_name} 
                        AFTER INSERT OR UPDATE OR DELETE ON {target_table} 
                        FOR EACH ROW EXECUTE FUNCTION {trigger_function};
                    """)
                    print(f"✓ Trigger created on '{target_table}' for syncing '{table_name}'")
                else:
                    print(f"✓ Trigger on '{target_table}' already exists")
                    
        except psycopg.Error as e:
            print(f"Database error during setup: {e}")
            conn.rollback()
            raise
        except Exception as e:
            print(f"Unexpected error during database setup: {e}")
            conn.rollback()
            raise
            
    conn.commit()
    print("✓ Database setup completed successfully")


def backfill_queue(db_conn, tables):
    """Populates the sync queue with all existing records for initial data load."""
    total_records_queued = 0
    
    for table in tables:
        table_name = table['name']
        collection_name = table['collection']
        table_records_queued = 0
        
        print(f"Starting backfill for table '{table_name}' → collection '{collection_name}'...")
        
        try:
            # Check if source table exists and has data
            with db_conn.cursor() as check_cur:
                check_cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name = %s
                    );
                """, (table_name,))
                table_exists = check_cur.fetchone()[0]
                
                if not table_exists:
                    print(f"⚠ Warning: Table '{table_name}' does not exist. Skipping backfill.")
                    continue
                
                # Get record count for progress tracking
                check_cur.execute(f"SELECT COUNT(*) FROM {table_name}")
                total_records = check_cur.fetchone()[0]
                print(f"  Total records to queue: {total_records}")
                
                if total_records == 0:
                    print(f"  Table '{table_name}' is empty. Skipping backfill.")
                    continue
            
            # Populate sync queue with all record IDs
            with db_conn.cursor() as insert_cur:
                print(f"  Queuing all records from '{table_name}' for sync...")
                
                # Insert all record IDs into the sync queue as INSERT operations
                insert_cur.execute(f"""
                    INSERT INTO typesense_sync_queue (record_id, table_name, operation_type)
                    SELECT id::TEXT, %s, 'INSERT'
                    FROM {table_name}
                    ORDER BY id
                """, (table_name,))
                
                table_records_queued = insert_cur.rowcount
                total_records_queued += table_records_queued
                
                print(f"✓ Queued {table_records_queued} records from table '{table_name}'")
            
            # Commit after each table
            db_conn.commit()
            
        except Exception as e:
            print(f"✗ Failed to queue records from table '{table_name}': {e}")
            db_conn.rollback()
            # Continue with next table instead of failing completely
            continue
    
    print(f"\n✓ Backfill process completed: {total_records_queued} total records queued")
    print(f"  Run 'sync' command to process the queue and load data into Typesense")
