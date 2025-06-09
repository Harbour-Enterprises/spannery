"""Tests for JOIN and relationship features."""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from spannery.fields import (
    BooleanField,
    DateTimeField,
    ForeignKeyField,
    StringField,
)
from spannery.model import SpannerModel
from spannery.query import JoinType, Query
from spannery.session import SpannerSession
from spannery.utils import get_model_class, register_model


# Test models for relationship and JOIN tests
class User(SpannerModel):
    """User model for testing JOIN functionality."""

    __tablename__ = "Users"

    UserID = StringField(primary_key=True, default=lambda: str(uuid.uuid4()))
    Email = StringField(max_length=255, nullable=False)
    FullName = StringField(max_length=255, nullable=False)
    Status = StringField(max_length=20, nullable=False, default="ACTIVE")
    CreatedAt = DateTimeField(nullable=False, default=lambda: datetime.now(timezone.utc))
    Active = BooleanField(nullable=False, default=True)


class Organization(SpannerModel):
    """Organization model for testing JOIN functionality."""

    __tablename__ = "Organizations"

    OrganizationID = StringField(primary_key=True, default=lambda: str(uuid.uuid4()))
    Name = StringField(max_length=255, nullable=False)
    Status = StringField(max_length=20, nullable=False, default="ACTIVE")
    CreatedAt = DateTimeField(nullable=False, default=lambda: datetime.now(timezone.utc))
    Active = BooleanField(nullable=False, default=True)


class OrganizationUser(SpannerModel):
    """OrganizationUser model with foreign keys for testing JOIN functionality."""

    __tablename__ = "OrganizationUsers"

    OrganizationID = ForeignKeyField("Organization", primary_key=True, related_name="users")
    UserID = ForeignKeyField("User", primary_key=True, related_name="organizations")
    Role = StringField(max_length=20, nullable=False)
    Status = StringField(max_length=20, nullable=False, default="ACTIVE")
    CreatedAt = DateTimeField(nullable=False, default=lambda: datetime.now(timezone.utc))


# Test ForeignKeyField
def test_foreign_key_field_creation():
    """Test ForeignKeyField creation and properties."""
    # Basic initialization
    field = ForeignKeyField("User")
    assert field.related_model == "User"
    assert field.related_name is None
    assert field.cascade_delete is False
    assert field.nullable is True
    assert field.primary_key is False

    # Custom initialization
    field = ForeignKeyField(
        "Organization",
        related_name="users",
        cascade_delete=True,
        primary_key=True,
        nullable=False,
    )
    assert field.related_model == "Organization"
    assert field.related_name == "users"
    assert field.cascade_delete is True
    assert field.nullable is False
    assert field.primary_key is True

    # Check Spanner type
    assert field.get_spanner_type() == "STRING(36)"


def test_foreign_key_to_db_value():
    """Test ForeignKeyField's to_db_value method."""
    field = ForeignKeyField("User")

    # None value
    assert field.to_db_value(None) is None

    # String value
    assert field.to_db_value("test-id") == "test-id"

    # Model instance value
    user = User(UserID="user-123", Email="test@example.com", FullName="Test User")
    assert field.to_db_value(user) == "user-123"


def test_model_relationships_processing():
    """Test relationship processing in models."""
    # Create model instances for testing
    org = Organization(Name="Test Org")
    user = User(Email="test@example.com", FullName="Test User")
    org_user = OrganizationUser(OrganizationID=org.OrganizationID, UserID=user.UserID, Role="ADMIN")

    # Check relationships processing
    OrganizationUser._process_relationships()
    relationships = OrganizationUser.__relationships__

    assert "OrganizationID" in relationships
    assert "UserID" in relationships
    assert relationships["OrganizationID"]["related_model"] == "Organization"
    assert relationships["UserID"]["related_model"] == "User"
    assert relationships["OrganizationID"]["related_name"] == "users"
    assert relationships["UserID"]["related_name"] == "organizations"


@patch("spannery.utils.get_model_class")
def test_get_related(mock_get_model_class):
    """Test get_related method."""
    # Setup mock database and related model class
    mock_db = MagicMock()

    # Mock Organization class with get method
    mock_org_class = MagicMock()
    mock_org_class._fields = {"OrganizationID": MagicMock(primary_key=True)}
    mock_org = MagicMock()
    mock_org_class.get.return_value = mock_org

    # Setup mock get_model_class to return our mock Organization class
    mock_get_model_class.return_value = mock_org_class

    # Create test OrganizationUser instance
    org_user = OrganizationUser(OrganizationID="org-123", UserID="user-123", Role="ADMIN")

    # Test get_related method
    result = org_user.get_related("OrganizationID", mock_db)

    # Verify the method worked correctly
    assert result == mock_org
    mock_get_model_class.assert_called_once_with("Organization")
    mock_org_class.get.assert_called_once_with(mock_db, **{"OrganizationID": "org-123"})


