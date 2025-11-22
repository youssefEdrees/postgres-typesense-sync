# transformers.py
import time
from datetime import datetime


def transform_tender(doc):
    return doc


def transform_product(doc):
    """
    Enhanced transformer function for the 'products' table.
    - Renames 'name' to 'product_name'
    - Adds 'is_on_sale' based on price
    - Adds default values for optional fields
    - Converts timestamps to int64
    """
    # Rename name field
    if 'name' in doc:
        doc['product_name'] = doc.pop('name')
    
    # Ensure price exists
    doc['is_on_sale'] = doc.get('price', 0) < 10.0
    
    # Set default values for optional fields
    if 'category' not in doc:
        doc['category'] = 'Uncategorized'
    
    if 'brand' not in doc:
        doc['brand'] = 'Generic'
    
    if 'stock_quantity' not in doc:
        doc['stock_quantity'] = 0
    
    if 'tags' not in doc:
        doc['tags'] = []
    elif isinstance(doc['tags'], str):
        # Convert comma-separated string to array
        doc['tags'] = [tag.strip() for tag in doc['tags'].split(',') if tag.strip()]
    
    # Convert datetime to Unix timestamp (int64)
    if 'created_at' in doc:
        if isinstance(doc['created_at'], datetime):
            doc['created_at'] = int(doc['created_at'].timestamp())
        elif isinstance(doc['created_at'], str):
            try:
                dt = datetime.fromisoformat(doc['created_at'].replace('Z', '+00:00'))
                doc['created_at'] = int(dt.timestamp())
            except:
                doc['created_at'] = int(time.time())
    else:
        doc['created_at'] = int(time.time())
    
    return doc

def transform_user(doc):
    """
    Enhanced transformer for the 'users' table.
    - Creates a 'full_name' field from 'username' or 'first_name'/'last_name'
    - Sets default values for optional fields
    - Converts timestamps
    - Handles roles array
    """
    # Create full_name
    if 'full_name' not in doc:
        if 'first_name' in doc and 'last_name' in doc:
            doc['full_name'] = f"{doc['first_name']} {doc['last_name']}"
        elif 'username' in doc:
            doc['full_name'] = doc['username'].upper()
        else:
            doc['full_name'] = 'Unknown User'
    
    # Set default account type
    if 'account_type' not in doc:
        doc['account_type'] = 'free'
    
    # Set default status
    if 'status' not in doc:
        doc['status'] = 'active'
    
    # Handle roles - ensure it's an array
    if 'roles' not in doc:
        doc['roles'] = ['user']
    elif isinstance(doc['roles'], str):
        # Convert comma-separated string to array
        doc['roles'] = [role.strip() for role in doc['roles'].split(',') if role.strip()]
    
    # Convert registration timestamp
    if 'registered_at' in doc:
        if isinstance(doc['registered_at'], datetime):
            doc['registered_at'] = int(doc['registered_at'].timestamp())
        elif isinstance(doc['registered_at'], str):
            try:
                dt = datetime.fromisoformat(doc['registered_at'].replace('Z', '+00:00'))
                doc['registered_at'] = int(dt.timestamp())
            except:
                doc['registered_at'] = int(time.time())
    else:
        doc['registered_at'] = int(time.time())
    
    # Set default is_verified
    if 'is_verified' not in doc:
        doc['is_verified'] = False
    
    return doc
