"""Add item_art table for tiered webp images.

Revision ID: 0017_item_art_webp
Revises: 0016_exp_notify
Create Date: 2026-02-02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0017_item_art"
down_revision: str | None = "0016_exp_notify"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "item_art",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("art_key", sa.String(length=64), nullable=False),
        sa.Column("tier", sa.Integer(), nullable=False),
        sa.Column("relative_path", sa.String(length=255), nullable=False),
        sa.Column("mime", sa.String(length=64), nullable=False, server_default=sa.text("'image/webp'")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("tier >= 1 AND tier <= 10", name="check_item_art_tier_range"),
        sa.UniqueConstraint("art_key", "tier", name="uq_item_art_key_tier"),
    )

    # Seed default mapping for tiered .webp assets.
    # Files are expected at: /webapp/assets/items_webp/<art_key>/t1.webp ... t10.webp
    art_keys = [
        "weapon_sword_1h",
        "weapon_sword_2h",
        "weapon_axe_1h",
        "weapon_axe_2h",
        "weapon_bow",
        "weapon_staff",
        "armor",
        "shield",
        "ring",
        "amulet",
        "generic",
    ]

    rows: list[dict] = []
    for k in art_keys:
        for t in range(1, 11):
            rows.append(
                {
                    "art_key": k,
                    "tier": t,
                    "relative_path": f"items_webp/{k}/t{t}.webp",
                    "mime": "image/webp",
                    "enabled": True,
                }
            )

    op.bulk_insert(
        sa.table(
            "item_art",
            sa.column("art_key", sa.String()),
            sa.column("tier", sa.Integer()),
            sa.column("relative_path", sa.String()),
            sa.column("mime", sa.String()),
            sa.column("enabled", sa.Boolean()),
        ),
        rows,
    )


def downgrade() -> None:
    op.drop_table("item_art")

