"""Test configuration and fixtures for Spannery."""

import os
import uuid
from collections.abc import Generator
from datetime import datetime, timezone

import pytest
from google.cloud.spanner_v1.client import Client
from google.cloud.spanner_v1.database import Database
from google.cloud.spanner_v1.instance import Instance

from spannery.fields import (
    BooleanField,
    DateTimeField,
    ForeignKeyField,
    IntegerField,
    NumericField,
    StringField,
)
from spannery.model import SpannerModel
from spannery.session import SpannerSession


# Test model definitions
class Organization(SpannerModel):
    __tablename__ = "Organizations"

    OrganizationID = StringField(
        primary_key=True, nullable=False, default=lambda: str(uuid.uuid4())
    )
    Name = StringField(max_length=255, nullable=False)
    Active = BooleanField(nullable=False, default=True)
    CreatedAt = DateTimeField(nullable=False, default=lambda: datetime.now(timezone.utc))


class Product(SpannerModel):
    __tablename__ = "Products"
    __interleave_in__ = "Organizations"
    __on_delete__ = "CASCADE"

    OrganizationID = StringField(primary_key=True, nullable=False)
    ProductID = StringField(primary_key=True, nullable=False, default=lambda: str(uuid.uuid4()))
    Name = StringField(max_length=255, nullable=False)
    Description = StringField(max_length=2000)
    Category = StringField(max_length=100)
    Stock = IntegerField(nullable=False, default=0)
    CreatedAt = DateTimeField(nullable=False, default=lambda: datetime.now(timezone.utc))
    UpdatedAt = DateTimeField(nullable=False, default=lambda: datetime.now(timezone.utc))
    Active = BooleanField(nullable=False, default=True)
    ListPrice = NumericField(nullable=False)
    CostPrice = NumericField()


# Models for JOIN tests
class User(SpannerModel):
    __tablename__ = "Users"

    UserID = StringField(primary_key=True, nullable=False, default=lambda: str(uuid.uuid4()))
    Email = StringField(max_length=255, nullable=False)
    FullName = StringField(max_length=255, nullable=False)
    Status = StringField(max_length=20, nullable=False, default="ACTIVE")
    CreatedAt = DateTimeField(nullable=False, default=lambda: datetime.now(timezone.utc))
    Active = BooleanField(nullable=False, default=True)


class OrganizationUser(SpannerModel):
    __tablename__ = "OrganizationUsers"

    OrganizationID = ForeignKeyField("Organization", primary_key=True, related_name="users")
    UserID = ForeignKeyField("User", primary_key=True, related_name="organizations")
    Role = StringField(max_length=20, nullable=False)
    Status = StringField(max_length=20, nullable=False, default="ACTIVE")
    CreatedAt = DateTimeField(nullable=False, default=lambda: datetime.now(timezone.utc))


# Check if running in CI or local development
USE_EMULATOR = os.getenv("SPANNER_EMULATOR_HOST") is not None
USE_MOCK = os.getenv("SPANNERORM_TEST_MODE") == "mock"


@pytest.fixture
def spanner_project_id() -> str:
    """Get Google Cloud project ID for tests."""
    return os.getenv("GOOGLE_CLOUD_PROJECT", "test-project")


@pytest.fixture
def spanner_instance_id() -> str:
    """Get Spanner instance ID for tests."""
    return os.getenv("SPANNER_INSTANCE", "test-instance")


@pytest.fixture
def spanner_database_id() -> str:
    """Get Spanner database ID for tests."""
    test_id = str(uuid.uuid4()).replace("-", "")[:10]
    return f"test-db-{test_id}"


@pytest.fixture
def spanner_client(spanner_project_id: str) -> Client:
    """Create a Spanner client for tests."""
    return Client(project=spanner_project_id)


@pytest.fixture
def spanner_instance(spanner_client: Client, spanner_instance_id: str) -> Instance:
    """Get or create a Spanner instance for tests."""
    instance = spanner_client.instance(spanner_instance_id)

    # Only create the instance if using the emulator
    if USE_EMULATOR and not instance.exists():
        instance.create()

    return instance


