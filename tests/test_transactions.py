"""Tests for transaction support in SpannerModel."""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from conftest import Organization, Product

from spannery.exceptions import ModelDefinitionError


@patch("google.cloud.spanner_v1.database.Database")
def test_save_with_transaction(mock_db):
    """Test saving a model with a transaction."""
    # Create mock transaction
    mock_transaction = MagicMock()

    # Create a test product
    product = Product(
        OrganizationID="test-org-id",
        Name="Test Product",
        ListPrice=99.99,
    )

    # Call save with transaction
    product.save(mock_db, transaction=mock_transaction)

    # Verify transaction.insert was called with the right parameters
    mock_transaction.insert.assert_called_once()
    call_args = mock_transaction.insert.call_args
    assert call_args[1]["table"] == "Products"
    assert "OrganizationID" in call_args[1]["columns"]
    assert "ProductID" in call_args[1]["columns"]
    assert "Name" in call_args[1]["columns"]
    assert len(call_args[1]["values"]) == 1  # One row of values


@patch("google.cloud.spanner_v1.database.Database")
def test_update_with_transaction(mock_db):
    """Test updating a model with a transaction."""
    # Create mock transaction
    mock_transaction = MagicMock()

    # Create a test product
    product = Product(
        OrganizationID="test-org-id",
        ProductID="test-product-id",
        Name="Test Product",
        ListPrice=99.99,
    )

    # Update product name
    product.Name = "Updated Product"

    # Call update with transaction
    product.update(mock_db, transaction=mock_transaction)

    # Verify transaction.update was called with the right parameters
    mock_transaction.update.assert_called_once()
    call_args = mock_transaction.update.call_args
    assert call_args[1]["table"] == "Products"
    assert "Name" in call_args[1]["columns"]
    assert len(call_args[1]["values"]) == 1  # One row of values


@patch("google.cloud.spanner_v1.database.Database")
def test_delete_with_transaction(mock_db):
    """Test deleting a model with a transaction."""
    # Create mock transaction
    mock_transaction = MagicMock()

    # Create a test product
    product = Product(
        OrganizationID="test-org-id",
        ProductID="test-product-id",
        Name="Test Product",
    )

    # Call delete with transaction
    product.delete(mock_db, transaction=mock_transaction)

    # Verify transaction.delete was called with the right parameters
    mock_transaction.delete.assert_called_once()
    call_args = mock_transaction.delete.call_args
    assert call_args[1]["table"] == "Products"
    assert "keyset" in call_args[1]


@patch("google.cloud.spanner_v1.database.Database")
def test_multiple_operations_with_transaction(mock_db):
    """Test multiple operations in a single transaction."""
    # Create mock transaction
    mock_transaction = MagicMock()

    # Create test organization and product
    org = Organization(
        OrganizationID="test-org-id",
        Name="Test Organization",
    )

    product1 = Product(
        OrganizationID="test-org-id",
        ProductID="product-1",
        Name="Product 1",
        ListPrice=99.99,
    )

    product2 = Product(
        OrganizationID="test-org-id",
        ProductID="product-2",
        Name="Product 2",
        ListPrice=199.99,
    )

    # Execute multiple operations with the same transaction
    org.save(mock_db, transaction=mock_transaction)
    product1.save(mock_db, transaction=mock_transaction)
    product2.save(mock_db, transaction=mock_transaction)

    # Verify transaction.insert was called three times
    assert mock_transaction.insert.call_count == 3


@pytest.mark.skip("Integration test requiring Spanner connection")
def test_transaction_with_database(spanner_session):
    """Integration test for transaction operations with a real database."""
    # Create unique IDs for this test
    org_id = f"org-{uuid.uuid4()}"
    product_id = f"product-{uuid.uuid4()}"

    # Create test models
    org = Organization(
        OrganizationID=org_id,
        Name="Transaction Test Organization",
    )

    product = Product(
        OrganizationID=org_id,
        ProductID=product_id,
        Name="Transaction Test Product",
        ListPrice=99.99,
    )

    # Get the database from the session
    database = spanner_session._database

    # Run operations in a transaction
    with database.transaction() as transaction:
        org.save(database, transaction=transaction)
        product.save(database, transaction=transaction)

    # Verify both records were saved
    retrieved_org = Organization.get(database, OrganizationID=org_id)
    retrieved_product = Product.get(database, OrganizationID=org_id, ProductID=product_id)

    assert retrieved_org is not None
    assert retrieved_org.OrganizationID == org_id

    assert retrieved_product is not None
    assert retrieved_product.ProductID == product_id

    # Clean up: delete in a transaction
    with database.transaction() as transaction:
        product.delete(database, transaction=transaction)
        org.delete(database, transaction=transaction)

    # Verify deletion
    assert Organization.get(database, OrganizationID=org_id) is None
    assert Product.get(database, OrganizationID=org_id, ProductID=product_id) is None


@pytest.mark.skip("Integration test requiring Spanner connection")
def test_transaction_rollback(spanner_session):
    """Test transaction rollback when an error occurs."""
    # Create unique IDs for this test
    org_id = f"org-{uuid.uuid4()}"
    product_id = f"product-{uuid.uuid4()}"

    # Create test models
    org = Organization(
        OrganizationID=org_id,
        Name="Rollback Test Organization",
    )

    product = Product(
        OrganizationID=org_id,
        ProductID=product_id,
        Name="Rollback Test Product",
        ListPrice=99.99,
    )

    # Get the database from the session
    database = spanner_session._database

    # First save the organization outside the transaction
    org.save(database)

    # Try to perform operations in a transaction, but cause an error
    try:
        with database.transaction() as transaction:
            # This should work
            product.save(database, transaction=transaction)

            # This will cause an error - trying to insert a duplicate organization
            org.save(database, transaction=transaction)
    except Exception:
        # Expected exception, transaction should be rolled back
        pass

    # Verify organization exists (it was saved outside the transaction)
    retrieved_org = Organization.get(database, OrganizationID=org_id)
    assert retrieved_org is not None

    # Verify product was NOT saved due to transaction rollback
    retrieved_product = Product.get(database, OrganizationID=org_id, ProductID=product_id)
    assert retrieved_product is None

    # Clean up: delete the organization
    org.delete(database)
