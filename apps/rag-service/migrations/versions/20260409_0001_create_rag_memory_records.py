"""create rag memory records

Revision ID: 20260409_0001
Revises: 
Create Date: 2026-04-09 18:30:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260409_0001"
down_revision = None
branch_labels = None
depends_on = None


TABLE_NAME = "rag_memory_records"
EMBEDDING_DIMENSION = 384


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            memory_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            captured_at TEXT,
            searchable_text TEXT NOT NULL DEFAULT '',
            embedding vector({EMBEDDING_DIMENSION}),
            document JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        f"""
        ALTER TABLE {TABLE_NAME}
        ADD COLUMN IF NOT EXISTS embedding vector({EMBEDDING_DIMENSION})
        """
    )
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_user_id
        ON {TABLE_NAME} (user_id)
        """
    )
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_user_id_captured_at
        ON {TABLE_NAME} (user_id, captured_at DESC, memory_id DESC)
        """
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS idx_{TABLE_NAME}_user_id_captured_at")
    op.execute(f"DROP INDEX IF EXISTS idx_{TABLE_NAME}_user_id")
    op.execute(f"DROP TABLE IF EXISTS {TABLE_NAME}")
