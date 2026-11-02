"""Indexes for directory search: trigram text, name order, practice places.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-02 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0007'
down_revision: Union[str, Sequence[str], None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    # Specialties and tags are JSON, not JSONB, so they cannot be indexed
    # directly. One immutable string of every searchable value gives the trigram
    # index something to cover. chr(31) keeps values apart, though the query
    # still checks each value on its own so a match can never span two.
    op.execute(
        """
        CREATE FUNCTION directory_search_text(name text, specialties json, tags json)
        RETURNS text
        LANGUAGE sql IMMUTABLE PARALLEL SAFE
        AS $$
            SELECT concat_ws(
                chr(31),
                lower(name),
                (SELECT string_agg(lower(v), chr(31))
                   FROM json_array_elements_text(
                       CASE WHEN json_typeof(specialties) = 'array' THEN specialties ELSE '[]'::json END
                   ) AS v),
                (SELECT string_agg(lower(v), chr(31))
                   FROM json_array_elements_text(
                       CASE WHEN json_typeof(tags) = 'array' THEN tags ELSE '[]'::json END
                   ) AS v)
            )
        $$
        """
    )
    op.execute(
        "CREATE INDEX ix_worker_profiles_search_trgm ON worker_profiles "
        "USING gin (directory_search_text(display_name, specialties, tags) gin_trgm_ops)"
    )
    op.execute(
        'CREATE INDEX ix_worker_profiles_name_c ON worker_profiles '
        '((lower(display_name) COLLATE "C"), user_id)'
    )
    op.create_index(
        'ix_saved_places_practice_lat_lng',
        'saved_places',
        ['latitude', 'longitude'],
        postgresql_where="visibility = 'practice' AND latitude IS NOT NULL AND longitude IS NOT NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_saved_places_practice_lat_lng', table_name='saved_places')
    op.execute("DROP INDEX ix_worker_profiles_name_c")
    op.execute("DROP INDEX ix_worker_profiles_search_trgm")
    op.execute("DROP FUNCTION directory_search_text(text, json, json)")
