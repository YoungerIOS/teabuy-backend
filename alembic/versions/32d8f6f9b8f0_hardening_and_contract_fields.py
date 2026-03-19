"""hardening_and_contract_fields

Revision ID: 32d8f6f9b8f0
Revises: 7acb41dba265
Create Date: 2026-03-04
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "32d8f6f9b8f0"
down_revision = "7acb41dba265"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("role", sa.String(length=16), nullable=False, server_default="user"))
    op.create_index(op.f("ix_users_role"), "users", ["role"], unique=False)

    op.add_column("products", sa.Column("subtitle", sa.String(length=160), nullable=False, server_default=""))
    op.add_column("products", sa.Column("market_price_cent", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("products", sa.Column("sold_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("products", sa.Column("badge_primary", sa.String(length=40), nullable=False, server_default=""))
    op.add_column("products", sa.Column("badge_secondary", sa.String(length=40), nullable=False, server_default=""))

    op.add_column("orders", sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))

    op.add_column("payments", sa.Column("callback_no", sa.String(length=80), nullable=False, server_default=""))
    op.add_column("payments", sa.Column("callback_payload", sa.Text(), nullable=False, server_default="{}"))
    op.add_column("payments", sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))

    op.add_column("refunds", sa.Column("reviewed_by", sa.String(length=36), nullable=False, server_default=""))
    op.add_column("refunds", sa.Column("reviewed_at", sa.DateTime(), nullable=True))
    op.add_column("refunds", sa.Column("reject_reason", sa.Text(), nullable=False, server_default=""))

    op.create_table(
        "order_status_logs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("order_id", sa.String(length=36), nullable=False),
        sa.Column("from_status", sa.String(length=30), nullable=False),
        sa.Column("to_status", sa.String(length=30), nullable=False),
        sa.Column("operator_id", sa.String(length=36), nullable=False),
        sa.Column("operator_role", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_order_status_logs_order_id"), "order_status_logs", ["order_id"], unique=False)

    op.create_index("ix_orders_user_status_created", "orders", ["user_id", "status", "created_at"], unique=False)
    op.create_index("ix_payments_order_created", "payments", ["order_id", "created_at"], unique=False)
    op.create_index("ix_refunds_user_status_created", "refunds", ["user_id", "status", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_refunds_user_status_created", table_name="refunds")
    op.drop_index("ix_payments_order_created", table_name="payments")
    op.drop_index("ix_orders_user_status_created", table_name="orders")

    op.drop_index(op.f("ix_order_status_logs_order_id"), table_name="order_status_logs")
    op.drop_table("order_status_logs")

    op.drop_column("refunds", "reject_reason")
    op.drop_column("refunds", "reviewed_at")
    op.drop_column("refunds", "reviewed_by")

    op.drop_column("payments", "updated_at")
    op.drop_column("payments", "callback_payload")
    op.drop_column("payments", "callback_no")

    op.drop_column("orders", "updated_at")

    op.drop_column("products", "badge_secondary")
    op.drop_column("products", "badge_primary")
    op.drop_column("products", "sold_count")
    op.drop_column("products", "market_price_cent")
    op.drop_column("products", "subtitle")

    op.drop_index(op.f("ix_users_role"), table_name="users")
    op.drop_column("users", "role")