@pytest.fixture
def spanner_database(
    spanner_instance: Instance, spanner_database_id: str
) -> Generator[Database, None, None]:
    """Create a test database and clean it up after tests."""
    # Skip actual database creation if using mocks
    if USE_MOCK:
        from unittest.mock import MagicMock

        mock_db = MagicMock()
        yield mock_db
        return

    # Create database for real tests
    database = spanner_instance.database(spanner_database_id)

    if not database.exists():
        # Create database with a single DDL statement
        database.create()

        # Create test tables
        database.update_ddl(
            [
                """
            CREATE TABLE Organizations (
                OrganizationID STRING(36) NOT NULL,
                Name STRING(255) NOT NULL,
                Active BOOL NOT NULL,
                CreatedAt TIMESTAMP NOT NULL,
            ) PRIMARY KEY (OrganizationID)
            """,
                """
            CREATE TABLE Products (
                OrganizationID STRING(36) NOT NULL,
                ProductID STRING(36) NOT NULL,
                Name STRING(255) NOT NULL,
                Description STRING(2000),
                Category STRING(100),
                Stock INT64 NOT NULL,
                CreatedAt TIMESTAMP NOT NULL,
                UpdatedAt TIMESTAMP,
                Active BOOL NOT NULL,
                ListPrice NUMERIC NOT NULL,
                CostPrice NUMERIC,
                FOREIGN KEY (OrganizationID) REFERENCES Organizations(OrganizationID),
            ) PRIMARY KEY (OrganizationID, ProductID),
            INTERLEAVE IN PARENT Organizations ON DELETE CASCADE
            """,
                """
            CREATE TABLE Users (
                UserID STRING(36) NOT NULL,
                Email STRING(255) NOT NULL,
                FullName STRING(255) NOT NULL,
                Status STRING(20) NOT NULL,
                CreatedAt TIMESTAMP NOT NULL,
                Active BOOL NOT NULL,
            ) PRIMARY KEY (UserID)
            """,
                """
            CREATE TABLE OrganizationUsers (
                OrganizationID STRING(36) NOT NULL,
                UserID STRING(36) NOT NULL,
                Role STRING(20) NOT NULL,
                Status STRING(20) NOT NULL,
                CreatedAt TIMESTAMP NOT NULL,
                FOREIGN KEY (OrganizationID) REFERENCES Organizations(OrganizationID),
                FOREIGN KEY (UserID) REFERENCES Users(UserID),
            ) PRIMARY KEY (OrganizationID, UserID)
            """,
            ]
        ).result()

    yield database

    # Clean up after tests
    if not USE_EMULATOR:
        # Don't actually delete real databases
        pass
    else:
        # Safe to delete emulator databases
        database.drop()


@pytest.fixture
def spanner_session(spanner_database: Database) -> SpannerSession:
    """Create a SpannerSession for tests."""
    return SpannerSession(spanner_database)


@pytest.fixture
def test_organization(spanner_session: SpannerSession) -> Organization:
    """Create a test organization."""
    org = Organization(
        Name="Test Organization",
        Active=True,
    )
    spanner_session.save(org)
    return org


@pytest.fixture
def test_product(spanner_session: SpannerSession, test_organization: Organization) -> Product:
    """Create a test product."""
    product = Product(
        OrganizationID=test_organization.OrganizationID,
        Name="Test Product",
        Description="This is a test product",
        Category="Test",
        Stock=100,
        ListPrice=99.99,
        CostPrice=49.99,
        Active=True,
    )
    spanner_session.save(product)
    return product


@pytest.fixture
def test_user(spanner_session: SpannerSession) -> User:
    """Create a test user."""
    user = User(
        Email="test@example.com",
        FullName="Test User",
        Status="ACTIVE",
        Active=True,
    )
    spanner_session.save(user)
    return user


@pytest.fixture
def test_organization_user(
    spanner_session: SpannerSession, test_organization: Organization, test_user: User
) -> OrganizationUser:
    """Create a test organization-user relationship."""
    org_user = OrganizationUser(
        OrganizationID=test_organization.OrganizationID,
        UserID=test_user.UserID,
        Role="ADMIN",
        Status="ACTIVE",
    )
    spanner_session.save(org_user)
    return org_user
