"""
Model definitions for Spannery.
"""

from typing import Any, ClassVar, TypeVar

from google.cloud.spanner_v1.database import Database
from google.cloud.spanner_v1.keyset import KeySet

from spannery.exceptions import RecordNotFoundError
from spannery.fields import Field, ForeignKeyField, TimestampField
from spannery.utils import register_model

T = TypeVar("T", bound="SpannerModel")


class ModelMeta(type):
    """Metaclass for SpannerModel to process model fields."""

    def __new__(mcs, name: str, bases: tuple, attrs: dict) -> type:
        # Skip processing for the base SpannerModel class
        if name == "SpannerModel" and not bases:
            return super().__new__(mcs, name, bases, attrs)

        # Process fields
        fields = {}
        for key, value in list(attrs.items()):
            if isinstance(value, Field):
                value.name = key  # Set the field name
                fields[key] = value

        # Store fields in class variables
        attrs["_fields"] = fields
        attrs["_table_name"] = attrs.get("__tablename__", name)

        # Create the class
        new_class = super().__new__(mcs, name, bases, attrs)

        # Register the model in the global registry
        register_model(new_class)

        return new_class


class SpannerModel(metaclass=ModelMeta):
    """
    Base model class for Spannery.

    Example:
        class Product(SpannerModel):
            __tablename__ = "Products"

            ProductID = StringField(primary_key=True)
            Name = StringField()
            Price = NumericField()
            CreatedAt = TimestampField(allow_commit_timestamp=True)
    """

    # Class variables for config
    __tablename__: ClassVar[str | None] = None

    # These are kept for metadata/documentation only
    __interleave_in__: ClassVar[str | None] = None
    __relationships__: ClassVar[dict[str, dict]] = {}

    # Fields will be stored here by the metaclass
    _fields: ClassVar[dict[str, Field]] = {}
    _table_name: ClassVar[str] = None

    def __init__(self, **kwargs):
        """
        Initialize a model instance with field values.

        Args:
            **kwargs: Field values to set on the model
        """
        # Set field values from kwargs or defaults
        for name, field in self._fields.items():
            if name in kwargs:
                setattr(self, name, kwargs[name])
            elif field.default is not None:
                default_value = field.default
                if callable(default_value):
                    default_value = default_value()
                setattr(self, name, default_value)
            else:
                setattr(self, name, None)

    def __repr__(self) -> str:
        """String representation of the model."""
        pk_values = []
        for name, field in self._fields.items():
            if field.primary_key:
                pk_values.append(f"{name}={getattr(self, name)}")

        class_name = self.__class__.__name__
        pk_str = ", ".join(pk_values)
        return f"<{class_name}({pk_str})>"

    def _get_primary_key_values(self) -> dict[str, Any]:
        """Get primary key field names and values."""
        return {
            name: getattr(self, name) for name, field in self._fields.items() if field.primary_key
        }

    def _get_field_values(self) -> list[Any]:
        """Get all field values formatted for Spanner."""
        values = []
        for name, field in self._fields.items():
            value = getattr(self, name)

            # Handle commit timestamp
            if isinstance(field, TimestampField) and field.allow_commit_timestamp:
                if value is None or value == "COMMIT_TIMESTAMP":
                    value = "COMMIT_TIMESTAMP"

            values.append(field.to_db_value(value))
        return values

    def save(self, database: Database, transaction=None) -> T:
        """
        Save the model to Spanner (insert).

        Args:
            database: Spanner database instance
            transaction: Optional ongoing transaction to use

        Returns:
            Self: The model instance
        """
        columns = list(self._fields.keys())
        values = [self._get_field_values()]

        if transaction:
            transaction.insert(table=self._table_name, columns=columns, values=values)
        else:
            with database.batch() as batch:
                batch.insert(table=self._table_name, columns=columns, values=values)

        return self

    def update(self, database: Database, transaction=None) -> T:
        """
        Update an existing model in Spanner.

        Args:
            database: Spanner database instance
            transaction: Optional ongoing transaction to use

        Returns:
            Self: The model instance
        """
        # For Spanner, we need to include ALL columns in the update
        all_columns = list(self._fields.keys())
        all_values = []

        for name in all_columns:
            field = self._fields[name]
            value = getattr(self, name)

            # Handle commit timestamp for updates
            if isinstance(field, TimestampField) and field.allow_commit_timestamp:
                if name.lower().endswith("updatedat") or name.lower().endswith("updated_at"):
                    value = "COMMIT_TIMESTAMP"

            all_values.append(field.to_db_value(value))

        if transaction:
            transaction.update(table=self._table_name, columns=all_columns, values=[all_values])
        else:
            with database.batch() as batch:
                batch.update(table=self._table_name, columns=all_columns, values=[all_values])

        return self

    def delete(self, database: Database, transaction=None) -> bool:
        """
        Delete the model from Spanner.

        Args:
            database: Spanner database instance
            transaction: Optional ongoing transaction to use

        Returns:
            bool: True if deletion was successful
        """
        pk_values = self._get_primary_key_values()

        # Create a KeySet with the primary key values
        keyset = KeySet(keys=[list(pk_values.values())])

        if transaction:
            transaction.delete(table=self._table_name, keyset=keyset)
        else:
            with database.batch() as batch:
                batch.delete(table=self._table_name, keyset=keyset)

        return True

    @classmethod
    def get(cls: type[T], database: Database, **kwargs) -> T | None:
        """
        Retrieve a single model by filter conditions.

        Args:
            database: Spanner database instance
            **kwargs: Filter conditions as field=value pairs

        Returns:
            Optional[Model]: Model instance or None if not found
        """
        conditions = []
        params = {}

        for key, value in kwargs.items():
            if key in cls._fields:
                conditions.append(f"{key} = @{key}")
                field = cls._fields[key]
                params[key] = field.to_db_value(value)

        if not conditions:
            return None

        sql = f"SELECT * FROM {cls._table_name} WHERE {' AND '.join(conditions)} LIMIT 1"  # nosec: B608

        with database.snapshot() as snapshot:
            results = snapshot.execute_sql(sql, params=params)
            rows = list(results)
            if not rows:
                return None

            # Map column values to field names
            instance_data = {}
            for i, column in enumerate(results.fields):
                column_name = column.name
                if column_name in cls._fields:
                    field = cls._fields[column_name]
                    instance_data[column_name] = field.from_db_value(rows[0][i])

            return cls(**instance_data)

    @classmethod
    def get_or_404(cls: type[T], database: Database, **kwargs) -> T:
        """
        Retrieve a model by filter conditions or raise RecordNotFoundError.

        Args:
            database: Spanner database instance
            **kwargs: Filter conditions as field=value pairs

        Returns:
            Model: The found model instance

        Raises:
            RecordNotFoundError: If no record is found
        """
        instance = cls.get(database, **kwargs)
        if instance is None:
            pk_clauses = ", ".join([f"{k}={v}" for k, v in kwargs.items()])
            raise RecordNotFoundError(f"{cls.__name__} with {pk_clauses} not found")
        return instance

    @classmethod
    def all(cls: type[T], database: Database) -> list[T]:
        """
        Retrieve all instances of this model.

        Args:
            database: Spanner database instance

        Returns:
            List[Model]: List of model instances
        """
        sql = f"SELECT * FROM {cls._table_name}"  # nosec B608

        with database.snapshot() as snapshot:
            results = snapshot.execute_sql(sql)

            instances = []
            for row in results:
                instance_data = {}
                for i, column in enumerate(results.fields):
                    column_name = column.name
                    if column_name in cls._fields:
                        field = cls._fields[column_name]
                        instance_data[column_name] = field.from_db_value(row[i])

                instances.append(cls(**instance_data))

            return instances

    @classmethod
    def from_query_result(cls: type[T], result_row, field_names) -> T:
        """
        Create a model instance from a query result row.

        Args:
            result_row: Row from query result
            field_names: List of field names in the order of result_row

        Returns:
            Model: Model instance with values from the row
        """
        field_values = {}

        for i, field_name in enumerate(field_names):
            if field_name not in cls._fields:
                continue

            field = cls._fields[field_name]
            value = result_row[i]
            field_values[field_name] = field.from_db_value(value)

        return cls(**field_values)

    def __eq__(self, other) -> bool:
        """
        Compare two model instances for equality.

        Models are considered equal if they are of the same class
        and have the same primary key values.
        """
        if not isinstance(other, self.__class__):
            return False

        # Compare primary key values
        for name, field in self._fields.items():
            if field.primary_key:
                if getattr(self, name) != getattr(other, name):
                    return False

        return True

    def to_dict(self) -> dict[str, Any]:
        """
        Convert model instance to a dictionary.

        Returns:
            Dict[str, Any]: Dictionary with field names as keys and field values as values
        """
        result = {}
        for name in self._fields:
            result[name] = getattr(self, name)
        return result

    @classmethod
    def from_dict(cls: type[T], data: dict[str, Any]) -> T:
        """
        Create a model instance from a dictionary.

        Args:
            data: Dictionary with field names as keys and field values as values

        Returns:
            Model instance of the class
        """
        return cls(**data)

    def get_related(self, field_name: str, database: Database) -> Any | None:
        """
        Get a related model instance through a foreign key.

        Args:
            field_name: Name of the foreign key field
            database: Spanner database instance

        Returns:
            Optional[SpannerModel]: Related model instance or None
        """
        field = self._fields.get(field_name)
        if not isinstance(field, ForeignKeyField):
            raise ValueError(f"Field {field_name} is not a foreign key")

        # Get the related model class
        from spannery.utils import get_model_class

        related_class = get_model_class(field.related_model)

        # Get the value of the foreign key
        fk_value = getattr(self, field_name)
        if fk_value is None:
            return None

        # Find primary key in related model (assume single PK for simplicity)
        primary_key = None
        for name, field in related_class._fields.items():
            if field.primary_key:
                primary_key = name
                break

        if primary_key is None:
            raise ValueError(f"Related model {field.related_model} has no primary key")

        # Query for the related model
        return related_class.get(database, **{primary_key: fk_value})
