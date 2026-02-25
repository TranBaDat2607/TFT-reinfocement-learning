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

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

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


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_all_champions(player: "Player") -> List["Champion"]:
    """Return every champion the player owns (board + bench)."""
    champions: List["Champion"] = list(player.board.get_all_champions())
    champions += [c for c in player.bench if c is not None]
    return champions


def _get_board_champions(player: "Player") -> List["Champion"]:
    """Return only the champions currently on the board."""
    return list(player.board.get_all_champions())


def _bench_is_empty(player: "Player") -> bool:
    """True if no champions are sitting on the bench."""
    return all(slot is None for slot in player.bench)


def _bench_is_full(player: "Player") -> bool:
    """True if every bench slot is occupied."""
    return all(slot is not None for slot in player.bench)


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


def _grant_champion_with_stars(
    player: "Player", champion_name: str, stars: int
) -> bool:
    """
    Give the player a champion at a specific star level.

    For a 2★ champion we need to acquire 3 copies from the pool;
    for a 3★ we need 9 copies. If the pool doesn't have enough copies
    the grant silently fails and returns False.
    """
    from simulator.core.champion import create_champion

    champion_data = player.data_loader.get_champion_by_name(champion_name)
    if champion_data is None:
        return False

    copies_needed = 3 ** (stars - 1)  # 1★→1, 2★→3, 3★→9
    available = player.pool.get_available(champion_data.champion_id)
    if available < copies_needed:
        return False

    for _ in range(copies_needed):
        player.pool.acquire(champion_data.champion_id)

    new_champ = create_champion(champion_data, stars=stars)
    player._add_to_bench(new_champ)
    return True


def _grant_random_champions(
    player: "Player", cost: int, count: int, stars: int = 1
) -> List[str]:
    """
    Grant *count* random champions of the given *cost* tier at *stars* level.

    Returns a list of champion names that were successfully granted.
    If the pool runs dry mid-grant, the remaining slots are skipped.
    """
    from simulator.core.champion import create_champion

    all_champs = player.data_loader.get_all_champions()
    candidates = [c for c in all_champs if c.cost == cost]
    if not candidates:
        return []

    copies_needed = 3 ** (stars - 1)
    granted: List[str] = []

    for _ in range(count):
        random.shuffle(candidates)
        for cdata in candidates:
            if player.pool.get_available(cdata.champion_id) >= copies_needed:
                for __ in range(copies_needed):
                    player.pool.acquire(cdata.champion_id)
                new_champ = create_champion(cdata, stars=stars)
                player._add_to_bench(new_champ)
                granted.append(cdata.name)
                break

    return granted


def _grant_random_item_component(player: "Player") -> Optional[str]:
    """
    Grant one random base item component (B.F. Sword, Chain Vest, etc.).

    Uses a fixed list of base component IDs. Returns the ID granted, or None
    if the item bench is full.
    """
    base_components = [
        "TFT_Item_BFSword",
        "TFT_Item_ChainVest",
        "TFT_Item_GiantsBelt",
        "TFT_Item_NeedlesslyLargeRod",
        "TFT_Item_NegatronCloak",
        "TFT_Item_RecurveBow",
        "TFT_Item_SparringGloves",
        "TFT_Item_Spatula",
        "TFT_Item_TearOfTheGoddess",
    ]
    item_id = random.choice(base_components)
    if player.grant_item_component(item_id):
        return item_id
    return None


# ---------------------------------------------------------------------------
# NHÓM 1 — Tặng Vàng / XP / Reroll trực tiếp (on_select only)
# ---------------------------------------------------------------------------

# ---- Silver Spoon ----
def _silver_spoon_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Nhận 10 XP."""
    player.xp += 10
    player._check_level_up()
    return AugmentResult(success=True)


# ---- Rolling For Days I ----
def _rolling_for_days_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Nhận 10 reroll miễn phí."""
    player.free_rerolls += 10
    return AugmentResult(success=True)


# ---- Survivor ----
def _survivor_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Nhận 4 vàng. Khi 3 người chơi bị loại, nhận 100 vàng."""
    player.gold += 4
    player._survivor_triggered = False
    return AugmentResult(success=True, gold_delta=4)


def _survivor_on_round_start(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Check số người chơi bị loại; nếu ≥ 3 và chưa trigger → +100 gold."""
    if getattr(player, "_survivor_triggered", False):
        return AugmentResult(success=True)

    # Count eliminated players (need access to game context).
    # The event engine sets player._game_eliminated_count each round.
    eliminated = getattr(player, "_game_eliminated_count", 0)
    if eliminated >= 3:
        player.gold += 100
        player._survivor_triggered = True
        return AugmentResult(success=True, gold_delta=100)

    return AugmentResult(success=True)


