"""
Utility functions for data transformation and type conversion
"""
import time
from datetime import datetime, date
from typing import Any, Optional, List, Union


def convert_date_to_timestamp(value: Any) -> Optional[int]:
    """
    Convert various date/datetime formats to Unix timestamp (int64).
    
    Supports:
    - datetime.datetime objects
    - datetime.date objects
    - ISO format strings (YYYY-MM-DD, YYYY-MM-DDTHH:MM:SS, etc.)
    - Unix timestamps (int/float) - passed through
    - None - returns None
    
    Args:
        value: The value to convert
    
    Returns:
        Unix timestamp as integer, or None if value is None
    
    Raises:
        ValueError: If the value cannot be converted to a timestamp
    """
    if value is None:
        return None
    
    # Already a timestamp (int or float)
    if isinstance(value, (int, float)):
        return int(value)
    
    # datetime.datetime object
    if isinstance(value, datetime):
        return int(value.timestamp())
    
    # datetime.date object (without time)
    if isinstance(value, date):
        # Convert to datetime at midnight UTC
        dt = datetime.combine(value, datetime.min.time())
        return int(dt.timestamp())
    
    # String - try to parse as ISO format
    if isinstance(value, str):
        # Remove timezone indicator 'Z' and replace with '+00:00' for parsing
        value_normalized = value.replace('Z', '+00:00')
        
        # Try various datetime formats
        formats = [
            '%Y-%m-%d %H:%M:%S',           # 2024-01-15 14:30:00
            '%Y-%m-%d %H:%M:%S.%f',        # 2024-01-15 14:30:00.123456
            '%Y-%m-%dT%H:%M:%S',           # 2024-01-15T14:30:00
            '%Y-%m-%dT%H:%M:%S.%f',        # 2024-01-15T14:30:00.123456
            '%Y-%m-%d',                     # 2024-01-15
        ]
        
        # First, try ISO format with fromisoformat (handles timezones)
        try:
            dt = datetime.fromisoformat(value_normalized)
            return int(dt.timestamp())
        except (ValueError, AttributeError):
            pass
        
        # Try each format
        for fmt in formats:
            try:
                dt = datetime.strptime(value, fmt)
                return int(dt.timestamp())
            except ValueError:
                continue
        
        # If all formats fail, raise error
        raise ValueError(
            f"Unable to parse date string: {value}. "
            f"Expected formats: ISO 8601 or standard date/datetime formats"
        )
    
    raise ValueError(f"Unsupported date type: {type(value).__name__}. Value: {value}")


def normalize_document_for_typesense(doc: dict, schema: list) -> dict:
    """
    Normalize a document according to the schema, converting types as needed.
    
    Args:
        doc: The document to normalize
        schema: The schema definition with field types and properties
    
    Returns:
        Normalized document with converted values
    """
    normalized = doc.copy()
    
    # Create a lookup of field types
    field_types = {field['name']: field for field in schema}
    
    for field_name, field_config in field_types.items():
        if field_name not in normalized:
            continue
        
        value = normalized[field_name]
        
        # Handle date type conversion
        if field_config.get('source_type') == 'date':
            try:
                normalized[field_name] = convert_date_to_timestamp(value)
            except ValueError as e:
                print(f"⚠ Warning: Failed to convert date field '{field_name}': {e}")
                # Set to None if conversion fails
                normalized[field_name] = None
        
        # Handle vector type conversion
        elif field_config.get('source_type') == 'vector':
            try:
                normalized[field_name] = convert_vector_to_float_array(value)
            except ValueError as e:
                print(f"⚠ Warning: Failed to convert vector field '{field_name}': {e}")
                # Set to None if conversion fails
                normalized[field_name] = None
        
        # Ensure non-string, non-numeric, non-bool, non-list values are converted to strings
        elif not isinstance(value, (str, int, float, bool, list, type(None))):
            # Handle special types
            if isinstance(value, (datetime, date)):
                # Convert to timestamp if not already marked as date type
                normalized[field_name] = convert_date_to_timestamp(value)
            else:
                normalized[field_name] = str(value)
    
    return normalized


