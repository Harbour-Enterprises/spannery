"""Tests for field types."""

import datetime
import os
from decimal import Decimal
from unittest.mock import patch

import pytest
from google.cloud.spanner_v1 import JsonObject

from spannery.fields import (
    ArrayField,
    BooleanField,
    BytesField,
    DateField,
    DateTimeField,
    Field,
    FloatField,
    ForeignKeyField,
    IntegerField,
    JsonField,
    NumericField,
    StringField,
)


def test_base_field_initialization():
    """Test base Field initialization with various options."""
    # Default initialization
    field = Field()
    assert field.primary_key is False
    assert field.nullable is True
    assert field.default is None
    assert field.index is False
    assert field.unique is False
    assert field.description is None

    # Custom initialization
    field = Field(
        primary_key=True,
        nullable=False,
        default="default_value",
        index=True,
        unique=True,
        description="Test field",
    )
    assert field.primary_key is True
    assert field.nullable is False
    assert field.default == "default_value"
    assert field.index is True
    assert field.unique is True
    assert field.description == "Test field"


def test_string_field():
    """Test StringField initialization and methods."""
    # Default initialization
    field = StringField()
    assert field.max_length is None

    # With max_length
    field = StringField(max_length=50)
    assert field.max_length == 50

    # Test to_db_value
    assert field.to_db_value("test") == "test"
    assert field.to_db_value(None) is None

    # Test from_db_value
    assert field.from_db_value("test") == "test"
    assert field.from_db_value(None) is None

    # Test get_spanner_type - use a fresh field for each test
    field_unlimited = StringField()
    assert field_unlimited.get_spanner_type() == "STRING(MAX)"

    field_limited = StringField(max_length=100)
    assert field_limited.get_spanner_type() == "STRING(100)"


def test_numeric_field():
    """Test NumericField initialization and methods."""
    # Default initialization
    field = NumericField()
    assert field.precision is None
    assert field.scale is None

    # With precision and scale
    field = NumericField(precision=10, scale=2)
    assert field.precision == 10
    assert field.scale == 2

    # Test to_db_value
    assert field.to_db_value(123.45) == Decimal("123.45")
    assert field.to_db_value(Decimal("123.45")) == Decimal("123.45")
    assert field.to_db_value("123.45") == Decimal("123.45")
    assert field.to_db_value(None) is None

    # Test get_spanner_type
    assert field.get_spanner_type() == "NUMERIC(10, 2)"
    field = NumericField()
    assert field.get_spanner_type() == "NUMERIC"


def test_integer_field():
    """Test IntegerField initialization and methods."""
    # Default initialization
    field = IntegerField()

    # Test to_db_value
    assert field.to_db_value(123) == 123
    assert field.to_db_value("123") == 123
    assert field.to_db_value(None) is None

    # Test from_db_value
    assert field.from_db_value(123) == 123
    assert field.from_db_value(None) is None

    # Test get_spanner_type
    assert field.get_spanner_type() == "INT64"


def test_boolean_field():
    """Test BooleanField initialization and methods."""
    # Default initialization
    field = BooleanField()

    # Test to_db_value
    assert field.to_db_value(True) is True
    assert field.to_db_value(False) is False
    assert field.to_db_value(1) is True
    assert field.to_db_value(0) is False
    assert field.to_db_value("true") is True
    assert field.to_db_value("false") is False
    assert field.to_db_value(None) is None

    # Test from_db_value
    assert field.from_db_value(True) is True
    assert field.from_db_value(False) is False
    assert field.from_db_value(None) is None

    # Test get_spanner_type
    assert field.get_spanner_type() == "BOOL"


