"""Unknown player attributes and durable import identities."""

from alembic import op
import sqlalchemy as sa

revision = "a72b60469e31"
down_revision = "950ea0f88807"
branch_labels = None
depends_on = None

FIELDS = {
    "team_id": sa.Integer(),
    "positions": sa.String(60),
    "dominant_foot": sa.String(10),
    "age_group": sa.String(12),
    "preferred_times": sa.String(200),
    "availability": sa.String(20),
    "skill": sa.Float(),
    "jersey": sa.Integer(),
}


def upgrade():
    # SQLite recreates this table; explicitly retain its unnamed skill constraint.
    with op.batch_alter_table(
        "players", table_args=(sa.CheckConstraint("skill >= 1 AND skill <= 10"),)
    ) as batch:
        for name, kind in FIELDS.items():
            batch.alter_column(name, existing_type=kind, nullable=True)
    op.create_table(
        "player_imports",
        sa.Column("import_id", sa.String(36), primary_key=True),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("source_key", sa.String(64), nullable=False),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id"), nullable=False, unique=True),
        sa.Column("source_fingerprint", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_player_imports_source", "player_imports", ["source"])
    op.create_index("ix_player_imports_source_key", "player_imports", ["source_key"])


def downgrade():
    players = sa.table("players", *(sa.column(name) for name in FIELDS))
    if op.get_bind().scalar(
        sa.select(sa.func.count())
        .select_from(players)
        .where(sa.or_(*(players.c[name].is_(None) for name in FIELDS)))
    ):
        raise RuntimeError("Complete unknown player fields before downgrading; no values will be invented")
    op.drop_table("player_imports")
    with op.batch_alter_table(
        "players", table_args=(sa.CheckConstraint("skill >= 1 AND skill <= 10"),)
    ) as batch:
        for name, kind in FIELDS.items():
            batch.alter_column(name, existing_type=kind, nullable=False)
