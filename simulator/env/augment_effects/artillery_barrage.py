"""
Artillery Barrage  (TFT16_Augment_RumbleCarry)

"Gain a Rumble. Your strongest Rumble gains +@MaxRange@ Range and
 constantly fires missiles at enemies, increased with Attack Speed."

effects = {"MaxRange": 7}

Offered at any augment selection round (no round restriction).
This augment exists in the crawled JSON data — no synthetic entry needed.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from simulator.env.augment_effects._base import AugmentResult, _get_all_champions, _grant_champion

if TYPE_CHECKING:
    from simulator.core.champion import Champion
    from simulator.core.player import Player


AUGMENT_ID = "TFT16_Augment_RumbleCarry"

# No synthetic Augment object needed — exists in JSON data.
SYNTHETIC_AUGMENT = None

# No round restriction — can appear at any augment selection round.
ELIGIBLE_ROUNDS = None


# ---------------------------------------------------------------------------
# Rumble-specific helpers
# ---------------------------------------------------------------------------

def _find_rumbles(player: "Player") -> List["Champion"]:
    """Return all Rumble units owned by the player."""
    return [c for c in _get_all_champions(player) if c.name == "Rumble"]


def _strongest_rumble(player: "Player") -> Optional["Champion"]:
    """
    Return the player's strongest Rumble.

    Priority:
      1. Board champions before bench champions (actively fighting).
      2. Higher star level wins.
      3. Ties broken by higher current HP (more durable).
    """
    board_rumbles = [c for c in player.board.get_all_champions() if c.name == "Rumble"]
    bench_rumbles = [c for c in player.bench if c is not None and c.name == "Rumble"]

    for pool in (board_rumbles, bench_rumbles):
        if pool:
            return max(pool, key=lambda c: (c.stars, c.current_hp))

    return None


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------

def _on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Grant a Rumble unit when the augment is chosen."""
    granted = _grant_champion(player, "Rumble")
    if granted:
        return AugmentResult(success=True, grants=["Rumble"])
    return AugmentResult(success=False)


def _passive(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """
    Before each combat, find the strongest Rumble and apply bonuses.

    Stats are mutated directly on the champion instance (not the shared
    data template).  The reset loop restores base values each call so
    bonuses never stack across successive passive applications.

    Attributes modified on the Champion instance:
        attack_range    — increased by MaxRange (e.g. +7 hexes)
        _fires_missiles — (bool) signals combat engine to enable the
                          continuous missile barrage scaled by attack_speed
    """
    bonus_range: int = int(effects.get("MaxRange", 0))

    for rumble in _find_rumbles(player):
        rumble.attack_range = rumble.data.stats.attack_range or 1
        rumble._fires_missiles = False

    target = _strongest_rumble(player)
    if target is None:
        return AugmentResult(success=False)

    target.attack_range += bonus_range
    target._fires_missiles = True
    return AugmentResult(success=True, affected_champions=[target.name])


HOOKS: Dict[str, Any] = {
    "on_select": _on_select,
    "passive":   _passive,
}
