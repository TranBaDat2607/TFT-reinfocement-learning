"""
Shared base types and helpers for augment effect modules.

Every augment file imports AugmentResult from here.
Helpers that are general enough to be useful across multiple augments
also live here (_get_all_champions, _grant_champion, _epoch_apply).
Augment-specific helpers stay in their own module.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from simulator.core.champion import Champion
    from simulator.core.player import Player


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
# Shared helpers
# ---------------------------------------------------------------------------

def _get_all_champions(player: "Player") -> List["Champion"]:
    """Return every champion the player owns (board + bench)."""
    champions: List["Champion"] = list(player.board.get_all_champions())
    champions += [c for c in player.bench if c is not None]
    return champions


def _grant_champion(player: "Player", champion_name: str) -> bool:
    """
    Give the player one copy of a champion by name, drawn from the shared pool.

    Returns True if successfully granted, False if the champion is not found
    in data or none remain in the pool.
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


def _epoch_apply(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """
    Grant free XP and free rerolls.

    Shared by Epoch (on_select / on_stage_start) and
    Epoch+ (on_select / on_stage_start).  The difference between the two
    augments lives entirely in their effects dict (XPAmount 4 vs 8).
    """
    xp_amount: int = int(effects.get("XPAmount", 4))
    reroll_count: int = int(effects.get("RerollCount", 3))

    player.xp += xp_amount
    player._check_level_up()
    player.free_rerolls += reroll_count

    return AugmentResult(success=True, xp_delta=xp_amount, rerolls_granted=reroll_count)
