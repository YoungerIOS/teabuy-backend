"""add_checkin_records

Revision ID: b1c4f8d7e2a1
Revises: 9f31a7c2c1de
Create Date: 2026-04-14
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b1c4f8d7e2a1"
down_revision = "9f31a7c2c1de"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "checkin_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("checkin_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "checkin_date", name="uq_checkin_user_date"),
    )
    op.create_index(op.f("ix_checkin_records_user_id"), "checkin_records", ["user_id"], unique=False)
    op.create_index(op.f("ix_checkin_records_checkin_date"), "checkin_records", ["checkin_date"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_checkin_records_checkin_date"), table_name="checkin_records")
    op.drop_index(op.f("ix_checkin_records_user_id"), table_name="checkin_records")
    op.drop_table("checkin_records")
