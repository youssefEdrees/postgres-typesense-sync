import atexit
import psycopg
from psycopg_pool import ConnectionPool
from .utils import is_view


class Database:
    def __init__(self, db_config):
        self.db_config = db_config
        self._connection_pool = None
        atexit.register(self._close_pool)

    def _close_pool(self):
        if self._connection_pool is not None:
            try:
                self._connection_pool.close()
                self._connection_pool = None
                print("✓ Database connection pool closed")
            except Exception as e:
                print(f"⚠ Warning: Error closing connection pool: {e}")

    def get_connection_pool(self):
        """Get or create a connection pool for the database."""
        if self._connection_pool is None:
            try:
                # Build connection string from config
                conninfo = f"host={self.db_config['host']} port={self.db_config['port']} " \
                          f"dbname={self.db_config['dbname']} user={self.db_config['user']} " \
                          f"password={self.db_config['password']}"
                
                # Create connection pool - connections created on demand
                self._connection_pool = ConnectionPool(
                    conninfo=conninfo,
                    min_size=1,  # Minimum connections to maintain
                    max_size=10,  # Maximum number of connections
                    max_waiting=5,  # Max clients waiting for a connection
                    timeout=10,  # Wait max 10 seconds to get a connection from pool
                    max_idle=300  # Maximum idle time before connection is closed (5 minutes)
                )
            except Exception as e:
                print(f"✗ Failed to create connection pool: {e}")
                raise
        
        return self._connection_pool

    def get_db_connection(self):
        """Get a connection from the pool.
        
        Raises an exception if the connection pool cannot be created or a connection cannot be obtained.
        """
        pool = self.get_connection_pool()
        conn = pool.getconn()
        return conn

    def close_db_connection(self, conn):
        """Return a connection back to the pool."""
        pool = self.get_connection_pool()
        pool.putconn(conn)

    def setup_database_objects(self, tables):
        """Validates database objects and creates only sync infrastructure with enhanced error handling."""
        conn = self.get_db_connection()
        try:
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
        finally:
            self.close_db_connection(conn)

    def backfill_queue(self, tables):
        """Populates the sync queue with all existing records for initial data load."""
        total_records_queued = 0
        
        for table in tables:
            table_name = table['name']
            collection_name = table['collection']
            table_records_queued = 0
            
            print(f"Starting backfill for table '{table_name}' → collection '{collection_name}'...")
            
            try:
                conn = self.get_db_connection()
                try:
                    # Check if source table exists and has data
                    with conn.cursor() as check_cur:
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
                    with conn.cursor() as insert_cur:
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
                    conn.commit()
                    
                finally:
                    self.close_db_connection(conn)
                
            except Exception as e:
                print(f"✗ Failed to queue records from table '{table_name}': {e}")
                # No rollback needed since we commit per table
                continue
        
        print(f"\n✓ Backfill process completed: {total_records_queued} total records queued")
        print("  Run 'sync' command to process the queue and load data into Typesense")
