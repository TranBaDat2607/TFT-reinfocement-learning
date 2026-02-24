"""
Augment effect handlers for TFT Set 16.

Each entry in AUGMENT_REGISTRY maps an augment API name to a dict of
lifecycle hooks. Hooks are called by the game engine at specific moments:

    on_select      — called once when the player picks the augment
    passive        — called before each combat; re-applies stat bonuses
    on_round_start — called at the start of each planning phase

Hook signature:
    (player: "Player", effects: Dict[str, Any]) -> AugmentResult

Stat bonuses applied in `passive` are stored as underscore-prefixed
attributes directly on the Champion instance (e.g. `_bonus_attack_range`).
These are reset and re-applied every time `passive` runs, so they always
reflect the correct value even after board changes.

Combat.py is responsible for reading these bonus attributes when computing
effective stats during a fight.

Usage
-----
    from simulator.env.augment_effects import apply_augment_hook

    # When player selects an augment:
    apply_augment_hook(player, augment, "on_select")

    # Before each combat:
    for augment in player.selected_augments:
        apply_augment_hook(player, augment, "passive")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, FrozenSet, List, Optional

if TYPE_CHECKING:
    from simulator.core.champion import Champion
    from simulator.core.player import Player

from data_loader.data_models import Augment


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------

@dataclass
class AugmentResult:
    """
    Standardised return value for every augment hook.

    Covers all augment categories:
        Unit grant   → grants populated, success=False if pool empty
        Stat modify  → affected_champions populated
        Economy      → gold_delta > 0
        Combat flag  → success=True, everything else empty (flag set on champion)

    The game engine / reward function can inspect this without knowing which
    specific augment fired.
    """
    success: bool = True
    grants: List[str] = field(default_factory=list)
    """Champion names added to the player's bench this event."""
    gold_delta: int = 0
    """Gold given (or taken) by this hook call."""
    affected_champions: List[str] = field(default_factory=list)
    """Display names of champions whose stats were modified."""
    xp_delta: int = 0
    """XP granted (free, no gold cost) by this hook call."""
    rerolls_granted: int = 0
    """Free shop rerolls added to the player by this hook call."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_all_champions(player: "Player") -> List["Champion"]:
    """Return every champion the player owns (board + bench)."""
    champions: List["Champion"] = list(player.board.get_all_champions())
    champions += [c for c in player.bench if c is not None]
    return champions


def _find_rumbles(player: "Player") -> List["Champion"]:
    """Return all Rumble units owned by the player."""
    return [c for c in _get_all_champions(player) if c.name == "Rumble"]


def _strongest_rumble(player: "Player") -> Optional["Champion"]:
    """
    Return the player's 'strongest' Rumble.

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


def _grant_champion(player: "Player", champion_name: str) -> bool:
    """
    Give the player one copy of a champion by name, drawn from the shared pool.

    Returns True if the champion was successfully granted, False otherwise
    (e.g. none left in the pool or champion name not found in data).
    """
    from simulator.core.champion import create_champion

    champion_data = player.data_loader.get_champion_by_name(champion_name)
    if champion_data is None:
        return False

    if not player.pool.is_available(champion_data.champion_id):
        return False

    player.pool.acquire(champion_data.champion_id)
    new_champ = create_champion(champion_data, stars=1)
    player._add_to_bench(new_champ)
    return True


# ---------------------------------------------------------------------------
# Artillery Barrage  (TFT16_Augment_RumbleCarry)
#
#   "Gain a Rumble. Your strongest Rumble gains +@MaxRange@ Range and
#    constantly fires missiles at enemies, increased with Attack Speed."
#
#   effects = {"MaxRange": 7}
# ---------------------------------------------------------------------------

def _artillery_barrage_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Grant a Rumble unit when the augment is chosen."""
    granted = _grant_champion(player, "Rumble")
    if granted:
        return AugmentResult(success=True, grants=["Rumble"])
    return AugmentResult(success=False)


def _artillery_barrage_passive(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """
    Before each combat, find the strongest Rumble and apply bonuses.

    Follows the same pattern as the reference project's items.initiate():
    stats are mutated directly on the champion instance (not on the shared
    data template). The reset loop above restores base values each call,
    so bonuses never stack across successive passive applications.

    Attributes modified on the champion instance:
        attack_range   — increased by MaxRange (e.g. +7 hexes)
        _fires_missiles (bool) — signals combat engine to enable the
                                 continuous missile barrage, scaled by
                                 the unit's attack_speed
    """
    bonus_range: int = int(effects.get("MaxRange", 0))

    # Restore base attack_range for all Rumbles before re-applying so
    # successive passive calls don't stack bonuses.
    for rumble in _find_rumbles(player):
        rumble.attack_range = rumble.data.stats.attack_range or 1
        rumble._fires_missiles = False

    target = _strongest_rumble(player)
    if target is None:
        return AugmentResult(success=False)

    # Direct mutation — same approach as reference project's change_stat().
    target.attack_range += bonus_range
    target._fires_missiles = True
    # NOTE: combat.py reads champion.attack_range for effective range and
    # champion._fires_missiles to enable the missile barrage loop
    # (missile frequency scales linearly with champion.attack_speed).
    return AugmentResult(success=True, affected_champions=[target.name])


# ---------------------------------------------------------------------------
# Epoch  (TFT16_Augment_Epoch)
#
#   "Now, and at the start of every stage, gain 4 XP and 3 free rerolls."
#   Offered only at 2-1 (augment selection round 6).
#
#   effects = {"XPAmount": 4, "RerollCount": 3}
# ---------------------------------------------------------------------------

def _epoch_apply(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Grant free XP and free rerolls — shared by on_select and on_stage_start."""
    xp_amount: int = int(effects.get("XPAmount", 4))
    reroll_count: int = int(effects.get("RerollCount", 3))

    player.xp += xp_amount
    player._check_level_up()
    player.free_rerolls += reroll_count

    return AugmentResult(success=True, xp_delta=xp_amount, rerolls_granted=reroll_count)


