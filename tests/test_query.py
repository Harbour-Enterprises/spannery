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
    assert query._select_fields is None

    # Select specific fields
    query = query.select("Name", "ListPrice")
    assert query._select_fields == ["Name", "ListPrice"]


def test_query_builder_filter():
    """Test query builder filter with Django-style operators."""
    mock_db = MagicMock()
    query = Query(Product, mock_db)

    # Simple equality filter
    query = query.filter(Name="Test")
    assert len(query._filters) == 1
    field, op, value = query._filters[0]
    assert field == "Name"
    assert op == "eq"
    assert value == "Test"

    # Test with operators
    query = Query(Product, mock_db)
    query = query.filter(
        Stock__lt=10,
        ListPrice__gte=100,
        Name__like="Widget%",
        Category__in=["A", "B", "C"],
        Active__ne=False,
    )
    assert len(query._filters) == 5

    # Check each filter
    filters_dict = {f[0] + "__" + f[1]: f[2] for f in query._filters}
    assert filters_dict["Stock__lt"] == 10
    assert filters_dict["ListPrice__gte"] == 100
    assert filters_dict["Name__like"] == "Widget%"
    assert filters_dict["Category__in"] == ["A", "B", "C"]
    assert filters_dict["Active__ne"] is False


def test_query_builder_advanced_filters():
    """Test advanced filter operators."""
    mock_db = MagicMock()

    # Test NOT IN
    query = Query(Product, mock_db).filter(Category__not_in=["A", "B", "C"])
    assert query._filters[0] == ("Category", "not_in", ["A", "B", "C"])

    # Test case-insensitive LIKE
    query = Query(Product, mock_db).filter(Name__ilike="%widget%")
    assert query._filters[0] == ("Name", "ilike", "%widget%")

    # Test IS NULL
    query = Query(Product, mock_db).filter(Description__is_null=True)
    assert query._filters[0] == ("Description", "is_null", True)

    # Test BETWEEN
    query = Query(Product, mock_db).filter(ListPrice__between=(10, 100))
    assert query._filters[0] == ("ListPrice", "between", (10, 100))

    # Test REGEX
    query = Query(Product, mock_db).filter(Name__regex=r"^Widget.*$")
    assert query._filters[0] == ("Name", "regex", r"^Widget.*$")


def test_query_builder_filter_or():
    """Test OR conditions."""
    mock_db = MagicMock()
    query = Query(Product, mock_db)

    # Test filter_or
    query = query.filter_or({"Name": "John"}, {"Name": "Jane"}, {"Email__like": "%@gmail.com"})

    assert len(query._filters) == 1
    field, op, conditions = query._filters[0]
    assert field == "__OR__"
    assert op == "or"
    assert len(conditions) == 3
    assert {"Name": "John"} in conditions
    assert {"Name": "Jane"} in conditions
    assert {"Email__like": "%@gmail.com"} in conditions


def test_query_builder_order_limit_offset():
    """Test query builder ordering, limit, and offset methods."""
    mock_db = MagicMock()
    query = Query(Product, mock_db)

    # Test order_by
    query = query.order_by("Name")
    assert ("Name", False) in query._order_by

    query = query.order_by("Stock", desc=True)
    assert ("Stock", True) in query._order_by

    # Test limit and offset
    query = query.limit(10)
    assert query._limit == 10

    query = query.offset(5)
    assert query._offset == 5


def test_query_spanner_features():
    """Test Spanner-specific query features."""
    mock_db = MagicMock()
    query = Query(Product, mock_db)

    # Test force index
    query = query.force_index("idx_products_category")
    assert query._force_index == "idx_products_category"

    # Test request tag
    query = query.with_request_tag("product-search")
    assert query._request_tag == "product-search"

    # Test priority
    query = query.with_priority("HIGH")
    assert query._request_priority == "HIGH"


def test_build_sql():
    """Test SQL building with new filter syntax."""
    mock_db = MagicMock()

    # Basic query
    query = Query(Product, mock_db).filter(Active=True)
    sql, params = query._build_sql()
    assert "WHERE Active = @p0" in sql
    assert params["p0"] is True

    # Query with operators
    query = Query(Product, mock_db).filter(ListPrice__gt=100, Stock__lte=10, Name__like="Widget%")
    sql, params = query._build_sql()
    assert "ListPrice > @p0" in sql
    assert "Stock <= @p1" in sql
    assert "Name LIKE @p2" in sql
    assert params["p0"] == 100
    assert params["p1"] == 10
    assert params["p2"] == "Widget%"

    # Query with BETWEEN
    query = Query(Product, mock_db).filter(ListPrice__between=(50, 150))
    sql, params = query._build_sql()
    assert "ListPrice BETWEEN @p0 AND @p1" in sql
    assert params["p0"] == 50
    assert params["p1"] == 150

    # Query with IN
    query = Query(Product, mock_db).filter(Category__in=["A", "B"])
    sql, params = query._build_sql()
    assert "Category IN (@p0, @p1)" in sql
    assert params["p0"] == "A"
    assert params["p1"] == "B"


