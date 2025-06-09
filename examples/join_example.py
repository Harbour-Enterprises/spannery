"""
Example demonstrating JOIN and relationship features in Spannery.

This example uses the Organizations, OrganizationUsers, and Users tables
to show how to define models with relationships and perform JOINs.
"""

import os
from datetime import datetime, timezone

from google.cloud import spanner
from google.cloud.spanner_v1.database import Database

from spannery import (
    BooleanField,
    DateTimeField,
    ForeignKeyField,
    JoinType,
    JsonField,
    SpannerModel,
    SpannerSession,
    StringField,
)


# Define models with relationships
class Organization(SpannerModel):
    __tablename__ = "Organizations"

    OrganizationID = StringField(primary_key=True)
    Name = StringField(max_length=255, nullable=False)
    Description = StringField(max_length=1000)
    Email = StringField(max_length=255, nullable=False)
    Phone = StringField(max_length=20)
    Website = StringField(max_length=255)
    Address = StringField(max_length=500)
    LogoURL = StringField(max_length=1000)
    CreatedAt = DateTimeField(nullable=False, auto_now_add=True)
    UpdatedAt = DateTimeField(auto_now=True)
    Status = StringField(max_length=20, nullable=False)
    PrimaryContactUserID = StringField(max_length=36)
    CNPJ = StringField(max_length=18)
    CNPJData = JsonField()
    BrandData = JsonField()
    Active = BooleanField(nullable=False)


class User(SpannerModel):
    __tablename__ = "Users"

    UserID = StringField(primary_key=True)
    Email = StringField(max_length=255, nullable=False)
    FullName = StringField(max_length=255, nullable=False)
    Role = StringField(max_length=20)
    CreatedAt = DateTimeField(nullable=False, auto_now_add=True)
    LastLogin = DateTimeField()
    Status = StringField(max_length=20, nullable=False)
    AvatarURL = StringField(max_length=1000)
    FirebaseUID = StringField(max_length=128)
    EmailVerified = BooleanField()
    Provider = StringField(max_length=50)
    UpdatedAt = DateTimeField(auto_now=True)
    Active = BooleanField(nullable=False)


class OrganizationUser(SpannerModel):
    __tablename__ = "OrganizationUsers"

    # Use ForeignKeyField to define relationships
    OrganizationID = ForeignKeyField("Organization", primary_key=True, related_name="users")
    UserID = ForeignKeyField("User", primary_key=True, related_name="organizations")
    Role = StringField(max_length=20, nullable=False)
    CreatedAt = DateTimeField(nullable=False, auto_now_add=True)
    Status = StringField(max_length=20, nullable=False)


def main():
    # Initialize Spanner client
    project_id = os.environ.get("SPANNER_PROJECT_ID")
    instance_id = os.environ.get("SPANNER_INSTANCE_ID")
    database_id = os.environ.get("SPANNER_DATABASE_ID")

    client = spanner.Client(project=project_id)
    instance = client.instance(instance_id)
    database = instance.database(database_id)

    # Create Spannery session
    session = SpannerSession(database)

    # Example 1: Get all users for a specific organization using JOIN
    print("Example 1: Get all users for an organization using JOIN")
    organization_id = "your-organization-id"  # Replace with actual ID

    # Query with JOIN
    users_in_org = (
        session.query(OrganizationUser)
        .join("User", "UserID", "UserID", join_type=JoinType.INNER)
        .filter(OrganizationID=organization_id, Status="ACTIVE")
        .all()
    )

    for org_user in users_in_org:
        # Get the related User model
        user = session.get_related(org_user, "UserID")
        print(f"User: {user.FullName}, Role: {org_user.Role}")

    # Example 2: Get all organizations for a specific user with JOIN
    print("\nExample 2: Get all organizations for a user with JOIN")
    user_id = "your-user-id"  # Replace with actual ID

    user_orgs = (
        session.query(OrganizationUser)
        .join("Organization", "OrganizationID", "OrganizationID")
        .filter(UserID=user_id)
        .all()
    )

    for org_user in user_orgs:
        organization = session.get_related(org_user, "OrganizationID")
        print(f"Organization: {organization.Name}, Role: {org_user.Role}")

    # Example 3: Use the join_query convenience method
    print("\nExample 3: Using join_query convenience method")

    users_query = session.join_query(OrganizationUser, "User", "UserID", "UserID")

    active_users = users_query.filter(Status="ACTIVE").all()
    for org_user in active_users:
        user = session.get_related(org_user, "UserID")
        print(f"Active user: {user.FullName}")

    # Example 4: Get User and Organization in a single query with multiple JOINs
    print("\nExample 4: Multiple JOINs in a single query")

    # Note: This example shows the syntax for multiple joins,
    # but results handling would require custom processing to
    # reconstruct the full object graph

    multi_join_query = (
        session.query(OrganizationUser)
        .join("User", "UserID", "UserID", join_type=JoinType.INNER)
        .join("Organization", "OrganizationID", "OrganizationID", join_type=JoinType.INNER)
        .filter(Status="ACTIVE")
        .all()
    )

    for org_user in multi_join_query:
        user = session.get_related(org_user, "UserID")
        organization = session.get_related(org_user, "OrganizationID")
        print(f"User: {user.FullName}, Organization: {organization.Name}")


if __name__ == "__main__":
    main()
