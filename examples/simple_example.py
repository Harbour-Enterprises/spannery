"""
Simple example showing Spannery usage for CRUD operations.

Assumes tables already exist in Spanner:
- Users table with UserID, Email, FullName, Active, CreatedAt, UpdatedAt
- Orders table with OrderID, UserID, Total, Status, CreatedAt
"""

import uuid
from datetime import datetime, timedelta

from google.cloud import spanner

from spannery import (
    BoolField,
    NumericField,
    SpannerModel,
    SpannerSession,
    StringField,
    TimestampField,
)


# Define models that map to existing tables
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


def main():
    # Connect to Spanner
    client = spanner.Client(project="your-project-id")
    instance = client.instance("your-instance-id")
    database = instance.database("your-database-id")

    # Create a session
    session = SpannerSession(database)

    # Create a new user (with request tag for monitoring)
    user = User(Email="john@example.com", FullName="John Doe")
    # CreatedAt and UpdatedAt will use COMMIT_TIMESTAMP automatically
    session.save(user, request_tag="user-creation")
    print(f"Created user: {user.UserID}")

    # Read the user
    user = session.get(User, UserID=user.UserID)
    print(f"Retrieved user: {user.Email}")

    # Update the user
    user.Email = "john.doe@example.com"
    # UpdatedAt will be set to COMMIT_TIMESTAMP automatically
    session.update(user)
    print("Updated user email")

    # Create an order for the user
    order = Order(UserID=user.UserID, Total=99.99)
    session.save(order)
    print(f"Created order: {order.OrderID}")

    # Query users with Django-style filters
    active_users = (
        session.query(User)
        .filter(Active=True, Email__like="%example.com", CreatedAt__gte="2024-01-01")
        .order_by("CreatedAt", desc=True)
        .limit(10)
        .all()
    )

    print(f"Found {len(active_users)} active users")

    # Query with simplified JOIN syntax
    user_orders = (
        session.query(Order).join(User, on=("UserID", "UserID")).filter(UserID=user.UserID).all()
    )

    print(f"User has {len(user_orders)} orders")

    # More complex query examples
    # Find high-value orders
    session.query(Order).filter(Total__gte=100, Status__in=["pending", "processing"]).order_by(
        "Total", desc=True
    ).all()

    # OR conditions - find orders that are either high value OR urgent
    session.query(Order).filter_or({"Total__gt": 500}, {"Status": "urgent"}).all()

    # Transaction example with request tag
    with session.transaction(request_tag="batch-order-create") as txn:
        # Create multiple orders atomically
        order1 = Order(UserID=user.UserID, Total=50.00, Status="pending")
        order2 = Order(UserID=user.UserID, Total=75.00, Status="pending")

        order1.save(database, transaction=txn)
        order2.save(database, transaction=txn)
        # Commits when exiting the context manager

    print("Created 2 orders in transaction")

    # Read-only transaction for consistent reads
    with session.read_only_transaction() as ro_txn:
        # All queries see the same snapshot
        user_count = ro_txn.query(User).filter(Active=True).count()
        order_count = ro_txn.query(Order).filter(Status="pending").count()

        # Can also execute raw SQL
        results = ro_txn.execute_sql(
            "SELECT AVG(Total) FROM Orders WHERE UserID = @user_id", params={"user_id": user.UserID}
        )
        avg_order = list(results)[0][0]

        print(f"Consistent snapshot: {user_count} users, {order_count} pending orders")
        print(f"User's average order: ${avg_order}")

    # Query with force index and priority
    session.query(Order).filter(Status="pending").force_index("idx_orders_status").with_priority(
        "HIGH"
    ).with_request_tag("urgent-order-check").all()

    # Stale read for analytics (non-critical queries)
    with session.snapshot(exact_staleness=timedelta(seconds=10)) as snapshot:
        # Read data as it was 10 seconds ago
        results = snapshot.execute_sql(
            "SELECT COUNT(*) FROM Orders WHERE Status = @status", params={"status": "pending"}
        )
        count = list(results)[0][0]
        print(f"Orders pending 10 seconds ago: {count}")

    # Filter by primary key convenience
    session.query(Order).filter_by_id(OrderID=order.OrderID).one()  # Expects exactly one result

    # Check existence
    has_orders = session.query(Order).filter(UserID=user.UserID).exists()
    print(f"User has orders: {has_orders}")

    # Delete an order
    session.delete(order)
    print("Deleted order")

    # Bulk operations example
    print("\nBulk operations example:")

    # Create test users
    test_users = []
    for i in range(5):
        u = User(Email=f"test{i}@example.com", FullName=f"Test User {i}")
        test_users.append(u)

    # Save all in one transaction
    with session.transaction() as txn:
        for u in test_users:
            u.save(database, transaction=txn)

    print(f"Created {len(test_users)} test users")

    # Query with various filters
    recent_users = (
        session.query(User)
        .filter(
            CreatedAt__between=(datetime.now() - timedelta(days=7), datetime.now()),
            Email__not_in=["admin@example.com", "system@example.com"],
        )
        .all()
    )

    # Pattern matching
    gmail_users = session.query(User).filter(Email__regex=r".*@gmail\.com$").all()

    # Case-insensitive search
    johns = session.query(User).filter(FullName__ilike="%john%").all()

    print(f"Recent users: {len(recent_users)}")
    print(f"Gmail users: {len(gmail_users)}")
    print(f"Users named John: {len(johns)}")

    # Clean up test users
    with session.transaction() as txn:
        for u in test_users:
            u.delete(database, transaction=txn)


if __name__ == "__main__":
    main()
