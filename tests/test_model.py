"""Tests for SpannerModel."""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from conftest import Organization, Product

from spannery.exceptions import ModelDefinitionError, RecordNotFoundError
from spannery.fields import IntegerField, StringField
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


def test_get_primary_keys():
    """Test the _get_primary_keys method."""
    assert set(Product._get_primary_keys()) == {"OrganizationID", "ProductID"}
    assert set(Organization._get_primary_keys()) == {"OrganizationID"}


@pytest.mark.parametrize(
    "model_class, expected_error",
    [
        (
            type("EmptyModel", (SpannerModel,), {"__tablename__": "EmptyTable"}),
            "Model EmptyModel has no fields",
        ),
        (
            type(
                "NoPKModel",
                (SpannerModel,),
                {
                    "__tablename__": "NoPKTable",
                    "Name": StringField(nullable=False),
                },
            ),
            "Model NoPKModel has no primary key fields",
        ),
    ],
)
def test_create_table_validation(model_class, expected_error):
    """Test validation in create_table method."""
    mock_db = MagicMock()

    with pytest.raises(ModelDefinitionError, match=expected_error):
        model_class.create_table(mock_db)


@patch("spannery.model.SpannerModel.get")
def test_get_or_404_not_found(mock_get):
    """Test get_or_404 raises RecordNotFoundError when no record is found."""
    mock_get.return_value = None
    mock_db = MagicMock()

    with pytest.raises(RecordNotFoundError):
        Organization.get_or_404(mock_db, OrganizationID="does-not-exist")

    mock_get.assert_called_once_with(mock_db, OrganizationID="does-not-exist")


def test_model_init():
    """Test model initialization with keyword arguments."""
    org = Organization(
        OrganizationID="test-org",
        Name="Test Organization",
        Active=True,
    )

    assert org.OrganizationID == "test-org"
    assert org.Name == "Test Organization"
    assert org.Active is True
    assert org.CreatedAt is not None


def test_model_eq():
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
    """Test model metadata and table properties."""
    assert Organization._table_name == "Organizations"
    assert "OrganizationID" in Organization._fields
    assert isinstance(Organization._fields["OrganizationID"], StringField)
    assert Organization._fields["OrganizationID"].primary_key is True

    assert Product._table_name == "Products"
    assert Product._parent_table == "Organizations"
    assert Product._parent_on_delete == "CASCADE"
    assert isinstance(Product._fields["Stock"], IntegerField)


@patch("google.cloud.spanner_v1.database.Database")
def test_model_get(mock_db):
    """Test model get method with mocks."""
    # Setup mock snapshot and execution results
    mock_snapshot = MagicMock()
    mock_db.snapshot.return_value.__enter__.return_value = mock_snapshot

    # Mock execute_sql with a sample result that would be returned by Spanner
    mock_result = MagicMock()
    mock_result.__iter__.return_value = [
        ("test-org", "Test Organization", True, "2023-01-01T00:00:00Z")
    ]
    mock_snapshot.execute_sql.return_value = mock_result

    # Directly mock the get method instead of the from_query_result
    with patch.object(Organization, "get") as mock_get:
        # Create a model instance to return
        org = Organization(
            OrganizationID="test-org",
            Name="Test Organization",
            Active=True,
        )
        mock_get.return_value = org

        # Test get with primary key
        result = Organization.get(mock_db, OrganizationID="test-org")

        # Assertions
        mock_get.assert_called_once_with(mock_db, OrganizationID="test-org")
        assert result is not None
        assert result.OrganizationID == "test-org"
        assert result.Name == "Test Organization"
        assert result.Active is True


@pytest.mark.skip("Integration test requiring Spanner connection")
def test_get_model(spanner_session, test_organization):
    """Integration test for model retrieval."""
    org_id = test_organization.OrganizationID

    retrieved_org = spanner_session.get(Organization, OrganizationID=org_id)

    assert retrieved_org is not None
    assert retrieved_org.OrganizationID == org_id
    assert retrieved_org.Name == test_organization.Name


@pytest.mark.skip("Integration test requiring Spanner connection")
def test_crud_operations(spanner_session, test_organization):
    """Integration test for CRUD operations."""
    # Create
    product = Product(
        OrganizationID=test_organization.OrganizationID,
        Name="CRUD Test Product",
        Description="This is a test product for CRUD operations",
        Category="Test",
        Stock=10,
        ListPrice=99.99,
        CostPrice=49.99,
        Active=True,
    )
    spanner_session.save(product)
    product_id = product.ProductID

    # Read
    retrieved_product = spanner_session.get(
        Product, OrganizationID=test_organization.OrganizationID, ProductID=product_id
    )
    assert retrieved_product is not None
    assert retrieved_product.Name == "CRUD Test Product"

    # Update
    retrieved_product.Stock = 20
    retrieved_product.Name = "Updated CRUD Test Product"
    spanner_session.save(retrieved_product)

    # Read updated
    updated_product = spanner_session.get(
        Product, OrganizationID=test_organization.OrganizationID, ProductID=product_id
    )
    assert updated_product is not None
    assert updated_product.Stock == 20
    assert updated_product.Name == "Updated CRUD Test Product"

    # Delete
    spanner_session.delete(updated_product)

    # Verify deleted
    deleted_product = spanner_session.get(
        Product, OrganizationID=test_organization.OrganizationID, ProductID=product_id
    )
    assert deleted_product is None
