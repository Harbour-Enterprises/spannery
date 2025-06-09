# Changelog

## 0.1.12 (2025-07-26)

### Added

- Added `table_filter` method to filter on joined tables in JOIN queries
- Enhanced Query builder to support table-qualified field names in WHERE clauses
- Added support for filtering on columns from different tables in the same query
- Fixed SQL generation for JOIN queries to properly handle table qualifications

### Fixed

- Fixed table aliasing in JOIN queries to use consistent t0, t1, t2, etc. naming scheme
- Properly qualified all field references with table aliases in generated SQL
- Ensured table aliases work correctly when referenced in WHERE conditions
- Fixed issue with table name to table alias conversion in WHERE clauses
- Resolved compatibility issues with Google Spanner SQL dialect for table references

## 0.1.11 (2025-07-25)

### Added

- Added transaction support to all database mutation operations
- Save, update, and delete methods now accept an optional transaction parameter
- Added comprehensive tests for transaction functionality
- Added detailed example demonstrating transaction usage patterns
- Added documentation for transaction features

## 0.1.10 (2025-07-11)

### Fixed

- Enhanced query.all() method to use StreamedResultSet.to_dict_list() when available
- Added more robust error handling for Spanner query execution
- Implemented improved fallback mechanism for results processing

## 0.1.9 (2025-07-10)

### Fixed

- Fixed additional edge cases with empty result handling

## 0.1.8 (2025-07-10)

### Fixed

- Fixed AttributeError in query.all() when processing empty query results
- Added robust error handling for null metadata in query results
- Ensured table aliases work correctly with filter operations

## 0.1.7 (2025-07-09)

### Added

- Added support for JOIN operations between tables
- Added ForeignKeyField for defining relationships
- Implemented functions to access related records
- Added convenient helper methods for common JOIN patterns
- Added support for all JOIN types (INNER, LEFT, RIGHT, FULL)
