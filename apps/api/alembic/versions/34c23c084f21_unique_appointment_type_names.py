"""Require appointment type names to be unique within an organization."""

from alembic import op

revision = "34c23c084f21"
down_revision = "19a3bf8cb782"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint(
        "uq_appointment_type_org_name",
        "appointment_types",
        ["organization_id", "name"],
    )


def downgrade():
    op.drop_constraint("uq_appointment_type_org_name", "appointment_types")
