"""
Augment registry — assembles all augment modules into the structures used
by the game engine.

Adding a new augment:
  1. Create simulator/env/augment_effects/<name>.py following the pattern of
     existing augment files (export AUGMENT_ID, HOOKS, SYNTHETIC_AUGMENT,
     ELIGIBLE_ROUNDS).
  2. Import the module here and add it to _AUGMENT_MODULES.
  That's it — everything else is assembled automatically.
"""
from __future__ import annotations

from typing import Any, Dict, FrozenSet, List, Optional, TYPE_CHECKING

from data_loader.data_models import Augment
from simulator.env.augment_effects._base import AugmentResult

# --- Import every augment module ---
from simulator.env.augment_effects import artillery_barrage
from simulator.env.augment_effects import exiles_ii
from simulator.env.augment_effects import epoch
from simulator.env.augment_effects import epoch_plus

if TYPE_CHECKING:
    from simulator.core.player import Player


# ---------------------------------------------------------------------------
# Auto-assembled structures
# ---------------------------------------------------------------------------

# List every augment module here.  Order only affects SYNTHETIC_AUGMENTS list.
_AUGMENT_MODULES = [
    artillery_barrage,
    exiles_ii,
    epoch,
    epoch_plus,
]

# AUGMENT_REGISTRY  maps  augment_id -> {event_name -> hook_fn}
AUGMENT_REGISTRY: Dict[str, Dict[str, Any]] = {
    mod.AUGMENT_ID: mod.HOOKS
    for mod in _AUGMENT_MODULES
}

# SYNTHETIC_AUGMENTS  — Augment objects for augments absent from the JSON data.
SYNTHETIC_AUGMENTS: List[Augment] = [
    mod.SYNTHETIC_AUGMENT
    for mod in _AUGMENT_MODULES
    if mod.SYNTHETIC_AUGMENT is not None
]

# AUGMENT_ELIGIBLE_ROUNDS  maps  augment_id -> frozenset of valid selection rounds.
# Augments absent from this dict are unrestricted (appear at every selection round).
AUGMENT_ELIGIBLE_ROUNDS: Dict[str, FrozenSet[int]] = {
    mod.AUGMENT_ID: mod.ELIGIBLE_ROUNDS
    for mod in _AUGMENT_MODULES
    if mod.ELIGIBLE_ROUNDS is not None
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def apply_augment_hook(
    player: "Player",
    augment: Augment,
    event: str,
) -> AugmentResult:
    """
    Fire a lifecycle hook for a single augment.

    Args:
        player:  The player who owns this augment.
        augment: The Augment data object.
        event:   One of "on_select", "passive", "on_stage_start".

    Returns:
        AugmentResult describing what happened.
        Returns AugmentResult(success=True) when the augment is not
        implemented or the event has no registered hook — safe to ignore.
    """
    handler = AUGMENT_REGISTRY.get(augment.augment_id)
    if handler is None:
        return AugmentResult(success=True)   # not implemented — silent no-op

    hook = handler.get(event)
    if hook is None:
        return AugmentResult(success=True)   # event not used by this augment

    return hook(player, augment.effects)


def apply_all_passives(player: "Player") -> None:
    """
    Re-apply passive bonuses for every augment the player holds.

    Call this at the start of each combat phase, after board changes
    and before combat.py reads champion stats.
    """
    for augment in player.selected_augments:
        apply_augment_hook(player, augment, "passive")


def apply_all_stage_start_hooks(player: "Player") -> None:
    """
    Fire on_stage_start hooks for every augment the player holds.

    Call this in the event engine whenever the stage number increases.
    """
    for augment in player.selected_augments:
        apply_augment_hook(player, augment, "on_stage_start")


def get_eligible_augments(
    round_number: int,
    data_augments: List[Augment],
) -> List[Augment]:
    """
    Return all augments that may be offered at the given selection round.

    The candidate pool is the union of data_augments (from TFTDataLoader) and
    SYNTHETIC_AUGMENTS (augments implemented in code but absent from the JSON).
    Duplicates (same augment_id) are deduplicated, with the synthetic entry
    taking precedence so effects are always up-to-date.

    An augment with an entry in AUGMENT_ELIGIBLE_ROUNDS is only included when
    round_number is in its frozenset.  Augments without an entry are
    unrestricted and appear at every selection round.

    Args:
        round_number:  The current augment-selection round (e.g. 10, 20, 29).
        data_augments: Augments loaded from the JSON data file.

    Returns:
        List of eligible Augment objects for this round.
    """
    seen: set = set()
    candidates: List[Augment] = []

    # Synthetic augments first so they shadow any data duplicate.
    for aug in SYNTHETIC_AUGMENTS:
        seen.add(aug.augment_id)
        candidates.append(aug)

    for aug in data_augments:
        if aug.augment_id not in seen:
            seen.add(aug.augment_id)
            candidates.append(aug)

    eligible: List[Augment] = []
    for aug in candidates:
        restriction = AUGMENT_ELIGIBLE_ROUNDS.get(aug.augment_id)
        if restriction is None or round_number in restriction:
            eligible.append(aug)

    return eligible
