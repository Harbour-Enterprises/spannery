#!/usr/bin/env python
"""
Simple CRUD example for Spannery.

This example demonstrates how to:
1. Define models
2. Connect to a Spanner database
3. Create tables
4. Perform CRUD operations
5. Use the query builder

Usage:
    python simple_crud.py [project_id] [instance_id] [database_id]

If no arguments are provided, it will use emulator settings.
"""

import os
import sys
import uuid

from google.cloud import spanner

from spannery.fields import (
    BooleanField,
    DateTimeField,
    IntegerField,
    NumericField,
    StringField,
)
from spannery.model import SpannerModel, SpannerSession


# Define models
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

    # Use the model's create_table method
    try:
        Organization.create_table(database)
        print("- Organizations table created")
    except Exception as e:
        print(f"- Error creating Organizations table: {e}")

    try:
        Product.create_table(database)
        print("- Products table created")
    except Exception as e:
        print(f"- Error creating Products table: {e}")


def create_data(session):
    """Create sample data in the database."""
    print("\nCreating sample data...")

    # Create an organization
    organization = Organization(Name="Acme Corporation")
    session.save(organization)
    print(f"- Created organization: {organization.Name} (ID: {organization.OrganizationID})")

    # Create products
    products = [
        Product(
            OrganizationID=organization.OrganizationID,
            Name="Super Widget",
            Description="Our flagship widget",
            Category="Widgets",
            Stock=100,
            ListPrice=99.99,
            CostPrice=49.99,
        ),
        Product(
            OrganizationID=organization.OrganizationID,
            Name="Mini Widget",
            Description="A smaller version of our widget",
            Category="Widgets",
            Stock=150,
            ListPrice=59.99,
            CostPrice=29.99,
        ),
        Product(
            OrganizationID=organization.OrganizationID,
            Name="Widget Pro",
            Description="Professional grade widget",
            Category="Widgets",
            Stock=50,
            ListPrice=199.99,
            CostPrice=99.99,
        ),
        Product(
            OrganizationID=organization.OrganizationID,
            Name="Widget Accessory",
            Description="An add-on for any widget",
            Category="Accessories",
            Stock=200,
            ListPrice=19.99,
            CostPrice=5.99,
        ),
    ]

    for product in products:
        session.save(product)
        print(f"- Created product: {product.Name} (ID: {product.ProductID})")

    return organization, products


def demonstrate_queries(session, organization):
    """Demonstrate various query operations."""
    print("\nDemonstrating queries...")

    # Count all products
    count = session.query(Product).filter(OrganizationID=organization.OrganizationID).count()
    print(f"- Total products: {count}")

    # Get products in "Widgets" category
    widgets = (
        session.query(Product)
        .filter(OrganizationID=organization.OrganizationID, Category="Widgets")
        .all()
    )
    print(f"- Widget products: {len(widgets)}")
    for widget in widgets:
        print(f"  * {widget.Name} - ${widget.ListPrice}")

    # Get products with price greater than 100
    expensive_products = (
        session.query(Product)
        .filter(OrganizationID=organization.OrganizationID)
        .filter_gte(ListPrice=100)
        .order_by("ListPrice", desc=True)
        .all()
    )

    print(f"- Expensive products (price >= $100): {len(expensive_products)}")
    for product in expensive_products:
        print(f"  * {product.Name} - ${product.ListPrice}")

    # Get products with low stock
    low_stock = (
        session.query(Product)
        .filter(OrganizationID=organization.OrganizationID)
        .filter_lt(Stock=100)
        .all()
    )

    print(f"- Low stock products (< 100 units): {len(low_stock)}")
    for product in low_stock:
        print(f"  * {product.Name} - {product.Stock} units")

    # Select specific fields
    names_only = (
        session.query(Product)
        .filter(OrganizationID=organization.OrganizationID)
        .select("Name", "Category")
        .all()
    )

    print("- Product names and categories:")
    for product in names_only:
        print(f"  * {product.Name} ({product.Category})")


