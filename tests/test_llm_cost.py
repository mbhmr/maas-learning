"""Cost of one call at list price: cached input and flex are counted, not guessed."""
from src.llm import cost_usd


def test_plain_call():
    assert abs(cost_usd("gpt-5.4-mini", 1_000_000, 0) - 0.75) < 1e-9


def test_cached_input_costs_its_share():
    # 1M input of which half cached: 0.5 * 0.75 + 0.5 * 0.75 * 0.10
    assert abs(cost_usd("gpt-5.4-mini", 1_000_000, 0, cached_tokens=500_000) - 0.4125) < 1e-9


def test_flex_is_half():
    assert abs(cost_usd("gpt-5.4-mini", 0, 1_000_000, tier="flex") - 2.25) < 1e-9
    assert abs(cost_usd("gpt-5.4-mini", 0, 1_000_000, tier="default") - 4.50) < 1e-9


def test_unknown_model():
    assert cost_usd("gpt-9", 10, 10) is None
