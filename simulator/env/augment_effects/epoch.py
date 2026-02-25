"""
Epoch  (TFT16_Augment_Epoch)

"Now, and at the start of every stage, gain 4 XP and 3 free rerolls."

effects = {"XPAmount": 4, "RerollCount": 3}

Offered only at 2-1 (round 10).
Not present in the crawled JSON — a synthetic Augment object is provided.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, FrozenSet

from data_loader.data_models import Augment
from simulator.env.augment_effects._base import AugmentResult, _epoch_apply

if TYPE_CHECKING:
    from simulator.core.player import Player


AUGMENT_ID = "TFT16_Augment_Epoch"

SYNTHETIC_AUGMENT = Augment(
    augment_id=AUGMENT_ID,
    name="Epoch",
    description="Now, and at the start of every stage, gain 4 XP and 3 free rerolls.",
    effects={"XPAmount": 4, "RerollCount": 3},
    associated_traits=[],
    incompatible_traits=[],
    tags=[],
    is_unique=False,
    icon="",
)

# Offered only at 2-1 (round 10).
ELIGIBLE_ROUNDS: FrozenSet[int] = frozenset({10})


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------

def _on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    return _epoch_apply(player, effects)


def _on_stage_start(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    return _epoch_apply(player, effects)


HOOKS: Dict[str, Any] = {
    "on_select":      _on_select,
    "on_stage_start": _on_stage_start,
}
