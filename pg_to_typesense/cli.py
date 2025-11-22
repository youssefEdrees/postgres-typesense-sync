import argparse
from .config import load_config
from .sync import setup, sync

def main():
    parser = argparse.ArgumentParser(description="PostgreSQL to Typesense Sync Tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    setup_parser = subparsers.add_parser("setup", help="Bootstrap the sync environment.")
    setup_parser.add_argument("--recreate", action="store_true", help="Force deletion and recreation of Typesense collections.")
    setup_parser.add_argument("--backfill-queue", action="store_true", help="Queue all existing records for sync (not run by default).")
    setup_parser.add_argument("--tables", type=str, help="Comma-separated list of table names to process (e.g., 'products,users'). If not specified, all tables are processed.")

    sync_parser = subparsers.add_parser("sync", help="Run the sync process.")
    sync_parser.add_argument("--batch-size", type=int, default=100, help="Number of items to process in a single batch.")
    sync_parser.add_argument("--tables", type=str, help="Comma-separated list of table names to sync (e.g., 'products,users'). If not specified, all tables are synced.")

    status_parser = subparsers.add_parser("status", help="Display sync system status and statistics.")
    status_parser.add_argument("--tables", type=str, help="Comma-separated list of table names to check (e.g., 'products,users'). If not specified, all tables are shown.")

    args = parser.parse_args()
    config = load_config()
    
    # Filter tables if specified
    if hasattr(args, 'tables') and args.tables:
        requested_tables = [t.strip() for t in args.tables.split(',')]
        original_count = len(config['tables'])
        config['tables'] = [t for t in config['tables'] if t['name'] in requested_tables]
        
        if len(config['tables']) == 0:
            print(f"✗ Error: No matching tables found for: {', '.join(requested_tables)}")
            print(f"Available tables: {', '.join([t['name'] for t in load_config()['tables']])}")
            return
        
        filtered_names = [t['name'] for t in config['tables']]
        print(f"Filtering to {len(config['tables'])} of {original_count} tables: {', '.join(filtered_names)}\n")

    if args.command == "setup":
        setup(config, args.recreate, not args.backfill_queue)
    elif args.command == "sync":
        sync(config, args.batch_size)
    elif args.command == "status":
        from .sync import status
        status(config)
