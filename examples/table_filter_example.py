"""
Example demonstrating the table_filter feature for JOIN queries.

This example shows how to query data from multiple tables using JOIN operations
and filter on columns from different tables in the same query.
"""

import uuid
from datetime import datetime, timezone

from google.cloud import spanner

from spannery.fields import (
    BooleanField,
    DateTimeField,
    ForeignKeyField,
    IntField,
    StringField,
)
from spannery.model import SpannerModel
from spannery.session import SpannerSession


# Define models for our example
class Organization(SpannerModel):
    """Organization model."""

    __tablename__ = "Organizations"

    OrganizationID = StringField(primary_key=True, default=lambda: str(uuid.uuid4()))
    Name = StringField(max_length=255, nullable=False)
    Status = StringField(max_length=20, nullable=False, default="ACTIVE")
    CreatedAt = DateTimeField(nullable=False, default=lambda: datetime.now(timezone.utc))
    Active = BooleanField(nullable=False, default=True)


class Product(SpannerModel):
    """Product model."""

    __tablename__ = "Products"
    __interleave_in__ = "Organizations"
    __on_delete__ = "CASCADE"

    OrganizationID = ForeignKeyField(
        "Organization", primary_key=True, nullable=False, related_name="products"
    )
    ProductID = StringField(primary_key=True, default=lambda: str(uuid.uuid4()))
    Name = StringField(max_length=255, nullable=False)
    Description = StringField(max_length=1000)
    Category = StringField(max_length=100)
    Stock = IntField(default=0)
    CreatedAt = DateTimeField(nullable=False, auto_now_add=True)
    UpdatedAt = DateTimeField(nullable=True, auto_now=True)
    Active = BooleanField(nullable=False, default=True)
    ListPrice = StringField(max_length=20, nullable=False)
    CostPrice = StringField(max_length=20)


class Media(SpannerModel):
    """Media model."""

    __tablename__ = "Media"
    __interleave_in__ = "Organizations"
    __on_delete__ = "NO ACTION"

    OrganizationID = ForeignKeyField(
        "Organization", primary_key=True, nullable=False, related_name="media"
    )
    MediaID = StringField(primary_key=True, default=lambda: str(uuid.uuid4()))
    StoragePath = StringField(max_length=500, nullable=False)
    BucketName = StringField(max_length=500, nullable=False)
    CreatedAt = DateTimeField(nullable=False, auto_now_add=True)
    CreatedBy = StringField(nullable=True)
    Active = BooleanField(nullable=False, default=True)
    MimeType = StringField(max_length=100, nullable=False)
    Filename = StringField(max_length=255, nullable=False)
    FileSize = IntField(nullable=True)
    Status = StringField(max_length=100, nullable=True)
    UpdatedAt = DateTimeField(nullable=True, auto_now=True)
    UpdatedBy = StringField(nullable=True)


class ProductMedia(SpannerModel):
    """ProductMedia model."""

    __tablename__ = "ProductMedia"
    __interleave_in__ = "Products"
    __on_delete__ = "CASCADE"

    OrganizationID = ForeignKeyField(
        "Organization",
        primary_key=True,
        nullable=False,
        related_name="product_media_orgs",
    )
    ProductID = ForeignKeyField(
        "Product", primary_key=True, nullable=False, related_name="media_links"
    )
    MediaID = ForeignKeyField(
        "Media", primary_key=True, nullable=False, related_name="product_links"
    )
    DisplayOrder = IntField(nullable=False)
    IsPrimary = BooleanField(nullable=False, default=False)
    CreatedAt = DateTimeField(nullable=False, auto_now_add=True)


def main():
    """Run the example."""
    # Initialize Spanner client and database
    client = spanner.Client()
    instance = client.instance("spanner-example-instance")
    database = instance.database("example-database")

    # Create a session
    session = SpannerSession(database)

    # Create example data
    org = Organization(Name="Example Organization")
    session.save(org)

    # Create a product
    product = Product(
        OrganizationID=org.OrganizationID,
        Name="Example Product",
        Category="Electronics",
        ListPrice="99.99",
        Stock=10,
    )
    session.save(product)

    # Create media
    media1 = Media(
        OrganizationID=org.OrganizationID,
        StoragePath="products/image1.jpg",
        BucketName="example-bucket",
        MimeType="image/jpeg",
        Filename="image1.jpg",
    )
    media2 = Media(
        OrganizationID=org.OrganizationID,
        StoragePath="products/image2.jpg",
        BucketName="example-bucket",
        MimeType="image/jpeg",
        Filename="image2.jpg",
    )
    session.save(media1)
    session.save(media2)

    # Link media to product
    product_media1 = ProductMedia(
        OrganizationID=org.OrganizationID,
        ProductID=product.ProductID,
        MediaID=media1.MediaID,
        DisplayOrder=1,
        IsPrimary=True,
    )
    product_media2 = ProductMedia(
        OrganizationID=org.OrganizationID,
        ProductID=product.ProductID,
        MediaID=media2.MediaID,
        DisplayOrder=2,
        IsPrimary=False,
    )
    session.save(product_media1)
    session.save(product_media2)

    # Example 1: Find all media for a specific product using JOIN and table_filter
    print("Finding media for a specific product...")
    query = session.query(Media)
    query = query.join(ProductMedia, "MediaID", "MediaID")
    query = query.table_filter("ProductMedia", ProductID=product.ProductID)
    results = query.all()

    print(f"Found {len(results)} media items for product {product.Name}")
    for media in results:
        print(f"  - {media.Filename} ({media.MimeType})")

    # Example 2: Find primary media for a product
    print("\nFinding primary media for the product...")
    query = session.query(Media)
    query = query.join(ProductMedia, "MediaID", "MediaID")
    query = query.table_filter("ProductMedia", ProductID=product.ProductID, IsPrimary=True)
    results = query.all()

    print(f"Found {len(results)} primary media items")
    for media in results:
        print(f"  - {media.Filename}")

    # Example 3: More complex query with multiple joins and filters
    print("\nFinding products with primary media in JPEG format...")
    query = session.query(Product)
    query = query.join(ProductMedia, "ProductID", "ProductID")
    query = query.join(Media, "MediaID", "MediaID")

    # Filter on joined table
    query = query.table_filter("ProductMedia", IsPrimary=True)
    # Filter on another joined table
    query = query.table_filter("Media", MimeType="image/jpeg")
    # Filter on base table
    query = query.filter(Category="Electronics")

    results = query.all()

    print(f"Found {len(results)} electronics products with primary JPEG media")
    for product in results:
        print(f"  - {product.Name} (ID: {product.ProductID})")


if __name__ == "__main__":
    main()