def _epoch_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    return _epoch_apply(player, effects)


def _epoch_on_stage_start(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    return _epoch_apply(player, effects)


# ---------------------------------------------------------------------------
# Epoch+  (TFT16_Augment_EpochPlus)
#
#   "Now, and at the start of every stage, gain 8 XP and 3 free rerolls."
#   Offered only at 3-2 (augment selection round 13).
#
#   effects = {"XPAmount": 8, "RerollCount": 3}
# ---------------------------------------------------------------------------

def _epoch_plus_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    return _epoch_apply(player, effects)


def _epoch_plus_on_stage_start(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    return _epoch_apply(player, effects)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

AUGMENT_REGISTRY: Dict[str, Dict[str, Any]] = {
    "TFT16_Augment_RumbleCarry": {
        "on_select": _artillery_barrage_on_select,
        "passive":   _artillery_barrage_passive,
    },
    "TFT16_Augment_Epoch": {
        "on_select":      _epoch_on_select,
        "on_stage_start": _epoch_on_stage_start,
    },
    "TFT16_Augment_EpochPlus": {
        "on_select":      _epoch_plus_on_select,
        "on_stage_start": _epoch_plus_on_stage_start,
    },
}


# ---------------------------------------------------------------------------
# Synthetic augments
#
# Augments not present in the crawled JSON data but with implemented hooks.
# These are merged into the selection pool by get_eligible_augments().
# ---------------------------------------------------------------------------

SYNTHETIC_AUGMENTS: List[Augment] = [
    Augment(
        augment_id="TFT16_Augment_Epoch",
        name="Epoch",
        description="Now, and at the start of every stage, gain 4 XP and 3 free rerolls.",
        effects={"XPAmount": 4, "RerollCount": 3},
        associated_traits=[],
        incompatible_traits=[],
        tags=[],
        is_unique=False,
        icon="",
    ),
    Augment(
        augment_id="TFT16_Augment_EpochPlus",
        name="Epoch+",
        description="Now, and at the start of every stage, gain 8 XP and 3 free rerolls.",
        effects={"XPAmount": 8, "RerollCount": 3},
        associated_traits=[],
        incompatible_traits=[],
        tags=[],
        is_unique=False,
        icon="",
    ),
]

# ---------------------------------------------------------------------------
# Round eligibility
#
# Maps augment_id -> frozenset of augment-selection round numbers where the
# augment may be offered.  Augments absent from this dict are unrestricted
# and may appear at any selection round.
# ---------------------------------------------------------------------------

AUGMENT_ELIGIBLE_ROUNDS: Dict[str, FrozenSet[int]] = {
    "TFT16_Augment_Epoch":     frozenset({10}),  # 2-1 only (round 10)
    "TFT16_Augment_EpochPlus": frozenset({20}),  # 3-2 only (round 20)
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
        event:   One of "on_select", "passive", "on_round_start".

    Returns:
        AugmentResult describing what happened.
        Returns a default AugmentResult(success=True) when the augment is
        not yet implemented or the event has no registered hook — safe to
        ignore in both cases.
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

    Call this in the event engine whenever the stage number increases
    (including the very first stage).
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
    Duplicates (same augment_id in both lists) are deduplicated, with the
    synthetic entry taking precedence so effects are always up-to-date.

    An augment with an entry in AUGMENT_ELIGIBLE_ROUNDS is only included when
    round_number is in its frozenset.  Augments without an entry are
    unrestricted and appear at every selection round.

    Args:
        round_number:  The current augment-selection round (e.g. 6, 13, or 20).
        data_augments: Augments loaded from the JSON data file.

    Returns:
        List of eligible Augment objects for this round.
    """
    # Synthetic augments take priority — build a lookup by id first.
    synthetic_by_id: Dict[str, Augment] = {a.augment_id: a for a in SYNTHETIC_AUGMENTS}

    seen: set = set()
    candidates: List[Augment] = []

    # Synthetic augments first so they shadow any data duplicate.
    for aug in SYNTHETIC_AUGMENTS:
        seen.add(aug.augment_id)
        candidates.append(aug)

    # Then data augments, skipping ids already covered by synthetics.
    for aug in data_augments:
        if aug.augment_id not in seen:
            seen.add(aug.augment_id)
            candidates.append(aug)

    # Filter by round eligibility.
    eligible: List[Augment] = []
    for aug in candidates:
        restriction = AUGMENT_ELIGIBLE_ROUNDS.get(aug.augment_id)
        if restriction is None or round_number in restriction:
            eligible.append(aug)

    return eligible
