# Spannery

[![PyPI](https://badge.fury.io/py/spannery.svg)](https://badge.fury.io/py/spannery)

A simple ORM for Google Cloud Spanner. Spannery focuses on simplicity and Spanner-native features, without the complexity of SQLAlchemy.

## Philosophy

**"We read and write data, we don't manage schemas"**

- ✅ Simple, intuitive API
- ✅ One way to do things
- ✅ Native Spanner features (commit timestamps, stale reads, request tags)
- ❌ No DDL/schema management (use Spanner tools)
- ❌ No migrations (use proper deployment tools)
- ❌ No magic or hidden queries

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

    user_id = StringField(primary_key=True, default=lambda: str(uuid.uuid4()))
    email = StringField()
    full_name = StringField()
    active = BoolField(default=True)
    created_at = TimestampField(allow_commit_timestamp=True)
    updated_at = TimestampField(allow_commit_timestamp=True)


class Order(SpannerModel):
    __tablename__ = "Orders"

    order_id = StringField(primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = StringField()
    total = NumericField()
    status = StringField(default="pending")
    created_at = TimestampField(allow_commit_timestamp=True)
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
user = User(email="john@example.com", full_name="John Doe")
session.save(user)  # created_at set by Spanner

# READ
user = session.get(User, user_id=user.user_id)

# UPDATE
user.email = "john.doe@example.com"
session.update(user)  # updated_at set by Spanner

# DELETE
session.delete(user)
```

### Querying

```python
# Simple queries
active_users = session.query(User).filter(active=True).all()

# Advanced filtering
users = session.query(User) \
    .filter_like(email="%@gmail.com") \
    .filter_gte(created_at="2024-01-01") \
    .order_by("created_at", desc=True) \
    .limit(10) \
    .all()

# JOINs
user_orders = session.query(Order) \
    .join(User, "user_id", "user_id") \
    .filter(user_id=user.user_id) \
    .all()
```

### Transactions

```python
# Simple transaction
with session.transaction() as txn:
    user = User(email="jane@example.com", full_name="Jane Smith")
    user.save(database, transaction=txn)

    order = Order(user_id=user.user_id, total=99.99)
    order.save(database, transaction=txn)
    # Commits on success, rolls back on exception
```

### Spanner-Specific Features

```python
# Stale reads (read data as it was 10 seconds ago)
from datetime import timedelta

with session.snapshot(exact_staleness=timedelta(seconds=10)) as snapshot:
    old_orders = snapshot.execute_sql(
        "SELECT * FROM Orders WHERE created_at < @cutoff",
        params={"cutoff": "2024-01-01"}
    )

# Commit timestamps (automatic server-side timestamps)
class Event(SpannerModel):
    __tablename__ = "Events"

    event_id = StringField(primary_key=True)
    occurred_at = TimestampField(allow_commit_timestamp=True)

event = Event(event_id="evt_123")
session.save(event)  # occurred_at set to commit timestamp by Spanner
```

## Field Types

| Spannery Field | Spanner Type | Notes |
|----------------|--------------|-------|
| `StringField` | `STRING` | |
| `Int64Field` | `INT64` | |
| `NumericField` | `NUMERIC` | Decimal type |
| `BoolField` | `BOOL` | |
| `TimestampField` | `TIMESTAMP` | Supports `allow_commit_timestamp` |
| `DateField` | `DATE` | |
| `Float64Field` | `FLOAT64` | |
| `BytesField` | `BYTES` | |
| `JsonField` | `JSON` | |
| `ArrayField` | `ARRAY<T>` | Requires item field type |

## Query Methods

- `filter(**kwargs)` - Equality filters
- `filter_lt()`, `filter_lte()`, `filter_gt()`, `filter_gte()` - Comparisons
- `filter_in()`, `filter_not_in()` - List membership
- `filter_like()`, `filter_ilike()` - Pattern matching
- `filter_is_null()`, `filter_is_not_null()` - NULL checks
- `filter_between()` - Range queries
- `order_by()` - Sorting
- `limit()`, `offset()` - Pagination
- `join()` - JOIN operations

## Why Spannery?

### Simpler than SQLAlchemy

```python
# SQLAlchemy - multiple ways to query
users = session.query(User).filter(User.email == "john@example.com").all()
users = session.execute(select(User).where(User.email == "john@example.com")).scalars().all()

# Spannery - one clear way
users = session.query(User).filter(email="john@example.com").all()
```

### No Schema Management Overhead

```python
# SQLAlchemy - requires schema management
Base.metadata.create_all(engine)
alembic upgrade head

# Spannery - just map to existing tables
class User(SpannerModel):
    __tablename__ = "Users"  # Table already exists
    user_id = StringField(primary_key=True)
```

### Native Spanner Features

```python
# Spannery makes Spanner features easy
created_at = TimestampField(allow_commit_timestamp=True)  # Auto-set by Spanner
with session.snapshot(exact_staleness=timedelta(seconds=10)):  # Stale reads
    # Read historical data
```

## License

MIT
