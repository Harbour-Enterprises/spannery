"""Tests for field types."""

import datetime
from decimal import Decimal

from google.cloud.spanner_v1 import JsonObject

from spannery.fields import (
    ArrayField,
    BoolField,
    BytesField,
    DateField,
    Field,
    Float64Field,
    ForeignKeyField,
    Int64Field,
    JsonField,
    NumericField,
    StringField,
    TimestampField,
)


def test_base_field_initialization():
    """Test base Field initialization."""
    # Default initialization
    field = Field()
    assert field.primary_key is False
    assert field.nullable is True
    assert field.default is None

    # Custom initialization
    field = Field(
        primary_key=True,
        nullable=False,
        default="default_value",
    )
    assert field.primary_key is True
    assert field.nullable is False
    assert field.default == "default_value"


def test_string_field():
    """Test StringField."""
    field = StringField()

    # Test to_db_value
    assert field.to_db_value("test") == "test"
    assert field.to_db_value(None) is None
    assert field.to_db_value(123) == "123"  # Converts to string

    # Test from_db_value
    assert field.from_db_value("test") == "test"
    assert field.from_db_value(None) is None

    # Test with max_length
    field = StringField(max_length=10)
    assert field.max_length == 10


def test_numeric_field():
    """Test NumericField."""
    field = NumericField()

    # Test to_db_value
    assert field.to_db_value(123.45) == Decimal("123.45")
    assert field.to_db_value(Decimal("123.45")) == Decimal("123.45")
    assert field.to_db_value("123.45") == Decimal("123.45")
    assert field.to_db_value(None) is None

    # Test from_db_value
    assert field.from_db_value(Decimal("123.45")) == Decimal("123.45")
    assert field.from_db_value(None) is None


def test_int64_field():
    """Test Int64Field"""
    field = Int64Field()

    # Test to_db_value
    assert field.to_db_value(123) == 123
    assert field.to_db_value("123") == 123
    assert field.to_db_value(None) is None

    # Test from_db_value
    assert field.from_db_value(123) == 123
    assert field.from_db_value(None) is None


def test_bool_field():
    """Test BoolField"""
    field = BoolField()

    # Test to_db_value
    assert field.to_db_value(True) is True
    assert field.to_db_value(False) is False
    assert field.to_db_value(1) is True
    assert field.to_db_value(0) is False
    assert field.to_db_value("true") is True
    assert field.to_db_value("false") is False
    assert field.to_db_value("") is False
    assert field.to_db_value(None) is None

    # Test from_db_value
    assert field.from_db_value(True) is True
    assert field.from_db_value(False) is False
    assert field.from_db_value(None) is None


def test_timestamp_field():
    """Test TimestampField with commit timestamp support."""
    # Basic field
    field = TimestampField()
    assert field.allow_commit_timestamp is False

    # With commit timestamp support
    field = TimestampField(allow_commit_timestamp=True)
    assert field.allow_commit_timestamp is True

    # Test to_db_value
    now = datetime.datetime.now(datetime.timezone.utc)
    assert field.to_db_value(now) == now
    assert field.to_db_value(None) is None

    # Test commit timestamp sentinel
    from google.cloud.spanner_v1 import COMMIT_TIMESTAMP

    result = field.to_db_value("COMMIT_TIMESTAMP")
    assert result == COMMIT_TIMESTAMP

    # Test string to datetime conversion
    iso_string = "2023-01-01T12:00:00"
    result = field.to_db_value(iso_string)
    assert isinstance(result, datetime.datetime)

    # Test from_db_value
    assert field.from_db_value(now) == now
    assert field.from_db_value(None) is None


def test_date_field():
    """Test DateField."""
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


def test_float64_field():
    """Test Float64Field"""
    field = Float64Field()

    # Test to_db_value
    assert field.to_db_value(123.45) == 123.45
    assert field.to_db_value("123.45") == 123.45
    assert field.to_db_value(None) is None

    # Test from_db_value
    assert field.from_db_value(123.45) == 123.45
    assert field.from_db_value(None) is None


def test_bytes_field():
    """Test BytesField."""
    field = BytesField()

    # Test to_db_value
    test_bytes = b"test bytes"
    assert field.to_db_value(test_bytes) == test_bytes
    assert field.to_db_value(None) is None

    # Test from_db_value
    assert field.from_db_value(test_bytes) == test_bytes
    assert field.from_db_value(None) is None


def test_array_field():
    """Test ArrayField."""
    # Array of strings
    field = ArrayField(StringField())
    assert field.to_db_value(["a", "b", "c"]) == ["a", "b", "c"]
    assert field.to_db_value(None) is None
    assert field.from_db_value(["a", "b", "c"]) == ["a", "b", "c"]

    # Array of integers
    field = ArrayField(Int64Field())
    assert field.to_db_value([1, "2", 3]) == [1, 2, 3]  # Converts "2" to int

    # Array with None values
    field = ArrayField(StringField())
    assert field.to_db_value(["a", None, "c"]) == ["a", None, "c"]


def test_json_field():
    """Test JsonField."""
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

    # Test None handling
    assert field.to_db_value(None) is None

    # Test from_db_value
    data = {"test": "value"}
    assert field.from_db_value(data) == data
    assert field.from_db_value(None) is None

    # Test with default
    field = JsonField(default={"status": "new"})
    assert field.default == {"status": "new"}


def test_foreign_key_field():
    """Test ForeignKeyField."""
    # Basic initialization
    field = ForeignKeyField("User")
    assert field.related_model == "User"
    assert field.related_name is None

    # With related name
    field = ForeignKeyField("Organization", related_name="users")
    assert field.related_model == "Organization"
    assert field.related_name == "users"

    # Test to_db_value
    assert field.to_db_value(None) is None
    assert field.to_db_value("test-id") == "test-id"

    # Test with model instance
    from spannery.model import SpannerModel

    class TestModel(SpannerModel):
        __tablename__ = "TestModels"
        id = StringField(primary_key=True)
        name = StringField()

    model = TestModel(id="model-123", name="Test Model")
    assert field.to_db_value(model) == "model-123"

    # Test from_db_value
    assert field.from_db_value("test-id") == "test-id"
    assert field.from_db_value(None) is None


def test_field_defaults():
    """Test field default values and callables."""
    # Static default
    field = StringField(default="default_value")
    assert field.default == "default_value"

    # Callable default
    counter = 0

    def increment():
        nonlocal counter
        counter += 1
        return f"value_{counter}"

    field = StringField(default=increment)
    assert field.default() == "value_1"
    assert field.default() == "value_2"

    # UUID default
    import uuid

    field = StringField(default=lambda: str(uuid.uuid4()))
    value1 = field.default()
    value2 = field.default()
    assert value1 != value2
    assert len(value1) == 36  # UUID string length
