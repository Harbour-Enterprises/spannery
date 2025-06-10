"""Tests for transaction support in SpannerModel."""

import uuid
from unittest.mock import MagicMock

import pytest
from conftest import Organization, Product

from spannery.fields import StringField, TimestampField
from spannery.model import SpannerModel

# ... (keep existing tests) ...


def test_transaction_with_commit_timestamp():
    """Test transaction with commit timestamp fields."""
    from google.cloud.spanner_v1 import COMMIT_TIMESTAMP

    class Event(SpannerModel):
        __tablename__ = "Events"

        event_id = StringField(primary_key=True)
        name = StringField()
        occurred_at = TimestampField(allow_commit_timestamp=True)

    mock_db = MagicMock()
    mock_transaction = MagicMock()

    # Create event - the timestamp should use commit timestamp
    event = Event(event_id="evt-123", name="Test Event", occurred_at="COMMIT_TIMESTAMP")
    event.save(mock_db, transaction=mock_transaction)

    # Verify the commit timestamp was passed
    call_args = mock_transaction.insert.call_args
    values = call_args[1]["values"][0]
    columns = call_args[1]["columns"]

    # Find occurred_at position
    occurred_at_idx = columns.index("occurred_at")
    assert values[occurred_at_idx] == COMMIT_TIMESTAMP


def test_transaction_with_request_tag():
    """Test using transactions with request tags via session."""
    from spannery.session import SpannerSession

    mock_db = MagicMock()
    mock_batch = MagicMock()
    mock_db.batch.return_value.__enter__.return_value = mock_batch

    session = SpannerSession(mock_db)

    # Use transaction with request tag
    with session.transaction(request_tag="bulk-import") as txn:
        assert txn == mock_batch

    # Verify request options were passed
    call_args = mock_db.batch.call_args
    assert "request_options" in call_args[1]
    assert call_args[1]["request_options"].request_tag == "bulk-import"


@pytest.mark.skip("Integration test requiring Spanner connection")
def test_transaction_with_multiple_models(spanner_session):
    """Test transaction with multiple different model types."""
    # Create unique IDs
    org_id = f"org-{uuid.uuid4()}"
    user_id = f"user-{uuid.uuid4()}"

    from spannery.fields import BoolField

    # Create a User model for this test
    class User(SpannerModel):
        __tablename__ = "Users"

        UserID = StringField(primary_key=True)
        Email = StringField()
        Active = BoolField(default=True)

    # Create instances
    org = Organization(OrganizationID=org_id, Name="Multi-Model Org")
    user = User(UserID=user_id, Email="test@example.com")
    product = Product(OrganizationID=org_id, Name="Multi-Model Product", ListPrice=99.99)

    database = spanner_session.database

    # Save all in one transaction
    with database.transaction() as txn:
        org.save(database, transaction=txn)
        user.save(database, transaction=txn)
        product.save(database, transaction=txn)

    # Verify all were saved
    assert Organization.get(database, OrganizationID=org_id) is not None
    assert User.get(database, UserID=user_id) is not None
    assert Product.get(database, OrganizationID=org_id, ProductID=product.ProductID) is not None

    # Clean up in transaction
    with database.transaction() as txn:
        product.delete(database, transaction=txn)
        user.delete(database, transaction=txn)
        org.delete(database, transaction=txn)

    # Verify all deleted
    assert Organization.get(database, OrganizationID=org_id) is None
    assert User.get(database, UserID=user_id) is None


@pytest.mark.skip("Integration test requiring Spanner connection")
def test_transaction_read_only(spanner_session):
    """Test read-only transactions for consistent reads."""
    # Create test data
    org = Organization(Name="Read-Only Test Org")
    spanner_session.save(org)

    products = []
    for i in range(3):
        product = Product(
            OrganizationID=org.OrganizationID,
            Name=f"Product {i}",
            ListPrice=50.0 * (i + 1),
            Stock=10 * (i + 1),
        )
        spanner_session.save(product)
        products.append(product)

    # Use read-only transaction for consistent reads
    with spanner_session.read_only_transaction() as ro_txn:
        # All reads see the same snapshot
        org_check = ro_txn.query(Organization).filter(OrganizationID=org.OrganizationID).first()

        product_count = ro_txn.query(Product).filter(OrganizationID=org.OrganizationID).count()

        expensive_products = (
            ro_txn.query(Product)
            .filter(OrganizationID=org.OrganizationID, ListPrice__gte=100)
            .all()
        )

        # Verify consistent results
        assert org_check is not None
        assert product_count == 3
        assert len(expensive_products) == 2

    # Clean up
    for product in products:
        spanner_session.delete(product)
    spanner_session.delete(org)
