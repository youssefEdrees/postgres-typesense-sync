import typesense

def get_typesense_client(ts_config):
    """Creates and validates a Typesense client connection."""
    try:
        config = {
            'nodes': [{'host': ts_config['host'], 'port': ts_config['port'], 'protocol': ts_config['protocol']}],
            'api_key': ts_config['api_key'],
            'connection_timeout_seconds': 10
        }
        print(f"Creating Typesense client with config: {ts_config['protocol']}://{ts_config['host']}:{ts_config['port']}")
        
        client = typesense.Client(config)
        
        # Test connection by attempting to retrieve collections
        try:
            collections_response = client.collections.retrieve()
            print(f"✓ Successfully connected to Typesense at {ts_config['protocol']}://{ts_config['host']}:{ts_config['port']}")
            print(f"  Server has {len(collections_response)} existing collections")
        except Exception as e:
            print(f"⚠ Warning: Typesense connection test failed: {e}")
            print(f"  Error type: {type(e).__name__}")
            print("  Client created but connection may be unstable")
            # Still return the client as it might work for other operations
        
        return client
        
    except Exception as e:
        print(f"✗ Failed to create Typesense client: {e}")
        print(f"  Error type: {type(e).__name__}")
        print(f"  Config attempted: {ts_config}")
        raise

def setup_typesense_collections(ts_client, tables, recreate=False):
    """Creates or recreates Typesense collections with enhanced error handling and validation."""
    try:
        # Get existing collections with error handling
        try:
            existing_collections_response = ts_client.collections.retrieve()
            existing_collections = {c['name'] for c in existing_collections_response}
            print(f"✓ Found {len(existing_collections)} existing collections: {list(existing_collections)}")
        except Exception as e:
            print(f"⚠ Warning: Could not retrieve existing collections: {e}")
            print(f"   This might indicate connection issues with Typesense")
            existing_collections = set()

        collections_created = 0
        collections_updated = 0
        collections_deleted = 0

        for table in tables:
            collection_name = table['collection']
            
            # Build schema with all supported field properties
            schema_fields = []
            for field in table['schema']:
                field_config = {
                    'name': field['name'],
                    'type': field['type']
                }
                
                # Add optional field properties
                if 'optional' in field:
                    field_config['optional'] = field['optional']
                
                if 'facet' in field:
                    field_config['facet'] = field['facet']
                
                if 'index' in field:
                    field_config['index'] = field['index']
                
                if 'sort' in field:
                    field_config['sort'] = field['sort']
                
                if 'infix' in field:
                    field_config['infix'] = field['infix']
                
                if 'locale' in field and field['locale']:
                    field_config['locale'] = field['locale']
                
                if 'stem' in field:
                    field_config['stem'] = field['stem']
                
                if 'store' in field:
                    field_config['store'] = field['store']
                
                # Handle embedding configuration
                if 'embed' in field:
                    field_config['embed'] = field['embed']
                
                if 'num_dim' in field:
                    field_config['num_dim'] = field['num_dim']
                
                schema_fields.append(field_config)
            
            schema = {
                'name': collection_name,
                'fields': schema_fields
            }
            
            # Add collection-level settings if specified
            if 'default_sorting_field' in table:
                schema['default_sorting_field'] = table['default_sorting_field']
            
            if 'token_separators' in table:
                schema['token_separators'] = table['token_separators']
            
            if 'symbols_to_index' in table:
                schema['symbols_to_index'] = table['symbols_to_index']
            
            print(f"\nProcessing collection: {collection_name}")
            print(f"Schema fields: {[f['name'] for f in schema_fields]}")
            
            # Display field configurations for verification
            for field in schema_fields:
                config_details = []
                if field.get('facet'):
                    config_details.append('facetable')
                if field.get('sort'):
                    config_details.append('sortable')
                if field.get('infix'):
                    config_details.append('infix')
                if field.get('stem'):
                    config_details.append('stem')
                if not field.get('index', True):
                    config_details.append('not-indexed')
                if field.get('optional', True):
                    config_details.append('optional')
                
                config_str = f" [{', '.join(config_details)}]" if config_details else ""
                print(f"  - {field['name']}: {field['type']}{config_str}")

            try:
                # Handle recreation if requested
                if recreate and collection_name in existing_collections:
                    print(f"Recreating collection: {collection_name}...")
                    try:
                        ts_client.collections[collection_name].delete()
                        existing_collections.remove(collection_name)
                        collections_deleted += 1
                        print(f"✓ Collection '{collection_name}' deleted for recreation")
                    except Exception as e:
                        print(f"⚠ Warning: Could not delete collection '{collection_name}': {e}")

                # Create collection if it doesn't exist
                if collection_name not in existing_collections:
                    print(f"Creating collection: {collection_name}...")
                    print(f"Using schema: {schema}")
                    try:
                        result = ts_client.collections.create(schema)
                        collections_created += 1
                        print(f"✓ Collection '{collection_name}' created successfully")
                        print(f"  Creation result: {result}")
                    except Exception as e:
                        print(f"✗ Failed to create collection '{collection_name}': {e}")
                        print(f"  Error type: {type(e).__name__}")
                        print(f"  Schema used: {schema}")
                        raise
                else:
                    # Validate existing collection schema
                    try:
                        existing_schema = ts_client.collections[collection_name].retrieve()
                        existing_fields = {f['name']: f for f in existing_schema.get('fields', [])}
                        new_fields = {f['name']: f for f in schema['fields']}
                        
                        # Check for schema differences
                        schema_differences = []
                        for field_name, field_config in new_fields.items():
                            if field_name not in existing_fields:
                                schema_differences.append(f"Missing field: {field_name}")
                            elif existing_fields[field_name] != field_config:
                                schema_differences.append(f"Field mismatch: {field_name}")
                        
                        if schema_differences:
                            print(f"⚠ Schema differences found for collection '{collection_name}':")
                            for diff in schema_differences:
                                print(f"  - {diff}")
                            print(f"  Consider using --recreate to update the schema")
                        else:
                            print(f"✓ Collection '{collection_name}' exists with correct schema")
                            collections_updated += 1
                            
                    except Exception as e:
                        print(f"⚠ Warning: Could not validate schema for collection '{collection_name}': {e}")
                        print(f"✓ Collection '{collection_name}' exists (schema validation skipped)")

            except Exception as e:
                print(f"✗ Error processing collection '{collection_name}': {e}")
                raise

        # Summary
        print(f"\n✓ Typesense collections setup summary:")
        print(f"  - Created: {collections_created}")
        print(f"  - Validated/Existing: {collections_updated}")
        if collections_deleted > 0:
            print(f"  - Deleted for recreation: {collections_deleted}")

    except Exception as e:
        print(f"✗ Failed to setup Typesense collections: {e}")
        raise
