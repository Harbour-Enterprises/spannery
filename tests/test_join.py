"""Tests for JOIN and relationship features."""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from spannery.fields import (
    BoolField,
    ForeignKeyField,
    StringField,
    TimestampField,
)
from spannery.model import SpannerModel
from spannery.query import Query
from spannery.session import SpannerSession


# Test models for relationship and JOIN tests
class User(SpannerModel):
    """User model for testing JOIN functionality."""

    __tablename__ = "Users"

    UserID = StringField(primary_key=True, default=lambda: str(uuid.uuid4()))
    Email = StringField(nullable=False)
    FullName = StringField(nullable=False)
    Status = StringField(nullable=False, default="ACTIVE")
    CreatedAt = TimestampField(nullable=False, default=lambda: datetime.now(timezone.utc))
    Active = BoolField(nullable=False, default=True)


class Organization(SpannerModel):
    """Organization model for testing JOIN functionality."""

    __tablename__ = "Organizations"

    OrganizationID = StringField(primary_key=True, default=lambda: str(uuid.uuid4()))
    Name = StringField(nullable=False)
    Status = StringField(nullable=False, default="ACTIVE")
    CreatedAt = TimestampField(nullable=False, default=lambda: datetime.now(timezone.utc))
    Active = BoolField(nullable=False, default=True)


class OrganizationUser(SpannerModel):
    """OrganizationUser model with foreign keys for testing JOIN functionality."""

    __tablename__ = "OrganizationUsers"

    OrganizationID = ForeignKeyField("Organization", primary_key=True, related_name="users")
    UserID = ForeignKeyField("User", primary_key=True, related_name="organizations")
    Role = StringField(nullable=False)
    Status = StringField(nullable=False, default="ACTIVE")
    CreatedAt = TimestampField(nullable=False, default=lambda: datetime.now(timezone.utc))


# Test ForeignKeyField
def test_foreign_key_field_creation():
    """Test ForeignKeyField creation and properties."""
    # Basic initialization
    field = ForeignKeyField("User")
    assert field.related_model == "User"
    assert field.related_name is None
    assert field.nullable is True
    assert field.primary_key is False

    # Custom initialization
    field = ForeignKeyField(
        "Organization",
        related_name="users",
        primary_key=True,
        nullable=False,
    )
    assert field.related_model == "Organization"
    assert field.related_name == "users"
    assert field.nullable is False
    assert field.primary_key is True


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


def test_query_join_simplified():
    """Test simplified join method in Query class."""
    # Setup mock database
    mock_db = MagicMock()

    # Create a query with simplified join syntax
    query = Query(OrganizationUser, mock_db)
    result = query.join("User", on=("UserID", "UserID"))

    # Verify the join was added correctly
    assert result == query  # Should return self for chaining
    assert len(query._joins) == 1
    join_info = query._joins[0]
    assert join_info["left_field"] == "UserID"
    assert join_info["right_field"] == "UserID"
    assert join_info["type"] == "INNER"
    assert join_info["model"] == User  # Should be the actual User class since it's registered


def test_query_left_join():
    """Test left join method."""
    mock_db = MagicMock()

    with patch("spannery.utils.get_model_class") as mock_get_model_class:
        mock_org_class = MagicMock()
        mock_org_class._table_name = "Organizations"
        mock_get_model_class.return_value = mock_org_class

        query = Query(OrganizationUser, mock_db)
        result = query.left_join("Organization", on=("OrganizationID", "OrganizationID"))

        assert result == query
        assert query._joins[0]["type"] == "LEFT"


def test_build_sql_with_joins():
    """Test SQL building with JOIN clauses."""
    mock_db = MagicMock()

    with patch("spannery.utils.get_model_class") as mock_get_model_class:
        # Mock both models
        mock_user_class = MagicMock()
        mock_user_class._table_name = "Users"
        mock_org_class = MagicMock()
        mock_org_class._table_name = "Organizations"

        mock_get_model_class.side_effect = lambda name: (
            mock_user_class if name == "User" else mock_org_class
        )

        # Create query with joins
        query = (
            Query(OrganizationUser, mock_db)
            .join("User", on=("UserID", "UserID"))
            .left_join("Organization", on=("OrganizationID", "OrganizationID"))
            .filter(Status="ACTIVE")
            .order_by("CreatedAt", desc=True)
        )

        sql, params = query._build_sql()

        # Verify SQL contains JOIN clauses
        assert "FROM OrganizationUsers" in sql
        assert "INNER JOIN Users ON OrganizationUsers.UserID = Users.UserID" in sql
        assert (
            "LEFT JOIN Organizations ON OrganizationUsers.OrganizationID = Organizations.OrganizationID"
            in sql
        )
        assert "WHERE Status = @p0" in sql
        assert "ORDER BY CreatedAt DESC" in sql
        assert params["p0"] == "ACTIVE"


