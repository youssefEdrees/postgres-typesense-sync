# PostgreSQL to Typesense Sync

[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![PostgreSQL](https://img.shields.io/badge/postgresql-12+-336791.svg)](https://www.postgresql.org/)
[![Typesense](https://img.shields.io/badge/typesense-0.24+-red.svg)](https://typesense.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Synchronizes PostgreSQL databases to Typesense search indexes using triggers and a queue-based architecture.

## Features

- Change detection via PostgreSQL triggers
- Queue-based architecture with automatic deduplication
- Automatic type conversion (dates, vectors, arrays, complex types)
- Custom Python transformers for data processing
- PostgreSQL view support
- pgvector to Typesense vector field conversion
- Column aliasing
- Batch processing with configurable sizes

---

## Installation

### Prerequisites

- Python 3.8+
- PostgreSQL 12+
- Typesense 0.24+
- pgvector extension (optional, for vector search)

### Setup

```bash
git clone https://github.com/youssefEdrees/postgres-typesense-sync.git
cd postgres-typesense-sync

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

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

## Quick Start

### 1. Configure Environment

Create `.env` with database and Typesense credentials:

```bash
# .env
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

Create `config.yml` with table configurations:

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

### 2. Initialize

```bash
python main.py setup --backfill-queue
```

Creates database triggers, Typesense collections, and queues existing records.

### 3. Sync Data

```bash
python main.py sync --batch-size 1000
```

### 4. Check Status

```bash
python main.py status
```

---

## Configuration

### Table Configuration (`config.yml`)

```yaml
tables:
  - name: "products"                    # PostgreSQL table/view name
    collection: "products_v1"           # Typesense collection name
    
    transformer: "transformers.transform_product"  # Optional custom transformer
    reference_table: "base_products"    # Optional: for views
    
    # Optional collection settings
    default_sorting_field: "created_at"
    token_separators: ["-", "_"]
    symbols_to_index: ["@", "#"]
    
    schema:
      # Field definitions
```

### Schema Fields

Field configuration options:

```yaml
schema:
  - name: "id"
    source_column: "product_id"         # Optional: PostgreSQL column name
    type: "string"
    optional: false
    
  - name: "title"
    type: "string"
    index: true                         # Full-text search (default: true)
    sort: true                          # Enable sorting (default: false)
    facet: false                        # Enable faceting (default: false)
    infix: false                        # Substring search (default: false)
    stem: true                          # Word stemming (default: false)
    locale: "en"                        # Stemming language (default: "")
    store: true                         # Store value (default: true)
    
  - name: "tags"
    type: "string[]"
    facet: true
    
  - name: "created_at"
    type: "date"                        # Auto-converts to Unix timestamp
    sort: true
    
  - name: "embedding"
    source_type: "vector"               # PostgreSQL type hint
    type: "float[]"
    num_dim: 384                        # Required for vectors
    
  - name: "metadata"
    type: "object"
    optional: true
```

#### Supported Types

**Scalar Types:**
- `string`, `int32`, `int64`, `float`, `bool`

**Array Types:**
- `string[]`, `int32[]`, `int64[]`, `float[]`, `bool[]`

**Special Types:**
- `date` - Converts datetime to Unix timestamp
- `geopoint` - Geographic coordinates `[lat, lng]`
- `geopoint[]` - Array of geopoints
- `object` - JSON objects
- `object[]` - Array of JSON objects
- `float[]` with `num_dim` - Vector embeddings

---

## CLI Commands

### Setup

Initialize sync infrastructure and Typesense collections.

```bash
python main.py setup [OPTIONS]
```

**Options:**
- `--recreate` - Drop and recreate collections (deletes data)
- `--backfill-queue` - Queue existing records for sync
- `--tables TABLE1,TABLE2` - Setup specific tables only

**Examples:**

```bash
python main.py setup
python main.py setup --recreate
python main.py setup --backfill-queue
python main.py setup --tables products,users
```

---

### Sync

Process queued changes and sync to Typesense.

```bash
python main.py sync [OPTIONS]
```

**Options:**
- `--batch-size SIZE` - Records per batch (default: 100)
- `--tables TABLE1,TABLE2` - Sync specific tables only

**Examples:**

```bash
python main.py sync
python main.py sync --batch-size 500
python main.py sync --tables products
```

---

### Status

Display sync statistics and system health.

```bash
python main.py status [OPTIONS]
```

**Options:**
- `--tables TABLE1,TABLE2` - Show specific tables only

**Examples:**

```bash
python main.py status
python main.py status --tables products
```

---

## Advanced Features

### Custom Transformers

Transform documents before indexing using Python functions.

**1. Create transformer:**

```python
# transformers.py

def transform_product(doc):
    """Transform product document before indexing."""
    
    doc['full_name'] = f"{doc.get('brand', '')} {doc.get('name', '')}".strip()
    
    if doc.get('price'):
        doc['price'] = round(float(doc['price']), 2)
    
    if 'status' not in doc:
        doc['status'] = 'active'
    
    doc.pop('internal_notes', None)
    
    return doc
```

**2. Reference in config:**

```yaml
tables:
  - name: "products"
    collection: "products_v1"
    transformer: "transformers.transform_product"
    schema:
      # ...
```

---

### Column Aliasing

Map PostgreSQL column names to different Typesense field names.

```yaml
tables:
  - name: "products"
    collection: "products_v1"
    schema:
      - name: "product_name"
        source_column: "name"
        type: "string"
        
      - name: "product_id"
        source_column: "id"
        type: "string"
```

---

### View Support

Sync from PostgreSQL views using reference table triggers.

**Config:**

```yaml
tables:
  - name: "product_search_view"
    reference_table: "products"
    collection: "products_search_v1"
    schema:
      # ...
```

Triggers on `reference_table` capture changes; data is fetched from the view.

---

### Vector Search

Convert pgvector embeddings to Typesense vector fields.

**PostgreSQL:**

```sql
CREATE EXTENSION vector;

CREATE TABLE products (
  id SERIAL PRIMARY KEY,
  name TEXT,
  embedding vector(384)
);
```

**Config:**

```yaml
schema:
  - name: "embedding"
    source_type: "vector"
    type: "float[]"
    num_dim: 384
```

Automatically converts pgvector format to float arrays.

---

### Automatic Date Conversion

Configure fields as `type: "date"` for automatic Unix timestamp conversion.

```yaml
schema:
  - name: "created_at"
    type: "date"
    sort: true
```

Supports datetime objects, ISO 8601 strings, and Unix timestamps.

---

## Architecture

### Queue-Based Sync

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

**PostgreSQL Triggers** capture INSERT/UPDATE/DELETE operations and queue them.

**Sync Queue Table** stores pending operations:

```sql
CREATE TABLE typesense_sync_queue (
  id SERIAL PRIMARY KEY,
  record_id TEXT NOT NULL,
  table_name TEXT NOT NULL,
  operation_type TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(record_id, table_name)
);
```

**Sync Engine** processes batches:
1. Fetch jobs from queue
2. Deduplicate (latest operation wins)
3. Fetch current data from PostgreSQL
4. Apply transformers and column mapping
5. Convert types (dates, vectors)
6. Upsert/delete in Typesense
7. Remove processed jobs
8. Commit transaction

**Transaction Safety:**
- Atomic batch operations
- Rollback on error
- Failed jobs remain in queue for retry
- Idempotent operations

---

## Deployment

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

---

## Contributing

Contributions welcome. Please:
- Check existing issues before creating new ones
- Provide reproduction steps and sanitized configuration
- Follow PEP 8 guidelines
- Add docstrings and type hints
- Test thoroughly before submitting PRs


## License

MIT License - see [LICENSE](LICENSE) for details.

---

## Support

- Issues: [GitHub Issues](https://github.com/youssefEdrees/postgres-typesense-sync/issues)
- Discussions: [GitHub Discussions](https://github.com/youssefEdrees/postgres-typesense-sync/discussions)
