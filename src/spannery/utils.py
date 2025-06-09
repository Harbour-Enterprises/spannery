"""
Utility functions for Spannery.
"""

import datetime
import uuid
from typing import Any, Dict, List, Optional, Tuple

from google.cloud import spanner
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


def get_param_type(value: Any) -> Optional[Type]:
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


def build_param_types(params: Dict[str, Any]) -> Dict[str, Type]:
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


def verify_relation_exists(
    database: Database,
    table_name: str,
    primary_key_columns: List[str],
    primary_key_values: List[Any],
) -> bool:
    """
    Verify that a relation exists in the database.

    Args:
        database: Spanner database instance
        table_name: Table name to check
        primary_key_columns: List of primary key column names
        primary_key_values: List of primary key values

    Returns:
        bool: True if relation exists
    """
    if len(primary_key_columns) != len(primary_key_values):
        raise ValueError("Number of primary key columns must match number of primary key values")

    params = {}
    param_types = {}
    where_conditions = []

    for i, (col, val) in enumerate(zip(primary_key_columns, primary_key_values)):
        param_name = f"pk_{i}"
        params[param_name] = val
        param_types[param_name] = get_param_type(val)
        where_conditions.append(f"{col} = @{param_name}")

    where_clause = " AND ".join(where_conditions)
    sql = f"SELECT COUNT(*) FROM {table_name} WHERE {where_clause}"

    with database.snapshot() as snapshot:
        result = snapshot.execute_sql(sql, params=params, param_types=param_types)
        count = list(result)[0][0]

    return count > 0


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


def get_table_schema(database: Database, table_name: str) -> List[Dict[str, Any]]:
    """
    Get schema information for a table.

    Args:
        database: Spanner database instance
        table_name: Table name to get schema for

    Returns:
        List[Dict]: List of column definitions
    """
    sql = """
    SELECT
        COLUMN_NAME,
        SPANNER_TYPE,
        IS_NULLABLE,
        COLUMN_DEFAULT
    FROM
        INFORMATION_SCHEMA.COLUMNS
    WHERE
        TABLE_NAME = @table_name
    ORDER BY
        ORDINAL_POSITION
    """

    params = {"table_name": table_name}
    param_types = {"table_name": Type(code="STRING")}

    columns = []
    with database.snapshot() as snapshot:
        results = snapshot.execute_sql(sql, params=params, param_types=param_types)
        for row in results:
            column = {
                "name": row[0],
                "type": row[1],
                "nullable": row[2] == "YES",
                "default": row[3],
            }
            columns.append(column)

    return columns


def get_primary_keys(database: Database, table_name: str) -> List[str]:
    """
    Get primary key column names for a table.

    Args:
        database: Spanner database instance
        table_name: Table name to get primary keys for

    Returns:
        List[str]: List of primary key column names in order
    """
    sql = """
    SELECT
        COLUMN_NAME
    FROM
        INFORMATION_SCHEMA.KEY_COLUMN_USAGE
    WHERE
        TABLE_NAME = @table_name
        AND CONSTRAINT_NAME = 'PRIMARY_KEY'
    ORDER BY
        ORDINAL_POSITION
    """

    params = {"table_name": table_name}
    param_types = {"table_name": Type(code="STRING")}

    primary_keys = []
    with database.snapshot() as snapshot:
        results = snapshot.execute_sql(sql, params=params, param_types=param_types)
        for row in results:
            primary_keys.append(row[0])

    return primary_keys


def create_spanner_client(
    project_id: str, instance_id: str, database_id: str, credentials_path: Optional[str] = None
) -> Tuple[Client, Instance, Database]:
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
