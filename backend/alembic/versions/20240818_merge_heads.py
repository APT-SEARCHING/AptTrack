"""merge plan and google places branches

Revision ID: merge_google_plan_heads
Revises: plan_schema_update, google_places_tables
Create Date: 2025-08-19 00:05:00.000000

"""

# revision identifiers, used by Alembic.
revision = 'merge_google_plan_heads'
down_revision = ('plan_schema_update', 'google_places_tables')
branch_labels = None
depends_on = None


def upgrade():
    # no-op merge migration
    pass


def downgrade():
    # cannot unmerge heads; no-op
    pass