def test_datetime_field():
    """Test DateTimeField initialization and methods."""
    # Default initialization
    field = DateTimeField()
    assert field.auto_now is False
    assert field.auto_now_add is False

    # With auto_now and auto_now_add
    field = DateTimeField(auto_now=True)
    assert field.auto_now is True
    assert field.auto_now_add is False

    field = DateTimeField(auto_now_add=True)
    assert field.auto_now is False
    assert field.auto_now_add is True

    # Test to_db_value
    now = datetime.datetime.now(datetime.timezone.utc)
    assert field.to_db_value(now) == now
    assert field.to_db_value(None) is None

    # Test auto_now behavior
    field = DateTimeField(auto_now=True)
    with patch("spannery.utils.utcnow") as mock_utcnow:
        test_now = datetime.datetime(2023, 1, 1, tzinfo=datetime.timezone.utc)
        mock_utcnow.return_value = test_now
        assert field.to_db_value("something") == test_now

    # Test from_db_value
    assert field.from_db_value(now) == now
    assert field.from_db_value(None) is None

    # Test get_spanner_type
    assert field.get_spanner_type() == "TIMESTAMP"


def test_date_field():
    """Test DateField initialization and methods."""
    # Default initialization
    field = DateField()

    # Test to_db_value
    today = datetime.date.today()
    assert field.to_db_value(today) == today
    assert field.to_db_value(None) is None

    # Test datetime to date conversion
    now = datetime.datetime.now()
    assert field.to_db_value(now) == now.date()

    # Test from_db_value
    assert field.from_db_value(today) == today
    assert field.from_db_value(None) is None

    # Test get_spanner_type
    assert field.get_spanner_type() == "DATE"


def test_float_field():
    """Test FloatField initialization and methods."""
    # Default initialization
    field = FloatField()

    # Test to_db_value
    assert field.to_db_value(123.45) == 123.45
    assert field.to_db_value("123.45") == 123.45
    assert field.to_db_value(None) is None

    # Test from_db_value
    assert field.from_db_value(123.45) == 123.45
    assert field.from_db_value(None) is None

    # Test get_spanner_type
    assert field.get_spanner_type() == "FLOAT64"


def test_bytes_field():
    """Test BytesField initialization and methods."""
    # Default initialization
    field = BytesField()
    assert field.max_length is None

    # With max_length
    field = BytesField(max_length=50)
    assert field.max_length == 50

    # Test to_db_value
    test_bytes = b"test bytes"
    assert field.to_db_value(test_bytes) == test_bytes
    assert field.to_db_value(None) is None

    # Test from_db_value
    assert field.from_db_value(test_bytes) == test_bytes
    assert field.from_db_value(None) is None

    # Test get_spanner_type
    assert field.get_spanner_type() == "BYTES(50)"
    field = BytesField()
    assert field.get_spanner_type() == "BYTES(MAX)"


def test_array_field():
    """Test ArrayField initialization and methods."""
    # Initialization with item_field
    string_field = StringField()
    field = ArrayField(string_field)
    assert field.item_field == string_field

    int_field = IntegerField()
    field = ArrayField(int_field)
    assert field.item_field == int_field

    # Test to_db_value
    field = ArrayField(StringField())
    assert field.to_db_value(["a", "b", "c"]) == ["a", "b", "c"]
    assert field.to_db_value(None) is None

    field = ArrayField(IntegerField())
    assert field.to_db_value([1, "2", 3]) == [1, 2, 3]  # Converts "2" to int

    # Test from_db_value
    field = ArrayField(StringField())
    assert field.from_db_value(["a", "b", "c"]) == ["a", "b", "c"]
    assert field.from_db_value(None) is None

    # Test get_spanner_type
    field = ArrayField(StringField())
    assert field.get_spanner_type() == "ARRAY<STRING(MAX)>"

    field = ArrayField(IntegerField())
    assert field.get_spanner_type() == "ARRAY<INT64>"

    field = ArrayField(StringField(max_length=50))
    assert field.get_spanner_type() == "ARRAY<STRING(50)>"


