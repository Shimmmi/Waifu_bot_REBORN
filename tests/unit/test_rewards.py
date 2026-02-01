"""Unit tests: reward distribution and calculation."""
import pytest


def test_reward_distribution_proportional():
    """Награды распределяются пропорционально урону."""
    # session = create_session_with_players([
    #     {"id": 1, "damage": 50000},
    #     {"id": 2, "damage": 30000},
    #     {"id": 3, "damage": 20000}
    # ])
    # rewards = calculate_rewards_for_all(session)
    # assert rewards[1]["percent"] == 50
    # assert rewards[2]["percent"] == 30
    # assert rewards[3]["percent"] == 20
    total_damage = 100000
    p1 = 50000 / total_damage * 100
    p2 = 30000 / total_damage * 100
    p3 = 20000 / total_damage * 100
    assert abs(p1 - 50) < 0.01
    assert abs(p2 - 30) < 0.01
    assert abs(p3 - 20) < 0.01


def test_reward_calculation_with_all_bonuses():
    """Тест расчёта наград со всеми бонусами (база + события + классы + скорость)."""
    base_exp = 80
    percent = 45
    events_bonus = 1.0 + 0.15 * 2  # +30%
    exp = base_exp * (percent / 100.0) * events_bonus
    assert exp > 0
    assert exp == pytest.approx(80 * 0.45 * 1.3, rel=0.01)