def test_join_type_constants():
    """Test JoinType constants."""
    assert JoinType.INNER == "INNER JOIN"
    assert JoinType.LEFT == "LEFT JOIN"
    assert JoinType.RIGHT == "RIGHT JOIN"
    assert JoinType.FULL == "FULL JOIN"


@patch("spannery.utils.get_model_class")
def test_query_join(mock_get_model_class):
    """Test join method in Query class."""
    # Setup mock database and related model class
    mock_db = MagicMock()

    # Mock User class
    mock_user_class = MagicMock()
    mock_user_class._table_name = "Users"

    # Setup mock get_model_class to return our mock User class
    mock_get_model_class.return_value = mock_user_class

    # Create a query for OrganizationUser with a join to User
    query = Query(OrganizationUser, mock_db)
    result = query.join("User", "UserID", "UserID", join_type=JoinType.INNER)

    # Verify the join was added correctly
    assert result == query  # Should return self for chaining
    assert len(query.join_clauses) == 1
    assert "INNER JOIN Users AS t1 ON t0.UserID = t1.UserID" in query.join_clauses
    assert query.table_aliases["Users"] == "t1"

    # Check the joined_models dictionary
    assert len(query.joined_models) == 1
    # We can't check for the exact mock since it won't be equal, just verify there is an entry


def test_table_filter():
    """Test the table_filter method in Query class."""
    # Setup mock database
    mock_db = MagicMock()

    # Create a query for Organization
    query = Query(Organization, mock_db)

    # Apply table_filter for a specific table
    result = query.table_filter("OrganizationUsers", Role="ADMIN")

    # Verify the filter was added correctly
    assert result == query  # Should return self for chaining
    assert len(query.filters) == 1

    filter_field, filter_op, filter_value = query.filters[0]
    assert filter_field == "OrganizationUsers.Role"
    assert filter_op == "="
    assert filter_value == "ADMIN"

    # Test with multiple filters
    query = Query(Organization, mock_db)
    query.table_filter("Products", Active=True, Stock=10)

    assert len(query.filters) == 2
    assert any(f[0] == "Products.Active" for f in query.filters)
    assert any(f[0] == "Products.Stock" for f in query.filters)


@patch("spannery.utils.get_model_class")
def test_build_query_with_table_filter(mock_get_model_class):
    """Test _build_query method with table_filter."""
    # Setup mocks
    mock_db = MagicMock()

    # Mock related model class
    mock_product_class = MagicMock()
    mock_product_class._table_name = "Products"
    mock_get_model_class.return_value = mock_product_class

    # Create a query with a join and table filter
    query = Query(Organization, mock_db)

    # Mock the join method to avoid calling the actual join method which uses get_model_class
    with patch.object(query, "join") as mock_join:
        # Make mock_join return the query itself for chaining
        mock_join.return_value = query

        # Manually add a join clause to simulate the join
        query.join_clauses.append(
            "INNER JOIN Products AS t1 ON Organizations.OrganizationID = t1.OrganizationID"
        )

        # Apply the table filter
        query.table_filter("Products", ProductID="test-123")

        # Build query
        sql, params, param_types = query._build_query()

        # Verify SQL
        assert "FROM Organizations" in sql
        assert "INNER JOIN Products" in sql
        assert "WHERE Products.ProductID = @param_0" in sql

        # Verify parameters
        assert "param_0" in params
        assert params["param_0"] == "test-123"


def test_session_join_query():
    """Test join_query convenience method in SpannerSession."""
    # Setup mocks
    mock_db = MagicMock()

    # Create a session
    session = SpannerSession(mock_db)

    # Patch both Query creation and join call
    with patch("spannery.session.Query") as mock_query_class:
        mock_query = MagicMock()
        mock_query_class.return_value = mock_query

        # Call join_query
        result = session.join_query(Organization, User, "OrganizationID", "UserID")

        # Verify the correct methods were called
        mock_query_class.assert_called_once_with(Organization, mock_db)
        mock_query.join.assert_called_once_with(User, "OrganizationID", "UserID")


