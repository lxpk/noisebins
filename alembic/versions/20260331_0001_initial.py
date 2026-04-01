"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-03-31

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("hashed_password", sa.String(length=1024), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_superuser", sa.Boolean(), nullable=False),
        sa.Column("is_verified", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_email"), "user", ["email"], unique=True)

    op.create_table(
        "noiseplaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("photo_ref", sa.String(length=512), nullable=True),
        sa.Column("parent_place_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("maintainer_name", sa.String(length=255), nullable=True),
        sa.Column("maintainer_email", sa.String(length=255), nullable=True),
        sa.Column("group_maintainer", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["parent_place_id"], ["noiseplaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "noisebins",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("noisecode", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("contents_text", sa.Text(), nullable=True),
        sa.Column("group_maintainer", sa.String(length=255), nullable=True),
        sa.Column("maintainer_name", sa.String(length=255), nullable=True),
        sa.Column("maintainer_email", sa.String(length=255), nullable=True),
        sa.Column("maintainer_phone", sa.String(length=255), nullable=True),
        sa.Column("maintainer_discord", sa.String(length=255), nullable=True),
        sa.Column("intent", sa.String(length=64), nullable=True),
        sa.Column("limbo_after", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("shelf_hint", sa.String(length=255), nullable=True),
        sa.Column("noiseplace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("claimed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("search_vector", postgresql.TSVECTOR(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["claimed_by_user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["noiseplace_id"], ["noiseplaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("noisecode", name="uq_noisebins_noisecode"),
    )
    op.create_index(op.f("ix_noisebins_noisecode"), "noisebins", ["noisecode"])

    op.create_table(
        "bin_photos",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bin_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("blob_key", sa.String(length=512), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["bin_id"], ["noisebins.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "noisethings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_bin_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("photo_blob_key", sa.String(length=512), nullable=True),
        sa.Column("barcode", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["parent_bin_id"], ["noisebins.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "content_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bin_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("diff", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["bin_id"], ["noisebins.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION noisebins_noisebins_search_vector_update()
            RETURNS trigger AS $$
            BEGIN
              NEW.search_vector :=
                to_tsvector('english',
                  coalesce(NEW.title, '') || ' ' ||
                  coalesce(NEW.description, '') || ' ' ||
                  coalesce(NEW.details, '') || ' ' ||
                  coalesce(NEW.contents_text, ''));
              RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
    )
    op.execute(
        sa.text(
            """
            DROP TRIGGER IF EXISTS noisebins_search_vector_trigger ON noisebins;
            CREATE TRIGGER noisebins_search_vector_trigger
            BEFORE INSERT OR UPDATE OF title, description, details, contents_text
            ON noisebins
            FOR EACH ROW
            EXECUTE FUNCTION noisebins_noisebins_search_vector_update();
            """
        )
    )

    op.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS ix_noisebins_search_vector
            ON noisebins USING GIN (search_vector);
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP TRIGGER IF EXISTS noisebins_search_vector_trigger ON noisebins;"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS noisebins_noisebins_search_vector_update();"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_noisebins_search_vector;"))
    op.drop_table("audit_logs")
    op.drop_table("content_history")
    op.drop_table("noisethings")
    op.drop_table("bin_photos")
    op.drop_table("noisebins")
    op.drop_table("noiseplaces")
    op.drop_index(op.f("ix_user_email"), table_name="user")
    op.drop_table("user")
