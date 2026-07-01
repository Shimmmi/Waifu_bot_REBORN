"""Unit tests for player mail service."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from waifu_bot.db.models import Player, PlayerMail, PlayerMailStatus
from waifu_bot.services import player_mail_service as mail_svc


@pytest.mark.asyncio
async def test_assert_same_guild_rejects_self():
    session = AsyncMock()
    with pytest.raises(ValueError, match="cannot_mail_self"):
        await mail_svc._assert_same_guild(session, 1, 1)


@pytest.mark.asyncio
async def test_send_mail_deducts_gold_and_creates_row():
    session = AsyncMock()
    sender = Player(id=1, gold=1000)
    recipient = Player(id=2, gold=0)

    async def _get(model, pk):
        if pk == 1:
            return sender
        if pk == 2:
            return recipient
        return None

    session.get = AsyncMock(side_effect=_get)

    s_mem = MagicMock(guild_id=10)
    r_mem = MagicMock(guild_id=10)
    mem_results = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=s_mem)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=r_mem)),
    ]
    count_results = [
        MagicMock(scalar=MagicMock(return_value=0)),
        MagicMock(scalar=MagicMock(return_value=0)),
    ]
    session.execute = AsyncMock(side_effect=[*mem_results, *count_results])
    session.flush = AsyncMock()

    def _add(obj):
        obj.id = 99

    session.add = MagicMock(side_effect=_add)
    session.commit = AsyncMock()

    async def _refresh(obj):
        if getattr(obj, "id", None) is None:
            obj.id = 99

    session.refresh = AsyncMock(side_effect=_refresh)

    with patch(
        "waifu_bot.services.player_mail_service.get_game_config_map",
        new_callable=AsyncMock,
        return_value={
            "mail.max_body_length": "500",
            "mail.max_gold_per_send": "100000",
            "mail.max_inbox": "50",
            "mail.daily_send_limit": "20",
        },
    ):
        with patch.object(mail_svc, "_assert_can_send_mail", new_callable=AsyncMock):
            result = await mail_svc.send_mail(
                session, 1, 2, body_text="Привет", gold_amount=100, inventory_item_id=None
            )

    assert sender.gold == 900
    session.add.assert_called_once()
    added = session.add.call_args[0][0]
    assert isinstance(added, PlayerMail)
    assert added.gold_amount == 100
    assert added.body_text == "Привет"
    assert result["gold_amount"] == 100


@pytest.mark.asyncio
async def test_claim_mail_transfers_gold():
    session = AsyncMock()
    mail = PlayerMail(
        id=5,
        sender_player_id=1,
        recipient_player_id=2,
        body_text="x",
        gold_amount=250,
        inventory_item_id=None,
        status=PlayerMailStatus.READ,
    )
    recipient = Player(id=2, gold=100)
    sender = Player(id=1, username="alice")

    session.get = AsyncMock(side_effect=lambda model, pk: {
        5: mail,
        2: recipient,
        1: sender,
    }.get(pk))
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    out = await mail_svc.claim_mail(session, 2, 5)
    assert recipient.gold == 350
    assert mail.status == PlayerMailStatus.CLAIMED
    assert mail.claimed_at is not None
    assert out["status"] == "claimed"


@pytest.mark.asyncio
async def test_unread_count():
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=3)
    count = await mail_svc.unread_count(session, 42)
    assert count == 3


@pytest.mark.asyncio
async def test_has_pending_rewards():
    mail = PlayerMail(
        id=1,
        sender_player_id=1,
        recipient_player_id=2,
        gold_amount=100,
        status=PlayerMailStatus.READ,
    )
    assert mail_svc._has_pending_rewards(mail) is True
    mail.status = PlayerMailStatus.CLAIMED
    assert mail_svc._has_pending_rewards(mail) is False


@pytest.mark.asyncio
async def test_delete_mail_auto_claims_before_soft_delete():
    session = AsyncMock()
    mail = PlayerMail(
        id=7,
        sender_player_id=1,
        recipient_player_id=2,
        body_text="gift",
        gold_amount=50,
        inventory_item_id=None,
        status=PlayerMailStatus.READ,
    )

    async def _get(model, pk):
        if pk == 7:
            return mail
        if pk == 2:
            return Player(id=2, gold=0)
        if pk == 1:
            return Player(id=1, username="bob")
        return None

    session.get = AsyncMock(side_effect=_get)
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    with patch.object(mail_svc, "claim_mail", new_callable=AsyncMock) as claim_mock:
        await mail_svc.delete_mail(session, 2, 7)
        claim_mock.assert_awaited_once_with(session, 2, 7)

    assert mail.recipient_deleted is True
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_mail_badge_show_when_unread_or_pending():
    session = AsyncMock()
    session.scalar = AsyncMock(side_effect=[2, 0])
    badge = await mail_svc.mail_badge(session, 99)
    assert badge == {"unread": 2, "pending_rewards": 0, "show": True}

    session.scalar = AsyncMock(side_effect=[0, 1])
    badge2 = await mail_svc.mail_badge(session, 99)
    assert badge2["show"] is True