def test_query_multiple_joins():
    """Test multiple joins in a single query."""
    # Setup mocks
    mock_db = MagicMock()

    # Create a query with multiple joins
    query = Query(OrganizationUser, mock_db)

    # Mock the joined model classes
    with patch("spannery.utils.get_model_class") as mock_get_model_class:
        # Mock User class
        mock_user_class = MagicMock()
        mock_user_class._table_name = "Users"

        # Mock Organization class
        mock_org_class = MagicMock()
        mock_org_class._table_name = "Organizations"

        # Setup return values for the mock
        mock_get_model_class.side_effect = lambda model: (
            mock_user_class if model == "User" else mock_org_class
        )

        # Add joins
        query = query.join("User", "UserID", "UserID", join_type=JoinType.INNER)
        query = query.join(
            "Organization", "OrganizationID", "OrganizationID", join_type=JoinType.LEFT
        )

    # Verify the joins were added correctly
    assert len(query.join_clauses) == 2
    assert "INNER JOIN Users AS t1 ON t0.UserID = t1.UserID" in query.join_clauses
    assert (
        "LEFT JOIN Organizations AS t2 ON t0.OrganizationID = t2.OrganizationID"
        in query.join_clauses
    )


def test_build_query_with_joins():
    """Test SQL generation with JOIN clauses."""
    # Create a query with joins
    mock_db = MagicMock()
    query = Query(OrganizationUser, mock_db)

    # Add the join through a patched get_model_class
    with patch("spannery.utils.get_model_class") as mock_get_model_class:
        # Mock User class
        mock_user_class = MagicMock()
        mock_user_class._table_name = "Users"

        # Setup return values
        mock_get_model_class.return_value = mock_user_class

        # Add join and filters
        query = query.join("User", "UserID", "UserID")

    # Add filter and ordering after join is set up
    query = query.filter(Status="ACTIVE")
    query = query.order_by("CreatedAt", desc=True)

    # Mock _build_query to avoid actually calling it
    orig_build_query = query._build_query
    with patch.object(query, "_build_query", wraps=orig_build_query) as mock_build:
        sql, params, param_types = query._build_query()

    # Verify SQL generation includes JOIN and WHERE
    assert "FROM OrganizationUsers AS t0" in sql
    assert "INNER JOIN Users" in sql
    assert "WHERE t0.Status = @param_0" in sql


@pytest.mark.skip("Integration test requiring Spanner connection")
def test_integration_join(spanner_session):
    """Integration test for JOIN operations."""
    # First create test data
    org = Organization(Name="Test Org A")
    spanner_session.save(org)

    user1 = User(Email="user1@example.com", FullName="User One")
    user2 = User(Email="user2@example.com", FullName="User Two")
    spanner_session.save(user1)
    spanner_session.save(user2)

    org_user1 = OrganizationUser(
        OrganizationID=org.OrganizationID, UserID=user1.UserID, Role="ADMIN"
    )
    org_user2 = OrganizationUser(
        OrganizationID=org.OrganizationID, UserID=user2.UserID, Role="MEMBER"
    )
    spanner_session.save(org_user1)
    spanner_session.save(org_user2)

    # Create and execute a JOIN query
    query = spanner_session.query(Organization)
    joined_query = query.join(
        OrganizationUser, "OrganizationID", "OrganizationID", join_type=JoinType.INNER
    )
    results = joined_query.all()

    # Verify results
    assert len(results) >= 1
    assert any(r.OrganizationID == org.OrganizationID for r in results)

    # Test a query with multiple joins
    double_joined_query = (
        query.join(
            OrganizationUser,
            "OrganizationID",
            "OrganizationID",
            join_type=JoinType.INNER,
        )
        .join(User, "UserID", "UserID", join_type=JoinType.INNER)
        .filter(Name="Test Org A")
    )
    results = double_joined_query.all()

    # Verify results
    assert len(results) >= 1
    assert any(r.OrganizationID == org.OrganizationID for r in results)


