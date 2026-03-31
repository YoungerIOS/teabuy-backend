"""notification_contract_fields

Revision ID: 9f31a7c2c1de
Revises: 32d8f6f9b8f0
Create Date: 2026-03-31
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9f31a7c2c1de"
down_revision = "32d8f6f9b8f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("notifications", sa.Column("read_at", sa.DateTime(), nullable=True))
    op.add_column("notifications", sa.Column("link_type", sa.String(length=30), nullable=False, server_default=""))
    op.add_column("notifications", sa.Column("link_value", sa.String(length=200), nullable=False, server_default=""))
    op.add_column("notifications", sa.Column("type", sa.String(length=30), nullable=False, server_default="system"))
    op.add_column("notifications", sa.Column("priority", sa.Integer(), nullable=False, server_default="0"))
    op.add_column(
        "notifications",
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index(
        "ix_notifications_user_read_created",
        "notifications",
        ["user_id", "is_read", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_user_read_created", table_name="notifications")
    op.drop_column("notifications", "updated_at")
    op.drop_column("notifications", "priority")
    op.drop_column("notifications", "type")
    op.drop_column("notifications", "link_value")
    op.drop_column("notifications", "link_type")
    op.drop_column("notifications", "read_at")
