"""
Utility functions for Spannery.
"""

import datetime
import uuid
from typing import Any

from google.cloud.spanner_v1.client import Client
from google.cloud.spanner_v1.database import Database
from google.cloud.spanner_v1.instance import Instance
from google.cloud.spanner_v1.param_types import Type

# Global registry of model classes
_MODEL_REGISTRY = {}


def register_model(model_class):
    """
    Register a model class in the global registry.

    Args:
        model_class: Model class to register
    """
    _MODEL_REGISTRY[model_class.__name__] = model_class


def get_model_class(model_name):
    """
    Get a model class by name from the registry.

    Args:
        model_name: Name of the model class

    Returns:
        SpannerModel: The model class

    Raises:
        ValueError: If model class is not found
    """
    if model_name not in _MODEL_REGISTRY:
        raise ValueError(f"Model class {model_name} not found in registry")
    return _MODEL_REGISTRY[model_name]


def generate_uuid() -> str:
    """Generate a UUID string."""
    return str(uuid.uuid4())


def utcnow() -> datetime.datetime:
    """Get current UTC datetime with timezone info."""
    return datetime.datetime.now(datetime.timezone.utc)


def get_param_type(value: Any) -> Type | None:
    """
    Get Spanner parameter type for a Python value.

    Args:
        value: Python value

    Returns:
        Type: Spanner parameter type or None
    """
    if value is None:
        return None

    if isinstance(value, bool):
        return Type(code="BOOL")
    elif isinstance(value, int):
        return Type(code="INT64")
    elif isinstance(value, float):
        return Type(code="FLOAT64")
    elif isinstance(value, str):
        return Type(code="STRING")
    elif isinstance(value, datetime.datetime):
        return Type(code="TIMESTAMP")
    elif isinstance(value, datetime.date):
        return Type(code="DATE")
    elif isinstance(value, bytes):
        return Type(code="BYTES")
    elif isinstance(value, list):
        if not value:
            # Can't determine array type for empty list
            return None
        # Use first non-None element to determine array type
        for item in value:
            if item is not None:
                item_type = get_param_type(item)
                if item_type:
                    return Type(code="ARRAY", array_element_type=item_type)
        return None

    # Default
    return None


def build_param_types(params: dict[str, Any]) -> dict[str, Type]:
    """
    Build parameter types dictionary for Spanner.

    Args:
        params: Dictionary of parameters

    Returns:
        Dict: Parameter types dictionary
    """
    param_types = {}
    for key, value in params.items():
        param_type = get_param_type(value)
        if param_type:
            param_types[key] = param_type
    return param_types


def execute_with_retry(
    database: Database, operation_func, max_attempts: int = 3, retry_delay: float = 1.0
) -> Any:
    """
    Execute a database operation with retry for transient errors.

    Args:
        database: Spanner database instance
        operation_func: Function that takes a transaction and returns a result
        max_attempts: Maximum number of attempts
        retry_delay: Delay between attempts in seconds

    Returns:
        Any: Result of the operation function
    """
    import time

    from google.api_core import exceptions

    attempt = 0
    last_exception = None

    # List of error types that are transient and can be retried
    transient_errors = (
        exceptions.Aborted,
        exceptions.DeadlineExceeded,
        exceptions.ServiceUnavailable,
        exceptions.ResourceExhausted,
    )

    while attempt < max_attempts:
        attempt += 1
        try:
            return database.run_in_transaction(operation_func)
        except transient_errors as e:
            last_exception = e
            if attempt < max_attempts:
                time.sleep(retry_delay)
                # Exponential backoff
                retry_delay *= 2
            else:
                break

    # If we get here, all attempts failed
    raise last_exception if last_exception else RuntimeError("Unknown error in execute_with_retry")


def create_spanner_client(
    project_id: str, instance_id: str, database_id: str, credentials_path: str | None = None
) -> tuple[Client, Instance, Database]:
    """
    Create Spanner client, instance, and database objects.

    Args:
        project_id: Google Cloud project ID
        instance_id: Spanner instance ID
        database_id: Spanner database ID
        credentials_path: Path to credentials file (optional)

    Returns:
        Tuple: (client, instance, database)
    """
    client_kwargs = {"project": project_id}

    if credentials_path:
        from google.oauth2 import service_account

        credentials = service_account.Credentials.from_service_account_file(credentials_path)
        client_kwargs["credentials"] = credentials

    client = Client(**client_kwargs)
    instance = client.instance(instance_id)
    database = instance.database(database_id)

    return client, instance, database