def demonstrate_crud(session, organization, products):
    """Demonstrate CRUD operations."""
    print("\nDemonstrating CRUD operations...")

    # Get a product for operations
    product = products[0]
    print(f"- Selected product: {product.Name} (ID: {product.ProductID})")

    # Read operation - get by primary key
    retrieved_product = session.get(
        Product, OrganizationID=organization.OrganizationID, ProductID=product.ProductID
    )
    print(f"- Retrieved product: {retrieved_product.Name}")

    # Update operation
    original_stock = retrieved_product.Stock
    original_price = retrieved_product.ListPrice

    retrieved_product.Stock = original_stock + 50
    retrieved_product.ListPrice = original_price * 1.1  # 10% price increase

    session.update(retrieved_product)
    print(f"- Updated product stock from {original_stock} to {retrieved_product.Stock}")
    print(f"- Updated product price from ${original_price} to ${retrieved_product.ListPrice}")

    # Verify the update
    updated_product = session.get(
        Product, OrganizationID=organization.OrganizationID, ProductID=product.ProductID
    )
    print(f"- Verified updated stock: {updated_product.Stock}")
    print(f"- Verified updated price: ${updated_product.ListPrice}")

    # Create operation - add a new product
    new_product = Product(
        OrganizationID=organization.OrganizationID,
        Name="New Widget X",
        Description="Our newest innovation",
        Category="Widgets",
        Stock=10,
        ListPrice=299.99,
        CostPrice=149.99,
    )
    session.save(new_product)
    print(f"- Created new product: {new_product.Name} (ID: {new_product.ProductID})")

    # Delete operation
    session.delete(new_product)
    print(f"- Deleted product: {new_product.Name}")

    # Verify deletion
    deleted_product = session.get(
        Product,
        OrganizationID=organization.OrganizationID,
        ProductID=new_product.ProductID,
    )

    if deleted_product is None:
        print("- Verified deletion: Product no longer exists")
    else:
        print("- Warning: Product still exists after deletion")


def demonstrate_transactions(session, organization):
    """Demonstrate transaction usage."""
    print("\nDemonstrating transactions...")

    # Create multiple products in a transaction
    with session.transaction() as batch:
        # Generate IDs in advance
        product_id1 = str(uuid.uuid4())
        product_id2 = str(uuid.uuid4())

        # Insert first product
        batch.insert(
            "Products",
            columns=[
                "OrganizationID",
                "ProductID",
                "Name",
                "Description",
                "Category",
                "Stock",
                "Active",
                "ListPrice",
                "CostPrice",
            ],
            values=[
                [
                    organization.OrganizationID,
                    product_id1,
                    "Transaction Widget A",
                    "Created in a transaction",
                    "Widgets",
                    10,
                    True,
                    49.99,
                    24.99,
                ]
            ],
        )

        # Insert second product
        batch.insert(
            "Products",
            columns=[
                "OrganizationID",
                "ProductID",
                "Name",
                "Description",
                "Category",
                "Stock",
                "Active",
                "ListPrice",
                "CostPrice",
            ],
            values=[
                [
                    organization.OrganizationID,
                    product_id2,
                    "Transaction Widget B",
                    "Also created in a transaction",
                    "Widgets",
                    20,
                    True,
                    59.99,
                    29.99,
                ]
            ],
        )

    print("- Created two products in a single transaction")

    # Verify the products were created
    products = (
        session.query(Product)
        .filter(OrganizationID=organization.OrganizationID)
        .filter_in(ProductID=[product_id1, product_id2])
        .all()
    )

    print(f"- Verified transaction: Retrieved {len(products)} products")
    for product in products:
        print(f"  * {product.Name} (ID: {product.ProductID})")


def main():
    """Run the example."""
    # Get Spanner connection parameters
    if len(sys.argv) >= 4:
        project_id = sys.argv[1]
        instance_id = sys.argv[2]
        database_id = sys.argv[3]
    else:
        # Default to emulator settings
        project_id = "emulator-project"
        instance_id = "emulator-instance"
        database_id = "emulator-db"
        os.environ["SPANNER_EMULATOR_HOST"] = "localhost:9010"

    print("Connecting to Spanner database:")
    print(f"- Project: {project_id}")
    print(f"- Instance: {instance_id}")
    print(f"- Database: {database_id}")

    # Create Spanner client
    client, instance, database = create_spanner_client(project_id, instance_id, database_id)

    # Create a session
    session = SpannerSession(database)

    # Create tables
    create_tables(database)

    # Create sample data
    organization, products = create_data(session)

    # Demonstrate queries
    demonstrate_queries(session, organization)

    # Demonstrate CRUD operations
    demonstrate_crud(session, organization, products)

    # Demonstrate transactions
    demonstrate_transactions(session, organization)

    print("\nExample completed successfully!")


if __name__ == "__main__":
    main()