def test_query_with_django_style_filters():
    """Test query with Django-style filter operators."""
    mock_db = MagicMock()

    query = (
        Query(User, mock_db)
        .filter(
            Active=True,
            CreatedAt__gte="2024-01-01",
            Email__like="%@example.com",
            Status__in=["ACTIVE", "PENDING"],
        )
        .order_by("Email")
    )

    assert len(query._filters) == 4

    # Check filters were parsed correctly
    filters_dict = {f"{f[0]}__{f[1]}": f[2] for f in query._filters}
    assert filters_dict["Active__eq"] is True
    assert filters_dict["CreatedAt__gte"] == "2024-01-01"
    assert filters_dict["Email__like"] == "%@example.com"
    assert filters_dict["Status__in"] == ["ACTIVE", "PENDING"]


def test_session_join_query():
    """Test join_query convenience method in SpannerSession."""
    mock_db = MagicMock()
    session = SpannerSession(mock_db)

    with patch("spannery.session.Query") as mock_query_class:
        mock_query = MagicMock()
        mock_query_class.return_value = mock_query

        # Call join_query with simplified syntax
        session.join_query(Organization, User, "UserID", "UserID")

        # Verify the correct methods were called
        mock_query_class.assert_called_once_with(Organization, mock_db)
        mock_query.join.assert_called_once_with(User, "UserID", "UserID")


@pytest.mark.skip("Integration test requiring Spanner connection")
def test_integration_join_simplified(spanner_session):
    """Integration test for simplified JOIN operations."""
    # Create test data
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

    # Test simplified join syntax
    admin_users = (
        spanner_session.query(OrganizationUser)
        .join(User, on=("UserID", "UserID"))
        .filter(Role="ADMIN")
        .all()
    )

    assert len(admin_users) == 1
    assert admin_users[0].Role == "ADMIN"

    # Test with related data access
    admin_user = admin_users[0]
    related_user = spanner_session.get_related(admin_user, "UserID")
    assert related_user.Email == "user1@example.com"

    # Test left join - get all orgs even without users
    empty_org = Organization(Name="Empty Org")
    spanner_session.save(empty_org)

    all_orgs = (
        spanner_session.query(Organization)
        .left_join(OrganizationUser, on=("OrganizationID", "OrganizationID"))
        .all()
    )

    # Should get both orgs
    org_names = {o.Name for o in all_orgs}
    assert "Test Org A" in org_names
    assert "Empty Org" in org_names

    # Clean up
    spanner_session.delete(org_user1)
    spanner_session.delete(org_user2)
    spanner_session.delete(user1)
    spanner_session.delete(user2)
    spanner_session.delete(org)
    spanner_session.delete(empty_org)


@pytest.mark.skip("Integration test requiring Spanner connection")
def test_integration_complex_query(spanner_session):
    """Integration test for complex queries with joins and filters."""
    # Create test data
    active_org = Organization(Name="Active Org", Status="ACTIVE")
    inactive_org = Organization(Name="Inactive Org", Status="INACTIVE")
    spanner_session.save(active_org)
    spanner_session.save(inactive_org)

    user = User(Email="test@example.com", FullName="Test User")
    spanner_session.save(user)

    # Link user to active org
    org_user = OrganizationUser(
        OrganizationID=active_org.OrganizationID, UserID=user.UserID, Role="ADMIN"
    )
    spanner_session.save(org_user)

    # Complex query with join and multiple filters
    active_admin_orgs = (
        spanner_session.query(Organization)
        .join(OrganizationUser, on=("OrganizationID", "OrganizationID"))
        .join(User, on=("UserID", "UserID"))
        .filter(Status="ACTIVE", Name__like="Active%")
        .filter(Role="ADMIN")  # Filter on joined table field
        .all()
    )

    assert len(active_admin_orgs) == 1
    assert active_admin_orgs[0].Name == "Active Org"

    # Clean up
    spanner_session.delete(org_user)
    spanner_session.delete(user)
    spanner_session.delete(active_org)
    spanner_session.delete(inactive_org)
