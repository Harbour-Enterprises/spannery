"""
Session management for Spannery.
"""

import logging
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional, Type, TypeVar, Union

from google.cloud.spanner_v1.database import Database

from spannery.exceptions import ConnectionError, TransactionError
from spannery.model import SpannerModel
from spannery.query import JoinType, Query

T = TypeVar("T", bound=SpannerModel)


class SpannerSession:
    """
    Session manager for Spanner database operations.

    Provides methods for CRUD operations and transaction management.

    Example:
        session = SpannerSession(database)
        product = Product(Name="Test Product", Price=10.99)
        session.save(product)
    """

    def __init__(self, database: Database):
        """
        Initialize a session with a Spanner database.

        Args:
            database: Spanner database instance
        """
        self.database = database

    def save(self, model: SpannerModel, transaction=None) -> SpannerModel:
        """
        Save a model to the database (insert).

        Args:
            model: Model instance to save
            transaction: Optional transaction to use

        Returns:
            Model: The saved model instance
        """
        try:
            return model.save(self.database, transaction)
        except Exception as e:
            raise TransactionError(f"Error saving {model.__class__.__name__}: {str(e)}") from e

    def update(self, model: SpannerModel, transaction=None) -> SpannerModel:
        """
        Update a model in the database.

        Args:
            model: Model instance to update
            transaction: Optional transaction to use

        Returns:
            Model: The updated model instance
        """
        try:
            return model.update(self.database, transaction)
        except Exception as e:
            raise TransactionError(f"Error updating {model.__class__.__name__}: {str(e)}") from e

    def delete(self, model: SpannerModel, transaction=None) -> bool:
        """
        Delete a model from the database.

        Args:
            model: Model instance to delete
            transaction: Optional transaction to use
        Returns:
            bool: True if deletion was successful
        """
        try:
            return model.delete(self.database, transaction)
        except Exception as e:
            raise TransactionError(f"Error deleting {model.__class__.__name__}: {str(e)}") from e

    def query(self, model_class: Type[T]) -> Query[T]:
        """
        Create a query for a model class.

        Args:
            model_class: Model class to query

        Returns:
            Query: Query builder for the model
        """
        return Query(model_class, self.database)

    def get(self, model_class: Type[T], **kwargs) -> Optional[T]:
        """
        Get a single model instance by filter conditions.

        Args:
            model_class: Model class to query
            **kwargs: Filter conditions as field=value pairs

        Returns:
            Optional[Model]: Model instance or None if not found
        """
        return model_class.get(self.database, **kwargs)

    def get_or_404(self, model_class: Type[T], **kwargs) -> T:
        """
        Get a model instance or raise RecordNotFoundError.

        Args:
            model_class: Model class to query
            **kwargs: Filter conditions as field=value pairs

        Returns:
            Model: The found model instance
        """
        return model_class.get_or_404(self.database, **kwargs)

    def refresh(self, model: SpannerModel) -> SpannerModel:
        """
        Refresh a model instance from the database.

        Args:
            model: Model instance to refresh

        Returns:
            Model: Fresh model instance from the database

        Raises:
            RecordNotFoundError: If the model no longer exists in the database
        """
        # Get primary key values
        primary_keys = {}
        for name, field in model._fields.items():
            if field.primary_key:
                primary_keys[name] = getattr(model, name)

        # Get fresh instance
        fresh_instance = model.__class__.get_or_404(self.database, **primary_keys)

        # Update current instance with values from fresh instance
        for name in model._fields:
            setattr(model, name, getattr(fresh_instance, name))

        return model

    def exists(self, model_class: Type[SpannerModel], **kwargs) -> bool:
        """
        Check if a record exists matching the conditions.

        Args:
            model_class: Model class to query
            **kwargs: Filter conditions as field=value pairs

        Returns:
            bool: True if a matching record exists
        """
        query = self.query(model_class).filter(**kwargs).limit(1)
        return query.count() > 0

    def all(self, model_class: Type[T]) -> List[T]:
        """
        Get all instances of a model.

        Args:
            model_class: Model class to query

        Returns:
            List[Model]: List of all model instances
        """
        return model_class.all(self.database)

    def create(self, model_class: Type[T], **kwargs) -> T:
        """
        Create and save a new model instance.

        Args:
            model_class: Model class to instantiate
            **kwargs: Field values for the new instance

        Returns:
            Model: The created model instance
        """
        instance = model_class(**kwargs)
        return self.save(instance)

    def get_or_create(self, model_class: Type[T], defaults=None, **kwargs) -> tuple[T, bool]:
        """
        Get a model instance or create it if it doesn't exist.

        Args:
            model_class: Model class to query/instantiate
            defaults: Default values to use if creating a new instance
            **kwargs: Field values for lookup and for new instance

        Returns:
            Tuple[Model, bool]: (instance, created) where created is True if a new instance was created
        """
        if defaults is None:
            defaults = {}

        # Try to get existing instance
        instance = model_class.get(self.database, **kwargs)

        if instance is not None:
            return instance, False

        # Create new instance with both kwargs and defaults
        create_kwargs = defaults.copy()
        create_kwargs.update(kwargs)
        instance = model_class(**create_kwargs)
        self.save(instance)
        return instance, True

    @contextmanager
    def transaction(self):
        """
        Context manager for transactions.

        Example:
            with session.transaction() as txn:
                txn.insert(...)
                txn.update(...)
        """
        try:
            with self.database.batch() as batch:
                yield batch
        except Exception as e:
            raise TransactionError(f"Transaction failed: {str(e)}") from e

    @contextmanager
    def snapshot(self, multi_use=False, read_timestamp=None, exact_staleness=None):
        """
        Context manager for read-only snapshots.

        Example:
            with session.snapshot() as snapshot:
                results = snapshot.execute_sql("SELECT * FROM Products")
        """
        try:
            with self.database.snapshot(
                multi_use=multi_use, read_timestamp=read_timestamp, exact_staleness=exact_staleness
            ) as snapshot:
                yield snapshot
        except Exception as e:
            raise ConnectionError(f"Snapshot failed: {str(e)}") from e

    def execute_sql(self, sql, params=None, param_types=None):
        """
        Execute a SQL statement with parameters.

        Example:
            results = session.execute_sql(
                "SELECT * FROM Products WHERE Category = @category",
                params={"category": "Electronics"}
            )
        """
        with self.snapshot() as snapshot:
            return snapshot.execute_sql(sql, params=params, param_types=param_types)

    def execute_update(self, sql, params=None, param_types=None):
        """
        Execute a DML statement that modifies data.

        Example:
            row_count = session.execute_update(
                "UPDATE Products SET Price = @price WHERE Category = @category",
                params={"price": 19.99, "category": "Electronics"}
            )
        """
        with self.transaction() as txn:
            row_count = txn.execute_update(sql, params=params, param_types=param_types)
            return row_count

    def get_related(self, model: SpannerModel, field_name: str):
        """
        Get a related model instance through a foreign key relationship.

        Args:
            model: Model instance to get related record for
            field_name: Name of the foreign key field

        Returns:
            Model: Related model instance
        """
        return model.get_related(field_name, self.database)

    def join_query(
        self, model_class: Type[T], related_model, from_field: str, to_field: str
    ) -> Query[T]:
        """
        Create a query with a JOIN pre-configured.

        Args:
            model_class: Base model class to query
            related_model: Related model to join with
            from_field: Field in base model to join on
            to_field: Field in related model to join on

        Returns:
            Query: Query builder with join configured
        """
        return self.query(model_class).join(related_model, from_field, to_field)