class TestJsonField:
    """Tests for JsonField."""

    def test_json_field_creation(self):
        """Test JsonField creation with various configurations."""
        field = JsonField()
        assert field.nullable is True
        assert field.primary_key is False
        assert field.get_spanner_type() == "JSON"

        required_field = JsonField(nullable=False)
        assert required_field.nullable is False

        field_with_default = JsonField(default={"status": "new"})
        assert field_with_default.default == {"status": "new"}

    def test_json_field_to_db_value(self):
        """Test conversion to database value."""
        field = JsonField()

        # Test dict conversion
        data = {"name": "Test", "value": 123, "active": True}
        db_value = field.to_db_value(data)
        assert isinstance(db_value, JsonObject)
        # JsonObject behaves like a dict
        for key, value in data.items():
            assert db_value[key] == value

        # Test list conversion
        data = [1, 2, "three", {"four": 4}]
        db_value = field.to_db_value(data)
        assert isinstance(db_value, JsonObject)
        # For lists, we just check the string representation matches
        assert str(db_value) == str(data)

        # Test None handling
        assert field.to_db_value(None) is None

        # Test primitive values
        num_value = field.to_db_value(42)
        assert isinstance(num_value, JsonObject)
        assert str(num_value) == str(42)

        str_value = field.to_db_value("string")
        assert isinstance(str_value, JsonObject)
        assert str(str_value) == "string"

        bool_value = field.to_db_value(True)
        assert isinstance(bool_value, JsonObject)
        assert str(bool_value) == str(True)

        # Test nested structures
        complex_data = {
            "id": 1,
            "name": "Product",
            "attributes": {
                "color": "blue",
                "sizes": ["S", "M", "L"],
                "metadata": {"created_at": "2023-01-01", "updated": True},
            },
        }
        db_value = field.to_db_value(complex_data)
        assert isinstance(db_value, JsonObject)
        # Check the structure matches
        assert db_value["id"] == complex_data["id"]
        assert db_value["name"] == complex_data["name"]
        assert db_value["attributes"]["color"] == complex_data["attributes"]["color"]
        # For the sizes array, we can only check the string representation
        assert str(db_value["attributes"]["sizes"]) == str(complex_data["attributes"]["sizes"])
        assert (
            db_value["attributes"]["metadata"]["created_at"]
            == complex_data["attributes"]["metadata"]["created_at"]
        )
        assert (
            db_value["attributes"]["metadata"]["updated"]
            == complex_data["attributes"]["metadata"]["updated"]
        )

    def test_json_field_from_db_value(self):
        """Test conversion from database value."""
        field = JsonField()

        # The from_db_value should return the same value as it's passed through
        data = {"test": "value", "nested": {"works": True}}
        assert field.from_db_value(data) == data

        # Test with None
        assert field.from_db_value(None) is None

    def test_json_field_with_default_callable(self):
        """Test JsonField with a callable default value."""
        default_callable = lambda: {
            "timestamp": datetime.datetime.now().isoformat(),
            "status": "new",
        }
        field = JsonField(default=default_callable)

        # Ensure the default is still the callable
        assert field.default == default_callable

        # The default value should be a callable that returns a dict
        default_value = field.default()
        assert isinstance(default_value, dict)
        assert "timestamp" in default_value
        assert default_value["status"] == "new"


