"""Tests for Query builder."""

from unittest.mock import MagicMock, patch

import pytest
from conftest import Product

from spannery.exceptions import RecordNotFoundError
from spannery.query import Query


def test_query_builder_select():
    """Test query builder select method."""
    mock_db = MagicMock()
    query = Query(Product, mock_db)

    # Default select (all fields)
    assert query.select_fields is None

    # Select specific fields
    query = query.select("Name", "ListPrice")
    assert query.select_fields == ["Name", "ListPrice"]


def test_query_builder_filter():
    """Test query builder filter methods."""
    mock_db = MagicMock()
    query = Query(Product, mock_db)

    # Simple equality filter
    query = query.filter(Name="Test")
    assert len(query.filters) == 1
    field, op, value = query.filters[0]
    assert field == "Name"
    assert op == "="
    assert value == "Test"

    # Add another filter
    query = query.filter(Active=True)
    assert len(query.filters) == 2

    # Test comparison operators
    query = Query(Product, mock_db)
    query = query.filter_lt(Stock=10)
    assert query.filters[0][1] == "<"

    query = Query(Product, mock_db)
    query = query.filter_lte(Stock=10)
    assert query.filters[0][1] == "<="

    query = Query(Product, mock_db)
    query = query.filter_gt(Stock=10)
    assert query.filters[0][1] == ">"

    query = Query(Product, mock_db)
    query = query.filter_gte(Stock=10)
    assert query.filters[0][1] == ">="

    query = Query(Product, mock_db)
    query = query.filter_in("Category", ["A", "B", "C"])
    assert query.filters[0][1] == "IN"

    query = Query(Product, mock_db)
    query = query.filter_not(Active=True)
    assert query.filters[0][1] == "!="


def test_query_builder_order_limit_offset():
    """Test query builder ordering, limit, and offset methods."""
    mock_db = MagicMock()
    query = Query(Product, mock_db)

    # Test order_by
    query = query.order_by("Name")
    assert "Name ASC" in query.order_by_clauses

    query = query.order_by("Stock", desc=True)
    assert "Stock DESC" in query.order_by_clauses

    # Test limit and offset
    query = query.limit(10)
    assert query.limit_value == 10

    query = query.offset(5)
    assert query.offset_value == 5


@patch("spannery.query.Query._build_query")
def test_query_count(mock_build_query):
    """Test query count method."""
    mock_db = MagicMock()
    query = Query(Product, mock_db)

    # Mock the database snapshot and result
    mock_snapshot = MagicMock()
    mock_db.snapshot.return_value.__enter__.return_value = mock_snapshot
    mock_result = MagicMock()
    mock_snapshot.execute_sql.return_value = mock_result
    mock_result.__iter__.return_value = [(5,)]

    # Mock _build_query
    mock_build_query.return_value = ("SELECT * FROM Products", {}, {})

    result = query.count()
    assert result == 5
    mock_snapshot.execute_sql.assert_called_once()


@patch("spannery.query.Query._build_query")
def test_query_all(mock_build_query):
    """Test query all method."""
    mock_db = MagicMock()
    query = Query(Product, mock_db)

    # Mock _build_query
    mock_build_query.return_value = ("SELECT * FROM Products", {}, {})

    # Mock the database snapshot and result
    mock_snapshot = MagicMock()
    mock_db.snapshot.return_value.__enter__.return_value = mock_snapshot
    mock_result = MagicMock()
    mock_snapshot.execute_sql.return_value = mock_result

    # Mock returned rows
    mock_result.__iter__.return_value = [
        ("org1", "prod1", "Product 1", None, None, 10, None, None, True, 99.99, 49.99),
        ("org1", "prod2", "Product 2", None, None, 20, None, None, True, 199.99, 99.99),
    ]

    # Mock from_query_result to return product instances
    with patch.object(Product, "from_query_result") as mock_from_query:
        product1 = Product(OrganizationID="org1", ProductID="prod1", Name="Product 1")
        product2 = Product(OrganizationID="org1", ProductID="prod2", Name="Product 2")
        mock_from_query.side_effect = [product1, product2]

        result = query.all()

        assert len(result) == 2
        assert result[0] == product1
        assert result[1] == product2


@patch("spannery.query.Query.all")
def test_query_first(mock_all):
    """Test query first method."""
    mock_db = MagicMock()
    query = Query(Product, mock_db)

    # Test when results exist
    product = Product(OrganizationID="org1", ProductID="prod1", Name="Product 1")
    mock_all.return_value = [product]

    result = query.first()
    assert result == product
    mock_all.assert_called_once()

    # Test when no results
    mock_all.return_value = []
    result = query.first()
    assert result is None


@patch("spannery.query.Query.first")
def test_query_first_or_404(mock_first):
    """Test query first_or_404 method."""
    mock_db = MagicMock()
    query = Query(Product, mock_db)

    # Test when result exists
    product = Product(OrganizationID="org1", ProductID="prod1", Name="Product 1")
    mock_first.return_value = product

    result = query.first_or_404()
    assert result == product

    # Test when no result exists
    mock_first.return_value = None

    with pytest.raises(RecordNotFoundError):
        query.first_or_404()


@pytest.mark.skip("Integration test requiring Spanner connection")
def test_query_integration(spanner_session, test_organization, test_product):
    """Integration test for query operations."""
    # Create additional test products
    for i in range(5):
        product = Product(
            OrganizationID=test_organization.OrganizationID,
            Name=f"Test Product {i}",
            Stock=i * 10,
            ListPrice=99.99 + i,
            CostPrice=49.99 + i,
            Active=True,
        )
        spanner_session.save(product)

    # Test basic filtering
    query = spanner_session.query(Product)
    query = query.filter(OrganizationID=test_organization.OrganizationID)

    # Test count
    count = query.count()
    assert count >= 6  # 5 new + at least 1 from fixture

    # Test ordering and limit
    ordered_query = query.order_by("Stock", desc=True).limit(3)
    results = ordered_query.all()

    assert len(results) == 3
    assert results[0].Stock >= results[1].Stock
    assert results[1].Stock >= results[2].Stock

    # Test field selection
    name_only_query = query.select("Name").order_by("Name")
    results = name_only_query.all()

    for product in results:
        assert hasattr(product, "Name")
        assert product.Name is not None
        # Other fields should have default values
        assert not hasattr(product, "Description") or product.Description is None

    # Test comparison operators
    high_stock_query = query.filter_gte(Stock=30)
    high_stock_products = high_stock_query.all()

    for product in high_stock_products:
        assert product.Stock >= 30
