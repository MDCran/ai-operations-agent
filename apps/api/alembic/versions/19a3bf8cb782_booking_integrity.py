"""Enforce appointment overlap protection and revision counters."""

import sqlalchemy as sa

from alembic import op

revision = "19a3bf8cb782"
down_revision = "6b575625cb47"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tickets", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("tasks", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.execute("""
        ALTER TABLE appointments ADD CONSTRAINT appointments_no_overlap
        EXCLUDE USING gist (
            organization_id WITH =,
            tstzrange(starts_at, ends_at, '[)') WITH &&
        ) WHERE (status = 'confirmed')
    """)


def downgrade():
    op.drop_constraint("appointments_no_overlap", "appointments")
    op.drop_column("tasks", "version")
    op.drop_column("tickets", "version")
