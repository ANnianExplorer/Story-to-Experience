"""widen conversation provider call ref

Revision ID: 815545f43753
Revises: 52f7f13bdfcb
Create Date: 2026-10-31 20:33:47.173251

The gateway's request id is not a UUID (it is a 48-char provider string), so the
original 36-char column truncated real conversation turns. Widening a varchar is
backward compatible: older application builds keep working against the new
schema, which is what makes this safe to apply before deploying the new code.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '815545f43753'
down_revision: Union[str, None] = '52f7f13bdfcb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "conversation_turns",
        "provider_call_ref",
        existing_type=sa.String(length=36),
        type_=sa.String(length=128),
        existing_nullable=True,
    )


def downgrade() -> None:
    # Truncating data is not reversible; only shorten when every stored value fits.
    op.execute(
        "UPDATE conversation_turns SET provider_call_ref = NULL "
        "WHERE char_length(provider_call_ref) > 36"
    )
    op.alter_column(
        "conversation_turns",
        "provider_call_ref",
        existing_type=sa.String(length=128),
        type_=sa.String(length=36),
        existing_nullable=True,
    )
