"""Tests for SpannerModel."""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from conftest import Organization, Product

from spannery.exceptions import RecordNotFoundError
from spannery.fields import Int64Field, StringField, TimestampField
from spannery.model import SpannerModel


def test_model_initialization():
    """Test that models can be properly initialized."""
    # Test with default values
    product = Product(
        OrganizationID="test-org-id",
        Name="Test Product",
        ListPrice=99.99,
    )

    assert product.OrganizationID == "test-org-id"
    assert product.Name == "Test Product"
    assert product.ListPrice == 99.99
    assert product.Stock == 0  # Default value
    assert product.Active is True  # Default value
    assert product.ProductID is not None  # Generated UUID

    # Test with provided values
    product_id = str(uuid.uuid4())
    product = Product(
        OrganizationID="test-org-id",
        ProductID=product_id,
        Name="Test Product",
        Stock=10,
        Active=False,
        ListPrice=99.99,
    )

    assert product.ProductID == product_id
    assert product.Stock == 10
    assert product.Active is False


def test_model_repr():
    """Test the string representation of models."""
    product_id = str(uuid.uuid4())
    org_id = str(uuid.uuid4())

    product = Product(
        OrganizationID=org_id,
        ProductID=product_id,
        Name="Test Product",
        ListPrice=99.99,
    )

    repr_str = repr(product)
    assert "Product" in repr_str
    assert f"OrganizationID={org_id}" in repr_str
    assert f"ProductID={product_id}" in repr_str


def test_model_fields():
    """Test that model fields are properly registered."""
    assert set(Organization._fields.keys()) == {
        "OrganizationID",
        "Name",
        "Active",
        "CreatedAt",
    }

    assert set(Product._fields.keys()) == {
        "OrganizationID",
        "ProductID",
        "Name",
        "Description",
        "Category",
        "Stock",
        "CreatedAt",
        "UpdatedAt",
        "Active",
        "ListPrice",
        "CostPrice",
    }

    # Test primary keys
    primary_keys = [name for name, field in Product._fields.items() if field.primary_key]
    assert set(primary_keys) == {"OrganizationID", "ProductID"}


def test_get_primary_key_values():
    """Test the _get_primary_key_values method."""
    product = Product(
        OrganizationID="org-123", ProductID="prod-456", Name="Test Product", ListPrice=99.99
    )

    pk_values = product._get_primary_key_values()
    assert pk_values == {"OrganizationID": "org-123", "ProductID": "prod-456"}


def test_model_equality():
    """Test model equality comparison."""
    org1 = Organization(OrganizationID="test-org", Name="Test Organization")
    org2 = Organization(OrganizationID="test-org", Name="Test Organization")
    org3 = Organization(OrganizationID="other-org", Name="Other Organization")

    assert org1 == org2
    assert org1 != org3
    assert org1 != "not a model"


def test_model_to_dict():
    """Test model to dictionary conversion."""
    org = Organization(
        OrganizationID="test-org",
        Name="Test Organization",
        Active=True,
    )

    data = org.to_dict()
    assert isinstance(data, dict)
    assert data["OrganizationID"] == "test-org"
    assert data["Name"] == "Test Organization"
    assert data["Active"] is True


def test_model_from_dict():
    """Test model creation from dictionary."""
    data = {
        "OrganizationID": "test-org",
        "Name": "Test Organization",
        "Active": True,
    }

    org = Organization.from_dict(data)
    assert org.OrganizationID == "test-org"
    assert org.Name == "Test Organization"
    assert org.Active is True


def test_model_metadata():
    """Test model metadata."""
    assert Organization._table_name == "Organizations"
    assert "OrganizationID" in Organization._fields
    assert isinstance(Organization._fields["OrganizationID"], StringField)
    assert Organization._fields["OrganizationID"].primary_key is True

    assert Product._table_name == "Products"
    assert Product.__interleave_in__ == "Organizations"
    assert isinstance(Product._fields["Stock"], Int64Field)


def test_commit_timestamp_fields():
    """Test models with commit timestamp fields."""
    from spannery.fields import StringField

    class Event(SpannerModel):
        __tablename__ = "Events"

        event_id = StringField(primary_key=True)
        name = StringField()
        created_at = TimestampField(allow_commit_timestamp=True)
        updated_at = TimestampField(allow_commit_timestamp=True)

    # Create event
    event = Event(event_id="evt-123", name="Test Event")

    # Get field values - should handle commit timestamps
    values = event._get_field_values()

    # When allow_commit_timestamp is True and value is None or "COMMIT_TIMESTAMP"
    # it should be handled by the field's to_db_value method
    assert len(values) == 4  # All fields present


