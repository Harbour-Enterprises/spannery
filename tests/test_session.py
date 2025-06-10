"""Tests for SpannerSession."""

from unittest.mock import MagicMock, patch

import pytest
from conftest import Product

from spannery.session import SpannerSession


@patch("google.cloud.spanner_v1.database.Database")
def test_session_save_insert(mock_db):
    """Test session save method with insert operation."""
    # Create a session with a mock database
    session = SpannerSession(mock_db)

    # Create a new product to save
    product = Product(
        OrganizationID="test-org",
        Name="Test Session Product",
        ListPrice=99.99,
    )

    # Mock the product.save method
    with patch.object(Product, "save") as mock_save:
        mock_save.return_value = product

        # Save the product
        result = session.save(product)

        # Verify product.save was called with the database and None for transaction
        mock_save.assert_called_once_with(mock_db, None)

        # Verify product ID was generated
        assert product.ProductID is not None

        # Verify the result is the product
        assert result is product


@patch("google.cloud.spanner_v1.database.Database")
def test_session_update(mock_db):
    """Test session update method."""
    # Create a session with a mock database
    session = SpannerSession(mock_db)

    # Create a product to update
    product = Product(
        OrganizationID="test-org",
        ProductID="test-product",
        Name="Original Name",
        Stock=10,
        ListPrice=99.99,
    )

    # Modify product attributes
    product.Name = "Updated Test Product"
    product.Stock = 50

    # Mock the product.update method
    with patch.object(Product, "update") as mock_update:
        mock_update.return_value = product

        # Update the product
        result = session.update(product)

        # Verify product.update was called with the database and None for transaction
        mock_update.assert_called_once_with(mock_db, None)

        # Verify the result is the product
        assert result is product


@patch("google.cloud.spanner_v1.database.Database")
def test_session_delete(mock_db):
    """Test session delete method."""
    # Create a session with a mock database
    session = SpannerSession(mock_db)

    # Create a product to delete
    product = Product(
        OrganizationID="test-org",
        ProductID="test-product",
        Name="Test Product",
        ListPrice=99.99,
    )

    # Mock the product.delete method
    with patch.object(Product, "delete") as mock_delete:
        mock_delete.return_value = True

        # Delete the product
        result = session.delete(product)

        # Verify product.delete was called with the database and None for transaction
        mock_delete.assert_called_once_with(mock_db, None)

        # Verify the result is True
        assert result is True


def test_session_query():
    """Test session query method."""
    # Create a mock database
    mock_db = MagicMock()

    # Create a session with the mock database
    session = SpannerSession(mock_db)

    # Mock the Query class with patch.object and autospec
    with patch("spannery.session.Query", autospec=True) as MockQuery:
        # Mock the Query initialization
        mock_query_instance = MagicMock()
        MockQuery.return_value = mock_query_instance

        # Call the query method
        result = session.query(Product)

        # Verify Query was initialized with the correct arguments
        MockQuery.assert_called_once_with(Product, mock_db)

        # Verify the result is the mock query instance
        assert result == mock_query_instance


@patch("google.cloud.spanner_v1.database.Database")
def test_session_get(mock_db):
    """Test session get method."""
    # Create a session with a mock database
    session = SpannerSession(mock_db)

    # Mock the model.get method
    with patch.object(Product, "get") as mock_get:
        # Create a mock product to return
        product = Product(
            OrganizationID="test-org",
            ProductID="test-product",
            Name="Test Product",
            ListPrice=99.99,
        )
        mock_get.return_value = product

        # Call the get method
        result = session.get(Product, OrganizationID="test-org", ProductID="test-product")

        # Verify model.get was called with the correct arguments
        mock_get.assert_called_once_with(
            mock_db, OrganizationID="test-org", ProductID="test-product"
        )

        # Verify the result is the mock product
        assert result == product


@patch("google.cloud.spanner_v1.database.Database")
def test_session_get_or_404(mock_db):
    """Test session get_or_404 method."""
    # Create a session with a mock database
    session = SpannerSession(mock_db)

    # Mock the model.get_or_404 method
    with patch.object(Product, "get_or_404") as mock_get_or_404:
        # Create a mock product to return
        product = Product(
            OrganizationID="test-org",
            ProductID="test-product",
            Name="Test Product",
            ListPrice=99.99,
        )
        mock_get_or_404.return_value = product

        # Call the get_or_404 method
        result = session.get_or_404(Product, OrganizationID="test-org", ProductID="test-product")

        # Verify model.get_or_404 was called with the correct arguments
        mock_get_or_404.assert_called_once_with(
            mock_db, OrganizationID="test-org", ProductID="test-product"
        )

        # Verify the result is the mock product
        assert result == product


