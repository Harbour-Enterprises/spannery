"""
Session management for Spannery.
"""

from contextlib import contextmanager
from typing import TypeVar

from google.cloud.spanner_v1 import RequestOptions
from google.cloud.spanner_v1.database import Database

from spannery.exceptions import ConnectionError, TransactionError
from spannery.model import SpannerModel
from spannery.query import Query

T = TypeVar("T", bound=SpannerModel)


class SpannerSession:
    """
    Session manager for Spanner database operations.

    Provides methods for CRUD operations and transaction management.

    Example:
        session = SpannerSession(database)
        product = Product(name="Test Product", price=10.99)
        session.save(product)
    """

    def __init__(self, database: Database):
        """
        Initialize a session with a Spanner database.

        Args:
            database: Spanner database instance
        """
        self.database = database

    def save(self, model: SpannerModel, transaction=None, request_tag: str = None) -> SpannerModel:
        """
        Save a model to the database (insert).

        Args:
            model: Model instance to save
            transaction: Optional transaction to use
            request_tag: Optional request tag for monitoring

        Returns:
            Model: The saved model instance
        """
        try:
            # Create request options if tag provided
            request_options = RequestOptions(request_tag=request_tag) if request_tag else None

            if transaction:
                return model.save(self.database, transaction)
            else:
                # Use request options if provided
                if request_options:
                    with self.database.batch(request_options=request_options) as batch:
                        model._transaction = batch
                        result = model.save(self.database, batch)
                        model._transaction = None
                        return result
                else:
                    return model.save(self.database)
        except Exception as e:
            raise TransactionError(f"Error saving {model.__class__.__name__}: {str(e)}") from e

    def update(
        self, model: SpannerModel, transaction=None, request_tag: str = None
    ) -> SpannerModel:
        """
        Update a model in the database.

        Args:
            model: Model instance to update
            transaction: Optional transaction to use
            request_tag: Optional request tag for monitoring

        Returns:
            Model: The updated model instance
        """
        try:
            # Create request options if tag provided
            request_options = RequestOptions(request_tag=request_tag) if request_tag else None

            if transaction:
                return model.update(self.database, transaction)
            else:
                # Use request options if provided
                if request_options:
                    with self.database.batch(request_options=request_options) as batch:
                        model._transaction = batch
                        result = model.update(self.database, batch)
                        model._transaction = None
                        return result
                else:
                    return model.update(self.database)
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

    def query(self, model_class: type[T]) -> Query[T]:
        """
        Create a query for a model class.

        Args:
            model_class: Model class to query

        Returns:
            Query: Query builder for the model
        """
        return Query(model_class, self.database)

    def get(self, model_class: type[T], **kwargs) -> T | None:
        """
        Get a single model instance by filter conditions.

        Args:
            model_class: Model class to query
            **kwargs: Filter conditions as field=value pairs

        Returns:
            Optional[Model]: Model instance or None if not found
        """
        return model_class.get(self.database, **kwargs)

    def get_or_404(self, model_class: type[T], **kwargs) -> T:
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

    def exists(self, model_class: type[SpannerModel], **kwargs) -> bool:
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

    def all(self, model_class: type[T]) -> list[T]:
        """
        Get all instances of a model.

        Args:
            model_class: Model class to query

        Returns:
            List[Model]: List of all model instances
        """
        return model_class.all(self.database)

    def create(self, model_class: type[T], **kwargs) -> T:
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

    def get_or_create(self, model_class: type[T], defaults=None, **kwargs) -> tuple[T, bool]:
        """
        Get a model instance or create it if it doesn't exist.

        Args:
            model_class: Model class to query/instantiate
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
    def transaction(self, request_tag: str = None):
        """
        Context manager for transactions.

        Args:
            request_tag: Optional request tag for monitoring

        Example:
            with session.transaction(request_tag="batch-import") as txn:
                txn.insert(...)
                txn.update(...)
        """
        try:
            request_options = RequestOptions(request_tag=request_tag) if request_tag else None
            with self.database.batch(request_options=request_options) as batch:
                yield batch
        except Exception as e:
            raise TransactionError(f"Transaction failed: {str(e)}") from e

    @contextmanager
    def snapshot(self, multi_use=False, read_timestamp=None, exact_staleness=None):
        """
        Context manager for read-only snapshots.

        Args:
            multi_use: Whether snapshot can be used for multiple reads
            read_timestamp: Read at specific timestamp
            exact_staleness: Read with exact staleness duration

        Example:
            with session.snapshot(exact_staleness=timedelta(seconds=10)) as snapshot:
                results = snapshot.execute_sql("SELECT * FROM Products")
        """
        try:
            with self.database.snapshot(
                multi_use=multi_use, read_timestamp=read_timestamp, exact_staleness=exact_staleness
            ) as snapshot:
                yield snapshot
        except Exception as e:
            raise ConnectionError(f"Snapshot failed: {str(e)}") from e

    @contextmanager
    def read_only_transaction(self, read_timestamp=None, exact_staleness=None):
        """
        Context manager for read-only transactions.

        Read-only transactions provide consistent reads across multiple operations.

        Args:
            read_timestamp: Read at specific timestamp
            exact_staleness: Read with exact staleness duration

        Example:
            with session.read_only_transaction() as ro_txn:
                users = self.query(User).all()
                orders = self.query(Order).filter(user_id=user.user_id).all()
                # Both reads see consistent state
        """
        try:
            # Create a multi-use snapshot which acts as a read-only transaction
            with self.database.snapshot(
                multi_use=True, read_timestamp=read_timestamp, exact_staleness=exact_staleness
            ) as snapshot:
                # Create a wrapper that provides query functionality
                class ReadOnlyTransaction:
                    def __init__(self, snapshot, session):
                        self.snapshot = snapshot
                        self.session = session

                    def query(self, model_class):
                        """Create a query within the read-only transaction."""
                        query = Query(model_class, self.session.database)
                        query._snapshot = self.snapshot  # Attach snapshot to query
                        return query

                    def execute_sql(self, sql, params=None, param_types=None):
                        """Execute SQL within the read-only transaction."""
                        return self.snapshot.execute_sql(
                            sql, params=params, param_types=param_types
                        )

                yield ReadOnlyTransaction(snapshot, self)

        except Exception as e:
            raise ConnectionError(f"Read-only transaction failed: {str(e)}") from e

    def execute_sql(self, sql, params=None, param_types=None, request_tag: str = None):
        """
        Execute a SQL statement with parameters.

        Args:
            sql: SQL query string
            params: Query parameters
            param_types: Parameter types
            request_tag: Optional request tag for monitoring

        Example:
            results = session.execute_sql(
                "SELECT * FROM Products WHERE category = @category",
                params={"category": "Electronics"},
                request_tag="product-search"
            )
        """
        request_options = RequestOptions(request_tag=request_tag) if request_tag else None

        with self.snapshot() as snapshot:
            return snapshot.execute_sql(
                sql, params=params, param_types=param_types, request_options=request_options
            )

    def execute_update(self, sql, params=None, param_types=None):
        """
        Execute a DML statement that modifies data.

        Example:
            row_count = session.execute_update(
                "UPDATE Products SET price = @price WHERE category = @category",
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
        self, model_class: type[T], related_model, from_field: str, to_field: str
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
