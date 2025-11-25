import sys
from collections import defaultdict
from psycopg.rows import dict_row
from .db import Database
from .typesense_client import get_typesense_client, setup_typesense_collections
from .utils import normalize_document_for_typesense, apply_column_aliases, remove_unmapped_fields

def setup(config, recreate_collections=False, skip_backfill=True):
    """Main function to handle the setup command with enhanced initialization logic.
    
    Args:
        config: Configuration dictionary
        recreate_collections: Whether to recreate existing Typesense collections
        skip_backfill: Whether to skip initial data backfill (default: True)
    """
    print("Starting setup...")
    
    # Initialize database connection with error handling
    db = Database(config['postgresql'])
    
    # Initialize Typesense client with error handling
    try:
        ts_client = get_typesense_client(config['typesense'])
        print("✓ Typesense client initialized")
    except Exception as e:
        print(f"✗ Failed to initialize Typesense client: {e}")
        return False
    
    # Setup database objects with validation
    try:
        db.setup_database_objects(config['tables'])
        print("✓ Database objects setup completed")
    except Exception as e:
        print(f"✗ Failed to setup database objects: {e}")
        return False
    
    # Setup Typesense collections with validation
    try:
        setup_typesense_collections(ts_client, config['tables'], recreate_collections)
        print("✓ Typesense collections setup completed")
    except Exception as e:
        print(f"✗ Failed to setup Typesense collections: {e}")
        return False
    
    # Perform backfill if requested
    if not skip_backfill:
        print("Starting initial data backfill...")
        try:
            db.backfill_queue(config['tables'])
            print("✓ Data backfill completed")
        except Exception as e:
            print(f"✗ Failed during data backfill: {e}")
            return False
    else:
        print("ℹ Queue backfill skipped (use --backfill-queue to enable)")
    
    print("\n✓ Setup completed successfully")
    return True