@patch("google.cloud.spanner_v1.database.Database")
def test_model_save(mock_db_class):
    """Test model save method."""
    mock_db = MagicMock()
    mock_batch = MagicMock()
    mock_db.batch.return_value.__enter__.return_value = mock_batch

    product = Product(OrganizationID="test-org", Name="Test Product", ListPrice=99.99)

    # Save the product
    result = product.save(mock_db)

    # Verify batch operations
    mock_db.batch.assert_called_once()
    mock_batch.insert.assert_called_once()

    # Check insert parameters
    call_args = mock_batch.insert.call_args
    assert call_args[1]["table"] == "Products"
    assert "OrganizationID" in call_args[1]["columns"]
    assert len(call_args[1]["values"]) == 1

    assert result == product


@patch("google.cloud.spanner_v1.database.Database")
def test_model_update(mock_db_class):
    """Test model update method."""
    mock_db = MagicMock()
    mock_batch = MagicMock()
    mock_db.batch.return_value.__enter__.return_value = mock_batch

    product = Product(
        OrganizationID="test-org",
        ProductID="test-product",
        Name="Original Name",
        Stock=10,
        ListPrice=99.99,
    )

    # Update the product
    product.Name = "Updated Name"
    result = product.update(mock_db)

    # Verify batch operations
    mock_batch.update.assert_called_once()

    # Check update parameters
    call_args = mock_batch.update.call_args
    assert call_args[1]["table"] == "Products"
    assert all(col in call_args[1]["columns"] for col in Product._fields.keys())

    assert result == product


@patch("google.cloud.spanner_v1.database.Database")
def test_model_delete(mock_db_class):
    """Test model delete method."""
    mock_db = MagicMock()
    mock_batch = MagicMock()
    mock_db.batch.return_value.__enter__.return_value = mock_batch

    product = Product(
        OrganizationID="test-org", ProductID="test-product", Name="Test Product", ListPrice=99.99
    )

    # Delete the product
    result = product.delete(mock_db)

    # Verify batch operations
    mock_batch.delete.assert_called_once()

    # Check delete parameters
    call_args = mock_batch.delete.call_args
    assert call_args[1]["table"] == "Products"
    assert "keyset" in call_args[1]

    assert result is True


@patch("google.cloud.spanner_v1.database.Database")
def test_model_get(mock_db_class):
    """Test model get method."""
    mock_db = MagicMock()
    mock_snapshot = MagicMock()
    mock_db.snapshot.return_value.__enter__.return_value = mock_snapshot

    # Mock query results
    mock_result = MagicMock()
    mock_field1 = MagicMock()
    mock_field1.name = "OrganizationID"
    mock_field2 = MagicMock()
    mock_field2.name = "Name"
    mock_field3 = MagicMock()
    mock_field3.name = "Active"
    mock_field4 = MagicMock()
    mock_field4.name = "CreatedAt"

    mock_result.fields = [mock_field1, mock_field2, mock_field3, mock_field4]
    mock_result.__iter__.return_value = [
        ("test-org", "Test Organization", True, datetime.now(timezone.utc))
    ]
    mock_snapshot.execute_sql.return_value = mock_result

    # Get organization
    result = Organization.get(mock_db, OrganizationID="test-org")

    # Verify SQL execution
    mock_snapshot.execute_sql.assert_called_once()
    sql = mock_snapshot.execute_sql.call_args[0][0]
    assert "SELECT * FROM Organizations" in sql
    assert "WHERE OrganizationID = @OrganizationID" in sql

    # Verify result
    assert result is not None
    assert result.OrganizationID == "test-org"
    assert result.Name == "Test Organization"


def test_get_or_404():
    """Test get_or_404 raises when no record found."""
    mock_db = MagicMock()

    with patch.object(Organization, "get", return_value=None):
        with pytest.raises(RecordNotFoundError) as exc_info:
            Organization.get_or_404(mock_db, OrganizationID="does-not-exist")

        assert "Organization with OrganizationID=does-not-exist not found" in str(exc_info.value)


