# Spannery Examples

This directory contains examples for using Spannery.

## Transaction Support

Spannery supports using transactions with models to ensure that multiple database operations are performed atomically. The `transaction_example.py` file demonstrates this functionality.

### Using Transactions with Models

All data mutation methods in Spannery now support an optional `transaction` parameter:

```python
# These methods now accept an optional transaction parameter
model.save(database, transaction=transaction)
model.update(database, transaction=transaction)
model.delete(database, transaction=transaction)
```

### Transaction with Context Manager

You can use a context manager to manage transactions:

```python
# Create and use a transaction with a context manager
with database.transaction() as transaction:
    # Perform multiple operations that will be committed or rolled back together
    customer.save(database, transaction=transaction)
    order.save(database, transaction=transaction)

    for item in order_items:
        item.save(database, transaction=transaction)

    # If any operation fails, all changes will be rolled back
    # If no errors occur, all changes will be committed when the block exits
```

### Transaction with Callback Function

You can also use the `run_in_transaction` method with a callback function:

```python
# Define a function that performs multiple operations
def create_order_with_items(transaction):
    # Save the order
    order.save(database, transaction=transaction)

    # Save order items
    for item in items:
        item.save(database, transaction=transaction)

    # Return a value if needed
    return order

# Execute the function in a transaction
result = database.run_in_transaction(create_order_with_items)
```

### Transaction Rollback

If any operation within a transaction raises an exception, all changes made in the transaction will be automatically rolled back:

```python
try:
    with database.transaction() as transaction:
        # This works
        customer.save(database, transaction=transaction)

        # This fails
        invalid_record.save(database, transaction=transaction)

        # This code won't execute
        order.save(database, transaction=transaction)
except Exception as e:
    # The transaction is automatically rolled back
    print(f"Transaction failed: {e}")
```

## Table Relationships and JOINs

Spannery now supports defining relationships between tables and performing JOINs in queries. The `join_example.py` file demonstrates this functionality.

### Defining Relationships

To define relationships between tables, use the `ForeignKeyField` class:

```python
from spannery import SpannerModel, StringField, ForeignKeyField

class Organization(SpannerModel):
    __tablename__ = "Organizations"

    OrganizationID = StringField(primary_key=True)
    Name = StringField(max_length=255, nullable=False)
    # ... other fields

class User(SpannerModel):
    __tablename__ = "Users"

    UserID = StringField(primary_key=True)
    Email = StringField(max_length=255, nullable=False)
    # ... other fields

class OrganizationUser(SpannerModel):
    __tablename__ = "OrganizationUsers"

    # Define relationships with ForeignKeyField
    OrganizationID = ForeignKeyField("Organization", primary_key=True)
    UserID = ForeignKeyField("User", primary_key=True)
    Role = StringField(max_length=20, nullable=False)
    # ... other fields
```

### Querying with JOINs

You can use the `join` method on the Query object to perform JOINs:

```python
# Get all users in an organization
users_in_org = (
    session.query(OrganizationUser)
    .join("User", "UserID", "UserID", join_type=JoinType.INNER)
    .filter(OrganizationID=organization_id)
    .all()
)
```

The `join` method accepts the following parameters:

- `related_model`: The model class or name to join with
- `from_field`: The field name in the base model for the join condition
- `to_field`: The field name in the related model for the join condition
- `join_type`: The type of join to perform (INNER, LEFT, RIGHT, FULL)
- `alias`: Optional alias for the joined table

### Accessing Related Records

You can access related records using the `get_related` method:

```python
# Get the User related to an OrganizationUser
user = session.get_related(organization_user, "UserID")

# Get the Organization related to an OrganizationUser
organization = session.get_related(organization_user, "OrganizationID")
```

### Convenience Methods

The `SpannerSession` class provides a `join_query` convenience method:

```python
# Create a query with a JOIN preconfigured
users_query = session.join_query(
    OrganizationUser,
    "User",
    "UserID",
    "UserID"
)

# Then add filters, sorting, etc.
active_users = users_query.filter(Status="ACTIVE").all()
```

### Multiple JOINs

You can chain multiple `join` calls to join with multiple tables:

```python
# Join with both User and Organization tables
results = (
    session.query(OrganizationUser)
    .join("User", "UserID", "UserID", join_type=JoinType.INNER)
    .join("Organization", "OrganizationID", "OrganizationID", join_type=JoinType.INNER)
    .filter(Status="ACTIVE")
    .all()
)
```

## Running the Examples

To run the examples, set the following environment variables:

```bash
export SPANNER_PROJECT_ID="your-project-id"
export SPANNER_INSTANCE_ID="your-instance-id"
export SPANNER_DATABASE_ID="your-database-id"
```

Then run the example:

```bash
python join_example.py
```