@patch("google.cloud.spanner_v1.database.Database")
def test_session_refresh(mock_db):
    """Test session refresh method."""
    # Create a session with a mock database
    session = SpannerSession(mock_db)

    # Create a product to refresh
    product = Product(
        OrganizationID="test-org",
        ProductID="test-product",
        Name="Original Name",
        Stock=10,
        ListPrice=99.99,
    )

    # Mock the model.get method to return an updated product
    with patch.object(Product, "get") as mock_get:
        updated_product = Product(
            OrganizationID="test-org",
            ProductID="test-product",
            Name="Refreshed Product",
            Stock=100,
            ListPrice=99.99,
        )
        mock_get.return_value = updated_product

        # Refresh the product
        session.refresh(product)

        # Verify model.get was called with the correct arguments
        mock_get.assert_called_once_with(
            mock_db, OrganizationID="test-org", ProductID="test-product"
        )

        # Verify the product was updated with the refreshed values
        assert product.Name == "Refreshed Product"
        assert product.Stock == 100


@patch("google.cloud.spanner_v1.database.Database")
def test_session_exists(mock_db):
    """Test session exists method."""
    # Create a session with a mock database
    session = SpannerSession(mock_db)

    # Set up mock query chain
    mock_query = MagicMock()
    mock_filter = MagicMock()
    mock_limit = MagicMock()

    mock_query.filter.return_value = mock_filter
    mock_filter.limit.return_value = mock_limit
    mock_limit.count.return_value = 1

    # Mock the session.query method
    with patch.object(session, "query", return_value=mock_query):
        # Call the exists method
        exists = session.exists(Product, OrganizationID="test-org", ProductID="test-product")

        # Verify query was called with Product
        session.query.assert_called_once_with(Product)

        # Verify filter was called with the correct arguments
        mock_query.filter.assert_called_once_with(
            OrganizationID="test-org", ProductID="test-product"
        )

        # Verify limit was called with 1
        mock_filter.limit.assert_called_once_with(1)

        # Verify count was called
        mock_limit.count.assert_called_once()

        # Verify the result is True
        assert exists is True


@patch("google.cloud.spanner_v1.database.Database")
def test_session_all(mock_db):
    """Test session all method."""
    # Create a session with a mock database
    session = SpannerSession(mock_db)

    # Create mock products to return
    products = [
        Product(OrganizationID="test-org", ProductID=f"prod{i}", Name=f"Product {i}")
        for i in range(4)
    ]

    # Mock the model.all method
    with patch.object(Product, "all", return_value=products) as mock_all:
        # Call the all method
        all_products = session.all(Product)

        # Verify model.all was called with the database
        mock_all.assert_called_once_with(mock_db)

        # Verify the result has the expected products
        assert all_products == products
        assert len(all_products) == 4


@patch("google.cloud.spanner_v1.database.Database")
def test_session_get_or_create(mock_db):
    """Test session get_or_create method."""
    # Create a session with a mock database
    session = SpannerSession(mock_db)

    # Case 1: Object doesn't exist
    # Create a product instance first that will be returned by the mocked save
    test_product = Product(
        OrganizationID="test-org",
        ProductID="new-product",
        Name="Get Or Create Product",
        ListPrice=99.99,
    )

    with patch.object(Product, "get", return_value=None) as mock_get:
        with patch.object(Product, "save", return_value=test_product) as mock_save:
            # Call get_or_create for a non-existent product
            product, created = session.get_or_create(
                Product,
                OrganizationID="test-org",
                ProductID="new-product",
                defaults={"Name": "Get Or Create Product", "ListPrice": 99.99},
            )

            # Verify get was called with the correct arguments
            mock_get.assert_called_once_with(
                mock_db, OrganizationID="test-org", ProductID="new-product"
            )

            # Verify save was called (with any Product instance)
            mock_save.assert_called_once()

            # Verify the product attributes
            assert product.OrganizationID == "test-org"
            assert product.ProductID == "new-product"
            assert product.Name == "Get Or Create Product"
            assert product.ListPrice == 99.99
            assert created is True

    # Case 2: Object exists
    existing_product = Product(
        OrganizationID="test-org",
        ProductID="existing-product",
        Name="Existing Product",
        ListPrice=199.99,
    )

    with patch.object(Product, "get", return_value=existing_product) as mock_get:
        with patch.object(Product, "save") as mock_save:
            # Call get_or_create for an existing product
            product, created = session.get_or_create(
                Product,
                OrganizationID="test-org",
                ProductID="existing-product",
                defaults={"Name": "Different Name", "ListPrice": 99.99},
            )

            # Verify get was called with the correct arguments
            mock_get.assert_called_once_with(
                mock_db, OrganizationID="test-org", ProductID="existing-product"
            )

            # Verify save was not called
            mock_save.assert_not_called()

            # Verify the product is the existing one
            assert product == existing_product
            assert product.Name == "Existing Product"  # Name should not change
            assert product.ListPrice == 199.99  # ListPrice should not change
            assert created is False