# Integration test for JsonField within a model
@pytest.mark.skipif(
    os.getenv("SPANNER_EMULATOR_HOST") is None,
    reason="Integration test requires Spanner emulator",
)
def test_json_field_integration(spanner_database, spanner_session):
    """Test JsonField integration with a real database."""
    import uuid

    from spannery.model import SpannerModel

    # Define a test model with JsonField
    class ProductWithMetadata(SpannerModel):
        __tablename__ = "ProductsWithMetadata"

        ProductID = StringField(primary_key=True, nullable=False, default=lambda: str(uuid.uuid4()))
        Name = StringField(max_length=255, nullable=False)
        Metadata = JsonField(nullable=True)
        Settings = JsonField(nullable=False, default={"version": 1, "active": True})

    # Create the table
    ddl = f"""
    CREATE TABLE {ProductWithMetadata.__tablename__} (
        ProductID STRING(36) NOT NULL,
        Name STRING(255) NOT NULL,
        Metadata JSON,
        Settings JSON NOT NULL,
    ) PRIMARY KEY (ProductID)
    """

    try:
        spanner_database.update_ddl([ddl]).result()

        # Create a product with JSON data
        metadata = {
            "color": "blue",
            "dimensions": {"width": 10, "height": 20, "depth": 5},
            "tags": ["electronics", "new", "sale"],
        }

        product = ProductWithMetadata(Name="Test Product with JSON", Metadata=metadata)

        # Save to database
        spanner_session.save(product)

        # Retrieve from database
        retrieved_product = spanner_session.get(ProductWithMetadata, ProductID=product.ProductID)

        # Verify JSON data was stored and retrieved correctly
        assert retrieved_product is not None
        assert retrieved_product.Name == "Test Product with JSON"
        assert retrieved_product.Metadata == metadata
        assert retrieved_product.Metadata["color"] == "blue"
        assert retrieved_product.Metadata["dimensions"]["width"] == 10
        assert retrieved_product.Metadata["tags"] == ["electronics", "new", "sale"]

        # Check default JSON value
        assert retrieved_product.Settings == {"version": 1, "active": True}

        # Test updating JSON field
        retrieved_product.Metadata["color"] = "red"
        retrieved_product.Metadata["tags"].append("updated")
        spanner_session.update(retrieved_product)

        # Verify update
        updated_product = spanner_session.get(ProductWithMetadata, ProductID=product.ProductID)

        assert updated_product.Metadata["color"] == "red"
        assert "updated" in updated_product.Metadata["tags"]

    finally:
        # Clean up - drop the test table
        spanner_database.update_ddl([f"DROP TABLE {ProductWithMetadata.__tablename__}"]).result()


class TestForeignKeyField:
    """Tests for ForeignKeyField."""

    def test_foreign_key_field_creation(self):
        """Test ForeignKeyField creation with various options."""
        from spannery.fields import ForeignKeyField

        # Default initialization
        field = ForeignKeyField("TestModel")
        assert field.related_model == "TestModel"
        assert field.related_name is None
        assert field.cascade_delete is False
        assert field.nullable is True
        assert field.primary_key is False

        # Custom initialization
        field = ForeignKeyField(
            "TestModel",
            related_name="test_relation",
            cascade_delete=True,
            primary_key=True,
            nullable=False,
            default="default-id",
        )
        assert field.related_model == "TestModel"
        assert field.related_name == "test_relation"
        assert field.cascade_delete is True
        assert field.primary_key is True
        assert field.nullable is False
        assert field.default == "default-id"

        # Check Spanner type
        assert field.get_spanner_type() == "STRING(36)"

    def test_foreign_key_to_db_value(self):
        """Test ForeignKeyField.to_db_value() method."""
        from spannery.fields import ForeignKeyField, StringField
        from spannery.model import SpannerModel

        # Create a test model class
        class TestModel(SpannerModel):
            __tablename__ = "TestModels"
            ID = StringField(primary_key=True)
            Name = StringField()

        field = ForeignKeyField("TestModel")

        # Test with None
        assert field.to_db_value(None) is None

        # Test with string
        assert field.to_db_value("test-id") == "test-id"

        # Test with model instance
        model = TestModel(ID="model-123", Name="Test Model")
        assert field.to_db_value(model) == "model-123"

    def test_foreign_key_from_db_value(self):
        """Test ForeignKeyField.from_db_value() method."""
        from spannery.fields import ForeignKeyField

        field = ForeignKeyField("TestModel")

        # Simple pass-through behavior
        assert field.from_db_value("test-id") == "test-id"
        assert field.from_db_value(None) is None
