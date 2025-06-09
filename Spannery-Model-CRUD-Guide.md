# Spannery - Models and CRUD Operations Guide

This guide provides everything you need to know about Spannery's models and basic CRUD operations.

## Table of Contents

- [Model Definition](#model-definition)
- [Field Types](#field-types)
- [Connection Setup](#connection-setup)
- [CRUD Operations](#crud-operations)
- [Querying Data](#querying-data)
- [Relationships and Joins](#relationships-and-joins)
- [Transactions](#transactions)

## Model Definition

Models in Spannery are defined as Python classes that inherit from `SpannerModel`:

```python
from spannery.model import SpannerModel
from spannery.fields import StringField, IntegerField, DateTimeField, BooleanField, NumericField

class Organization(SpannerModel):
    __tablename__ = "Organizations"

    OrganizationID = StringField(primary_key=True, default=lambda: str(uuid.uuid4()))
    Name = StringField(nullable=False)
    Active = BooleanField(default=True)
    CreatedAt = DateTimeField(auto_now_add=True)
```

### Key Model Properties

- `__tablename__`: Required. Defines the table name in Spanner.
- `__interleave_in__`: Optional. Specifies the parent table for interleaved tables.
- `__on_delete__`: Optional. Defines cascade delete behavior ("CASCADE" or "NO ACTION").

### Interleaved Tables

Interleaved tables use composite primary keys and must include the parent table's primary key:

```python
class Product(SpannerModel):
    __tablename__ = "Products"
    __interleave_in__ = "Organizations"

    OrganizationID = StringField(primary_key=True)  # Parent table's key
    ProductID = StringField(primary_key=True, default=lambda: str(uuid.uuid4()))
    Name = StringField(nullable=False)
    Price = NumericField(precision=10, scale=2)
```

## Field Types

Spannery provides various field types that map to Spanner column types:

| Spannery Field | Spanner Type | Description                              |
| ------------------- | ------------ | ---------------------------------------- |
| `StringField`       | STRING       | Text data                                |
| `IntegerField`      | INT64        | Integer values                           |
| `IntField`          | INT64        | Alias for IntegerField                   |
| `NumericField`      | NUMERIC      | Decimal numbers with precision and scale |
| `BooleanField`      | BOOL         | True/False values                        |
| `DateTimeField`     | TIMESTAMP    | Date and time values                     |
| `DateField`         | DATE         | Date values (without time)               |
| `FloatField`        | FLOAT64      | Floating point numbers                   |
| `BytesField`        | BYTES        | Binary data                              |
| `JsonField`         | JSON         | JSON data                                |
| `ArrayField`        | ARRAY        | Array of values                          |
| `ForeignKeyField`   | Varies       | Foreign key relationship                 |

### Field Parameters

Common parameters for all field types:

- `primary_key`: Boolean indicating if the field is part of the primary key
- `nullable`: Boolean indicating if NULL values are allowed
- `default`: Default value or function
- `auto_now_add`: Auto-populate with current timestamp on create (DateTimeField only)
- `auto_now`: Auto-update with current timestamp on every update (DateTimeField only)
- `max_length`: Maximum string length (StringField only)
- `precision` and `scale`: For NumericField to define decimal precision

## Connection Setup

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

## CRUD Operations

### Create

```python
# Create an organization
org = Organization(Name="Acme Corporation")
session.save(org)

# Create a product in that organization
product = Product(
    OrganizationID=org.OrganizationID,
    Name="Super Widget",
    Price=99.99
)
session.save(product)
```

### Read

```python
# Get by primary key
org = session.get(Organization, OrganizationID="org-id-here")
product = session.get(Product, OrganizationID="org-id", ProductID="product-id")

# Query all records of a model
all_orgs = session.query(Organization).all()
```

### Update

```python
# Get, modify, and save
product = session.get(Product, OrganizationID="org-id", ProductID="product-id")
product.Name = "Updated Widget"
product.Price = 129.99
session.update(product)
```

### Delete

```python
# Get and delete
product = session.get(Product, OrganizationID="org-id", ProductID="product-id")
session.delete(product)
```

## Querying Data

Spannery provides a fluent query builder interface:

```python
# Basic filters
active_products = session.query(Product) \
    .filter(OrganizationID="org-id", Active=True) \
    .all()

# Comparison operators
in_stock = session.query(Product) \
    .filter_gt(Stock=0) \
    .all()

# Ordering
ordered = session.query(Product) \
    .order_by("Name") \
    .all()

# Descending ordering
expensive_first = session.query(Product) \
    .order_by("Price", desc=True) \
    .all()

# Selecting specific fields
names_only = session.query(Product) \
    .select("Name", "Category") \
    .all()

# Counting records
count = session.query(Product) \
    .filter(OrganizationID="org-id") \
    .count()

# Limit and offset
paginated = session.query(Product) \
    .limit(10) \
    .offset(20) \
    .all()
```

### Comparison Operators

- `.filter_eq()`: Equal to (same as filter())
- `.filter_ne()`: Not equal to
- `.filter_gt()`: Greater than
- `.filter_gte()`: Greater than or equal to
- `.filter_lt()`: Less than
- `.filter_lte()`: Less than or equal to

## Relationships and Joins

### Defining Relationships

Use `ForeignKeyField` to define relationships between models:

```python
class OrganizationUser(SpannerModel):
    __tablename__ = "OrganizationUsers"

    OrganizationID = ForeignKeyField("Organization", primary_key=True, related_name="users")
    UserID = ForeignKeyField("User", primary_key=True, related_name="organizations")
    Role = StringField(nullable=False)
```

### Performing Joins

```python
# Inner join
users_in_org = session.query(OrganizationUser) \
    .join("User", "UserID", "UserID", join_type=JoinType.INNER) \
    .filter(OrganizationID="org-id-here") \
    .all()

# Get the related User model
for org_user in users_in_org:
    user = session.get_related(org_user, "UserID")
    print(f"User: {user.FullName}, Role: {org_user.Role}")

# Multiple joins
multi_join_query = session.query(OrganizationUser) \
    .join("User", "UserID", "UserID") \
    .join("Organization", "OrganizationID", "OrganizationID") \
    .all()
```

### Table Filters

Filter on columns from joined tables:

```python
# Get all media files for a specific product
media_files = session.query(Media) \
    .join(ProductMedia, "MediaID", "MediaID") \
    .table_filter("ProductMedia", ProductID="product-id") \
    .all()

# More complex query with filters on different tables
products = session.query(Product) \
    .join(ProductMedia, "ProductID", "ProductID") \
    .join(Media, "MediaID", "MediaID") \
    .filter(Category="Electronics") \  # Filter on base table
    .table_filter("ProductMedia", IsPrimary=True) \  # Filter on first joined table
    .table_filter("Media", MimeType="image/jpeg") \  # Filter on second joined table
    .all()
```

## Transactions

### Using Context Manager

```python
try:
    with database.transaction() as transaction:
        # Save a customer
        customer.save(database, transaction=transaction)

        # Create and save an order
        order = Order(CustomerID=customer.CustomerID)
        order.save(database, transaction=transaction)

        # Save order items
        for item in items:
            item.save(database, transaction=transaction)

        # All operations will be committed at the end of the with block
except Exception as e:
    # Transaction will be automatically rolled back on error
    print(f"Error: {e}")
```

### Using Session Transaction

```python
with session.transaction() as batch:
    # Insert a new product
    batch.insert(
        "Products",
        columns=["OrganizationID", "ProductID", "Name", "Price"],
        values=[["org-id", "new-product-id", "New Product", 149.99]]
    )

    # Update an existing product
    batch.update(
        "Products",
        columns=["OrganizationID", "ProductID", "Stock"],
        values=[["org-id", "existing-id", 25]]
    )
```