def sync(config, batch_size=100):
    """Processes all changes from the queue in batches with enhanced error handling."""
    print(f"Starting sync process (batch size: {batch_size})...")
    
    # Initialize connections with error handling
    db = Database(config['postgresql'])
    try:
        db_conn = db.get_db_connection()
    except Exception as e:
        print(f"✗ Failed to connect to database for sync: {e}")
        return False
    
    try:
        ts_client = get_typesense_client(config['typesense'])
    except Exception as e:
        print(f"✗ Failed to connect to Typesense for sync: {e}")
        db.close_db_connection(db_conn)
        return False
    
    table_map = {t['name']: t for t in config['tables']}
    
    # Check if sync queue table exists
    try:
        with db_conn.cursor(row_factory=dict_row) as check_cur:
            check_cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'typesense_sync_queue'
                ) as queue_exists;
            """)
            result = check_cur.fetchone()
            queue_exists = result['queue_exists']
            if not queue_exists:
                print("✗ Sync queue table does not exist. Please run setup first.")
                db.close_db_connection(db_conn)
                return False
            
            # Get total count of jobs to process
            check_cur.execute("SELECT COUNT(*) as total FROM typesense_sync_queue")
            total_jobs = check_cur.fetchone()['total']
            
            if total_jobs == 0:
                print("✓ No new jobs to process.")
                db.close_db_connection(db_conn)
                return True
            
            print(f"Total jobs in queue: {total_jobs}")
    except Exception as e:
        print(f"✗ Failed to check sync queue: {e}")
        db.close_db_connection(db_conn)
        return False
    
    # Process all jobs in batches
    total_processed = 0
    batch_number = 0
    
    while True:
        batch_number += 1
        print(f"\n--- Batch {batch_number} ---")
        
        try:
            # Start a transaction manually
            with db_conn.cursor(row_factory=dict_row) as cur:
                # Fetch jobs from queue
                table_name_placeholders = ', '.join(['%s'] * len(table_map.keys()))

                # Build the full SQL query
                sql_query = f"""
                    SELECT * FROM typesense_sync_queue
                    WHERE table_name IN ({table_name_placeholders})
                    ORDER BY created_at ASC
                    LIMIT %s
                    FOR UPDATE SKIP LOCKED;
                """

                # Create a list of parameters in the correct order
                params = list(table_map.keys()) + [batch_size]

                cur.execute(sql_query, params)
                jobs = cur.fetchall()

                if not jobs:
                    print("✓ No more jobs to process in this batch.")
                    break

                print(f"Processing {len(jobs)} jobs from sync queue...")
                
                # Deduplicate jobs (keep latest operation for each record)
                final_ops = { (job['record_id'], job['table_name']): job for job in jobs }
                print(f"After deduplication: {len(final_ops)} unique operations")

                ids_to_fetch = defaultdict(list)
                deletes = defaultdict(list)

                # Categorize operations
                for (record_id, table_name), job in final_ops.items():
                    if table_name not in table_map:
                        print(f"⚠ Warning: Unknown table '{table_name}' in sync queue. Skipping.")
                        continue
                        
                    collection = table_map[table_name]['collection']
                    if job['operation_type'] in ['INSERT', 'UPDATE']:
                        ids_to_fetch[table_name].append(record_id)
                    elif job['operation_type'] == 'DELETE':
                        deletes[collection].append({'id': record_id})

                # Process upserts
                upserts = defaultdict(list)
                for table_name, ids in ids_to_fetch.items():
                    if table_name not in table_map:
                        continue
                        
                    transformer = table_map[table_name]['transformer']
                    collection = table_map[table_name]['collection']
                    schema = table_map[table_name]['schema']
                    column_mapping = table_map[table_name].get('column_mapping', {})

                    try:
                        cur.execute(f"SELECT * FROM {table_name} WHERE id = ANY(%s)", (ids,))
                        records = {str(row['id']): dict(row) for row in cur.fetchall()}

                        for record_id in ids:
                            if record_id in records:
                                try:
                                    doc = transformer(records[record_id])
                                    # Apply column aliasing (PostgreSQL names -> Typesense names)
                                    doc = apply_column_aliases(doc, column_mapping)
                                    # Remove fields not in schema
                                    doc = remove_unmapped_fields(doc, schema)
                                    # Normalize document values (handles date conversion automatically)
                                    doc = normalize_document_for_typesense(doc, schema)
                                    # print(f"✓ Transformed record {doc}")
                                    upserts[collection].append(doc)
                                except Exception as e:
                                    print(f"⚠ Warning: Failed to transform record {record_id}: {e}")
                            else:
                                # Record no longer exists, treat as delete
                                deletes[collection].append({'id': record_id})
                                
                    except Exception as e:
                        print(f"⚠ Warning: Failed to fetch records from table '{table_name}': {e}")

                # Sync to Typesense
                sync_success = True
                try:
                    upsert_count = 0
                    delete_count = 0
                    
                    for collection, docs in upserts.items():
                        if docs:
                            try:
                                result = ts_client.collections[collection].documents.import_(docs, {'action': 'upsert'})
                                upsert_count += len(docs)
                                print(f"✓ Upserted {len(docs)} documents to collection '{collection}'")
                                for doc in result:
                                    if doc['success'] is False:
                                        print(f"Error upserting document: {doc['error']}")
                                        sync_success = False
                            except Exception as e:
                                print(f"✗ Failed to upsert to collection '{collection}': {e}")
                                sync_success = False
                                
                    for collection, docs in deletes.items():
                        if docs:
                            try:
                                # Delete documents individually (Typesense doesn't support batch delete via import_)
                                deleted = 0
                                failed = 0
                                for doc in docs:
                                    try:
                                        result = ts_client.collections[collection].documents[doc['id']].delete()
                                        # Validate the result has the expected id field
                                        if result and 'id' in result:
                                            deleted += 1
                                        else:
                                            print(f"⚠ Warning: Unexpected delete response for document {doc['id']}: {result}")
                                            failed += 1
                                    except Exception as del_err:
                                        # Document may already be deleted (404), treat as success
                                        if "404" in str(del_err) or "Not Found" in str(del_err):
                                            deleted += 1
                                        else:
                                            print(f"⚠ Warning: Failed to delete document {doc['id']}: {del_err}")
                                            failed += 1
                                            sync_success = False
                                delete_count += deleted
                                if failed > 0:
                                    print(f"✓ Deleted {deleted} documents from collection '{collection}' ({failed} failed)")
                                else:
                                    print(f"✓ Deleted {deleted} documents from collection '{collection}'")
                            except Exception as e:
                                print(f"✗ Failed to delete from collection '{collection}': {e}")
                                sync_success = False
                    
                    if not sync_success:
                        raise Exception("One or more Typesense operations failed")
                        
                    print(f"✓ Batch sync completed: {upsert_count} upserts, {delete_count} deletes")
                    
                except Exception as e:
                    print(f"✗ Error syncing to Typesense: {e}")
                    db_conn.rollback()
                    raise  # Re-raise to exit the loop

                # Clean up processed jobs
                try:
                    job_ids = [job['id'] for job in jobs]
                    cur.execute("DELETE FROM typesense_sync_queue WHERE id = ANY(%s)", (job_ids,))
                    deleted_count = cur.rowcount
                    total_processed += deleted_count
                    print(f"✓ Removed {deleted_count} processed jobs from queue")
                except Exception as e:
                    print(f"⚠ Warning: Failed to clean up processed jobs: {e}")
                    db_conn.rollback()
                    raise  # Re-raise to exit the loop
                
                # Commit the transaction
                db_conn.commit()
                
                    
        except Exception as e:
            print(f"✗ Error in batch {batch_number}: {e}")
            print("  Transaction rolled back. Jobs remain in queue for retry.")
            # Continue to next batch or exit based on error type
            break
    
    db.close_db_connection(db_conn)
    
    if total_processed > 0:
        print(f"\n✓ Sync completed successfully: {total_processed} total jobs processed in {batch_number} batch(es)")
        return True
    else:
        print(f"\n⚠ Sync completed with no jobs processed")
        return False


def status(config):
    """Display current sync system status, queue statistics, and connection health."""
    print("=" * 70)
    print("PostgreSQL to Typesense Sync - System Status")
    print("=" * 70)
    
    # Test PostgreSQL connection
    print("\n[Database Connection]")
    db = Database(config['postgresql'])
    try:
        db_conn = db.get_db_connection()
        print(f"✓ PostgreSQL: Connected")
        print(f"  Host: {config['postgresql']['host']}:{config['postgresql']['port']}")
        print(f"  Database: {config['postgresql']['dbname']}")
    except Exception as e:
        print(f"✗ PostgreSQL: Connection failed")
        print(f"  Error: {e}")
        return False
    
    # Test Typesense connection
    print("\n[Typesense Connection]")
    try:
        ts_client = get_typesense_client(config['typesense'])
        print(f"✓ Typesense: Connected")
        print(f"  Host: {config['typesense']['protocol']}://{config['typesense']['host']}:{config['typesense']['port']}")
        
        # Get collection information
        try:
            collections_response = ts_client.collections.retrieve()
            existing_collections = {c['name']: c for c in collections_response}
            print(f"  Collections: {len(existing_collections)} total")
        except Exception as e:
            print(f"  ⚠ Warning: Could not retrieve collections: {e}")
            existing_collections = {}
    except Exception as e:
        print(f"✗ Typesense: Connection failed")
        print(f"  Error: {e}")
        db_conn.close()
        return False
    
    # Check if sync queue exists
    print("\n[Sync Infrastructure]")
    try:
        with db_conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'typesense_sync_queue'
                ) as queue_exists;
            """)
            queue_exists = cur.fetchone()['queue_exists']
            
            if queue_exists:
                print("✓ Sync queue table: Exists")
                
                # Get queue statistics
                cur.execute("""
                    SELECT 
                        COUNT(*) as total_jobs,
                        MIN(created_at) as oldest_job,
                        MAX(created_at) as newest_job
                    FROM typesense_sync_queue
                """)
                stats = cur.fetchone()
                
                print(f"\n[Queue Statistics]")
                print(f"Total pending jobs: {stats['total_jobs']}")
                
                if stats['total_jobs'] > 0:
                    print(f"Oldest job: {stats['oldest_job']}")
                    print(f"Newest job: {stats['newest_job']}")
                    
                    # Get breakdown by table and operation
                    cur.execute("""
                        SELECT 
                            table_name,
                            operation_type,
                            COUNT(*) as count
                        FROM typesense_sync_queue
                        GROUP BY table_name, operation_type
                        ORDER BY table_name, operation_type
                    """)
                    breakdown = cur.fetchall()
                    
                    if breakdown:
                        print("\nBreakdown by table and operation:")
                        current_table = None
                        for row in breakdown:
                            if current_table != row['table_name']:
                                print(f"  {row['table_name']}:")
                                current_table = row['table_name']
                            print(f"    {row['operation_type']}: {row['count']} jobs")
                else:
                    print("✓ Queue is empty (no pending jobs)")
                    
            else:
                print("✗ Sync queue table: Does not exist")
                print("  Run 'setup' command to initialize sync infrastructure")
    except Exception as e:
        print(f"✗ Failed to check sync infrastructure: {e}")
    
    # Check configured tables and collections
    print(f"\n[Configured Tables]")
    print(f"Total configured: {len(config['tables'])}")
    
    for table in config['tables']:
        table_name = table['name']
        collection_name = table['collection']
        print(f"\n  Table: {table_name} → Collection: {collection_name}")
        
        # Check if source table exists
        try:
            with db_conn.cursor() as cur:
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name = %s
                    );
                """, (table_name,))
                table_exists = cur.fetchone()[0]
                
                if table_exists:
                    print(f"    ✓ Source table exists")
                    
                    # Get record count
                    cur.execute(f"SELECT COUNT(*) FROM {table_name}")
                    count = cur.fetchone()[0]
                    print(f"      Records: {count}")
                    
                    # Check if trigger exists
                    trigger_name = f"trigger_{table_name}_to_typesense"
                    cur.execute("""
                        SELECT EXISTS (
                            SELECT FROM pg_trigger 
                            WHERE tgname = %s 
                            AND tgrelid = %s::regclass
                        );
                    """, (trigger_name, table_name))
                    trigger_exists = cur.fetchone()[0]
                    
                    if trigger_exists:
                        print(f"      ✓ Trigger installed")
                    else:
                        print(f"      ✗ Trigger not found")
                else:
                    print(f"    ✗ Source table does not exist")
        except Exception as e:
            print(f"    ✗ Error checking source table: {e}")
        
        # Check if Typesense collection exists
        if collection_name in existing_collections:
            collection_info = existing_collections[collection_name]
            print(f"    ✓ Typesense collection exists")
            print(f"      Fields: {len(collection_info.get('fields', []))}")
            print(f"      Documents: {collection_info.get('num_documents', 0)}")
        else:
            print(f"    ✗ Typesense collection does not exist")
            print(f"      Run 'setup' command to create collections")
    
    db.close_db_connection(db_conn)
    print("\n" + "=" * 70)
    print("Status check completed")
    print("=" * 70)
    return True