def test_execute_sql():
    """Test execute_sql method."""
    # Create a mock database
    mock_db = MagicMock()

    # Create a session with the mock database
    session = SpannerSession(mock_db)

    # Create a mock for the snapshot context
    mock_snapshot = MagicMock()
    mock_db.snapshot.return_value.__enter__.return_value = mock_snapshot

    # Create a mock result
    mock_result = MagicMock()
    mock_snapshot.execute_sql.return_value = mock_result

    # Call execute_sql
    sql = "SELECT COUNT(*) FROM Products"
    result = session.execute_sql(sql)

    # Verify snapshot.execute_sql was called with the correct arguments
    mock_snapshot.execute_sql.assert_called_once_with(sql, params=None, param_types=None)

    # Verify the result is the mock result
    assert result == mock_result


def test_execute_update():
    """Test execute_update method."""
    # Create a mock database
    mock_db = MagicMock()

    # Create a session with the mock database
    session = SpannerSession(mock_db)

    # Mock the database.batch method for the transaction context manager
    mock_txn = MagicMock()
    mock_txn.execute_update.return_value = 1
    mock_db.batch.return_value.__enter__.return_value = mock_txn

    # Call execute_update
    sql = "UPDATE Products SET Stock = 0 WHERE OrganizationID = @org_id"
    params = {"org_id": "test-org"}
    param_types = {"org_id": "STRING"}

    result = session.execute_update(sql, params, param_types)

    # Verify txn.execute_update was called with the correct arguments
    mock_txn.execute_update.assert_called_once_with(sql, params=params, param_types=param_types)

    # Verify the result is 1
    assert result == 1


def test_transaction_context_manager():
    """Test transaction as context manager."""
    # Create a mock database
    mock_db = MagicMock()

    # Create a session with the mock database
    session = SpannerSession(mock_db)

    # Mock the database.batch method
    mock_batch = MagicMock()
    mock_db.batch.return_value.__enter__.return_value = mock_batch

    # Use the transaction context manager
    with session.transaction() as batch:
        # Insert a new product
        batch.insert(
            "Products",
            columns=["OrganizationID", "ProductID", "Name"],
            values=[["test-org", "test-product", "Transaction Test Product"]],
        )

    # Verify batch.insert was called
    mock_batch.insert.assert_called_once()


# Skip integration tests that require Spanner
@pytest.mark.skip("Integration test requiring Spanner connection")
def test_session_save_insert_integration(spanner_session, test_organization):
    """Integration test for session save method with insert operation."""
    product = Product(
        OrganizationID=test_organization.OrganizationID,
        Name="Test Session Product",
        ListPrice=99.99,
    )

    # Save the product
    spanner_session.save(product)

    # Product ID should have been generated
    assert product.ProductID is not None

    # Verify product was saved
    saved_product = spanner_session.get(
        Product,
        OrganizationID=test_organization.OrganizationID,
        ProductID=product.ProductID,
    )

    assert saved_product is not None
    assert saved_product.Name == "Test Session Product"


@pytest.mark.skip("Integration test requiring Spanner connection")
def test_session_update_integration(spanner_session, test_organization, test_product):
    """Integration test for session update method."""
    # Modify product attributes
    test_product.Name = "Updated Test Product"
    test_product.Stock = 50

    # Update the product
    spanner_session.update(test_product)

    # Verify product was updated
    updated_product = spanner_session.get(
        Product,
        OrganizationID=test_organization.OrganizationID,
        ProductID=test_product.ProductID,
    )

    assert updated_product is not None
    assert updated_product.Name == "Updated Test Product"
    assert updated_product.Stock == 50
