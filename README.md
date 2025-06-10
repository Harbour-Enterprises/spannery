# Spannery

[![PyPI](https://badge.fury.io/py/spannery.svg)](https://badge.fury.io/py/spannery)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A lightweight ORM for Google Cloud Spanner that doesn't try to be everything. Spannery focuses on simplicity, clarity, and native Spanner features.

## Philosophy

**"We read and write data, we don't manage schemas"**

- ✅ **Simple API** - One way to do things, no magic
- ✅ **Django-style filters** - Intuitive `field__operator=value` syntax
- ✅ **Native Spanner features** - Commit timestamps, stale reads, request tags
- ❌ **No DDL/schema management** - Use Spanner tools or Terraform
- ❌ **No migration system** - Your CI/CD pipeline should handle that
- ❌ **No lazy loading** - Explicit is better than implicit

## Installation

```bash
pip install spannery
```

## Quick Start

### Define Models

```python
from spannery import SpannerModel, StringField, TimestampField, BoolField, NumericField
import uuid

class User(SpannerModel):
    __tablename__ = "Users"

    UserID = StringField(primary_key=True, default=lambda: str(uuid.uuid4()))
    Email = StringField()
    FullName = StringField()
    Active = BoolField(default=True)
    CreatedAt = TimestampField(allow_commit_timestamp=True)
    UpdatedAt = TimestampField(allow_commit_timestamp=True)


class Order(SpannerModel):
    __tablename__ = "Orders"

    OrderID = StringField(primary_key=True, default=lambda: str(uuid.uuid4()))
    UserID = StringField()
    Total = NumericField()
    Status = StringField(default="pending")
    CreatedAt = TimestampField(allow_commit_timestamp=True)
```

### Basic CRUD Operations

```python
from google.cloud import spanner
from spannery import SpannerSession

# Connect to Spanner
client = spanner.Client()
instance = client.instance("your-instance")
database = instance.database("your-database")

# Create a session
session = SpannerSession(database)

# CREATE
user = User(Email="john@example.com", FullName="John Doe")
session.save(user)  # CreatedAt set by Spanner commit timestamp

# READ
user = session.get(User, UserID=user.UserID)

# UPDATE
user.Email = "john.doe@example.com"
session.update(user)  # UpdatedAt set by Spanner commit timestamp

# DELETE
session.delete(user)
```

### Querying with Django-Style Filters

```python
# Simple equality
active_users = session.query(User).filter(Active=True).all()

# Operators
users = (
    session.query(User)
    .filter(
        Active=True,
        CreatedAt__gte="2024-01-01",
        Email__like="%@gmail.com"
    )
    .order_by("CreatedAt", desc=True)
    .limit(10)
    .all()
)

# OR conditions
premium_or_trial = (
    session.query(User)
    .filter_or(
        {"Status": "premium"},
        {"Status": "trial", "CreatedAt__gte": "2024-01-01"}
    )
    .all()
)

# Complex queries
results = (
    session.query(Order)
    .filter(
        Status__in=["pending", "processing"],
        Total__between=(100, 1000),
        UserID__is_null=False
    )
    .order_by("Total", desc=True)
    .all()
)
```

### Filter Operators

| Operator | SQL Equivalent | Example |
|----------|----------------|---------|
| (none) | = | `filter(Status="active")` |
| __lt | < | `filter(Price__lt=100)` |
| __lte | <= | `filter(Price__lte=100)` |
| __gt | > | `filter(Price__gt=100)` |
| __gte | >= | `filter(Price__gte=100)` |
| __ne | != | `filter(Status__ne="deleted")` |
| __in | IN | `filter(Status__in=["A", "B"])` |
| __not_in | NOT IN | `filter(Status__not_in=["X", "Y"])` |
| __like | LIKE | `filter(Email__like="%@gmail%")` |
| __ilike | ILIKE | `filter(Name__ilike="%john%")` |
| __is_null | IS NULL | `filter(DeletedAt__is_null=True)` |
| __between | BETWEEN | `filter(Price__between=(10, 100))` |
| __regex | REGEXP | `filter(Email__regex=r"^[a-z]+@")` |

### JOINs

```python
# Simple join
user_orders = (
    session.query(Order)
    .join(User, on=("UserID", "UserID"))
    .filter(Active=True)
    .all()
)

# Left join
all_users_maybe_orders = (
    session.query(User)
    .left_join(Order, on=("UserID", "UserID"))
    .all()
)

# Multiple joins
full_data = (
    session.query(Order)
    .join(User, on=("UserID", "UserID"))
    .join(Product, on=("ProductID", "ProductID"))
    .filter(User__Active=True)
    .all()
)
```

### Transactions

```python
# Simple transaction
with session.transaction() as txn:
    user = User(Email="jane@example.com", FullName="Jane Smith")
    user.save(database, transaction=txn)

    order = Order(UserID=user.UserID, Total=99.99)
    order.save(database, transaction=txn)
    # Commits on success, rolls back on exception

# With request tag for monitoring
with session.transaction(request_tag="batch-import") as txn:
    for user_data in user_list:
        user = User(**user_data)
        user.save(database, transaction=txn)
```

### Spanner-Specific Features

```python
# Stale reads
from datetime import timedelta

with session.snapshot(exact_staleness=timedelta(seconds=10)) as snapshot:
    results = snapshot.execute_sql(
        "SELECT COUNT(*) FROM Orders WHERE Status = @status",
        params={"status": "pending"}
    )

# Read-only transactions (consistent reads)
with session.read_only_transaction() as ro_txn:
    # All queries see the same snapshot
    users = ro_txn.query(User).filter(Active=True).count()
    orders = ro_txn.query(Order).filter(Status="pending").count()

# Commit timestamps
event = Event(EventID="evt_123")  # CreatedAt will use COMMIT_TIMESTAMP
session.save(event)

# Force index usage
results = (
    session.query(Order)
    .filter(Status="pending")
    .force_index("idx_orders_status")
    .all()
)

# Request tags and priority
urgent_orders = (
    session.query(Order)
    .filter(Priority="urgent")
    .with_request_tag("urgent-queue")
    .with_priority("HIGH")
    .all()
)
```

## Field Types

| Spannery Field | Spanner Type | Python Type | Notes |
|----------------|--------------|-------------|-------|
| `StringField` | `STRING` | `str` | |
| `Int64Field` | `INT64` | `int` | |
| `NumericField` | `NUMERIC` | `Decimal` | For monetary values |
| `BoolField` | `BOOL` | `bool` | |
| `TimestampField` | `TIMESTAMP` | `datetime` | Supports `allow_commit_timestamp` |
| `DateField` | `DATE` | `date` | |
| `Float64Field` | `FLOAT64` | `float` | |
| `BytesField` | `BYTES` | `bytes` | |
| `JsonField` | `JSON` | `dict/list` | |
| `ArrayField` | `ARRAY<T>` | `list` | Requires item field type |
| `ForeignKeyField` | `STRING` | `str` | For relationships |

## Query Methods

```python
# Filtering
.filter(**kwargs)           # Django-style field lookups
.filter_or(*conditions)     # OR conditions
.filter_by_id(**kwargs)     # Filter by primary key(s)

# Results
.all()                      # Get all results
.first()                    # Get first or None
.one()                      # Get exactly one (error if not found or multiple)
.count()                    # Count matching records
.exists()                   # Check if any match

# Modifiers
.select(*fields)            # Select specific fields
.order_by(field, desc=False)  # Sort results
.limit(n)                   # Limit results
.offset(n)                  # Skip results

# Joins
.join(Model, on=("field1", "field2"))       # Inner join
.left_join(Model, on=("field1", "field2"))  # Left join

# Spanner features
.force_index("index_name")  # Force index usage
.with_request_tag("tag")    # Add request tag
.with_priority("HIGH")      # Set priority (LOW/MEDIUM/HIGH)
```

## Why Spannery?

### 1. Simpler than SQLAlchemy

```python
# SQLAlchemy - multiple ways, more complexity
users = session.query(User).filter(User.email == "john@example.com").all()
users = session.execute(select(User).where(User.email == "john@example.com")).scalars().all()

# Spannery - one intuitive way
users = session.query(User).filter(Email="john@example.com").all()
```

### 2. No Schema Management Overhead

```python
# SQLAlchemy - requires schema management
Base.metadata.create_all(engine)
alembic upgrade head

# Spannery - just map to existing tables
class User(SpannerModel):
    __tablename__ = "Users"  # Table already exists in Spanner
    UserID = StringField(primary_key=True)
```

### 3. Native Spanner Features

```python
# Spannery embraces Spanner-specific features
CreatedAt = TimestampField(allow_commit_timestamp=True)  # Auto-set by Spanner

with session.read_only_transaction() as ro_txn:  # Consistent reads
    # All queries in this block see the same snapshot

session.query(Order).force_index("idx_status").all()  # Index hints
```

### 4. Production-Ready Patterns

```python
# Request tagging for monitoring
session.save(user, request_tag="user-signup")

# Explicit transaction handling
with session.transaction(request_tag="payment-processing") as txn:
    # Your atomic operations here

# Query result guarantees
user = session.query(User).filter(Email=email).one()  # Fails if not exactly one
```

## Advanced Usage

### Custom Field Types

```python
from spannery import Field
from decimal import Decimal

class MoneyField(NumericField):
    """Currency field with automatic rounding."""

    def to_db_value(self, value):
        if value is not None:
            return Decimal(value).quantize(Decimal("0.01"))
        return None
```

### Interleaved Tables

```python
class Order(SpannerModel):
    __tablename__ = "Orders"
    __interleave_in__ = "Users"  # Parent table

    UserID = StringField(primary_key=True)
    OrderID = StringField(primary_key=True)
    Total = NumericField()
```

### Batch Operations

```python
# Efficient bulk insert
users = [User(Email=f"user{i}@example.com") for i in range(1000)]

with session.transaction() as txn:
    for user in users:
        user.save(database, transaction=txn)
```

### Raw SQL When Needed

```python
# Sometimes you need raw SQL
results = session.execute_sql(
    """
    SELECT u.Email, COUNT(o.OrderID) as OrderCount
    FROM Users u
    LEFT JOIN Orders o ON u.UserID = o.UserID
    WHERE u.Active = @active
    GROUP BY u.Email
    HAVING COUNT(o.OrderID) > @min_orders
    """,
    params={"active": True, "min_orders": 5}
)
```

## Best Practices

1. **Let Spanner handle timestamps**: Use `TimestampField(allow_commit_timestamp=True)`
2. **Use transactions explicitly**: Wrap related operations in transactions
3. **Add request tags**: Use `request_tag` for monitoring and debugging
4. **Design for Spanner**: Embrace interleaved tables and array types
5. **Keep queries simple**: Use raw SQL for complex analytical queries

## FAQ

**Q: How do I create tables?**
A: Use Spanner's UI, `gcloud` CLI, or Terraform. Spannery doesn't manage schemas.

**Q: How do I handle migrations?**
A: Use your existing CI/CD pipeline with tools like Liquibase or custom scripts.

**Q: Can I use composite primary keys?**
A: Yes! Just mark multiple fields with `primary_key=True`.

**Q: Does it support async?**
A: Not yet. Spanner's Python client doesn't support async operations.

**Q: How do I contribute?**
A: We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md).

## License

MIT - see [LICENSE](LICENSE) for details.
