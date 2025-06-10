#!/usr/bin/env python
"""
Transaction example for Spannery.

This example demonstrates how to use transactions with Spannery models to:
1. Perform multiple operations atomically
2. Roll back changes when errors occur
3. Use different transaction approaches

Usage:
    python transaction_example.py [project_id] [instance_id] [database_id]

If no arguments are provided, it will use emulator settings.
"""

import os
import sys
import uuid

from google.cloud import spanner

from spannery.fields import (
    DateTimeField,
    IntegerField,
    NumericField,
    StringField,
)
from spannery.model import SpannerModel


# Define models
class Customer(SpannerModel):
    __tablename__ = "Customers"

    CustomerID = StringField(primary_key=True, default=lambda: str(uuid.uuid4()))
    Name = StringField(nullable=False)
    Email = StringField(nullable=True)
    CreatedAt = DateTimeField(auto_now_add=True)


class Order(SpannerModel):
    __tablename__ = "Orders"
    __interleave_in__ = "Customers"
    __on_delete__ = "CASCADE"

    CustomerID = StringField(primary_key=True)
    OrderID = StringField(primary_key=True, default=lambda: str(uuid.uuid4()))
    OrderDate = DateTimeField(auto_now_add=True)
    Status = StringField(default="PENDING")
    TotalAmount = NumericField(precision=10, scale=2, default=0)


class OrderItem(SpannerModel):
    __tablename__ = "OrderItems"
    __interleave_in__ = "Orders"
    __on_delete__ = "CASCADE"

    CustomerID = StringField(primary_key=True)
    OrderID = StringField(primary_key=True)
    ItemID = StringField(primary_key=True, default=lambda: str(uuid.uuid4()))
    ProductName = StringField(nullable=False)
    Quantity = IntegerField(default=1)
    UnitPrice = NumericField(precision=10, scale=2, nullable=False)
    Subtotal = NumericField(precision=10, scale=2, nullable=False)


def create_spanner_client(project_id, instance_id, database_id):
    """Create and return a Spanner client, instance, and database."""
    # Check if using emulator
    if os.environ.get("SPANNER_EMULATOR_HOST"):
        print(f"Using Spanner emulator at {os.environ['SPANNER_EMULATOR_HOST']}")

    client = spanner.Client(project=project_id)
    instance = client.instance(instance_id)
    database = instance.database(database_id)

    return client, instance, database


def create_tables(database):
    """Create tables in the database."""
    print("Creating tables...")

    try:
        Customer.create_table(database)
        print("- Customers table created")
    except Exception as e:
        print(f"- Error creating Customers table: {e}")

    try:
        Order.create_table(database)
        print("- Orders table created")
    except Exception as e:
        print(f"- Error creating Orders table: {e}")

    try:
        OrderItem.create_table(database)
        print("- OrderItems table created")
    except Exception as e:
        print(f"- Error creating OrderItems table: {e}")


def demonstrate_transaction_with_context_manager(database):
    """Demonstrate using a transaction with a context manager."""
    print("\nDemonstrating transaction with context manager...")

    # Create a customer
    customer = Customer(Name="Jane Smith", Email="jane@example.com")

    # Create an order with multiple items in a single transaction
    try:
        with database.transaction() as transaction:
            # Save the customer
            customer.save(database, transaction=transaction)
            print(f"- Created customer: {customer.Name} (ID: {customer.CustomerID})")

            # Create an order
            order = Order(
                CustomerID=customer.CustomerID,
                TotalAmount=0,  # Will be calculated from items
            )

            # Create order items
            items = [
                OrderItem(
                    CustomerID=customer.CustomerID,
                    OrderID=order.OrderID,
                    ProductName="Laptop",
                    Quantity=1,
                    UnitPrice=1299.99,
                    Subtotal=1299.99,
                ),
                OrderItem(
                    CustomerID=customer.CustomerID,
                    OrderID=order.OrderID,
                    ProductName="Mouse",
                    Quantity=1,
                    UnitPrice=24.99,
                    Subtotal=24.99,
                ),
                OrderItem(
                    CustomerID=customer.CustomerID,
                    OrderID=order.OrderID,
                    ProductName="Keyboard",
                    Quantity=1,
                    UnitPrice=99.99,
                    Subtotal=99.99,
                ),
            ]

            # Calculate order total
            order.TotalAmount = sum(item.Subtotal for item in items)

            # Save order
            order.save(database, transaction=transaction)
            print(f"- Created order: {order.OrderID} with total ${order.TotalAmount}")

            # Save all items
            for item in items:
                item.save(database, transaction=transaction)
                print(f"  * Added item: {item.ProductName} - ${item.Subtotal}")

            # All operations will be committed at the end of the with block
            print("- All operations committed successfully")

        # Verify data was saved
        saved_customer = Customer.get(database, CustomerID=customer.CustomerID)
        saved_order = Order.get(database, CustomerID=customer.CustomerID, OrderID=order.OrderID)

        print(f"- Verified customer: {saved_customer.Name}")
        print(f"- Verified order: Total ${saved_order.TotalAmount}")

        return customer, order

    except Exception as e:
        print(f"- Error in transaction: {e}")
        print("- All operations were rolled back")
        return None, None


