"""Tests for SpannerSession."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from conftest import Product

from spannery.exceptions import ConnectionError, TransactionError
from spannery.session import SpannerSession

# ... (keep existing basic CRUD tests) ...


def test_session_save_with_request_tag():
    """Test save with request tag."""
    mock_db = MagicMock()
    session = SpannerSession(mock_db)

    product = Product(
        OrganizationID="test-org",
        Name="Test Product",
        ListPrice=99.99,
    )

    # Mock the batch context manager
    mock_batch = MagicMock()
    mock_db.batch.return_value.__enter__.return_value = mock_batch

    # Save with request tag
    with patch.object(Product, "save", return_value=product):
        session.save(product, request_tag="product-import")

        # Verify request options were created
        mock_db.batch.assert_called_once()
        call_args = mock_db.batch.call_args
        assert "request_options" in call_args[1]
        assert call_args[1]["request_options"].request_tag == "product-import"


def test_session_transaction_with_request_tag():
    """Test transaction with request tag."""
    mock_db = MagicMock()
    session = SpannerSession(mock_db)

    mock_batch = MagicMock()
    mock_db.batch.return_value.__enter__.return_value = mock_batch

    # Use transaction with request tag
    with session.transaction(request_tag="batch-update") as txn:
        assert txn == mock_batch

    # Verify request options were passed
    call_args = mock_db.batch.call_args
    assert "request_options" in call_args[1]
    assert call_args[1]["request_options"].request_tag == "batch-update"


def test_session_read_only_transaction():
    """Test read-only transaction context manager."""
    mock_db = MagicMock()
    session = SpannerSession(mock_db)

    # Mock snapshot
    mock_snapshot = MagicMock()
    mock_db.snapshot.return_value.__enter__.return_value = mock_snapshot

    # Use read-only transaction
    with session.read_only_transaction() as ro_txn:
        # Should provide query method
        assert hasattr(ro_txn, "query")
        assert hasattr(ro_txn, "execute_sql")

        # Test query within transaction
        query = ro_txn.query(Product)
        assert query._snapshot == mock_snapshot

    # Verify multi-use snapshot was created
    mock_db.snapshot.assert_called_once_with(
        multi_use=True, read_timestamp=None, exact_staleness=None
    )


def test_session_read_only_transaction_with_staleness():
    """Test read-only transaction with exact staleness."""
    mock_db = MagicMock()
    session = SpannerSession(mock_db)

    mock_snapshot = MagicMock()
    mock_db.snapshot.return_value.__enter__.return_value = mock_snapshot

    staleness = timedelta(seconds=15)

    with session.read_only_transaction(exact_staleness=staleness) as ro_txn:
        # Execute SQL within transaction
        ro_txn.execute_sql("SELECT * FROM Products")

        # Verify SQL was executed on snapshot
        mock_snapshot.execute_sql.assert_called_once()

    # Verify staleness was passed
    mock_db.snapshot.assert_called_once_with(
        multi_use=True, read_timestamp=None, exact_staleness=staleness
    )


def test_session_snapshot():
    """Test snapshot context manager."""
    mock_db = MagicMock()
    session = SpannerSession(mock_db)

    mock_snapshot = MagicMock()
    mock_db.snapshot.return_value.__enter__.return_value = mock_snapshot

    # Test basic snapshot
    with session.snapshot() as snapshot:
        assert snapshot == mock_snapshot

    # Test snapshot with options
    with session.snapshot(multi_use=True, exact_staleness=timedelta(seconds=10)) as snapshot:
        pass

    # Verify options were passed
    calls = mock_db.snapshot.call_args_list
    assert calls[1][1]["multi_use"] is True
    assert calls[1][1]["exact_staleness"] == timedelta(seconds=10)


def test_session_execute_sql_with_request_tag():
    """Test execute_sql with request tag."""
    mock_db = MagicMock()
    session = SpannerSession(mock_db)

    mock_snapshot = MagicMock()
    mock_db.snapshot.return_value.__enter__.return_value = mock_snapshot
    mock_snapshot.execute_sql.return_value = []

    # Execute with request tag
    session.execute_sql(
        "SELECT * FROM Products WHERE Category = @cat",
        params={"cat": "Electronics"},
        request_tag="category-search",
    )

    # Verify request options were passed
    mock_snapshot.execute_sql.assert_called_once()
    call_args = mock_snapshot.execute_sql.call_args
    assert "request_options" in call_args[1]
    assert call_args[1]["request_options"].request_tag == "category-search"


def test_session_error_handling():
    """Test proper error handling and exception types."""
    mock_db = MagicMock()
    session = SpannerSession(mock_db)

    # Test transaction error
    with patch.object(Product, "save", side_effect=Exception("DB error")):
        product = Product(Name="Test")

        with pytest.raises(TransactionError) as exc_info:
            session.save(product)

        assert "Error saving Product" in str(exc_info.value)
        assert "DB error" in str(exc_info.value)

    # Test snapshot error
    mock_db.snapshot.side_effect = Exception("Connection failed")

    with pytest.raises(ConnectionError) as exc_info:
        with session.snapshot():
            pass

    assert "Snapshot failed" in str(exc_info.value)


def test_session_query_integration():
    """Test that session.query returns properly configured Query."""
    mock_db = MagicMock()
    session = SpannerSession(mock_db)

    # Test query creation
    query = session.query(Product)

    assert query.model_class == Product
    assert query.database == mock_db

    # Test chaining
    filtered = query.filter(Active=True).limit(10)
    assert filtered is query  # Same instance


# Integration tests (keep existing ones, just update filter syntax)
@pytest.mark.skip("Integration test requiring Spanner connection")
def test_session_integration(spanner_session, test_organization):
    """Integration test for session with new features."""
    # Test query with new filter syntax
    spanner_session.query(Product).filter(OrganizationID=test_organization.OrganizationID).all()
    spanner_session.query(Product).filter(
        OrganizationID=test_organization.OrganizationID,
        Stock__gte=10,
        ListPrice__between=(50, 150),
    ).order_by("ListPrice").all()

    # Test with request tag
    product = Product(
        OrganizationID=test_organization.OrganizationID, Name="Tagged Product", ListPrice=99.99
    )
    spanner_session.save(product, request_tag="integration-test")

    # Test read-only transaction
    with spanner_session.read_only_transaction() as ro_txn:
        # Multiple consistent reads
        ro_txn.query(Product).filter(OrganizationID=test_organization.OrganizationID).all()

        specific_product = ro_txn.query(Product).filter(ProductID=product.ProductID).first()

        assert specific_product is not None
        assert specific_product.Name == "Tagged Product"