@pytest.mark.skip("Integration test requiring Spanner connection")
def test_integration_table_filter(spanner_session):
    """Integration test for table_filter feature with JOIN operations."""
    # First create test data
    org = Organization(Name="Test Org B - Table Filter")
    spanner_session.save(org)

    user1 = User(Email="tablefilter1@example.com", FullName="Table Filter User One")
    user2 = User(Email="tablefilter2@example.com", FullName="Table Filter User Two")
    spanner_session.save(user1)
    spanner_session.save(user2)

    org_user1 = OrganizationUser(
        OrganizationID=org.OrganizationID, UserID=user1.UserID, Role="ADMIN"
    )
    org_user2 = OrganizationUser(
        OrganizationID=org.OrganizationID, UserID=user2.UserID, Role="MEMBER"
    )
    spanner_session.save(org_user1)
    spanner_session.save(org_user2)

    # Create a join query with table_filter
    query = spanner_session.query(Organization)
    query = query.join(
        OrganizationUser, "OrganizationID", "OrganizationID", join_type=JoinType.INNER
    )

    # Filter on the joined table
    query = query.table_filter("OrganizationUsers", Role="ADMIN")
    results = query.all()

    # Verify results - should only get the organization with admin users
    assert len(results) >= 1
    assert any(r.OrganizationID == org.OrganizationID for r in results)

    # Try another filter that should return no results
    query = spanner_session.query(Organization)
    query = query.join(
        OrganizationUser, "OrganizationID", "OrganizationID", join_type=JoinType.INNER
    )
    query = query.table_filter("OrganizationUsers", Role="NONEXISTENT_ROLE")
    results = query.all()

    # Should return no results
    assert len(results) == 0

    # Test with multiple joins and filters
    query = spanner_session.query(User)
    query = query.join(OrganizationUser, "UserID", "UserID", join_type=JoinType.INNER).join(
        Organization, "OrganizationID", "OrganizationID", join_type=JoinType.INNER
    )

    # Filter on multiple tables
    query = query.filter(Email="tablefilter1@example.com")  # Filter on base table
    query = query.table_filter(
        "Organizations", Name="Test Org B - Table Filter"
    )  # Filter on joined table
    results = query.all()

    # Should return only User One
    assert len(results) == 1
    assert results[0].UserID == user1.UserID
    assert results[0].Email == "tablefilter1@example.com"


def test_filter_with_table_aliases():
    """Test filtering with table aliases to ensure it works correctly."""
    # Setup mock database
    mock_db = MagicMock()
    mock_snapshot = MagicMock()
    mock_result = MagicMock()

    # Setup mock snapshot and results
    mock_db.snapshot.return_value.__enter__.return_value = mock_snapshot
    mock_snapshot.execute_sql.return_value = mock_result

    # Set up fields and row data
    mock_column1 = MagicMock()
    mock_column1.name = "UserID"
    mock_column2 = MagicMock()
    mock_column2.name = "Email"
    mock_column3 = MagicMock()
    mock_column3.name = "FullName"

    # Mock the results.fields attribute
    mock_result.fields = [mock_column1, mock_column2, mock_column3]

    # Mock a row result
    mock_row = ["user-123", "test@example.com", "Test User"]
    mock_result.__iter__.return_value = [mock_row]

    # Create a query with filter
    query = Query(User, mock_db)
    query = query.filter(Email="test@example.com", Active=True)

    # Execute the query
    results = query.all()

    # Verify the query was built correctly
    mock_snapshot.execute_sql.assert_called_once()
    call_args = mock_snapshot.execute_sql.call_args[0]
    sql = call_args[0]

    # Check that the SQL contains the table alias for the filter conditions
    assert "t0.Email = @param_" in sql
    assert "t0.Active = @param_" in sql

    # Check that we got the expected results
    assert len(results) == 1
    assert results[0].Email == "test@example.com"


def test_empty_results_handling():
    """Test handling of empty query results."""
    # Setup mock database
    mock_db = MagicMock()
    mock_snapshot = MagicMock()
    mock_result = MagicMock()

    # Setup mock snapshot and results
    mock_db.snapshot.return_value.__enter__.return_value = mock_snapshot
    mock_snapshot.execute_sql.return_value = mock_result

    # Mock empty results - no fields attribute
    mock_result.fields = None
    mock_result.__iter__.return_value = []

    # Create a query with filter
    query = Query(User, mock_db)
    query = query.filter(Email="nonexistent@example.com")

    # Execute the query - this should not raise an exception
    results = query.all()

    # Check that we got empty results
    assert len(results) == 0

    # Test the first() method with empty results
    result = query.first()
    assert result is None


def test_to_dict_list_results_handling():
    """Test handling of results with to_dict_list method."""
    # Setup mock database
    mock_db = MagicMock()
    mock_snapshot = MagicMock()
    mock_result = MagicMock()

    # Setup mock snapshot and results
    mock_db.snapshot.return_value.__enter__.return_value = mock_snapshot
    mock_snapshot.execute_sql.return_value = mock_result

    # Set fields to None to force the code to use to_dict_list path
    mock_result.fields = None

    # Mock the to_dict_list method to return a list of dictionaries
    mock_result.to_dict_list.return_value = [
        {
            "UserID": "user-123",
            "Email": "test@example.com",
            "FullName": "Test User",
            "Active": True,
        }
    ]

    # Create a query
    query = Query(User, mock_db)

    # Execute the query
    results = query.all()

    # Verify to_dict_list was called
    mock_result.to_dict_list.assert_called_once()

    # Check that we got the expected results
    assert len(results) == 1
    assert results[0].UserID == "user-123"
    assert results[0].Email == "test@example.com"
    assert results[0].FullName == "Test User"
    assert results[0].Active is True