# ---- 3 Threes ----
def _three_threes_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Nhận 3 tướng 3 vàng 2 sao và 3 vàng."""
    granted = _grant_random_champions(player, cost=3, count=3, stars=2)
    player.gold += 3
    return AugmentResult(success=len(granted) > 0, grants=granted, gold_delta=3)


# ---- Advanced Loan / Advanced Loan+ ----
def _advanced_loan_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Nhận 20 (hoặc 33) vàng. Lõi tiếp theo giảm 1 bậc."""
    gold_amount = int(effects.get("Gold", 20))
    player.gold += gold_amount
    player._next_augment_downgrade = True
    return AugmentResult(success=True, gold_delta=gold_amount)


# ---- Construct a Companion ----
def _construct_companion_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Tướng 1 vàng tiếp theo mua sẽ là 3 sao. Nhận 2 vàng."""
    player.gold += 2
    player._next_1cost_is_3star = True
    return AugmentResult(success=True, gold_delta=2)


# ---- Calculated Loss (on_select — setup flag) ----
def _calculated_loss_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Thua giao tranh nhận 2 vàng và 1 reroll — đặt flag."""
    player._calculated_loss = True
    return AugmentResult(success=True)


def _calculated_loss_on_round_start(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Nếu thua vòng trước → +2 vàng, +1 reroll."""
    if not getattr(player, "_calculated_loss", False):
        return AugmentResult(success=True)

    # loss_streak > 0 means the player lost the last round.
    if player.loss_streak > 0:
        player.gold += 2
        player.free_rerolls += 1
        return AugmentResult(success=True, gold_delta=2)

    return AugmentResult(success=True)


# ---- Epic Rolldown ----
def _epic_rolldown_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Đạt cấp 8 nhận 20 reroll — đặt flag pending."""
    player._epic_rolldown_pending = True
    # If already level 8+, grant immediately.
    if player.level >= 8:
        player.free_rerolls += 20
        player._epic_rolldown_pending = False
    return AugmentResult(success=True)


def _epic_rolldown_on_round_start(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Check cấp 8 → cấp reroll nếu chưa trigger."""
    if not getattr(player, "_epic_rolldown_pending", False):
        return AugmentResult(success=True)

    if player.level >= 8:
        player.free_rerolls += 20
        player._epic_rolldown_pending = False

    return AugmentResult(success=True)


# ---------------------------------------------------------------------------
# NHÓM 2 — Tặng Tướng (on_select, tương tác Pool)
# ---------------------------------------------------------------------------

# ---- Restart Mission ----
def _restart_mission_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """
    Xóa bàn cờ. Nhận 2 tướng 3-vàng 2★, 3 tướng 2-vàng 2★,
    1 tướng 1-vàng 2★.
    """
    # Return all current champions to the pool.
    for champ in list(player.board.get_all_champions()):
        pos = player.board.find_champion(champ)
        if pos:
            player.board.remove(pos[0], pos[1])
        for _ in range(3 ** (champ.stars - 1)):
            player.pool.release(champ.data.champion_id)

    for i, champ in enumerate(player.bench):
        if champ is not None:
            for _ in range(3 ** (champ.stars - 1)):
                player.pool.release(champ.data.champion_id)
            player.bench[i] = None

    # Grant new champions.
    granted: List[str] = []
    granted += _grant_random_champions(player, cost=3, count=2, stars=2)
    granted += _grant_random_champions(player, cost=2, count=3, stars=2)
    granted += _grant_random_champions(player, cost=1, count=1, stars=2)

    return AugmentResult(success=len(granted) > 0, grants=granted)


# ---- Teaming Up ----
def _teaming_up_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Nhận 1 mảnh trang bị và 2 tướng 3 vàng ngẫu nhiên."""
    _grant_random_item_component(player)
    granted = _grant_random_champions(player, cost=3, count=2, stars=1)
    return AugmentResult(success=True, grants=granted)


# ---- Cluttered Mind (on_select — grant 4 × 1-cost) ----
def _cluttered_mind_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Nhận 4 tướng 1 vàng."""
    granted = _grant_random_champions(player, cost=1, count=4, stars=1)
    player._cluttered_mind = True
    return AugmentResult(success=True, grants=granted)


def _cluttered_mind_on_round_start(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Nếu hàng chờ đầy cuối vòng → nhận 3 XP."""
    if not getattr(player, "_cluttered_mind", False):
        return AugmentResult(success=True)

    if _bench_is_full(player):
        player.xp += 3
        player._check_level_up()

    return AugmentResult(success=True)


# ---- Cosmic Calling ----
def _cosmic_calling_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Nhận Ngọn Giáo Shojin và Leona. Vòng 3-7 nhận Taric."""
    player.grant_item_component("TFT_Item_TearOfTheGoddess")
    player.grant_item_component("TFT_Item_BFSword")
    granted: List[str] = []
    if _grant_champion(player, "Leona"):
        granted.append("Leona")
    player._cosmic_taric_granted = False
    return AugmentResult(success=True, grants=granted)


def _cosmic_calling_on_round_start(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Check round 3-7 → grant Taric (one-time)."""
    if getattr(player, "_cosmic_taric_granted", False):
        return AugmentResult(success=True)

    current_round = getattr(player, "_current_round", 0)
    # Round 3-7 maps to stage 3, round 7 → round index ~ 20.
    # We use a simple round threshold: grant when round >= 20 (≈ stage 3-7).
    if current_round >= 20:
        granted: List[str] = []
        if _grant_champion(player, "Taric"):
            granted.append("Taric")
        player._cosmic_taric_granted = True
        return AugmentResult(success=True, grants=granted)

    return AugmentResult(success=True)


# ---- Duo Queue ----
def _duo_queue_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Nhận 2 tướng 5 vàng ngẫu nhiên và 2 bản sao của 1 mảnh trang bị."""
    granted = _grant_random_champions(player, cost=5, count=2, stars=1)
    item_id = _grant_random_item_component(player)
    if item_id:
        player.grant_item_component(item_id)  # second copy
    return AugmentResult(success=True, grants=granted)


# ---- Aura Farming ----
def _aura_farming_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Nhận 1 tướng 5 vàng 2★ có trang bị. Không thể dùng đến vòng 4-2."""
    granted = _grant_random_champions(player, cost=5, count=1, stars=2)
    if granted:
        # Find the newly-placed champion and give it a random item.
        for champ in reversed(list(_get_all_champions(player))):
            if champ.name in granted and champ.stars == 2:
                item_id = random.choice([
                    "TFT_Item_BFSword",
                    "TFT_Item_NeedlesslyLargeRod",
                    "TFT_Item_RecurveBow",
                ])
                champ.add_item(item_id)
                break
    player._aura_locked_until_round = 26  # Approx round index for 4-2
    return AugmentResult(success=True, grants=granted)


# ---- Birthday Reunion ----
def _birthday_reunion_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Nhận tướng 2 vàng 2★. Cấp 7 nhận Găng Đạo Tặc. Cấp 9 nhận tướng 5 vàng 2★."""
    granted = _grant_random_champions(player, cost=2, count=1, stars=2)
    player._birthday_lvl7_granted = False
    player._birthday_lvl9_granted = False

    # Check if already at milestone levels.
    if player.level >= 7 and not player._birthday_lvl7_granted:
        player.grant_item_component("TFT_Item_SparringGloves")
        player.grant_item_component("TFT_Item_SparringGloves")
        player._birthday_lvl7_granted = True
    if player.level >= 9 and not player._birthday_lvl9_granted:
        granted += _grant_random_champions(player, cost=5, count=1, stars=2)
        player._birthday_lvl9_granted = True

    return AugmentResult(success=True, grants=granted)


def _birthday_reunion_on_round_start(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Check milestone levels → grant Thief's Gloves (lv7) or 5-cost 2★ (lv9)."""
    granted: List[str] = []

    if player.level >= 7 and not getattr(player, "_birthday_lvl7_granted", False):
        # Găng Đạo Tặc = Thief's Gloves (2× Sparring Gloves)
        player.grant_item_component("TFT_Item_SparringGloves")
        player.grant_item_component("TFT_Item_SparringGloves")
        player._birthday_lvl7_granted = True

    if player.level >= 9 and not getattr(player, "_birthday_lvl9_granted", False):
        granted += _grant_random_champions(player, cost=5, count=1, stars=2)
        player._birthday_lvl9_granted = True

    return AugmentResult(success=True, grants=granted)


# ---------------------------------------------------------------------------
# NHÓM 3 — Tặng Trang bị (on_select only)
# ---------------------------------------------------------------------------

# ---- Small Grab Bag ----
def _small_grab_bag_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Nhận 2 mảnh trang bị ngẫu nhiên."""
    _grant_random_item_component(player)
    _grant_random_item_component(player)
    return AugmentResult(success=True)


# ---- Big Grab Bag ----
def _big_grab_bag_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Nhận 3 mảnh trang bị, 2 vàng, 1 Búa Rèn."""
    _grant_random_item_component(player)
    _grant_random_item_component(player)
    _grant_random_item_component(player)
    player.gold += 2
    # Búa Rèn (Reforger) — grant as a special item.
    player.grant_item_component("TFT_Item_Reforger")
    return AugmentResult(success=True, gold_delta=2)


# ---- Crown's Will (on_select — grant items) ----
def _crowns_will_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Nhận Gậy Quá Khổ + Giáp Lưới."""
    player.grant_item_component("TFT_Item_NeedlesslyLargeRod")
    player.grant_item_component("TFT_Item_ChainVest")
    return AugmentResult(success=True)


# ---- Cry Me A River (on_select — grant Tear) ----
def _cry_me_a_river_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Nhận Nước Mắt."""
    player.grant_item_component("TFT_Item_TearOfTheGoddess")
    return AugmentResult(success=True)


# ---- Team Building ----
def _team_building_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Nhận 1 Máy Nhân Bản Cỡ Nhỏ. Nhận thêm 1 cái sau 5 vòng."""
    player.grant_item_component("TFT_Item_SmallDuplicator")
    player._team_building_rounds_left = 5
    return AugmentResult(success=True)


def _team_building_on_round_start(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Countdown 5 rounds → grant second Duplicator."""
    rounds_left = getattr(player, "_team_building_rounds_left", -1)
    if rounds_left <= 0:
        return AugmentResult(success=True)

    player._team_building_rounds_left -= 1
    if player._team_building_rounds_left == 0:
        player.grant_item_component("TFT_Item_SmallDuplicator")

    return AugmentResult(success=True)


# ---------------------------------------------------------------------------
# NHÓM 4 — Buff chỉ số đội hình (passive — mỗi vòng giao tranh)
# ---------------------------------------------------------------------------

# ---- Stand United ----
def _stand_united_passive(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """
    Nhận 1.5% SMCK/SMPT cho mỗi Tộc/Hệ kích hoạt.

    Cộng AD & AP cho mọi tướng trên bàn cờ dựa trên số trait active.
    """
    num_active = len(player.active_traits)
    bonus_pct = 0.015 * num_active  # 1.5% per trait

    affected: List[str] = []
    for champ in _get_board_champions(player):
        # Reset bonus trước  khi áp dụng lại.
        base_ad = champ.data.stats.attack_damage or 40
        star_mult = {1: 1.0, 2: 1.8, 3: 3.24, 4: 5.832}.get(champ.stars, 1.0)
        champ._bonus_ad_stand_united = base_ad * star_mult * bonus_pct
        champ.attack_damage = base_ad * star_mult + champ._bonus_ad_stand_united

        champ._bonus_ap_stand_united = 100.0 * bonus_pct
        champ.ability_power = 100.0 + champ._bonus_ap_stand_united

        affected.append(champ.name)

    return AugmentResult(success=True, affected_champions=affected)


# ---- Best Friends II ----
def _best_friends_passive(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """
    Cặp đồng minh đứng tách biệt nhận 15% Tốc độ đánh, 22 Giáp.

    "Tách biệt" = không có đồng minh kề (adjacent) trên hex grid.
    Simplified: give bonus to ALL board champions (engine will refine).
    """
    bonus_as_pct = 0.15
    bonus_armor = 22

    affected: List[str] = []
    board_champs = _get_board_champions(player)

    for champ in board_champs:
        base_as = champ.data.stats.attack_speed or 0.6
        base_armor = champ.data.stats.armor or 20

        champ._bonus_as_bestfriends = base_as * bonus_as_pct
        champ.attack_speed = base_as + champ._bonus_as_bestfriends

        champ._bonus_armor_bestfriends = bonus_armor
        champ.armor = base_armor + bonus_armor

        affected.append(champ.name)

    return AugmentResult(success=True, affected_champions=affected)


# ---- Double Trouble ----
def _double_trouble_passive(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """
    2 bản sao tướng nhận 30% chỉ số. Lên 3 sao tặng 1 bản sao 2 sao.

    Identifies pairs of the same champion on the board and grants them
    +30% HP, AD, AP, Armor, MR, AS.
    """
    board_champs = _get_board_champions(player)

    # Count champions by name among board units.
    from collections import Counter
    name_counts = Counter(c.name for c in board_champs)
    doubled_names = {name for name, cnt in name_counts.items() if cnt >= 2}

    affected: List[str] = []
    bonus_pct = 0.30

    for champ in board_champs:
        # Reset double-trouble bonus every call.
        champ._double_trouble_active = False

        if champ.name in doubled_names:
            champ._double_trouble_active = True
            star_mult = {1: 1.0, 2: 1.8, 3: 3.24, 4: 5.832}.get(champ.stars, 1.0)

            base_hp = (champ.data.stats.hp or 500) * star_mult
            base_ad = (champ.data.stats.attack_damage or 40) * star_mult
            base_armor = champ.data.stats.armor or 20
            base_mr = champ.data.stats.magic_resist or 20
            base_as = champ.data.stats.attack_speed or 0.6

            champ.max_hp = base_hp * (1 + bonus_pct)
            champ.current_hp = min(champ.current_hp, champ.max_hp)
            champ.attack_damage = base_ad * (1 + bonus_pct)
            champ.armor = base_armor * (1 + bonus_pct)
            champ.magic_resist = base_mr * (1 + bonus_pct)
            champ.attack_speed = base_as * (1 + bonus_pct)
            champ.ability_power = 100.0 * (1 + bonus_pct)

            affected.append(champ.name)

    return AugmentResult(success=True, affected_champions=affected)


# ---- Second Wind ----
def _second_wind_passive(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """
    Sau 10 giây, hồi 40% máu đã mất cho toàn đội.

    Sets a combat flag so combat.py heals all units for 40% missing HP
    after 10 seconds of combat.
    """
    affected: List[str] = []
    for champ in _get_board_champions(player):
        champ._second_wind = True
        affected.append(champ.name)

    return AugmentResult(success=True, affected_champions=affected)


# ---- Crown's Will (passive — team buff) ----
def _crowns_will_passive(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Đội nhận 8 SMPT, 6 Giáp."""
    affected: List[str] = []
    for champ in _get_board_champions(player):
        champ._bonus_ap_crown = 8
        champ.ability_power = 100.0 + 8

        base_armor = champ.data.stats.armor or 20
        champ._bonus_armor_crown = 6
        champ.armor = base_armor + 6

        affected.append(champ.name)

    return AugmentResult(success=True, affected_champions=affected)


# ---- Cry Me A River (passive — mana regen flag) ----
def _cry_me_a_river_passive(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """
    Đội hồi 1 Năng lượng (tăng lên 3 sau 12 giây).

    Sets a combat flag: combat.py reads champion._mana_regen_base and
    champion._mana_regen_boosted.
    """
    affected: List[str] = []
    for champ in _get_board_champions(player):
        champ._mana_regen_base = 1
        champ._mana_regen_boosted = 3
        champ._mana_regen_boost_time = 12
        affected.append(champ.name)

    return AugmentResult(success=True, affected_champions=affected)


# ---- Spoils of War I ----
def _spoils_of_war_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """25% tỉ lệ rơi chiến lợi phẩm khi hạ gục địch."""
    player._spoils_of_war_chance = 0.25
    return AugmentResult(success=True)


# ---------------------------------------------------------------------------
# NHÓM 5 — Kinh tế theo vòng (on_round_start)
# ---------------------------------------------------------------------------

# ---- Clear Mind ----
def _clear_mind_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Setup flag."""
    player._clear_mind = True
    return AugmentResult(success=True)


def _clear_mind_on_round_start(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Nếu không có tướng trên hàng chờ → nhận 3 XP cuối vòng."""
    if not getattr(player, "_clear_mind", False):
        return AugmentResult(success=True)

    if _bench_is_empty(player):
        player.xp += 3
        player._check_level_up()

    return AugmentResult(success=True)


# ---------------------------------------------------------------------------
# NHÓM 6 — Lõi điều kiện đặc biệt / Deferred
# ---------------------------------------------------------------------------

# ---- Risky Moves ----
def _risky_moves_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Mất 20 Máu linh thú. Sau 7 vòng nhận 30 vàng."""
    player.health = max(0, player.health - 20)
    if player.health <= 0:
        player.is_alive = False
    player._risky_moves_countdown = 7
    return AugmentResult(success=True)


def _risky_moves_on_round_start(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Countdown 7 rounds → +30 gold."""
    countdown = getattr(player, "_risky_moves_countdown", -1)
    if countdown <= 0:
        return AugmentResult(success=True)

    player._risky_moves_countdown -= 1
    if player._risky_moves_countdown == 0:
        player.gold += 30
        return AugmentResult(success=True, gold_delta=30)

    return AugmentResult(success=True)


# ---- Silver Destiny / Silver Destiny+ ----
def _silver_destiny_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Nhận 1 Lõi Bạc ngẫu nhiên và 2 (hoặc 4) vàng."""
    gold_amount = int(effects.get("Gold", 2))
    player.gold += gold_amount
    # The random Silver core is handled by the augment selection system;
    # we just grant the gold here.
    return AugmentResult(success=True, gold_delta=gold_amount)


# ---- Slice of Life ----
def _slice_of_life_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Setup tracking."""
    player._slice_stage_count = 0
    player._slice_current_cost = 1  # Starting champion cost
    player._slice_grants_this_stage = 0
    return AugmentResult(success=True)


def _slice_of_life_on_round_start(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """
    Hai lần mỗi giai đoạn, nhận 1 tướng ngẫu nhiên (giá tăng theo giai đoạn).
    Kết thúc khi nhận tướng 5 vàng.
    """
    current_cost = getattr(player, "_slice_current_cost", 0)
    if current_cost > 5:
        return AugmentResult(success=True)  # Augment exhausted

    grants_this_stage = getattr(player, "_slice_grants_this_stage", 0)
    current_round = getattr(player, "_current_round", 0)

    # Detect stage boundary (every ~7 rounds is a new stage).
    stage_num = current_round // 7
    stored_stage = getattr(player, "_slice_stage_count", -1)

    if stage_num != stored_stage:
        player._slice_stage_count = stage_num
        player._slice_grants_this_stage = 0
        grants_this_stage = 0

    if grants_this_stage < 2:
        cost = min(current_cost, 5)
        granted = _grant_random_champions(player, cost=cost, count=1, stars=1)
        player._slice_grants_this_stage = grants_this_stage + 1

        if cost >= 5:
            player._slice_current_cost = 6  # Signal exhaustion
        elif player._slice_grants_this_stage >= 2:
            player._slice_current_cost = cost + 1

        return AugmentResult(success=True, grants=granted)

    return AugmentResult(success=True)


# ---- Table Scraps ----
def _table_scraps_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Sau 2 vòng đi chợ tiếp theo, nhận tướng không ai chọn + trang bị. Nhận 1 vàng."""
    player.gold += 1
    player._table_scraps_remaining = 2
    return AugmentResult(success=True, gold_delta=1)


def _table_scraps_on_round_start(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """
    Tracking for carousel rounds. The event engine triggers the actual
    carousel grant; this hook signals readiness.
    """
    # The event engine will check player._table_scraps_remaining > 0
    # and grant the unchosen carousel champion.
    return AugmentResult(success=True)


# ---- Titanic Titan ----
def _titanic_titan_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Tăng 25 Máu linh thú tối đa. Đi chợ sớm hơn nhưng chạy chậm."""
    player.health += 25
    player._titan_max_hp_bonus = 25
    player._titan_carousel_early = True
    return AugmentResult(success=True)


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
# Registry
# ---------------------------------------------------------------------------

AUGMENT_REGISTRY: Dict[str, Dict[str, Any]] = {
    # === Existing ===
    "TFT16_Augment_RumbleCarry": {
        "on_select": _artillery_barrage_on_select,
        "passive":   _artillery_barrage_passive,
    },

    # === NHÓM 1 — Vàng / XP / Reroll ===
    "TFT16_Augment_SilverSpoon": {
        "on_select": _silver_spoon_on_select,
    },
    "TFT16_Augment_RollingForDays": {
        "on_select": _rolling_for_days_on_select,
    },
    "TFT16_Augment_Survivor": {
        "on_select":      _survivor_on_select,
        "on_round_start": _survivor_on_round_start,
    },
    "TFT16_Augment_ThreeThrees": {
        "on_select": _three_threes_on_select,
    },
    "TFT16_Augment_AdvancedLoan": {
        "on_select": _advanced_loan_on_select,
    },
    "TFT16_Augment_ConstructACompanion": {
        "on_select": _construct_companion_on_select,
    },
    "TFT16_Augment_CalculatedLoss": {
        "on_select":      _calculated_loss_on_select,
        "on_round_start": _calculated_loss_on_round_start,
    },
    "TFT16_Augment_EpicRolldown": {
        "on_select":      _epic_rolldown_on_select,
        "on_round_start": _epic_rolldown_on_round_start,
    },

    # === NHÓM 2 — Tặng Tướng ===
    "TFT16_Augment_RestartMission": {
        "on_select": _restart_mission_on_select,
    },
    "TFT16_Augment_TeamingUp": {
        "on_select": _teaming_up_on_select,
    },
    "TFT16_Augment_ClutteredMind": {
        "on_select":      _cluttered_mind_on_select,
        "on_round_start": _cluttered_mind_on_round_start,
    },
    "TFT16_Augment_CosmicCalling": {
        "on_select":      _cosmic_calling_on_select,
        "on_round_start": _cosmic_calling_on_round_start,
    },
    "TFT16_Augment_DuoQueue": {
        "on_select": _duo_queue_on_select,
    },
    "TFT16_Augment_AuraFarming": {
        "on_select": _aura_farming_on_select,
    },
    "TFT16_Augment_BirthdayReunion": {
        "on_select":      _birthday_reunion_on_select,
        "on_round_start": _birthday_reunion_on_round_start,
    },

    # === NHÓM 3 — Tặng Trang bị ===
    "TFT16_Augment_SmallGrabBag": {
        "on_select": _small_grab_bag_on_select,
    },
    "TFT16_Augment_BigGrabBag": {
        "on_select": _big_grab_bag_on_select,
    },
    "TFT16_Augment_CrownsWill": {
        "on_select": _crowns_will_on_select,
        "passive":   _crowns_will_passive,
    },
    "TFT16_Augment_CryMeARiver": {
        "on_select": _cry_me_a_river_on_select,
        "passive":   _cry_me_a_river_passive,
    },
    "TFT16_Augment_TeamBuilding": {
        "on_select":      _team_building_on_select,
        "on_round_start": _team_building_on_round_start,
    },

    # === NHÓM 4 — Buff chỉ số (passive) ===
    "TFT16_Augment_StandUnited": {
        "passive": _stand_united_passive,
    },
    "TFT16_Augment_BestFriends": {
        "passive": _best_friends_passive,
    },
    "TFT16_Augment_DoubleTrouble": {
        "passive": _double_trouble_passive,
    },
    "TFT16_Augment_SecondWind": {
        "passive": _second_wind_passive,
    },
    "TFT16_Augment_SpoilsOfWar": {
        "on_select": _spoils_of_war_on_select,
    },

    # === NHÓM 5 — Kinh tế theo vòng ===
    "TFT16_Augment_ClearMind": {
        "on_select":      _clear_mind_on_select,
        "on_round_start": _clear_mind_on_round_start,
    },

    # === NHÓM 6 — Điều kiện đặc biệt ===
    "TFT16_Augment_RiskyMoves": {
        "on_select":      _risky_moves_on_select,
        "on_round_start": _risky_moves_on_round_start,
    },
    "TFT16_Augment_SilverDestiny": {
        "on_select": _silver_destiny_on_select,
    },
    "TFT16_Augment_SliceOfLife": {
        "on_select":      _slice_of_life_on_select,
        "on_round_start": _slice_of_life_on_round_start,
    },
    "TFT16_Augment_TableScraps": {
        "on_select":      _table_scraps_on_select,
        "on_round_start": _table_scraps_on_round_start,
    },
    "TFT16_Augment_TitanicTitan": {
        "on_select": _titanic_titan_on_select,
    },
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


def apply_all_round_starts(player: "Player") -> None:
    """
    Fire on_round_start for every augment the player holds.

    Call this at the beginning of each planning phase, after gold income.
    """
    for augment in player.selected_augments:
        apply_augment_hook(player, augment, "on_round_start")