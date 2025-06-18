"""
Query builder for Spannery.
"""

from typing import Any, Generic, TypeVar

from google.cloud.spanner_v1 import RequestOptions
from google.cloud.spanner_v1.database import Database

from spannery.exceptions import RecordNotFoundError
from spannery.model import SpannerModel
from spannery.utils import build_param_types, get_model_class

T = TypeVar("T", bound=SpannerModel)


class Query(Generic[T]):
    """
    Query builder for Spannery models.

    Simple, explicit query building with Spanner-specific features.

    Example:
        # Simple query
        products = session.query(Product).filter(active=True).all()

        # With operators
        expensive = session.query(Product).filter(price__gt=100).all()

        # Multiple conditions
        results = session.query(Product).filter(
            category="Electronics",
            price__between=(50, 200),
            name__like="Widget%"
        ).order_by("price").all()
    """

    def __init__(self, model_class: type[T], database: Database):
        """
        Initialize a query builder.

        Args:
            model_class: The model class to query
            database: Spanner database instance
        """
        self.model_class = model_class
        self.database = database
        self._filters = []
        self._order_by = []
        self._limit = None
        self._offset = None
        self._select_fields = None
        self._joins = []
        self._force_index = None
        self._request_tag = None
        self._request_priority = None
        self._snapshot = None  # For read-only transactions

    def select(self, *fields) -> "Query[T]":
        """
        Select specific fields.

        Args:
            *fields: Field names to select

        Returns:
            Query: Self for method chaining
        """
        self._select_fields = list(fields)
        return self

    def filter(self, **kwargs) -> "Query[T]":
        """
        Add filter conditions using Django-style operators.

        Operators:
            field=value         → field = value
            field__lt=value     → field < value
            field__lte=value    → field <= value
            field__gt=value     → field > value
            field__gte=value    → field >= value
            field__ne=value     → field != value
            field__in=[...]     → field IN (...)
            field__not_in=[...] → field NOT IN (...)
            field__like=pattern → field LIKE pattern
            field__ilike=pattern → case-insensitive LIKE
            field__is_null=True → field IS NULL
            field__between=(a,b) → field BETWEEN a AND b
            field__regex=pattern → REGEXP_CONTAINS(field, pattern)

        Example:
            users = session.query(User).filter(
                active=True,
                created_at__gte="2024-01-01",
                email__like="%@gmail.com"
            ).all()

        Returns:
            Query: Self for method chaining
        """
        for key, value in kwargs.items():
            if "__" in key:
                field, op = key.split("__", 1)
            else:
                field, op = key, "eq"

            # Only add filter if field exists in model
            if field in self.model_class._fields:
                self._filters.append((field, op, value))

        return self

    def filter_or(self, *conditions) -> "Query[T]":
        """
        Add OR conditions.

        Args:
            *conditions: Each condition is a dict of field__op=value

        Example:
            # Find products that are cheap OR on sale
            products = query.filter_or(
                {"price__lt": 20},
                {"on_sale": True}
            )

        Returns:
            Query: Self for method chaining
        """
        if conditions:
            self._filters.append(("__OR__", "or", conditions))
        return self

    def order_by(self, field: str, desc: bool = False) -> "Query[T]":
        """
        Add ordering.

        Args:
            field: Field name to order by
            desc: If True, order descending

        Returns:
            Query: Self for method chaining
        """
        if field in self.model_class._fields:
            self._order_by.append((field, desc))
        return self

    def limit(self, n: int) -> "Query[T]":
        """Set result limit."""
        self._limit = n
        return self

    def offset(self, n: int) -> "Query[T]":
        """Set result offset."""
        self._offset = n
        return self

    def join(self, related_model: str | type[SpannerModel], on: tuple[str, str]) -> "Query[T]":
        """
        Add a JOIN clause.

        Args:
            related_model: Model to join with
            on: Tuple of (left_field, right_field) for the join condition

        Example:
            # Join orders with users
            orders = session.query(Order).join(User, on=("user_id", "user_id")).all()

        Returns:
            Query: Self for method chaining
        """
        if isinstance(related_model, str):
            related_model = get_model_class(related_model)

        self._joins.append(
            {"model": related_model, "left_field": on[0], "right_field": on[1], "type": "INNER"}
        )
        return self

    def left_join(self, related_model: str | type[SpannerModel], on: tuple[str, str]) -> "Query[T]":
        """Add a LEFT JOIN clause."""
        if isinstance(related_model, str):
            related_model = get_model_class(related_model)

        self._joins.append(
            {"model": related_model, "left_field": on[0], "right_field": on[1], "type": "LEFT"}
        )
        return self

    def force_index(self, index_name: str) -> "Query[T]":
        """
        Force Spanner to use a specific index.

        Args:
            index_name: Name of the index to use

        Returns:
            Query: Self for method chaining
        """
        self._force_index = index_name
        return self

    def with_request_tag(self, tag: str) -> "Query[T]":
        """
        Add a request tag for monitoring.

        Args:
            tag: Request tag string

        Returns:
            Query: Self for method chaining
        """
        self._request_tag = tag
        return self

    def with_priority(self, priority: str) -> "Query[T]":
        """
        Set request priority (LOW, MEDIUM, HIGH).

        Args:
            priority: Priority level

        Returns:
            Query: Self for method chaining
        """
        self._request_priority = priority
        return self

    def _build_sql(self) -> tuple[str, dict[str, Any]]:
        """
        Build SQL query and parameters.

        Returns:
            Tuple of (sql, params)
        """
        # SELECT clause
        if self._select_fields:
            select_clause = f"SELECT {', '.join(self._select_fields)}"
        else:
            select_clause = "SELECT *"

        # FROM clause with index hint
        from_clause = f"FROM {self.model_class._table_name}"
        if self._force_index:
            from_clause += f"@{{FORCE_INDEX={self._force_index}}}"

        # JOIN clauses
        for join in self._joins:
            join_type = join["type"]
            related_table = join["model"]._table_name
            left_field = join["left_field"]
            right_field = join["right_field"]

            from_clause += f" {join_type} JOIN {related_table} ON {self.model_class._table_name}.{left_field} = {related_table}.{right_field}"

        # WHERE clause
        where_parts = []
        params = {}
        param_counter = 0

        for field, op, value in self._filters:
            # Handle OR conditions
            if field == "__OR__":
                or_parts = []
                for condition_dict in value:
                    for cond_key, cond_value in condition_dict.items():
                        if "__" in cond_key:
                            cond_field, cond_op = cond_key.split("__", 1)
                        else:
                            cond_field, cond_op = cond_key, "eq"

                        param_name = f"p{param_counter}"
                        param_counter += 1
                        params[param_name] = cond_value

                        or_parts.append(self._build_condition(cond_field, cond_op, param_name))

                if or_parts:
                    where_parts.append(f"({' OR '.join(or_parts)})")
                continue

            # Regular conditions
            if op == "is_null":
                if value:
                    where_parts.append(f"{field} IS NULL")
                else:
                    where_parts.append(f"{field} IS NOT NULL")
            elif op == "between":
                param_start = f"p{param_counter}"
                param_end = f"p{param_counter + 1}"
                param_counter += 2
                params[param_start] = value[0]
                params[param_end] = value[1]
                where_parts.append(f"{field} BETWEEN @{param_start} AND @{param_end}")
            elif op in ("in", "not_in"):
                # Handle IN/NOT IN with multiple parameters
                param_names = []
                for v in value:
                    param_name = f"p{param_counter}"
                    param_counter += 1
                    params[param_name] = v
                    param_names.append(f"@{param_name}")

                operator = "IN" if op == "in" else "NOT IN"
                where_parts.append(f"{field} {operator} ({', '.join(param_names)})")
            else:
                param_name = f"p{param_counter}"
                param_counter += 1
                params[param_name] = value
                where_parts.append(self._build_condition(field, op, param_name))

        where_clause = f" WHERE {' AND '.join(where_parts)}" if where_parts else ""

        # ORDER BY clause
        order_by_clause = ""
        if self._order_by:
            order_parts = []
            for field, desc in self._order_by:
                order_parts.append(f"{field} {'DESC' if desc else 'ASC'}")
            order_by_clause = f" ORDER BY {', '.join(order_parts)}"

        # LIMIT/OFFSET
        limit_clause = f" LIMIT {self._limit}" if self._limit else ""
        offset_clause = f" OFFSET {self._offset}" if self._offset else ""

        sql = (
            select_clause
            + " "
            + from_clause
            + where_clause
            + order_by_clause
            + limit_clause
            + offset_clause
        )

        return sql, params

    def _build_condition(self, field: str, op: str, param_name: str) -> str:
        """Build a WHERE condition."""
        operators = {
            "eq": "=",
            "ne": "!=",
            "lt": "<",
            "lte": "<=",
            "gt": ">",
            "gte": ">=",
            "like": "LIKE",
            "ilike": "LIKE",  # Will wrap with LOWER()
        }

        if op == "regex":
            return f"REGEXP_CONTAINS({field}, @{param_name})"
        elif op == "ilike":
            return f"LOWER({field}) LIKE LOWER(@{param_name})"
        else:
            sql_op = operators.get(op, "=")
            return f"{field} {sql_op} @{param_name}"

    def _execute(self, sql: str, params: dict) -> Any:
        """Execute the query with proper Spanner options."""
        # Build parameter types
        param_types = build_param_types(params)

        # Create request options if needed
        request_options = None
        if self._request_tag or self._request_priority:
            request_options = RequestOptions(
                request_tag=self._request_tag, priority=self._request_priority
            )

        # Use snapshot if provided (for read-only transactions)
        if self._snapshot:
            # If we already have a snapshot (from read-only transaction), use it directly
            return self._snapshot.execute_sql(
                sql, params=params, param_types=param_types, request_options=request_options
            )
        else:
            # Create a new snapshot for this query
            with self.database.snapshot() as snapshot:
                return snapshot.execute_sql(
                    sql, params=params, param_types=param_types, request_options=request_options
                )

    def count(self) -> int:
        """
        Get count of matching records.

        Returns:
            int: Number of matching records
        """
        # Don't try to parse SQL strings - build a proper COUNT query
        # using the same components but simplified

        # Build parameter dictionary
        params = {}
        param_counter = 0

        # Build WHERE clause from scratch using our filters
        where_parts = []

        for field, op, value in self._filters:
            # Handle OR conditions
            if field == "__OR__":
                or_parts = []
                for condition_dict in value:
                    for cond_key, cond_value in condition_dict.items():
                        if "__" in cond_key:
                            cond_field, cond_op = cond_key.split("__", 1)
                        else:
                            cond_field, cond_op = cond_key, "eq"

                        param_name = f"p{param_counter}"
                        param_counter += 1
                        params[param_name] = cond_value

                        or_parts.append(self._build_condition(cond_field, cond_op, param_name))

                if or_parts:
                    where_parts.append(f"({' OR '.join(or_parts)})")
                continue

            # Regular conditions
            if op == "is_null":
                if value:
                    where_parts.append(f"{field} IS NULL")
                else:
                    where_parts.append(f"{field} IS NOT NULL")
            elif op == "between":
                param_start = f"p{param_counter}"
                param_end = f"p{param_counter + 1}"
                param_counter += 2
                params[param_start] = value[0]
                params[param_end] = value[1]
                where_parts.append(f"{field} BETWEEN @{param_start} AND @{param_end}")
            elif op in ("in", "not_in"):
                # Handle IN/NOT IN with multiple parameters
                param_names = []
                for v in value:
                    param_name = f"p{param_counter}"
                    param_counter += 1
                    params[param_name] = v
                    param_names.append(f"@{param_name}")

                operator = "IN" if op == "in" else "NOT IN"
                where_parts.append(f"{field} {operator} ({', '.join(param_names)})")
            else:
                param_name = f"p{param_counter}"
                param_counter += 1
                params[param_name] = value
                where_parts.append(self._build_condition(field, op, param_name))

        # Build FROM clause with JOINs if needed
        from_clause = self.model_class._table_name

        # Add JOINs if present
        for join in self._joins:
            join_type = join["type"]
            related_table = join["model"]._table_name
            left_field = join["left_field"]
            right_field = join["right_field"]

            from_clause += f" {join_type} JOIN {related_table} ON {self.model_class._table_name}.{left_field} = {related_table}.{right_field}"

        # Build the complete COUNT query
        count_sql = f"SELECT COUNT(*) FROM {from_clause}"  # nosec B608

        if where_parts:
            count_sql += f" WHERE {' AND '.join(where_parts)}"

        # Execute the count query
        results = self._execute(count_sql, params)
        return list(results)[0][0]

    def all(self) -> list[T]:
        """
        Execute query and return all results.

        Returns:
            List[T]: List of model instances
        """
        sql, params = self._build_sql()
        results = self._execute(sql, params)

        instances = []
        for row in results:
            # Convert row to model instance
            if hasattr(results, "fields"):
                # Use field information if available
                field_names = [f.name for f in results.fields]
                instance = self.model_class.from_query_result(row, field_names)
            else:
                # Fallback: assume fields are in model order
                field_values = {}
                for i, (name, field) in enumerate(self.model_class._fields.items()):
                    if i < len(row):
                        field_values[name] = field.from_db_value(row[i])
                instance = self.model_class(**field_values)

            instances.append(instance)

        return instances

    def first(self) -> T | None:
        """
        Get first result or None.

        Returns:
            Optional[T]: First result or None
        """
        self.limit(1)
        results = self.all()
        return results[0] if results else None

    def one(self) -> T:
        """
        Get exactly one result.

        Returns:
            T: The single result

        Raises:
            RecordNotFoundError: If no results
            MultipleRecordsFoundError: If more than one result
        """
        self.limit(2)
        results = self.all()

        if not results:
            raise RecordNotFoundError(f"No {self.model_class.__name__} found")

        if len(results) > 1:
            from spannery.exceptions import MultipleRecordsFoundError

            raise MultipleRecordsFoundError(
                f"Expected one {self.model_class.__name__}, found multiple"
            )

        return results[0]

    def exists(self) -> bool:
        """
        Check if any matching records exist.

        Returns:
            bool: True if any matches exist
        """
        return self.count() > 0

    # Convenience methods for common filters
    def filter_by_id(self, **id_values) -> "Query[T]":
        """
        Filter by primary key values.

        Example:
            user = session.query(User).filter_by_id(user_id="123").one()

        Returns:
            Query: Self for method chaining
        """
        return self.filter(**id_values)