def test_query_join():
    """Test simplified JOIN syntax."""
    mock_db = MagicMock()

    # Test basic join
    query = Query(Product, mock_db).join("Organization", on=("OrganizationID", "OrganizationID"))
    assert len(query._joins) == 1
    join = query._joins[0]
    assert join["left_field"] == "OrganizationID"
    assert join["right_field"] == "OrganizationID"
    assert join["type"] == "INNER"

    # Test left join
    query = Query(Product, mock_db).left_join("Media", on=("ProductID", "ProductID"))
    assert query._joins[0]["type"] == "LEFT"


@patch("spannery.query.Query._build_sql")
@patch("spannery.query.Query._execute")
def test_query_count(mock_execute, mock_build_sql):
    """Test query count method."""
    mock_db = MagicMock()
    query = Query(Product, mock_db)

    # Mock the SQL building and execution
    mock_build_sql.return_value = ("SELECT * FROM Products WHERE Active = @p0", {"p0": True})
    mock_result = MagicMock()
    mock_result.__iter__.return_value = [(5,)]
    mock_execute.return_value = mock_result

    result = query.filter(Active=True).count()
    assert result == 5

    # Verify count SQL was built correctly
    mock_execute.assert_called_once()
    count_sql = mock_execute.call_args[0][0]
    assert "SELECT COUNT(*)" in count_sql
    assert "FROM Products" in count_sql
    assert "WHERE" in count_sql


@patch("spannery.query.Query._build_sql")
@patch("spannery.query.Query._execute")
def test_query_all(mock_execute, mock_build_sql):
    """Test query all method."""
    mock_db = MagicMock()
    query = Query(Product, mock_db)

    # Mock SQL building
    mock_build_sql.return_value = ("SELECT * FROM Products", {})

    # Mock execution results
    mock_result = MagicMock()
    mock_field1 = MagicMock()
    mock_field1.name = "ProductID"
    mock_field2 = MagicMock()
    mock_field2.name = "Name"

    mock_result.fields = [mock_field1, mock_field2]
    mock_result.__iter__.return_value = [
        ("prod1", "Product 1"),
        ("prod2", "Product 2"),
    ]
    mock_execute.return_value = mock_result

    # Mock from_query_result
    with patch.object(Product, "from_query_result") as mock_from_query:
        product1 = Product(ProductID="prod1", Name="Product 1")
        product2 = Product(ProductID="prod2", Name="Product 2")
        mock_from_query.side_effect = [product1, product2]

        results = query.all()

        assert len(results) == 2
        assert results[0].ProductID == "prod1"
        assert results[1].ProductID == "prod2"


def test_query_first():
    """Test query first method."""
    mock_db = MagicMock()
    query = Query(Product, mock_db)

    with patch.object(query, "all") as mock_all:
        # Test when results exist
        product = Product(ProductID="prod1", Name="Product 1")
        mock_all.return_value = [product]

        result = query.first()
        assert result == product
        assert query._limit == 1  # Should set limit to 1

        # Test when no results
        mock_all.return_value = []
        result = query.first()
        assert result is None


def test_query_one():
    """Test query one method."""
    mock_db = MagicMock()
    query = Query(Product, mock_db)

    with patch.object(query, "all") as mock_all:
        # Test single result
        product = Product(ProductID="prod1", Name="Product 1")
        mock_all.return_value = [product]

        result = query.one()
        assert result == product

        # Test no results
        mock_all.return_value = []
        with pytest.raises(RecordNotFoundError):
            query.one()

        # Test multiple results
        mock_all.return_value = [product, product]
        with pytest.raises(Exception) as exc_info:
            query.one()
        assert "multiple" in str(exc_info.value).lower()


def test_query_exists():
    """Test query exists method."""
    mock_db = MagicMock()
    query = Query(Product, mock_db)

    with patch.object(query, "count") as mock_count:
        # Test when records exist
        mock_count.return_value = 5
        assert query.exists() is True

        # Test when no records
        mock_count.return_value = 0
        assert query.exists() is False


def test_query_filter_by_id():
    """Test filter_by_id convenience method."""
    mock_db = MagicMock()
    query = Query(Product, mock_db)

    # Test filter by primary keys
    query = query.filter_by_id(OrganizationID="org1", ProductID="prod1")

    assert len(query._filters) == 2
    filters_dict = {f[0]: f[2] for f in query._filters}
    assert filters_dict["OrganizationID"] == "org1"
    assert filters_dict["ProductID"] == "prod1"


def test_query_method_chaining():
    """Test that all methods support chaining."""
    mock_db = MagicMock()
    query = Query(Product, mock_db)

    # Test complex chaining
    chained = (
        query.filter(Category="Electronics", Active=True)
        .filter(ListPrice__between=(50, 200))
        .filter_or({"Stock__gt": 0}, {"OnOrder": True})
        .order_by("ListPrice")
        .order_by("Name", desc=True)
        .limit(10)
        .offset(20)
        .force_index("idx_category")
        .with_request_tag("search")
        .with_priority("HIGH")
    )

    # Verify all settings were applied
    assert chained is query  # Same instance
    assert len(query._filters) == 3
    assert len(query._order_by) == 2
    assert query._limit == 10
    assert query._offset == 20
    assert query._force_index == "idx_category"
    assert query._request_tag == "search"
    assert query._request_priority == "HIGH"
