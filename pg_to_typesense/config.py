import yaml
import importlib
import os
from dotenv import load_dotenv

def load_transformer(path):
    """Dynamically loads a transformer function from a string path."""
    if not path:
        return lambda doc: doc
    module_path, func_name = path.rsplit('.', 1)
    try:
        module = importlib.import_module(module_path)
        return getattr(module, func_name)
    except (ImportError, AttributeError) as e:
        raise Exception(f"Could not load transformer function at '{path}': {e}")

def load_config(path="config.yml"):
    """Loads and validates the configuration from a YAML file."""
    # Load environment variables from .env file
    load_dotenv()
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        raise Exception(f"Configuration file not found at: {path}")
    except yaml.YAMLError as e:
        raise Exception(f"Invalid YAML configuration: {e}")

    # Validate configuration structure
    if not isinstance(config, dict):
        raise Exception("Invalid configuration: root must be a dictionary.")
    
    config["postgresql"] = {
        "host": os.getenv("POSTGRES_HOST"),
        "port": int(os.getenv("POSTGRES_PORT", 5432)),
        "user": os.getenv("POSTGRES_USER"),
        "password": os.getenv("POSTGRES_PASSWORD"),
        "dbname": os.getenv("POSTGRES_DBNAME"),
    }
    
    config["typesense"] = {
        "api_key": os.getenv("TYPESENSE_API_KEY"),
        "host": os.getenv("TYPESENSE_HOST"),
        "port": int(os.getenv("TYPESENSE_PORT", 8108)),
        "protocol": os.getenv("TYPESENSE_PROTOCOL", "http"),
    }
    
    # Validate PostgreSQL configuration
    for key in ["host", "user", "password", "dbname"]:
        if config["postgresql"][key] is None:
            raise Exception(f"Missing environment variable 'POSTGRES_{key.upper()}'. Set it in your .env file.")
    
    # Validate Typesense configuration
    for key in ["api_key", "host"]:
        if config["typesense"][key] is None:
            raise Exception(f"Missing environment variable 'TYPESENSE_{key.upper()}'. Set it in your .env file.")
    
    # Validate tables configuration
    if not config["tables"] or not isinstance(config["tables"], list):
        raise Exception("No tables defined in the configuration or 'tables' is not a list.")

    for i, table in enumerate(config["tables"]):
        if not isinstance(table, dict):
            raise Exception(f"Table {i+1} must be a dictionary.")
        if "name" not in table or "collection" not in table or "schema" not in table:
            raise Exception(f"Table {i+1} must have 'name', 'collection', and 'schema' fields.")
        if not isinstance(table["schema"], list):
            raise Exception(f"Table {i+1} 'schema' must be a list.")
        
        # Validate reference_table if specified (for view support)
        if "reference_table" in table:
            if not isinstance(table["reference_table"], str) or not table["reference_table"]:
                raise Exception(f"Table {i+1} 'reference_table' must be a non-empty string.")
        
        # Build column mapping for aliasing
        # Maps Typesense field names to PostgreSQL column names
        column_mapping = {}
        reverse_mapping = {}  # Maps PostgreSQL names to Typesense names
        
        # Validate schema fields
        for j, field in enumerate(table["schema"]):
            if not isinstance(field, dict):
                raise Exception(f"Table {i+1}, schema field {j+1} must be a dictionary.")
            if "name" not in field or "type" not in field:
                raise Exception(f"Table {i+1}, schema field {j+1} must have 'name' and 'type'.")
            
            # Handle column aliasing
            # 'name' is the Typesense field name
            # 'source_column' (optional) is the PostgreSQL column name
            typesense_name = field['name']
            postgres_name = field.get('source_column', typesense_name)
            
            column_mapping[typesense_name] = postgres_name
            reverse_mapping[postgres_name] = typesense_name
            
            # Validate field type
            valid_types = [
                'string', 'int32', 'int64', 'float', 'bool', 
                'geopoint', 'geopoint[]', 'string[]', 'int32[]', 
                'int64[]', 'float[]', 'bool[]', 'object', 'object[]', 
                'auto', 'string*',  # string* for auto-detection
                'date',  # date type (will be converted to int64 timestamp)
                'vector'  # PostgreSQL vector type (pgvector) - converts to float[]
            ]
            if field['type'] not in valid_types:
                raise Exception(
                    f"Table {i+1}, schema field {j+1} ('{field['name']}'): "
                    f"invalid type '{field['type']}'. Valid types: {', '.join(valid_types)}"
                )
            
            # Convert 'date' type to 'int64' for Typesense schema (actual conversion happens during sync)
            # Store original type for reference
            if field['type'] == 'date':
                field['source_type'] = 'date'  # Remember it was originally a date
                field['type'] = 'int64'  # Typesense will store as int64 timestamp
            
            # Convert 'vector' type to 'float[]' for Typesense schema
            if field['type'] == 'vector':
                field['source_type'] = 'vector'  # Remember it was originally a vector
                field['type'] = 'float[]'  # Typesense stores vectors as float[]
                
                # Validate num_dim is provided for vectors
                if 'num_dim' not in field:
                    raise Exception(
                        f"Table {i+1}, schema field {j+1} ('{field['name']}'): "
                        f"'num_dim' is required for vector fields"
                    )
            
            # Set default values for optional field properties
            if 'optional' not in field:
                # ID field should not be optional by default
                field['optional'] = False if field['name'] == 'id' else True
            
            if 'facet' not in field:
                field['facet'] = False
            
            if 'index' not in field:
                # Objects and some arrays don't index by default
                field['index'] = field['type'] not in ['object', 'object[]']
            
            if 'sort' not in field:
                field['sort'] = False
            
            # Validate boolean properties
            for bool_prop in ['optional', 'facet', 'index', 'sort', 'infix', 'stem', 'store']:
                if bool_prop in field and not isinstance(field[bool_prop], bool):
                    raise Exception(
                        f"Table {i+1}, schema field {j+1} ('{field['name']}'): "
                        f"'{bool_prop}' must be a boolean (true/false)"
                    )
            
            # Validate locale if present
            if 'locale' in field and not isinstance(field['locale'], str):
                raise Exception(
                    f"Table {i+1}, schema field {j+1} ('{field['name']}'): "
                    f"'locale' must be a string"
                )
            
            # Validate num_dim for embedding fields
            if 'num_dim' in field and not isinstance(field['num_dim'], int):
                raise Exception(
                    f"Table {i+1}, schema field {j+1} ('{field['name']}'): "
                    f"'num_dim' must be an integer"
                )
            
            # Validate embed configuration
            if 'embed' in field:
                if not isinstance(field['embed'], dict):
                    raise Exception(
                        f"Table {i+1}, schema field {j+1} ('{field['name']}'): "
                        f"'embed' must be a dictionary"
                    )
                if 'from' not in field['embed']:
                    raise Exception(
                        f"Table {i+1}, schema field {j+1} ('{field['name']}'): "
                        f"'embed.from' is required for embedding fields"
                    )
        
        # Store column mappings in table config
        table['column_mapping'] = column_mapping  # Typesense -> PostgreSQL
        table['reverse_column_mapping'] = reverse_mapping  # PostgreSQL -> Typesense
        
        # Load transformer function
        table['transformer'] = load_transformer(table.get('transformer'))

    return config