def get_current_timestamp() -> int:
    """Get current Unix timestamp as int64"""
    return int(time.time())


def convert_vector_to_float_array(value: Any) -> Optional[List[float]]:
    """
    Convert PostgreSQL vector (pgvector) to float array for Typesense.
    
    Supports:
    - pgvector.Vector objects
    - String representations: "[1.0, 2.0, 3.0]"
    - Lists/tuples of numbers
    - None values
    
    Args:
        value: The vector value to convert
    
    Returns:
        List of floats, or None if value is None
    
    Raises:
        ValueError: If the value cannot be converted to a float array
    """
    if value is None:
        return None
    
    # Already a list
    if isinstance(value, list):
        try:
            return [float(x) for x in value]
        except (TypeError, ValueError) as e:
            raise ValueError(f"Invalid vector list: {value}. Error: {e}")
    
    # Tuple
    if isinstance(value, tuple):
        try:
            return [float(x) for x in value]
        except (TypeError, ValueError) as e:
            raise ValueError(f"Invalid vector tuple: {value}. Error: {e}")
    
    
    # pgvector Vector object
    if hasattr(value, 'tolist'):
        # pgvector.Vector has a tolist() method
        try:
            result = value.tolist()
            return [float(x) for x in result]
        except Exception as e:
            raise ValueError(f"Failed to convert pgvector.Vector: {e}")
    
    # String representation
    if isinstance(value, str):
        # Try parsing as string representation of list
        # pgvector returns strings like "[1.0, 2.0, 3.0]"
        value = value.strip()
        
        if value.startswith('[') and value.endswith(']'):
            try:
                # Remove brackets and split by comma
                inner = value[1:-1].strip()
                if not inner:
                    return []
                
                parts = inner.split(',')
                return [float(x.strip()) for x in parts]
            except (ValueError, AttributeError) as e:
                raise ValueError(f"Failed to parse vector string: {value}. Error: {e}")
        else:
            raise ValueError(f"Vector string must be in format '[x, y, z]': {value}")
    
    # Try converting directly if it has __iter__ (but not dict, set, etc.)
    if hasattr(value, '__iter__') and not isinstance(value, (str, bytes, dict, set)):
        try:
            return [float(x) for x in value]
        except (TypeError, ValueError) as e:
            raise ValueError(f"Failed to convert iterable to vector: {value}. Error: {e}")
    
    raise ValueError(f"Unsupported vector type: {type(value).__name__}. Value: {value}")


def apply_column_aliases(doc: dict, column_mapping: dict) -> dict:
    """
    Apply column aliasing to map PostgreSQL column names to Typesense field names.
    
    Args:
        doc: Document with PostgreSQL column names
        column_mapping: Dict mapping Typesense field names to PostgreSQL column names
    
    Returns:
        Document with Typesense field names
    """
    if not column_mapping:
        return doc
    
    aliased_doc = {}
    
    # Reverse the mapping: PostgreSQL -> Typesense
    reverse_mapping = {pg_name: ts_name for ts_name, pg_name in column_mapping.items()}
    
    for pg_col, value in doc.items():
        # Use the aliased name if it exists, otherwise keep original
        ts_col = reverse_mapping.get(pg_col, pg_col)
        aliased_doc[ts_col] = value
    
    return aliased_doc


def remove_unmapped_fields(doc: dict, schema: list) -> dict:
    """
    Remove fields from document that are not in the schema.
    
    Args:
        doc: Document to filter
        schema: Schema definition with field names
    
    Returns:
        Filtered document with only schema fields
    """
    schema_fields = {field['name'] for field in schema}
    return {k: v for k, v in doc.items() if k in schema_fields}


def is_view(conn, table_name: str) -> bool:
    """
    Check if a table name is actually a view.
    
    Args:
        conn: PostgreSQL database connection
        table_name: Name of the table/view to check
    
    Returns:
        True if the table is a view, False if it's a base table
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT table_type FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = %s
        """, (table_name,))
        result = cur.fetchone()
        if result:
            return result[0] == 'VIEW'
        return False
