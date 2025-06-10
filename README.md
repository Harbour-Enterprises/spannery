# Spannery

[![PyPI](https://badge.fury.io/py/spannery.svg)](https://badge.fury.io/py/spannery)

A Python ORM for Google Cloud Spanner, designed to provide an intuitive interface for working with Spanner databases.

## Features

- Model definition with field types that map to Spanner column types
- Support for interleaved tables and composite primary keys
- Automatic table creation and schema management
- Fluent query builder interface
- Session management for database operations
- Transaction and batch support
- Comprehensive field types (String, Integer, Boolean, DateTime, etc.)

## Installation

```bash
pip install spannery
```

## Quick Start

### Define Models

```python
from spannery.model import SpannerModel, SpannerSession
from spannery.fields import (
    StringField, IntegerField, DateTimeField, BooleanField, NumericField
)
import uuid

class Organization(SpannerModel):
    __tablename__ = "Organizations"

    OrganizationID = StringField(primary_key=True, default=lambda: str(uuid.uuid4()))
    Name = StringField(nullable=False)
    Active = BooleanField(default=True)
    CreatedAt = DateTimeField(auto_now_add=True)


class Product(SpannerModel):
    __tablename__ = "Products"
    __interleave_in__ = "Organizations"

    OrganizationID = StringField(primary_key=True)
    ProductID = StringField(primary_key=True, default=lambda: str(uuid.uuid4()))
    Name = StringField(nullable=False)
    Description = StringField(nullable=True)
    Category = StringField(nullable=True)
    Stock = IntegerField(default=0)
    CreatedAt = DateTimeField(auto_now_add=True)
    UpdatedAt = DateTimeField(auto_now=True, nullable=True)
    Active = BooleanField(default=True)
    ListPrice = NumericField(precision=10, scale=2, nullable=False)
    CostPrice = NumericField(precision=10, scale=2, nullable=True)
```

### Connect to Spanner and Create Tables

```python
from google.cloud import spanner
from spannery.session import SpannerSession

# Create Spanner client
client = spanner.Client(project="your-project-id")
instance = client.instance("your-instance-id")
database = instance.database("your-database-id")

# Create a session
session = SpannerSession(database)

# Create tables if they don't exist
Organization.create_table(database)
Product.create_table(database)
```

### Create and Save Models

```python
# Create an organization
org = Organization(Name="Acme Corporation")
session.save(org)

# Create a product in that organization
product = Product(
    OrganizationID=org.OrganizationID,
    Name="Super Widget",
    Description="A fantastic widget",
    Category="Widgets",
    Stock=100,
    ListPrice=99.99,
    CostPrice=49.99
)
session.save(product)
```

### Query Data

```python
# Get a single record by primary key
org = session.get(Organization, OrganizationID="org-id-here")

# Query with conditions using the query builder
active_products = session.query(Product) \
    .filter(OrganizationID=org.OrganizationID) \
    .filter(Active=True) \
    .filter_gt(Stock=0) \
    .order_by("Name") \
    .all()

# Advanced filtering options
products = session.query(Product) \
    .filter_not_in("Category", ["Discontinued", "Archive"]) \
    .filter_like("Name", "Widget%") \
    .filter_between("ListPrice", 10, 100) \
    .filter_is_not_null("Description") \
    .all()

# OR conditions
results = session.query(Product) \
    .filter_or({"Category": "Electronics"}, {"ListPrice__lt": 50}) \
    .all()

# Pattern matching and regex
email_users = session.query(User) \
    .filter_regex("Email", r".*@(gmail|yahoo)\.com$") \
    .filter_ilike("Name", "%john%") \
    .all()

# Count products
product_count = session.query(Product) \
    .filter(OrganizationID=org.OrganizationID) \
    .count()

# Select specific fields
names_only = session.query(Product) \
    .filter(OrganizationID=org.OrganizationID) \
    .select("Name", "Category") \
    .all()
```

### Update Records

```python
# Get a product, update it, and save
product = session.get(Product, OrganizationID="org-id", ProductID="product-id")
product.Stock = 50
product.ListPrice = 129.99
session.update(product)
```

### Delete Records

```python
# Get and delete a product
product = session.get(Product, OrganizationID="org-id", ProductID="product-id")
session.delete(product)
```

### Transactions

```python
# Run multiple operations in a transaction
with session.transaction() as batch:
    # Insert a new product
    batch.insert(
        "Products",
        columns=["OrganizationID", "ProductID", "Name", "ListPrice"],
        values=[["org-id", "new-product-id", "New Product", 149.99]]
    )

    # Update an existing product
    batch.update(
        "Products",
        columns=["OrganizationID", "ProductID", "Stock"],
        values=[["org-id", "existing-id", 25]]
    )
```

## Querying Data with JOIN and Table Filters

Spannery supports complex JOIN operations and filtering on columns from different tables:

```python
# Query all media files for a specific product
media_query = session.query(Media).join(
    ProductMedia, "MediaID", "MediaID"
).table_filter(
    "ProductMedia", ProductID="abc123"
)
media_files = media_query.all()

# More complex queries with multiple joins and filters on different tables
products = session.query(Product).join(
    ProductMedia, "ProductID", "ProductID"
).join(
    Media, "MediaID", "MediaID"
).filter(
    Category="Electronics"  # Filter on the base table
).table_filter(
    "ProductMedia", IsPrimary=True  # Filter on first joined table
).table_filter(
    "Media", MimeType="image/jpeg"  # Filter on second joined table
).all()
```

See the full example in [examples/table_filter_example.py](examples/table_filter_example.py)

## Query Filter Methods

Beyond basic equality filters, Spannery supports advanced filtering:

- `filter_not_in(field, values)`: Exclude values from a list
- `filter_like(field, pattern)`: Pattern matching with wildcards (%)
- `filter_ilike(field, pattern)`: Case-insensitive pattern matching
- `filter_between(field, start, end)`: Range filtering
- `filter_is_null(field)` / `filter_is_not_null(field)`: NULL checks
- `filter_regex(field, pattern)`: Regular expression matching
- `filter_or(*conditions)`: OR logic between multiple conditions

## Available Field Types

- `StringField`: For Spanner STRING columns
- `IntegerField`: For Spanner INT64 columns
- `NumericField`: For Spanner NUMERIC columns
- `BooleanField`: For Spanner BOOL columns
- `DateTimeField`: For Spanner TIMESTAMP columns
- `DateField`: For Spanner DATE columns
- `FloatField`: For Spanner FLOAT64 columns
- `BytesField`: For Spanner BYTES columns
- `ArrayField`: For Spanner ARRAY columns

## Advanced Usage

### Custom SQL Queries

```python
# Execute a custom SQL query
result = session.execute_sql(
    "SELECT p.Name, COUNT(*) as OrderCount "
    "FROM Products p JOIN Orders o ON p.ProductID = o.ProductID "
    "WHERE p.OrganizationID = @org_id "
    "GROUP BY p.Name",
    params={"org_id": "org-id-here"},
    param_types={"org_id": spanner.param_types.STRING}
)

# Process results
for row in result:
    print(f"Product: {row[0]}, Orders: {row[1]}")
```

### Migrations

In development. For now, you can use Spanner's DDL capabilities directly for schema migrations.

## License

MIT
