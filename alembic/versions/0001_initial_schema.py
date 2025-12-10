"""Initial schema."""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # players
    op.create_table(
        "players",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("first_name", sa.String(length=255), nullable=True),
        sa.Column("last_name", sa.String(length=255), nullable=True),
        sa.Column("language_code", sa.String(length=10), nullable=True),
        sa.Column("current_act", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("gold", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_active", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # main waifus
    op.create_table(
        "main_waifus",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("player_id", sa.BigInteger(), sa.ForeignKey("players.id"), unique=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("race", sa.Integer(), nullable=False),
        sa.Column("class", sa.Integer(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("experience", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("energy", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column("max_energy", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column("strength", sa.Integer(), nullable=False, server_default=sa.text("10")),
        sa.Column("agility", sa.Integer(), nullable=False, server_default=sa.text("10")),
        sa.Column("intelligence", sa.Integer(), nullable=False, server_default=sa.text("10")),
        sa.Column("endurance", sa.Integer(), nullable=False, server_default=sa.text("10")),
        sa.Column("charm", sa.Integer(), nullable=False, server_default=sa.text("10")),
        sa.Column("luck", sa.Integer(), nullable=False, server_default=sa.text("10")),
        sa.Column("max_hp", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column("current_hp", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("level >= 1 AND level <= 50", name="check_level_range"),
        sa.CheckConstraint("energy >= 0 AND energy <= max_energy", name="check_energy_range"),
        sa.CheckConstraint("current_hp >= 0 AND current_hp <= max_hp", name="check_hp_range"),
    )

    # hired waifus
    op.create_table(
        "hired_waifus",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("player_id", sa.BigInteger(), sa.ForeignKey("players.id")),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("race", sa.Integer(), nullable=False),
        sa.Column("class", sa.Integer(), nullable=False),
        sa.Column("rarity", sa.Integer(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("experience", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("strength", sa.Integer(), nullable=False, server_default=sa.text("10")),
        sa.Column("agility", sa.Integer(), nullable=False, server_default=sa.text("10")),
        sa.Column("intelligence", sa.Integer(), nullable=False, server_default=sa.text("10")),
        sa.Column("endurance", sa.Integer(), nullable=False, server_default=sa.text("10")),
        sa.Column("charm", sa.Integer(), nullable=False, server_default=sa.text("10")),
        sa.Column("luck", sa.Integer(), nullable=False, server_default=sa.text("10")),
        sa.Column("squad_position", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("level >= 1", name="check_hired_level"),
        sa.CheckConstraint(
            "squad_position IS NULL OR (squad_position >= 0 AND squad_position <= 6)",
            name="check_squad_position",
        ),
    )

    # items
    op.create_table(
        "items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("rarity", sa.Integer(), nullable=False),
        sa.Column("tier", sa.Integer(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("item_type", sa.Integer(), nullable=False),
        sa.Column("damage", sa.Integer(), nullable=True),
        sa.Column("attack_speed", sa.Integer(), nullable=True),
        sa.Column("weapon_type", sa.String(length=50), nullable=True),
        sa.Column("attack_type", sa.String(length=50), nullable=True),
        sa.Column("required_level", sa.Integer(), nullable=True),
        sa.Column("required_strength", sa.Integer(), nullable=True),
        sa.Column("required_agility", sa.Integer(), nullable=True),
        sa.Column("required_intelligence", sa.Integer(), nullable=True),
        sa.Column("affixes", sa.JSON(), nullable=True),
        sa.Column("base_value", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_legendary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("tier >= 1 AND tier <= 10", name="check_tier_range"),
        sa.CheckConstraint("level >= 1", name="check_item_level"),
    )

    # inventory items
    op.create_table(
        "inventory_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("player_id", sa.BigInteger(), sa.ForeignKey("players.id")),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id")),
        sa.Column("equipment_slot", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "equipment_slot IS NULL OR (equipment_slot >= 0 AND equipment_slot <= 6)",
            name="check_equipment_slot",
        ),
    )

    # dungeons
    op.create_table(
        "dungeons",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("act", sa.Integer(), nullable=False),
        sa.Column("dungeon_number", sa.Integer(), nullable=False),
        sa.Column("dungeon_type", sa.Integer(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("obstacle_count", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("base_experience", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("base_gold", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("act >= 1 AND act <= 5", name="check_act_range"),
        sa.CheckConstraint("dungeon_number >= 1 AND dungeon_number <= 5", name="check_dungeon_number"),
        sa.CheckConstraint("obstacle_count >= 1", name="check_obstacle_count"),
    )

    # monsters
    op.create_table(
        "monsters",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("dungeon_id", sa.Integer(), sa.ForeignKey("dungeons.id")),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("max_hp", sa.Integer(), nullable=False),
        sa.Column("damage", sa.Integer(), nullable=False),
        sa.Column("experience_reward", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("monster_type", sa.String(length=50), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # dungeon progress
    op.create_table(
        "dungeon_progress",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("player_id", sa.BigInteger(), sa.ForeignKey("players.id")),
        sa.Column("dungeon_id", sa.Integer(), sa.ForeignKey("dungeons.id")),
        sa.Column("is_completed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("current_monster_position", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("current_monster_hp", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # guilds
    op.create_table(
        "guilds",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=100), nullable=False, unique=True),
        sa.Column("tag", sa.String(length=10), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("level", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("experience", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("gold", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_recruiting", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("min_level_requirement", sa.Integer(), nullable=True),
        sa.Column("required_race", sa.Integer(), nullable=True),
        sa.Column("required_class", sa.Integer(), nullable=True),
        sa.Column("icon_path", sa.String(length=255), nullable=True),
        sa.Column("max_bank_items", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column("withdrawal_limit", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("level >= 1", name="check_guild_level"),
        sa.CheckConstraint("max_bank_items >= 0", name="check_max_bank_items"),
    )

    # guild members
    op.create_table(
        "guild_members",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("guild_id", sa.Integer(), sa.ForeignKey("guilds.id")),
        sa.Column("player_id", sa.BigInteger(), sa.ForeignKey("players.id"), unique=True),
        sa.Column("is_leader", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # guild bank
    op.create_table(
        "guild_bank",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("guild_id", sa.Integer(), sa.ForeignKey("guilds.id")),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # skills
    op.create_table(
        "skills",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("skill_type", sa.Integer(), nullable=False),
        sa.Column("tier", sa.Integer(), nullable=False),
        sa.Column("base_damage", sa.Integer(), nullable=True),
        sa.Column("energy_cost", sa.Integer(), nullable=True),
        sa.Column("cooldown", sa.Integer(), nullable=True),
        sa.Column("stat_bonus", sa.String(length=50), nullable=True),
        sa.Column("bonus_value", sa.Integer(), nullable=True),
        sa.Column("required_level", sa.Integer(), nullable=True),
        sa.Column("required_skill_id", sa.Integer(), sa.ForeignKey("skills.id"), nullable=True),
        sa.Column("max_level_act_1", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column("max_level_act_2", sa.Integer(), nullable=False, server_default=sa.text("6")),
        sa.Column("max_level_act_3", sa.Integer(), nullable=False, server_default=sa.text("9")),
        sa.Column("max_level_act_4", sa.Integer(), nullable=False, server_default=sa.text("12")),
        sa.Column("max_level_act_5", sa.Integer(), nullable=False, server_default=sa.text("15")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # waifu skills
    op.create_table(
        "waifu_skills",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("waifu_id", sa.Integer(), sa.ForeignKey("main_waifus.id")),
        sa.Column("skill_id", sa.Integer(), sa.ForeignKey("skills.id")),
        sa.Column("level", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("level >= 1", name="check_waifu_skill_level"),
    )

    # guild skills
    op.create_table(
        "guild_skills",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("guild_id", sa.Integer(), sa.ForeignKey("guilds.id")),
        sa.Column("skill_id", sa.Integer(), sa.ForeignKey("skills.id")),
        sa.Column("level", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("level >= 1", name="check_guild_skill_level"),
    )

    # battle logs
    op.create_table(
        "battle_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("player_id", sa.BigInteger(), sa.ForeignKey("players.id")),
        sa.Column("dungeon_id", sa.Integer(), sa.ForeignKey("dungeons.id")),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("event_data", sa.JSON(), nullable=True),
        sa.Column("monster_hp_before", sa.Integer(), nullable=True),
        sa.Column("monster_hp_after", sa.Integer(), nullable=True),
        sa.Column("player_hp_before", sa.Integer(), nullable=True),
        sa.Column("player_hp_after", sa.Integer(), nullable=True),
        sa.Column("message_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("battle_logs")
    op.drop_table("guild_skills")
    op.drop_table("waifu_skills")
    op.drop_table("skills")
    op.drop_table("guild_bank")
    op.drop_table("guild_members")
    op.drop_table("guilds")
    op.drop_table("dungeon_progress")
    op.drop_table("monsters")
    op.drop_table("dungeons")
    op.drop_table("inventory_items")
    op.drop_table("items")
    op.drop_table("hired_waifus")
    op.drop_table("main_waifus")
    op.drop_table("players")

