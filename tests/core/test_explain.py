"""Tests for the one-sentence explanation of a regulation tick."""

from custom_components.solarbalance.core.explain import explain_tick


def test_discharging_names_the_house_and_the_solar_share() -> None:
    # The exact question asked repeatedly during this week's incidents: why is the
    # fleet discharging 800 W?
    e = explain_tick(target_w=-800.0, house_w=900.0, pv_w=100.0)
    assert e.key == "discharge"
    assert "Discharging 800 W" in e.text
    assert "house draws 900 W" in e.text
    assert "solar covers 100 W" in e.text


def test_charging_names_the_surplus() -> None:
    e = explain_tick(target_w=700.0, house_w=300.0, pv_w=1200.0)
    assert e.key == "charge"
    assert "Charging 700 W" in e.text
    assert "1200 W" in e.text and "300 W" in e.text


def test_a_clamp_that_moved_the_target_is_named_in_plain_words() -> None:
    e = explain_tick(
        target_w=-825.0, house_w=830.0, pv_w=825.0, binding="no_charge_floor", binding_moved_w=300.0
    )
    assert e.key == "discharge_no_charge_floor"
    assert "own solar" in e.text
    assert "no_charge_floor" not in e.text, "jargon leaked into the sentence"


def test_a_clamp_that_merely_grazed_the_target_is_not_mentioned() -> None:
    # The cosmetic base<->no_charge_floor flip fixed in beta62: the floor sat 2 W
    # from the target. Naming it would suggest it decided something.
    e = explain_tick(
        target_w=-825.0, house_w=830.0, pv_w=825.0, binding="no_charge_floor", binding_moved_w=2.0
    )
    assert e.key == "discharge"
    assert "own solar" not in e.text


def test_an_unknown_binding_never_breaks_the_sentence() -> None:
    e = explain_tick(
        target_w=-500.0, house_w=600.0, pv_w=100.0, binding="something_new", binding_moved_w=400.0
    )
    assert e.text.endswith(".")
    assert "something_new" not in e.text


def test_a_missing_meter_is_answered_on_its_own_terms() -> None:
    # With no meter the house figure is derived from the missing measurement, so
    # quoting it would be precision that isn't there.
    e = explain_tick(target_w=0.0, house_w=900.0, pv_w=100.0, degraded=True)
    assert e.key == "degraded_no_meter"
    assert "900 W" not in e.text


def test_the_solar_fallback_says_what_it_is_doing_and_what_it_refuses() -> None:
    e = explain_tick(
        target_w=630.0,
        house_w=300.0,
        pv_w=1200.0,
        degraded=True,
        solar_fallback_active=True,
        solar_fallback_w=630.0,
    )
    assert e.key == "degraded_solar_fallback"
    assert "630 W" in e.text
    assert "never discharging" in e.text


def test_running_on_the_backup_meter_is_stated_up_front() -> None:
    e = explain_tick(target_w=-400.0, house_w=500.0, pv_w=100.0, grid_source="backup")
    assert e.text.startswith("Running on the backup grid sensor.")


def test_settle_explains_the_deliberate_inaction() -> None:
    e = explain_tick(target_w=-100.0, house_w=200.0, pv_w=100.0, settle_active=True)
    assert e.key == "settle_hold"
    assert "chasing the transient" in e.text


def test_holding_at_the_balance_point_says_so() -> None:
    """A tick that is silent on purpose must not look like a loop that stopped."""
    e = explain_tick(target_w=-100.0, house_w=200.0, pv_w=100.0, balance_settled=True)
    assert e.key == "balance_settled"
    assert "balance point" in e.text


def test_a_lost_meter_still_outranks_the_balance_hold() -> None:
    """Order matters: with no meter, "close enough to target" is not a fact we have."""
    e = explain_tick(target_w=0.0, house_w=200.0, pv_w=100.0, balance_settled=True, degraded=True)
    assert e.key == "degraded_no_meter"


def test_idle_is_described_as_balance_not_as_failure() -> None:
    e = explain_tick(target_w=5.0, house_w=400.0, pv_w=400.0)
    assert e.key == "idle"
    assert "balanced" in e.text


def test_near_full_and_anticipation_are_appended() -> None:
    e = explain_tick(target_w=200.0, house_w=300.0, pv_w=1500.0, near_full=True, anticipating=True)
    assert "nearly full" in e.text
    assert "pre-curtailing" in e.text


def test_params_carry_the_numbers_for_a_ui_to_reformat() -> None:
    e = explain_tick(target_w=-800.0, house_w=900.4, pv_w=100.6, binding="base")
    assert e.params["target_w"] == -800
    assert e.params["house_w"] == 900
    assert e.params["pv_w"] == 101
    assert e.params["binding"] == "base"