@patch("google.cloud.spanner_v1.database.Database")
def test_model_all(mock_db_class):
    """Test model all method."""
    mock_db = MagicMock()
    mock_snapshot = MagicMock()
    mock_db.snapshot.return_value.__enter__.return_value = mock_snapshot

    # Mock query results
    mock_result = MagicMock()
    mock_field1 = MagicMock()
    mock_field1.name = "OrganizationID"
    mock_field2 = MagicMock()
    mock_field2.name = "Name"
    mock_field3 = MagicMock()
    mock_field3.name = "Active"
    mock_field4 = MagicMock()
    mock_field4.name = "CreatedAt"

    mock_result.fields = [mock_field1, mock_field2, mock_field3, mock_field4]
    mock_result.__iter__.return_value = [
        ("org1", "Organization 1", True, datetime.now(timezone.utc)),
        ("org2", "Organization 2", False, datetime.now(timezone.utc)),
    ]
    mock_snapshot.execute_sql.return_value = mock_result

    # Get all organizations
    results = Organization.all(mock_db)

    # Verify SQL execution
    mock_snapshot.execute_sql.assert_called_once()
    sql = mock_snapshot.execute_sql.call_args[0][0]
    assert sql == "SELECT * FROM Organizations"

    # Verify results
    assert len(results) == 2
    assert results[0].OrganizationID == "org1"
    assert results[1].OrganizationID == "org2"


def test_from_query_result():
    """Test creating model from query result."""
    row = ("test-org", "Test Organization", True, datetime.now(timezone.utc))
    field_names = ["OrganizationID", "Name", "Active", "CreatedAt"]

    org = Organization.from_query_result(row, field_names)

    assert org.OrganizationID == "test-org"
    assert org.Name == "Test Organization"
    assert org.Active is True
    assert isinstance(org.CreatedAt, datetime)


def test_get_related():
    """Test get_related method for foreign keys."""
    from spannery.fields import ForeignKeyField, StringField

    class Order(SpannerModel):
        __tablename__ = "Orders"

        order_id = StringField(primary_key=True)
        user_id = ForeignKeyField("User", related_name="orders")
        total = StringField()

    mock_db = MagicMock()

    # Create order with user_id
    order = Order(order_id="ord-123", user_id="usr-456", total="99.99")

    # Mock the related User model
    with patch("spannery.utils.get_model_class") as mock_get_model_class:
        mock_user_class = MagicMock()
        mock_user_class._fields = {"user_id": MagicMock(primary_key=True)}
        mock_user = MagicMock()
        mock_user_class.get.return_value = mock_user

        mock_get_model_class.return_value = mock_user_class

        # Get related user
        result = order.get_related("user_id", mock_db)

        # Verify
        assert result == mock_user
        mock_user_class.get.assert_called_once_with(mock_db, user_id="usr-456")


def test_commit_timestamp_in_save():
    """Test that commit timestamp fields are handled in save."""

    from spannery.fields import StringField

    class Event(SpannerModel):
        __tablename__ = "Events"

        event_id = StringField(primary_key=True)
        created_at = TimestampField(allow_commit_timestamp=True)

    mock_db = MagicMock()
    mock_batch = MagicMock()
    mock_db.batch.return_value.__enter__.return_value = mock_batch

    event = Event(event_id="evt-123")
    event.save(mock_db)

    # Check that commit timestamp fields are handled
    call_args = mock_batch.insert.call_args
    # values[0] is the row, [1] is the created_at field (second field after event_id)
    assert call_args[1]["values"][0][1] == "spanner.commit_timestamp()"

    # The field should handle the commit timestamp conversion
    # We can't check the exact value here as it depends on the field implementation


def test_commit_timestamp_in_update():
    """Test that UpdatedAt fields get commit timestamp on update."""
    from spannery.fields import StringField

    class Document(SpannerModel):
        __tablename__ = "Documents"

        doc_id = StringField(primary_key=True)
        title = StringField()
        created_at = TimestampField(allow_commit_timestamp=True)
        updated_at = TimestampField(allow_commit_timestamp=True)

    mock_db = MagicMock()
    mock_batch = MagicMock()
    mock_db.batch.return_value.__enter__.return_value = mock_batch

    doc = Document(doc_id="doc-123", title="Original")
    doc.title = "Updated"
    doc.update(mock_db)

    # The update method should handle updated_at fields specially
    call_args = mock_batch.update.call_args
    # values[0] is the row, [3] is the updated_at field (fourth field: doc_id, title, created_at, updated_at)
    assert call_args[1]["values"][0][3] == "spanner.commit_timestamp()"
    # We can verify the method was called but the exact timestamp handling
    # is done in the field's to_db_value method
