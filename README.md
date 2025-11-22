# PostgreSQL to Typesense Sync

[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![PostgreSQL](https://img.shields.io/badge/postgresql-12+-336791.svg)](https://www.postgresql.org/)
[![Typesense](https://img.shields.io/badge/typesense-0.24+-red.svg)](https://typesense.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> **Real-time, production-ready synchronization tool that keeps your Typesense search collections in perfect sync with PostgreSQL databases.**

A robust Python-based sync engine that uses PostgreSQL triggers and a queue-based architecture to automatically propagate database changes (INSERT, UPDATE, DELETE) to Typesense search indexes. No polling, no delays—just instant, reliable search index updates.

## ✨ Key Features

- **🔄 Real-Time Change Detection** - PostgreSQL triggers capture every data change automatically
- **⚡ Queue-Based Architecture** - Reliable, transactional sync with automatic deduplication
- **🎯 Type Intelligence** - Automatic conversion for dates, vectors (pgvector), arrays, and complex types
- **🔧 Advanced Schema Control** - Full control over Typesense field properties (faceting, sorting, stemming, etc.)
- **🔀 Data Transformation** - Custom Python transformers to reshape data before indexing
- **📊 View Support** - Sync from PostgreSQL views using reference table triggers
- **🧮 Vector Search Ready** - Native pgvector to Typesense vector field conversion
- **🎛️ Column Aliasing** - Map PostgreSQL columns to clean Typesense field names
- **📈 Production-Ready** - Comprehensive error handling, status monitoring, and batch processing

---

## 📋 Table of Contents

- [Installation](#-installation)
- [Quick Start](#-quick-start)
- [Configuration](#-configuration)
  - [Database Connection](#database-connection)
  - [Typesense Connection](#typesense-connection)
  - [Table Configuration](#table-configuration)
  - [Schema Fields](#schema-fields)
- [CLI Commands](#-cli-commands)
  - [Setup](#setup-command)
  - [Sync](#sync-command)
  - [Status](#status-command)
- [Advanced Features](#-advanced-features)
  - [Custom Transformers](#custom-transformers)
  - [Column Aliasing](#column-aliasing)
  - [View Support](#view-support)
  - [Vector Search Integration](#vector-search-integration)
  - [Automatic Date Conversion](#automatic-date-conversion)
- [Architecture](#-architecture)
- [Deployment](#-deployment)
- [Additional Documentation](#-additional-documentation)
- [Contributing](#-contributing)
- [License](#-license)

---

## 🚀 Installation

### Prerequisites

- Python 3.8 or higher
- PostgreSQL 12 or higher
- Typesense 0.24 or higher
- (Optional) pgvector extension for vector search support

### Install Dependencies

```bash
# Clone the repository
git clone https://github.com/youssefEdrees/postgres-typesense-sync.git
cd postgres-typesense-sync

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install required packages
pip install -r requirements.txt
```

### Dependencies

- `typesense` - Typesense Python client
- `psycopg[binary]` - PostgreSQL adapter (psycopg3)
- `pyyaml` - YAML configuration parsing
- `tqdm` - Progress bars for batch operations
- `pgvector` - PostgreSQL vector extension support
- `python-dotenv` - Environment variable management

---

## 🎯 Quick Start

### 1. Configure Your Environment

**Create a `.env` file** with your connection credentials (copy from `.env.example`):

```bash
# .env file
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your-password
POSTGRES_DBNAME=mydb

TYPESENSE_API_KEY=your-api-key
TYPESENSE_HOST=localhost
TYPESENSE_PORT=8108
TYPESENSE_PROTOCOL=http
```

**Create a `config.yml` file** (or copy from `config.example.yml`) with your table configurations:

```yaml
tables:
  - name: "products"
    collection: "products_v1"
    schema:
      - name: "id"
        type: "string"
        optional: false
      - name: "name"
        type: "string"
        index: true
        sort: true
      - name: "price"
        type: "float"
        sort: true
      - name: "created_at"
        type: "date"
        sort: true
```

**🔒 Security:** Ensure `.env` is in `.gitignore` and never commit credentials to version control.

### 2. Initialize Sync Infrastructure

```bash
# Set up database triggers and Typesense collections
python main.py setup --backfill-queue
```

This command:
- Creates the `typesense_sync_queue` table in PostgreSQL
- Installs triggers on configured tables to capture changes
- Creates Typesense collections with your schema
- Queues existing records for initial sync (with `--backfill-queue`)

### 3. Perform Initial Sync

```bash
# Sync all queued changes to Typesense
python main.py sync --batch-size 1000
```

### 4. Check Status

```bash
# View sync status and statistics
python main.py status
```

---

## ⚙️ Configuration

Configuration is split between two files:
- **`.env`** - Database and Typesense connection settings (required)
- **`config.yml`** - Table and schema configurations

### Database Connection (`.env`)

All connection settings are configured via environment variables in your `.env` file:

```bash
# PostgreSQL Connection
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your-password
POSTGRES_DBNAME=mydb
```

### Typesense Connection (`.env`)

```bash
# Typesense Connection
TYPESENSE_API_KEY=your-api-key
TYPESENSE_HOST=localhost
TYPESENSE_PORT=8108
TYPESENSE_PROTOCOL=http  # or https
```

### Table Configuration (`config.yml`)

Table and schema configurations are defined in `config.yml`:

```yaml
tables:
  - name: "products"                    # PostgreSQL table/view name
    collection: "products_v1"           # Typesense collection name
    
    # Optional: Custom transformer function
    transformer: "transformers.transform_product"
    
    # Optional: For views, specify the underlying reference table
    reference_table: "base_products"
    
    # Optional: Typesense collection settings
    default_sorting_field: "created_at"
    token_separators: ["-", "_"]
    symbols_to_index: ["@", "#"]
    
    schema:
      # Field definitions (see next section)
```

### Schema Fields

Each field in your schema supports the following properties:

```yaml
schema:
  - name: "id"                          # Field name in Typesense
    source_column: "product_id"         # Optional: PostgreSQL column name (if different)
    type: "string"                      # Field type (see types below)
    optional: false                     # Required field (default: false)
    
  - name: "title"
    type: "string"
    index: true                         # Enable full-text search (default: true)
    sort: true                          # Enable sorting (default: false)
    facet: false                        # Enable faceting/filtering (default: false)
    infix: false                        # Enable substring search (default: false)
    stem: true                          # Enable word stemming (default: false)
    locale: "en"                        # Language for stemming (default: "")
    store: true                         # Store value (default: true)
    
  - name: "tags"
    type: "string[]"                    # Array type
    facet: true
    
  - name: "created_at"
    type: "date"                        # Auto-converts to Unix timestamp
    sort: true
    
  - name: "embedding"
    source_type: "vector"               # PostgreSQL type hint
    type: "float[]"                     # Typesense type
    num_dim: 384                        # Required for vector fields
    
  - name: "metadata"
    type: "object"                      # JSON object
    optional: true
```

#### Supported Types

**Scalar Types:**
- `string` - Text fields
- `int32` - 32-bit integers
- `int64` - 64-bit integers
- `float` - Floating-point numbers
- `bool` - Boolean values

**Array Types:**
- `string[]`, `int32[]`, `int64[]`, `float[]`, `bool[]`

**Special Types:**
- `date` - Automatically converts datetime to Unix timestamp (int64)
- `geopoint` - Geographic coordinates `[lat, lng]`
- `geopoint[]` - Array of geopoints
- `object` - JSON objects
- `object[]` - Array of JSON objects
- `float[]` with `num_dim` - Vector embeddings for semantic search

**💡 Pro Tip:** Use `type: "date"` instead of manually converting dates to timestamps. The sync engine handles this automatically!

---

## 🖥️ CLI Commands

### Setup Command

Initializes sync infrastructure and Typesense collections.

```bash
python main.py setup [OPTIONS]
```

**Options:**
- `--recreate` - Drop and recreate Typesense collections (⚠️ deletes all data)
- `--backfill-queue` - Queue all existing records for sync
- `--tables TABLE1,TABLE2` - Only setup specific tables

**Examples:**

```bash
# Basic setup (no backfill)
python main.py setup

# Setup with collection recreation
python main.py setup --recreate

# Setup with immediate backfill
python main.py setup --backfill-queue

# Setup specific tables only
python main.py setup --tables products,users
```

**What it does:**
1. Validates source tables/views exist in PostgreSQL
2. Creates `typesense_sync_queue` table (if not exists)
3. Creates trigger functions in PostgreSQL
4. Installs triggers on configured tables
5. Creates Typesense collections with configured schemas
6. Optionally queues existing records for initial sync

---

### Sync Command

Processes queued changes and syncs to Typesense.

```bash
python main.py sync [OPTIONS]
```

**Options:**
- `--batch-size SIZE` - Number of records per batch (default: 100)
- `--tables TABLE1,TABLE2` - Only sync specific tables

**Examples:**

```bash
# Sync all tables (default batch size: 100)
python main.py sync

# Custom batch size for large datasets
python main.py sync --batch-size 500

# Sync specific tables only
python main.py sync --tables products

# High-throughput sync
python main.py sync --batch-size 1000
```

**What it does:**
1. Fetches queued jobs from `typesense_sync_queue` in batches
2. Deduplicates operations per record (latest wins)
3. Fetches current data from PostgreSQL
4. Applies custom transformers (if configured)
5. Applies column aliasing
6. Converts types automatically (dates → timestamps, vectors → float arrays)
7. Upserts/deletes documents in Typesense
8. Removes processed jobs from queue
9. Commits transaction on success, rolls back on errors

**Deduplication Logic:**

If multiple operations exist for the same record in a batch:
- **Latest operation wins** (by queue ID)
- **DELETE > UPDATE > INSERT** priority
- Ensures data consistency and reduces unnecessary operations

---

### Status Command

Displays system health and synchronization statistics.

```bash
python main.py status [OPTIONS]
```

**Options:**
- `--tables TABLE1,TABLE2` - Only show status for specific tables

**Examples:**

```bash
# Check all tables
python main.py status

# Check specific tables
python main.py status --tables products
```

**Output includes:**
- Database connection status
- Typesense connection status
- Queue table existence and pending job counts
- Breakdown by table and operation type (INSERT/UPDATE/DELETE)
- Source table record counts in PostgreSQL
- Trigger installation status
- Typesense collection existence and document counts

**Example Output:**

```
Database Status: Connected ✓
Typesense Status: Connected ✓

Queue Status:
  Total pending jobs: 1,234
  
  By table:
    products: 856 jobs (INSERT: 800, UPDATE: 50, DELETE: 6)
    users: 378 jobs (INSERT: 300, UPDATE: 75, DELETE: 3)

Source Tables:
  products: 10,542 records | Trigger: ✓ | Collection: ✓ (10,500 docs)
  users: 5,231 records | Trigger: ✓ | Collection: ✓ (5,200 docs)
```

---

## 🔥 Advanced Features

### Custom Transformers

Transform documents before indexing with Python functions. Useful for:
- Computed fields
- Data enrichment
- Field renaming/restructuring
- Default values
- Complex business logic

**1. Create a transformer function:**

```python
# transformers.py (or any Python module)

def transform_product(doc):
    """Transform product document before indexing."""
    
    # Add computed fields
    doc['full_name'] = f"{doc.get('brand', '')} {doc.get('name', '')}".strip()
    
    # Normalize data
    if doc.get('price'):
        doc['price'] = round(float(doc['price']), 2)
    
    # Add defaults
    if 'status' not in doc:
        doc['status'] = 'active'
    
    # Remove internal fields
    doc.pop('internal_notes', None)
    
    return doc


def transform_user(doc):
    """Transform user document."""
    
    # Combine name fields
    first = doc.get('first_name', '')
    last = doc.get('last_name', '')
    doc['display_name'] = f"{first} {last}".strip() or 'Anonymous'
    
    # Hash sensitive data
    if 'email' in doc:
        doc['email_domain'] = doc['email'].split('@')[-1]
    
    # Convert timestamps
    doc['last_seen_friendly'] = (
        'recently' if doc.get('last_login_timestamp', 0) > time.time() - 86400
        else 'inactive'
    )
    
    return doc
```

**2. Reference in configuration:**

```yaml
tables:
  - name: "products"
    collection: "products_v1"
    transformer: "transformers.transform_product"  # module.function
    schema:
      # ... your schema
```

**📝 Note:** 
- Transformers run **after** fetching from PostgreSQL but **before** type conversion
- Date fields configured as `type: "date"` are automatically converted—no manual conversion needed
- Return the modified `doc` dictionary
- Exceptions in transformers are logged; the record is skipped

---

### Column Aliasing

Map PostgreSQL column names to different Typesense field names for cleaner search APIs.

```yaml
tables:
  - name: "products"
    collection: "products_v1"
    schema:
      - name: "product_name"           # Clean Typesense field name
        source_column: "name"           # PostgreSQL column name
        type: "string"
        
      - name: "product_id"
        source_column: "id"
        type: "string"
        
      - name: "category"               # If no source_column, uses same name
        type: "string"
```

**PostgreSQL query:**
```sql
SELECT id, name, category FROM products WHERE id = 123;
-- Returns: {'id': 123, 'name': 'Widget', 'category': 'Tools'}
```

**Typesense document:**
```json
{
  "product_id": "123",
  "product_name": "Widget",
  "category": "Tools"
}
```

---

### View Support

Sync from PostgreSQL views using reference table triggers.

**Use cases:**
- Pre-joined data for search
- Filtered/transformed datasets
- Materialized views with complex logic
- Denormalized search structures

**Configuration:**

```yaml
tables:
  - name: "product_search_view"         # Your view name
    reference_table: "products"         # Underlying table for triggers
    collection: "products_search_v1"
    schema:
      # Define schema based on view columns
```

**How it works:**
1. Triggers are installed on the `reference_table` (e.g., `products`)
2. When the reference table changes, the view name is passed to the queue
3. Sync engine fetches data from the view, not the reference table
4. This allows complex JOINs and transformations at the database level

**Example view:**

```sql
CREATE VIEW product_search_view AS
SELECT 
  p.id,
  p.name,
  p.price,
  c.name as category_name,
  b.name as brand_name,
  array_agg(t.name) as tags
FROM products p
LEFT JOIN categories c ON p.category_id = c.id
LEFT JOIN brands b ON p.brand_id = b.id
LEFT JOIN product_tags pt ON p.id = pt.product_id
LEFT JOIN tags t ON pt.tag_id = t.id
GROUP BY p.id, p.name, p.price, c.name, b.name;
```

**⚠️ Important:** Views must include the primary key from the reference table for proper sync tracking.

---

### Vector Search Integration

Native support for pgvector embeddings with automatic conversion to Typesense vector fields.

**1. Install pgvector in PostgreSQL:**

```sql
CREATE EXTENSION vector;

CREATE TABLE products (
  id SERIAL PRIMARY KEY,
  name TEXT,
  embedding vector(384)  -- 384-dimensional embeddings
);
```

**2. Configure schema:**

```yaml
tables:
  - name: "products"
    collection: "products_v1"
    schema:
      - name: "id"
        type: "string"
        
      - name: "name"
        type: "string"
        index: true
        
      - name: "embedding"
        source_type: "vector"           # Hint for pgvector type
        type: "float[]"                 # Typesense type
        num_dim: 384                    # Required: embedding dimensions
```

**3. Automatic conversion:**

The sync engine automatically converts pgvector data:

```python
# PostgreSQL: vector column
"[0.123, -0.456, 0.789, ...]"  # String representation

# Typesense: float[] field
[0.123, -0.456, 0.789, ...]    # Array of floats
```

**4. Query with vector search:**

```python
# Typesense vector search query
client.collections['products_v1'].documents.search({
  'q': '*',
  'vector_query': 'embedding:([0.96826, 0.94, ...], k:100)'
})
```

**Supported input formats:**
- pgvector string: `"[1.0, 2.0, 3.0]"`
- Python list: `[1.0, 2.0, 3.0]`
- Vector object: `Vector([1.0, 2.0, 3.0])`

---

### Automatic Date Conversion

No more manual timestamp conversion! Just configure fields as `type: "date"` and the sync engine handles everything.

**Configuration:**

```yaml
schema:
  - name: "created_at"
    type: "date"          # Automatically converts to Unix timestamp
    sort: true
    
  - name: "updated_at"
    type: "date"
    sort: true
```

**Supported input formats:**
- ISO 8601 strings: `"2025-11-22T10:30:00Z"`
- Python datetime objects
- Unix timestamps (passed through)

**Before (manual conversion):**

```python
def transform_product(doc):
    # Manual conversion required
    if 'created_at' in doc and isinstance(doc['created_at'], datetime):
        doc['created_at'] = int(doc['created_at'].timestamp())
    return doc
```

**After (automatic):**

```python
def transform_product(doc):
    # No date conversion needed!
    # Just focus on your business logic
    doc['display_name'] = doc['name'].upper()
    return doc
```

**💡 Benefit:** Cleaner transformers, less boilerplate, no errors from incorrect conversion.

See [DATE_TYPE_GUIDE.md](DATE_TYPE_GUIDE.md) for comprehensive examples.

---

## 🏗️ Architecture

### Queue-Based Sync Architecture

```
┌─────────────────┐
│   PostgreSQL    │
│                 │
│  ┌───────────┐  │       ┌──────────────────┐
│  │  Tables   │  │       │  Sync Engine     │
│  │           │──┼──────▶│  (main.py)       │
│  │ Triggers  │  │       │                  │
│  └─────┬─────┘  │       │  1. Fetch queue  │
│        │        │       │  2. Deduplicate  │
│        ▼        │       │  3. Transform    │
│  ┌───────────┐  │       │  4. Type convert │
│  │   Queue   │  │       │  5. Upsert/Del   │
│  │   Table   │◀─┼───────│  6. Commit       │
│  └───────────┘  │       └────────┬─────────┘
│                 │                │
└─────────────────┘                │
                                   ▼
                          ┌─────────────────┐
                          │   Typesense     │
                          │   Collections   │
                          └─────────────────┘
```

### Key Components

#### 1. **PostgreSQL Triggers**
- **Standard Trigger:** `log_changes_for_typesense()` - Uses table name from trigger context
- **View-Aware Trigger:** `log_changes_for_typesense_with_name()` - Custom table name via arguments

**Installed on:** INSERT, UPDATE, DELETE operations

**Trigger behavior:**
```sql
-- Example: INSERT/UPDATE trigger
INSERT INTO typesense_sync_queue (record_id, table_name, operation_type)
VALUES (NEW.id, 'products', 'INSERT')
ON CONFLICT (record_id, table_name) 
DO UPDATE SET operation_type = EXCLUDED.operation_type;

-- Example: DELETE trigger
INSERT INTO typesense_sync_queue (record_id, table_name, operation_type)
VALUES (OLD.id, 'products', 'DELETE');
```

#### 2. **Sync Queue Table**

```sql
CREATE TABLE typesense_sync_queue (
  id SERIAL PRIMARY KEY,
  record_id TEXT NOT NULL,
  table_name TEXT NOT NULL,
  operation_type TEXT NOT NULL,  -- 'INSERT', 'UPDATE', or 'DELETE'
  created_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(record_id, table_name)  -- Ensures one entry per record
);
```

#### 3. **Sync Engine Workflow**

```python
# Simplified sync flow
while True:
    # 1. Fetch batch from queue
    jobs = fetch_jobs(batch_size=100)
    
    # 2. Deduplicate (latest operation wins)
    jobs = deduplicate_by_record_id(jobs)
    
    # 3. Fetch current data from PostgreSQL
    records = fetch_records_by_ids(jobs)
    
    # 4. Apply transformers
    for record in records:
        if transformer:
            record = transformer(record)
    
    # 5. Apply column aliasing
    records = apply_column_mapping(records)
    
    # 6. Convert types (dates → timestamps, vectors → arrays)
    records = normalize_types(records)
    
    # 7. Sync to Typesense
    for job in jobs:
        if job.operation == 'DELETE':
            typesense.delete(job.record_id)
        else:
            typesense.upsert(records[job.record_id])
    
    # 8. Remove processed jobs from queue
    delete_jobs(jobs)
    
    # 9. Commit transaction
    commit()
```

#### 4. **Type Conversion Pipeline**

```python
# Date conversion
def convert_date_fields(doc, schema):
    for field in schema:
        if field['type'] == 'date' and field['name'] in doc:
            value = doc[field['name']]
            if isinstance(value, datetime):
                doc[field['name']] = int(value.timestamp())
            elif isinstance(value, str):
                doc[field['name']] = int(datetime.fromisoformat(value).timestamp())
    return doc

# Vector conversion
def convert_vector_fields(doc, schema):
    for field in schema:
        if field.get('source_type') == 'vector' and field['name'] in doc:
            value = doc[field['name']]
            if isinstance(value, str):
                # "[1.0, 2.0, 3.0]" → [1.0, 2.0, 3.0]
                doc[field['name']] = json.loads(value)
    return doc
```

### Transaction Safety

- **Atomic operations:** All changes in a batch are committed together
- **Rollback on error:** If Typesense sync fails, queue jobs are NOT removed
- **Retry-friendly:** Failed jobs remain in queue for next sync run
- **Idempotent:** Reprocessing same job produces same result

### Performance Characteristics

- **Batch processing:** Configurable batch size (default: 100)
- **Deduplication:** Reduces unnecessary operations
- **Single transaction:** Minimizes database overhead
- **Progress bars:** Visual feedback with tqdm
- **Parallel potential:** Multiple sync processes can run (queue-based)

---

## 🚀 Deployment

### Production Setup

#### 1. **Environment Configuration**

Create a `.env` file for credentials:

```bash
# .env
POSTGRES_HOST=your-db-host.com
POSTGRES_PORT=5432
POSTGRES_USER=sync_user
POSTGRES_PASSWORD=secure-password
POSTGRES_DBNAME=production_db

TYPESENSE_API_KEY=your-api-key
TYPESENSE_HOST=typesense.yourdomain.com
TYPESENSE_PORT=443
TYPESENSE_PROTOCOL=https
```

**Security:** Ensure `.env` is in `.gitignore` and not committed to version control.

#### 2. **Monitoring**

**Log rotation:**

```bash
# /etc/logrotate.d/typesense-sync
/var/log/typesense-sync.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
}
```

**Status monitoring script:**

```bash
#!/bin/bash
# check_sync_status.sh

output=$(cd /path/to/postgres-typesense-sync && /path/to/venv/bin/python main.py status)

# Check for pending jobs
pending=$(echo "$output" | grep "Total pending jobs" | awk '{print $4}')

if [ "$pending" -gt 1000 ]; then
    echo "WARNING: $pending jobs pending in sync queue"
    # Send alert (email, Slack, etc.)
fi
```

**Prometheus metrics (optional):**

Create a metrics endpoint to expose sync statistics:
- Queue depth
- Sync latency
- Success/failure rates
- Records processed per minute

---

## 📚 Additional Documentation

This project includes comprehensive guides for specific features:

- **[DATE_TYPE_GUIDE.md](DATE_TYPE_GUIDE.md)** - Complete guide to automatic date/timestamp conversion
- **[SCHEMA_QUICK_REFERENCE.md](SCHEMA_QUICK_REFERENCE.md)** - Quick reference for all field configuration options
- **[TYPESENSE_SCHEMA_GUIDE.md](TYPESENSE_SCHEMA_GUIDE.md)** - Detailed documentation of Typesense schema capabilities with examples

### Example Files

- **`config.example.yml`** - Example configuration with all available options
- **`transformers.py`** - Sample transformer functions for different use cases
- **`create_test_tables.py`** - Script to create test tables for development
- **`check_tables.py`** - Utility to validate table configurations

---

## 🤝 Contributing

Contributions are welcome! Here's how you can help:

### Reporting Issues

- Check existing issues first
- Provide detailed reproduction steps
- Include configuration (sanitized)
- Share error messages and logs

### Pull Requests

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Test thoroughly
5. Commit with clear messages (`git commit -m 'Add amazing feature'`)
6. Push to your fork (`git push origin feature/amazing-feature`)
7. Open a Pull Request

### Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/postgres-typesense-sync.git
cd postgres-typesense-sync

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set up test database
python create_test_tables.py

# Run tests
python check_tables.py
```

### Code Style

- Follow PEP 8 guidelines
- Use type hints where appropriate
- Add docstrings to functions
- Keep functions focused and testable

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **Typesense** - Lightning-fast, typo-tolerant search engine
- **PostgreSQL** - World's most advanced open source database
- **pgvector** - PostgreSQL extension for vector similarity search
- **psycopg3** - Modern PostgreSQL adapter for Python

---

## 📞 Support

- **Issues:** [GitHub Issues](https://github.com/youssefEdrees/postgres-typesense-sync/issues)
- **Discussions:** [GitHub Discussions](https://github.com/youssefEdrees/postgres-typesense-sync/discussions)
- **Email:** youssef.edrees@example.com (update with actual contact)

---

## 🗺️ Roadmap

Future enhancements under consideration:

- [ ] Multi-collection sync (one table → multiple collections)
- [ ] Conditional sync (filter records by criteria)
- [ ] Incremental field updates (partial document updates)
- [ ] Sync metrics dashboard
- [ ] Webhook notifications for sync events
- [ ] Cloud deployment templates (AWS, GCP, Azure)
- [ ] GraphQL API for configuration
- [ ] GUI for configuration management
- [ ] Support for additional databases (MySQL, MongoDB)

---

**Made with ❤️ for developers who need instant, reliable search**

If this project helps you, consider giving it a ⭐ on GitHub!
