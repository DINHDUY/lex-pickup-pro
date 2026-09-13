"""Provider-neutral command receipts, ID counters and reminder leases."""

import sqlalchemy as sa

from alembic import op

revision = "b498e32f471a"
down_revision = "a72b60469e31"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "storage_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("counters", sa.JSON(), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
    )
    op.create_table(
        "command_receipts",
        sa.Column("command_id", sa.String(64), primary_key=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "reminder_dispatches",
        sa.Column("dispatch_id", sa.String(64), primary_key=True),
        sa.Column("match_id", sa.Integer(), sa.ForeignKey("matches.id"), nullable=False),
        sa.Column("owner", sa.String(36), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_table("reminder_dispatches")
    op.drop_table("command_receipts")
    op.drop_table("storage_state")
