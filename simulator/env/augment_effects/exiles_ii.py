"""
Exiles II  (TFT16_Augment_Exiles2)

"Your champions that start combat with no adjacent champions gain a
 30% max Health shield for 10 seconds."

effects = {"ShieldPercent": 0.30, "Duration": 10}

Offered only at 3-2 (round 20) or 4-2 (round 29).
Not present in the crawled JSON — a synthetic Augment object is provided.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, FrozenSet, List, Optional

from data_loader.data_models import Augment
from simulator.env.augment_effects._base import AugmentResult

if TYPE_CHECKING:
    from simulator.core.player import Player


AUGMENT_ID = "TFT16_Augment_Exiles2"

SYNTHETIC_AUGMENT = Augment(
    augment_id=AUGMENT_ID,
    name="Exiles II",
    description=(
        "Your champions that start combat with no adjacent champions "
        "gain a 30% max Health shield for 10 seconds."
    ),
    effects={"ShieldPercent": 0.30, "Duration": 10},
    associated_traits=[],
    incompatible_traits=[],
    tags=[],
    is_unique=False,
    icon="",
)

# Offered at 3-2 (round 20) or 4-2 (round 29).
ELIGIBLE_ROUNDS: FrozenSet[int] = frozenset({20, 29})


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------

def _passive(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """
    Before each combat, grant a shield to every board champion that has
    no friendly champion in an adjacent hex.

    Follows the same reset-then-apply pattern as Artillery Barrage so that
    shield values never stack across successive passive calls.

    Attribute set on the Champion instance:
        _shield (float) — flat HP shield absorbed before HP damage is taken.
                          combat.py reads this when computing team power.
                          Reset to 0.0 for non-isolated champions each call.
    """
    shield_pct: float = float(effects.get("ShieldPercent", 0.30))

    board_champions = list(player.board.get_all_champions())

    # Build a set of occupied positions for fast neighbour lookup.
    occupied: set = {champ.position for champ in board_champions if champ.position}

    # Reset shields first so a champion that moved next to an ally no longer
    # benefits from the previous round's shield.
    for champ in board_champions:
        champ._shield = 0.0

    shielded: List[str] = []

    for champ in board_champions:
        if champ.position is None:
            continue

        row, col = champ.position
        neighbors = player.board.get_hex_neighbors(row, col)

        # Isolated = none of the 6 adjacent hexes contain a friendly champion.
        if not any(pos in occupied for pos in neighbors):
            champ._shield = champ.max_hp * shield_pct
            shielded.append(champ.name)

    return AugmentResult(success=True, affected_champions=shielded)


HOOKS: Dict[str, Any] = {
    "passive": _passive,
}
