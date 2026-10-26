"""oauth accounts for Noiseport / OIDC single sign-on

Revision ID: 0002_oauth_accounts
Revises: 0001_initial
Create Date: 2026-10-26

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from fastapi_users_db_sqlalchemy.generics import GUID

revision: str = "0002_oauth_accounts"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("user", sa.Column("display_name", sa.String(length=255), nullable=True))
    op.create_table(
        "oauth_account",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("user_id", GUID(), nullable=False),
        sa.Column("oauth_name", sa.String(length=100), nullable=False),
        sa.Column("access_token", sa.String(length=1024), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=True),
        sa.Column("refresh_token", sa.String(length=1024), nullable=True),
        sa.Column("account_id", sa.String(length=320), nullable=False),
        sa.Column("account_email", sa.String(length=320), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="cascade"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("oauth_name", "account_id", name="uq_oauth_account_provider_sub"),
    )
    op.create_index(op.f("ix_oauth_account_oauth_name"), "oauth_account", ["oauth_name"])
    op.create_index(op.f("ix_oauth_account_account_id"), "oauth_account", ["account_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_oauth_account_account_id"), table_name="oauth_account")
    op.drop_index(op.f("ix_oauth_account_oauth_name"), table_name="oauth_account")
    op.drop_table("oauth_account")
    op.drop_column("user", "display_name")
