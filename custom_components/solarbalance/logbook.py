"""Logbook descriptions for SolarBalance bus events."""

from collections.abc import Callable

from homeassistant.core import Event, HomeAssistant, callback

from .const import (
    DOMAIN,
    EVENT_FORCE_CHARGE,
    EVENT_MODE_CHANGED,
    EVENT_SHEDDING,
    EVENT_TEMPO_RED_DAY,
)

_NAME = "SolarBalance"

# Bilingual messages, picked by the HA language at describe time.
_MSG: dict[str, dict[str, str]] = {
    "fr": {
        "mode": "mode {old} → {new}",
        "shed_started": "délestage priorité batterie démarré ({loads})",
        "shed_stopped": "délestage priorité batterie terminé",
        "red_started": "jour rouge Tempo à venir — pré-charge des batteries",
        "red_stopped": "fin de la pré-charge avant jour rouge",
        "fc_started": "charge forcée démarrée ({loads})",
        "fc_stopped": "charge forcée terminée",
    },
    "en": {
        "mode": "mode {old} → {new}",
        "shed_started": "battery-priority shedding started ({loads})",
        "shed_stopped": "battery-priority shedding ended",
        "red_started": "upcoming Tempo red day — pre-charging batteries",
        "red_stopped": "red-day pre-charge ended",
        "fc_started": "force charge started ({loads})",
        "fc_stopped": "force charge ended",
    },
}


@callback
def async_describe_events(
    hass: HomeAssistant,
    async_describe_event: Callable[[str, str, Callable[[Event], dict[str, str]]], None],
) -> None:
    """Register human-readable logbook descriptions for SolarBalance events."""

    def _lang() -> dict[str, str]:
        return _MSG["fr" if (hass.config.language or "en").startswith("fr") else "en"]

    @callback
    def describe_mode(event: Event) -> dict[str, str]:
        m = _lang()["mode"].format(old=event.data.get("old"), new=event.data.get("new"))
        return {"name": _NAME, "message": m}

    @callback
    def describe_shed(event: Event) -> dict[str, str]:
        t = _lang()
        if event.data.get("action") == "started":
            loads = ", ".join(event.data.get("loads") or []) or "—"
            return {"name": _NAME, "message": t["shed_started"].format(loads=loads)}
        return {"name": _NAME, "message": t["shed_stopped"]}

    @callback
    def describe_red(event: Event) -> dict[str, str]:
        t = _lang()
        key = "red_started" if event.data.get("action") == "started" else "red_stopped"
        return {"name": _NAME, "message": t[key]}

    @callback
    def describe_force_charge(event: Event) -> dict[str, str]:
        t = _lang()
        if event.data.get("action") == "started":
            loads = ", ".join(event.data.get("loads") or []) or "—"
            return {"name": _NAME, "message": t["fc_started"].format(loads=loads)}
        return {"name": _NAME, "message": t["fc_stopped"]}

    async_describe_event(DOMAIN, EVENT_MODE_CHANGED, describe_mode)
    async_describe_event(DOMAIN, EVENT_SHEDDING, describe_shed)
    async_describe_event(DOMAIN, EVENT_TEMPO_RED_DAY, describe_red)
    async_describe_event(DOMAIN, EVENT_FORCE_CHARGE, describe_force_charge)