def demonstrate_transaction_with_callback(database):
    """Demonstrate using a transaction with a callback function."""
    print("\nDemonstrating transaction with callback function...")

    # Create a customer outside the transaction
    customer = Customer(Name="Bob Johnson", Email="bob@example.com")
    customer.save(database)
    print(f"- Created customer: {customer.Name} (ID: {customer.CustomerID})")

    # Define the transaction function
    def create_order_with_items(transaction):
        # Create an order
        order = Order(
            CustomerID=customer.CustomerID,
            Status="PROCESSING",
            TotalAmount=0,  # Will be calculated
        )

        # Save the order within the transaction
        order.save(database, transaction=transaction)

        # Create order items
        items = [
            OrderItem(
                CustomerID=customer.CustomerID,
                OrderID=order.OrderID,
                ProductName="Smartphone",
                Quantity=1,
                UnitPrice=899.99,
                Subtotal=899.99,
            ),
            OrderItem(
                CustomerID=customer.CustomerID,
                OrderID=order.OrderID,
                ProductName="Phone Case",
                Quantity=1,
                UnitPrice=29.99,
                Subtotal=29.99,
            ),
        ]

        # Calculate order total
        order.TotalAmount = sum(item.Subtotal for item in items)

        # Update the order with the calculated total
        order.update(database, transaction=transaction)

        # Save all items
        for item in items:
            item.save(database, transaction=transaction)

        # Return the order for use after the transaction
        return order

    try:
        # Execute the transaction function
        order = database.run_in_transaction(create_order_with_items)
        print(f"- Created order: {order.OrderID} with total ${order.TotalAmount}")

        # Verify data
        saved_order = Order.get(database, CustomerID=customer.CustomerID, OrderID=order.OrderID)
        print(f"- Verified order: Total ${saved_order.TotalAmount}")

        return customer, order

    except Exception as e:
        print(f"- Error in transaction: {e}")
        print("- All operations were rolled back")
        return customer, None


def demonstrate_transaction_rollback(database, customer):
    """Demonstrate transaction rollback when an error occurs."""
    print("\nDemonstrating transaction rollback...")

    if not customer:
        print("- Customer required for this demonstration")
        return

    # Try to create an order with an invalid item (price below 0)
    try:
        with database.transaction() as transaction:
            # Create a new order
            order = Order(CustomerID=customer.CustomerID, Status="NEW", TotalAmount=0)
            order.save(database, transaction=transaction)
            print(f"- Created order: {order.OrderID}")

            # Create a valid item
            item1 = OrderItem(
                CustomerID=customer.CustomerID,
                OrderID=order.OrderID,
                ProductName="Valid Item",
                Quantity=1,
                UnitPrice=50.00,
                Subtotal=50.00,
            )
            item1.save(database, transaction=transaction)
            print("- Added valid item")

            # This will cause a logical error - negative price
            # We'll simulate this by trying to insert a duplicate customer
            # which violates the primary key constraint
            print("- Attempting to save invalid data...")
            customer_duplicate = Customer(
                CustomerID=customer.CustomerID,  # Using the same ID will cause an error
                Name="Duplicate Customer",
                Email="duplicate@example.com",
            )
            customer_duplicate.save(database, transaction=transaction)

            # This code should not execute due to the error
            print("- This should not print if transaction is rolled back")

    except Exception as e:
        print(f"- Error occurred as expected: {e}")
        print("- Transaction was rolled back")

    # Verify the order and item were not saved
    saved_order = Order.get(database, CustomerID=customer.CustomerID, OrderID=order.OrderID)
    print(f"- Order exists: {saved_order is not None}")  # Should be False

    if saved_order is None:
        print("- Verified that no data was saved due to rollback")


def cleanup(database, customers):
    """Clean up test data."""
    print("\nCleaning up test data...")

    for customer in customers:
        if customer:
            # Due to interleaving with CASCADE delete,
            # deleting the customer should delete all related orders and items
            customer.delete(database)
            print(f"- Deleted customer: {customer.CustomerID}")


def main():
    """Main function."""
    # Parse command line arguments or use defaults for emulator
    project_id = sys.argv[1] if len(sys.argv) > 1 else "emulator-project"
    instance_id = sys.argv[2] if len(sys.argv) > 2 else "test-instance"
    database_id = sys.argv[3] if len(sys.argv) > 3 else "testdb"

    # Create Spanner client
    _, _, database = create_spanner_client(project_id, instance_id, database_id)

    # Create tables
    create_tables(database)

    # Demonstrate transactions
    customer1, order1 = demonstrate_transaction_with_context_manager(database)
    customer2, order2 = demonstrate_transaction_with_callback(database)

    # Demonstrate rollback
    demonstrate_transaction_rollback(database, customer1)

    # Clean up
    cleanup(database, [customer1, customer2])


if __name__ == "__main__":
    main()
