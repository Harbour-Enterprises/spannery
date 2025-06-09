"""
Model definitions for Spannery.
"""

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, ClassVar, Dict, List, Optional, Type, TypeVar, Tuple, Union

from google.cloud import spanner
from google.cloud.spanner_v1.database import Database
from google.cloud.spanner_v1.keyset import KeySet

from spannery.exceptions import ModelDefinitionError, RecordNotFoundError
from spannery.fields import DateTimeField, Field, ForeignKeyField

from spannery.utils import register_model

T = TypeVar("T", bound="SpannerModel")


class ModelMeta(type):
    """Metaclass for SpannerModel to process model fields and configuration."""

    def __new__(mcs, name: str, bases: tuple, attrs: dict) -> Type:
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
    Base model class for SpannerORM.

    Example:
        class Product(SpannerModel):
            __tablename__ = "Products"
            __interleave_in__ = "Organizations"

            OrganizationID = StringField(primary_key=True, nullable=False)
            ProductID = StringField(primary_key=True, nullable=False)
            Name = StringField(max_length=255, nullable=False)
    """

    # Class variables for config
    __tablename__: ClassVar[Optional[str]] = None
    __interleave_in__: ClassVar[Optional[str]] = None
    __on_delete__: ClassVar[Optional[str]] = "NO ACTION"  # CASCADE, NO ACTION
    __relationships__: ClassVar[Dict[str, Dict]] = {}  # Will store relationship information

    # Fields will be stored here by the metaclass
    _fields: ClassVar[Dict[str, Field]] = {}
    _table_name: ClassVar[str] = None

    @property
    def _parent_table(self):
        """Get the parent table name if this model is interleaved."""
        return self.__class__.__interleave_in__

    @classmethod
    @property
    def _parent_table(cls):
        """Get the parent table name if this model is interleaved."""
        return cls.__interleave_in__

    @property
    def _parent_on_delete(self):
        """Get the on_delete behavior for this interleaved model."""
        return self.__class__.__on_delete__

    @classmethod
    @property
    def _parent_on_delete(cls):
        """Get the on_delete behavior for this interleaved model."""
        return cls.__on_delete__

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

    @classmethod
    def create_table(cls, database: Database) -> bool:
        """
        Create table in Spanner based on the model definition.

        Args:
            database: Spanner database instance

        Returns:
            bool: True if table creation was successful

        Raises:
            ModelDefinitionError: If the model definition is invalid
        """
        if not cls._fields:
            raise ModelDefinitionError(f"Model {cls.__name__} has no fields")

        fields_sql = []
        primary_keys = []

        for name, field in cls._fields.items():
            field_type = field.get_spanner_type()

            nullable_str = "NOT NULL" if not field.nullable else ""
            fields_sql.append(f"{name} {field_type} {nullable_str}")

            if field.primary_key:
                primary_keys.append(name)

        if not primary_keys:
            raise ModelDefinitionError(f"Model {cls.__name__} has no primary key fields")

        interleave_clause = ""
        on_delete_clause = ""

        if cls.__interleave_in__:
            interleave_clause = f", INTERLEAVE IN PARENT {cls.__interleave_in__}"
            if cls.__on_delete__ == "CASCADE":
                on_delete_clause = " ON DELETE CASCADE"

        sql = f"""
        CREATE TABLE {cls._table_name} (
            {', '.join(fields_sql)}
        ) PRIMARY KEY ({', '.join(primary_keys)}){interleave_clause}{on_delete_clause}
        """

        database.update_ddl([sql]).result()
        return True

    @classmethod
    def _get_primary_keys(cls) -> List[str]:
        """Get list of primary key field names."""
        return [name for name, field in cls._fields.items() if field.primary_key]

    def _get_field_values(self) -> List[Any]:
        """Get all field values formatted for Spanner."""
        values = []
        for name, field in self._fields.items():
            value = getattr(self, name)
            # Check if this is a DateTimeField with auto_now
            if isinstance(field, DateTimeField) and field.auto_now:
                value = datetime.now(timezone.utc)
                setattr(self, name, value)
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
        # Update timestamps if needed
        current_time = datetime.now(timezone.utc)

        for name, field in self._fields.items():
            if isinstance(field, DateTimeField):
                # Handle auto_now_add for new records
                if field.auto_now_add and getattr(self, name) is None:
                    setattr(self, name, current_time)
                # Handle auto_now fields
                elif field.auto_now:
                    setattr(self, name, current_time)

        columns = list(self._fields.keys())
        values = [self._get_field_values()]

        if transaction:
            # Use the provided transaction
            transaction.insert(table=self._table_name, columns=columns, values=values)
        else:
            # Create a new batch transaction
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
        primary_keys = self._get_primary_keys()

        if not primary_keys:
            raise ModelDefinitionError("Cannot update model without primary keys")

        # Update timestamps if needed
        for name, field in self._fields.items():
            if isinstance(field, DateTimeField) and field.auto_now:
                setattr(self, name, datetime.now(timezone.utc))

        # For Spanner, we need to include ALL columns in the update
        all_columns = list(self._fields.keys())

        # Get all field values in the correct order
        all_values = []
        for name in all_columns:
            value = getattr(self, name)
            all_values.append(self._fields[name].to_db_value(value))

        if transaction:
            # Use the provided transaction
            transaction.update(
                table=self._table_name,
                columns=all_columns,
                values=[all_values],  # Wrap in a list as update expects a list of rows
            )
        else:
            # Execute update using Spanner's batch API
            with database.batch() as batch:
                batch.update(
                    table=self._table_name,
                    columns=all_columns,
                    values=[all_values],  # Wrap in a list as batch.update expects a list of rows
                )

        return self

    def delete(self, database: Database, transaction=None) -> bool:
        """
        Delete the model from Spanner.

        Args:
            database: Spanner database instance
            transaction: Optional ongoing transaction to use

        Returns:
            bool: True if deletion was successful

        Raises:
            ModelDefinitionError: If the model has no primary keys
        """
        primary_keys = self._get_primary_keys()

        if not primary_keys:
            raise ModelDefinitionError("Cannot delete model without primary keys")

        # Create a dictionary of primary key values for deletion
        key_dict = {pk: getattr(self, pk) for pk in primary_keys}

        try:
            # Create a KeySet with the primary key values
            keyset = KeySet(keys=[list(key_dict.values())])

            if transaction:
                # Use the provided transaction
                transaction.delete(table=self._table_name, keyset=keyset)
            else:
                # Execute deletion using batch
                with database.batch() as batch:
                    batch.delete(table=self._table_name, keyset=keyset)
            return True
        except Exception as e:
            # Reraise with more context
            raise type(e)(f"Error deleting {self._table_name}: {str(e)}") from e

    @classmethod
    def get(cls: Type[T], database: Database, **kwargs) -> Optional[T]:
        """
        Retrieve a single model by filter conditions.

        Args:
            database: Spanner database instance
            **kwargs: Filter conditions as field=value pairs

        Returns:
            Optional[Model]: Model instance or None if not found

        Raises:
            ModelDefinitionError: If no valid filter conditions are provided
        """
        conditions = []
        params = {}
        param_types = {}

        for key, value in kwargs.items():
            if key in cls._fields:
                conditions.append(f"{key} = @{key}")
                field = cls._fields[key]
                params[key] = field.to_db_value(value)
                # Would set param_types here based on field type

        if not conditions:
            raise ModelDefinitionError("No valid filter conditions specified")

        sql = f"SELECT * FROM {cls._table_name} WHERE {' AND '.join(conditions)} LIMIT 1"

        with database.snapshot() as snapshot:
            results = snapshot.execute_sql(sql, params=params, param_types=param_types)
            rows = list(results)
            if not rows:
                return None

            # Map column values to field names
            instance_data = {}
            for i, column in enumerate(results.fields):
                column_name = column.name
                if column_name in cls._fields:
                    instance_data[column_name] = rows[0][i]

            return cls(**instance_data)

    @classmethod
    def get_or_404(cls: Type[T], database: Database, **kwargs) -> T:
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
    def all(cls: Type[T], database: Database) -> List[T]:
        """
        Retrieve all instances of this model.

        Args:
            database: Spanner database instance

        Returns:
            List[Model]: List of model instances
        """
        sql = f"SELECT * FROM {cls._table_name}"

        with database.snapshot() as snapshot:
            results = snapshot.execute_sql(sql)

            instances = []
            for row in results:
                # Map column values to field names
                instance_data = {}
                for i, column in enumerate(results.fields):
                    column_name = column.name
                    if column_name in cls._fields:
                        instance_data[column_name] = row[i]

                instances.append(cls(**instance_data))

            return instances

    @classmethod
    def from_query_result(cls: Type[T], result_row, field_names) -> T:
        """
        Create a model instance from a query result row.

        Args:
            result_row: Row from query result
            field_names: List of field names in the order of result_row

        Returns:
            Model: Model instance with values from the row
        """
        # Create a dictionary of field values
        field_values = {}

        for i, field_name in enumerate(field_names):
            # Skip fields that don't exist in this model
            if field_name not in cls._fields:
                continue

            # Convert the value using the field's from_db_value method
            field = cls._fields[field_name]
            value = result_row[i]
            field_values[field_name] = field.from_db_value(value)

        # Create a new instance with the field values
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

    def to_dict(self) -> Dict[str, Any]:
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
    def from_dict(cls: Type[T], data: Dict[str, Any]) -> T:
        """
        Create a model instance from a dictionary.

        Args:
            data: Dictionary with field names as keys and field values as values

        Returns:
            Model instance of the class
        """
        return cls(**data)

    @classmethod
    def _process_relationships(cls):
        """
        Process relationships defined in the model.

        This method collects all ForeignKeyField instances and stores
        information about relationships.
        """
        if hasattr(cls, "__relationships__") and cls.__relationships__:
            # Already processed
            return

        cls.__relationships__ = {}

        # Import here to avoid circular import
        from spannery.fields import ForeignKeyField

        for name, field in cls._fields.items():
            if isinstance(field, ForeignKeyField):
                cls.__relationships__[name] = {
                    "field": field,
                    "related_model": field.related_model,
                    "related_name": field.related_name,
                }

    def get_related(self, field_name: str, database: Database) -> Optional[Any]:
        """
        Get a related model instance.

        Args:
            field_name: Name of the foreign key field
            database: Spanner database instance

        Returns:
            Optional[SpannerModel]: Related model instance or None
        """
        self.__class__._process_relationships()

        if field_name not in self.__class__.__relationships__:
            raise ValueError(f"Field {field_name} is not a foreign key")

        relationship = self.__class__.__relationships__[field_name]
        related_model_name = relationship["related_model"]

        # Get the related model class by name
        from spannery.utils import get_model_class

        related_class = get_model_class(related_model_name)

        # Get the value of the foreign key
        fk_value = getattr(self, field_name)
        if fk_value is None:
            return None

        # Find primary key field in related model
        primary_key = None
        for name, field in related_class._fields.items():
            if field.primary_key:
                primary_key = name
                break

        if primary_key is None:
            raise ValueError(f"Related model {related_model_name} has no primary key")

        # Query for the related model
        filter_kwargs = {primary_key: fk_value}
        return related_class.get(database, **filter_kwargs)
