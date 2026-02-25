"""
Augment effect handlers for TFT Set 16.

Each entry in AUGMENT_REGISTRY maps an augment API name to a dict of
lifecycle hooks. Hooks are called by the game engine at specific moments:

    on_select      — called once when the player picks the augment
    passive        — called before each combat; re-applies stat bonuses
    on_round_start — called at the start of each planning phase
    on_combat_end  — called after combat resolves

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

def _grant_champion(player: "Player", champion_name: str, stars: int = 1) -> bool:
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
    new_champ = create_champion(champion_data, stars=stars)
    player._add_to_bench(new_champ)
    return True

def _grant_random_by_cost(player: "Player", cost: int, stars: int = 1) -> Optional[str]:
    """Grant a random champion of a specific cost. Returns champion name or None."""
    candidates = player.data_loader.get_champions_by_cost(cost)
    if not candidates:
        return None
    random.shuffle(candidates)
    for c in candidates:
        if player.pool.is_available(c.champion_id):
            if _grant_champion(player, c.name, stars=stars):
                return c.name
    return None

def _grant_item(player: "Player", item_name: str) -> bool:
    """Grant a specific item by display name."""
    item = player.data_loader.get_item_by_name(item_name)
    if item is None:
        return False
    player.items.append(item.item_id)
    return True

def _grant_random_component(player: "Player") -> Optional[str]:
    """Grant a random base item component. Returns item name or None."""
    all_items = player.data_loader.get_all_items()
    comps = [i for i in all_items if not i.composition
             and not i.item_id.startswith("TFT16_Augment_")]
    if not comps:
        return None
    chosen = random.choice(comps)
    player.items.append(chosen.item_id)
    return chosen.name

def _augment_state_get(player: "Player", key: str, default: Any = None) -> Any:
    """Get augment-specific state stored on the player."""
    if not hasattr(player, '_augment_state'):
        player._augment_state = {}
    return player._augment_state.get(key, default)

def _augment_state_set(player: "Player", key: str, value: Any) -> None:
    """Set augment-specific state on the player."""
    if not hasattr(player, '_augment_state'):
        player._augment_state = {}
    player._augment_state[key] = value


# ---------------------------------------------------------------------------
# RESTART MISSION (TFT16_Augment_RestartMission)
# "Xóa bàn cờ. Nhận 2 tướng 3 vàng 2 sao, 3 tướng 2 vàng 2 sao, 1 tướng 1 vàng 2 sao."
# ---------------------------------------------------------------------------
def _restart_mission_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Sell all units on board and bench, then grant the specified units."""
    # (Implementation of selling all units requires simulator support, mock for now)
    player.board.clear_board()
    player.bench = [None] * 9
    
    grants = []
    for _ in range(2):
        name = _grant_random_by_cost(player, 3, stars=2)
        if name: grants.append(name)
    for _ in range(3):
        name = _grant_random_by_cost(player, 2, stars=2)
        if name: grants.append(name)
    for _ in range(1):
        name = _grant_random_by_cost(player, 1, stars=2)
        if name: grants.append(name)
    return AugmentResult(success=True, grants=grants)


# ---------------------------------------------------------------------------
# RISKY MOVES (TFT16_Augment_RiskyMoves)
# "Mất 20 Máu linh thú. Sau 7 vòng nhận 30 vàng."
# ---------------------------------------------------------------------------
def _risky_moves_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Lose 20 HP. Set state to grant 30 gold after 7 rounds."""
    player.health -= 20
    _augment_state_set(player, 'risky_moves_target_round', player.round + 7)
    return AugmentResult(success=True)

def _risky_moves_on_round_start(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Check if 7 rounds have passed, grant 30 gold if so."""
    target_round = _augment_state_get(player, 'risky_moves_target_round', -1)
    if player.round == target_round:
        player.gold += 30
        return AugmentResult(success=True, gold_delta=30)
    return AugmentResult(success=True)


# ---------------------------------------------------------------------------
# ROLLING FOR DAYS I (TFT16_Augment_RollingForDays1)
# "Nhận 10 reroll miễn phí."
# ---------------------------------------------------------------------------
def _rolling_for_days_i_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Grant 10 free shop rerolls."""
    player.free_rerolls = getattr(player, 'free_rerolls', 0) + 10
    return AugmentResult(success=True)


# ---------------------------------------------------------------------------
# SECOND WIND (TFT16_Augment_SecondWind)
# "Sau 10 giây, hồi 40% máu đã mất cho toàn đội."
# ---------------------------------------------------------------------------
def _second_wind_passive(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Set flag for combat engine to heal 40% missing HP after 10 seconds."""
    for champ in _get_all_champions(player):
        champ._second_wind_heal = 0.40
    return AugmentResult(success=True)


# ---------------------------------------------------------------------------
# SILVER DESTINY (TFT16_Augment_SilverDestiny)
# "Nhận 1 Lõi Bạc ngẫu nhiên và 2 (hoặc 4) vàng."
# ---------------------------------------------------------------------------
def _silver_destiny_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Grant 2 gold and flag for augmenting."""
    # (Actual augment rolling requires simulator state, just grant gold for now)
    player.gold += 2
    return AugmentResult(success=True, gold_delta=2)


# ---------------------------------------------------------------------------
# SILVER SPOON (TFT16_Augment_SilverSpoon)
# "Nhận 10 XP."
# ---------------------------------------------------------------------------
def _silver_spoon_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Grant 10 XP."""
    player.exp += 10
    return AugmentResult(success=True)


# ---------------------------------------------------------------------------
# SLICE OF LIFE (TFT16_Augment_SliceOfLife)
# "Hai lần mỗi giai đoạn, nhận 1 tướng ngẫu nhiên (giá tăng theo giai đoạn). Kết thúc khi nhận tướng 5 vàng."
# ---------------------------------------------------------------------------
def _slice_of_life_on_round_start(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Grant champion 2 times per stage based on stage number."""
    stage = player.round // 5 + 1  # approximate stage calculation
    cost = min(stage, 5)
    
    stage_grants = _augment_state_get(player, f'slice_life_stage_{stage}', 0)
    if stage_grants < 2 and cost <= 5:
        name = _grant_random_by_cost(player, cost, stars=1)
        if name:
            _augment_state_set(player, f'slice_life_stage_{stage}', stage_grants + 1)
            return AugmentResult(success=True, grants=[name])
            
    return AugmentResult(success=True)


# ---------------------------------------------------------------------------
# SMALL GRAB BAG (TFT16_Augment_SmallGrabBag)
# "Nhận 2 mảnh trang bị ngẫu nhiên."
# ---------------------------------------------------------------------------
def _small_grab_bag_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Grant 2 random item components."""
    grants = []
    for _ in range(2):
        name = _grant_random_component(player)
        if name: grants.append(name)
    return AugmentResult(success=True)


# ---------------------------------------------------------------------------
# SPOILS OF WAR I (TFT16_Augment_SpoilsOfWar1)
# "25% tỉ lệ rơi chiến lợi phẩm khi hạ gục địch."
# ---------------------------------------------------------------------------
def _spoils_of_war_passive(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Set flag for combat engine to drop loot on kill."""
    for champ in _get_all_champions(player):
        champ._spoils_of_war_chance = 0.25
    return AugmentResult(success=True)


# ---------------------------------------------------------------------------
# STAND UNITED (TFT16_Augment_StandUnited)
# "Nhận 1.5% SMCK/SMPT cho mỗi Tộc/Hệ kích hoạt."
# ---------------------------------------------------------------------------
def _stand_united_passive(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Calculate active traits and apply AP/AD bonus."""
    active_traits = sum(1 for tier in player.active_traits.values() if tier > 0)
    bonus = active_traits * 1.5
    
    affected = []
    for champ in _get_all_champions(player):
        champ.ability_power += bonus
        # Use a safe additive multiplier or just apply to current (since we reset in apply_all_passives)
        champ.attack_damage *= (1 + bonus / 100)
        affected.append(champ.name)
        
    return AugmentResult(success=True, affected_champions=affected)


# ---------------------------------------------------------------------------
# SURVIVOR (TFT16_Augment_Survivor)
# "Nhận 4 vàng. Khi 3 người chơi bị loại, nhận 100 vàng."
# ---------------------------------------------------------------------------
def _survivor_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Grant 4 gold. Set flag for elimination tracking."""
    player.gold += 4
    return AugmentResult(success=True, gold_delta=4)


# ---------------------------------------------------------------------------
# TABLE SCRAPS (TFT16_Augment_TableScraps)
# "Sau 2 vòng đi chợ tiếp theo, nhận tướng không ai chọn + trang bị của nó. Nhận 1 vàng."
# ---------------------------------------------------------------------------
def _table_scraps_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Grant 1 gold."""
    player.gold += 1
    return AugmentResult(success=True, gold_delta=1)

def _table_scraps_on_round_start(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """(Carousel logic requires simulator support, mock for now)"""
    return AugmentResult(success=True)


# ---------------------------------------------------------------------------
# TEAM BUILDING (TFT16_Augment_TeamBuilding)
# "Nhận 1 Máy Nhân Bản Cỡ Nhỏ. Nhận thêm 1 cái sau 5 vòng."
# ---------------------------------------------------------------------------
def _team_building_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Grant a Lesser Champion Duplicator. Track rounds for the second one."""
    _grant_item(player, "Lesser Champion Duplicator")
    _augment_state_set(player, 'team_building_round', player.round + 5)
    return AugmentResult(success=True)

def _team_building_on_round_start(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Grant the second duplicator after 5 rounds."""
    target_round = _augment_state_get(player, 'team_building_round', -1)
    if player.round == target_round:
        _grant_item(player, "Lesser Champion Duplicator")
    return AugmentResult(success=True)


# ---------------------------------------------------------------------------
# TEAMING UP (TFT16_Augment_TeamingUp)
# "Nhận 1 mảnh trang bị và 2 tướng 3 vàng ngẫu nhiên."
# ---------------------------------------------------------------------------
def _teaming_up_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Grant 1 component and 2 random 3-cost champions."""
    grants = []
    _grant_random_component(player)
    for _ in range(2):
        name = _grant_random_by_cost(player, 3, stars=1)
        if name: grants.append(name)
    return AugmentResult(success=True, grants=grants)


# ---------------------------------------------------------------------------
# TITANIC TITAN (TFT16_Augment_TitanicTitan)
# "Tăng 25 Máu linh thú tối đa. Đi chợ sớm hơn nhưng chạy chậm."
# ---------------------------------------------------------------------------
def _titanic_titan_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Increase player max health by 25 and heal 25."""
    player.max_health = getattr(player, 'max_health', 100) + 25
    player.health += 25
    return AugmentResult(success=True)


# ---------------------------------------------------------------------------
# 3 THREES (TFT16_Augment_ThreeThrees)
# "Nhận 3 tướng 3 vàng 2 sao và 3 vàng."
# ---------------------------------------------------------------------------
def _3_threes_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Grant 3x random 3-cost 2-star champions and 3 gold."""
    player.gold += 3
    grants = []
    for _ in range(3):
        name = _grant_random_by_cost(player, 3, stars=2)
        if name: grants.append(name)
    return AugmentResult(success=True, gold_delta=3, grants=grants)


# ---------------------------------------------------------------------------
# ADVANCED LOAN (TFT16_Augment_AdvancedLoan)
# "Nhận 20 (hoặc 33) vàng. Lõi tiếp theo giảm 1 bậc."
# ---------------------------------------------------------------------------
def _advanced_loan_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Grant 20 gold (or 33 for Plus)."""
    gold = int(effects.get("Gold", 20))
    player.gold += gold
    return AugmentResult(success=True, gold_delta=gold)


# ---------------------------------------------------------------------------
# AURA FARMING (TFT16_Augment_AuraFarming)
# "Nhận 1 tướng 5 vàng 2 sao có trang bị. Không thể dùng đến vòng 4-2."
# ---------------------------------------------------------------------------
def _aura_farming_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Grant 5-cost 2-star and lock it until 4-2."""
    name = _grant_random_by_cost(player, 5, stars=2)
    # Simulator support needed for locking standard usage
    return AugmentResult(success=True, grants=[name] if name else [])


# ---------------------------------------------------------------------------
# BEST FRIENDS II (TFT16_Augment_BestFriends2)
# "Cặp đồng minh đứng tách biệt nhận 15% Tốc độ đánh, 22 Giáp."
# ---------------------------------------------------------------------------
def _best_friends_passive(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Apply AS and Armor (Position logic requires board parsing)."""
    # Assuming standard stat granting for now
    affected = []
    for champ in _get_all_champions(player):
        champ.attack_speed *= 1.15
        champ.armor += 22
        affected.append(champ.name)
    return AugmentResult(success=True, affected_champions=affected)


# ---------------------------------------------------------------------------
# BIG GRAB BAG (TFT16_Augment_BigGrabBag)
# "Nhận 3 mảnh trang bị, 2 vàng, 1 Búa Rèn."
# ---------------------------------------------------------------------------
def _big_grab_bag_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Grant 3 components, 2 gold, 1 reforger."""
    player.gold += 2
    _grant_item(player, "Reforger")
    for _ in range(3):
        _grant_random_component(player)
    return AugmentResult(success=True, gold_delta=2)


# ---------------------------------------------------------------------------
# BIRTHDAY REUNION (TFT16_Augment_BirthdayReunion)
# "Nhận tướng 2 vàng 2 sao. Cấp 7 nhận Găng Đạo Tặc. Cấp 9 nhận tướng 5 vàng 2 sao."
# ---------------------------------------------------------------------------
def _birthday_reunion_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Grant a random 2-cost 2-star champion."""
    name = _grant_random_by_cost(player, 2, stars=2)
    return AugmentResult(success=True, grants=[name] if name else [])

def _birthday_reunion_on_round_start(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Check player level for level 7 and level 9 rewards."""
    lvl7 = _augment_state_get(player, 'birthday_lvl_7_done', False)
    lvl9 = _augment_state_get(player, 'birthday_lvl_9_done', False)
    
    if player.level >= 7 and not lvl7:
        _grant_item(player, "Thief's Gloves")
        _augment_state_set(player, 'birthday_lvl_7_done', True)
        
    if player.level >= 9 and not lvl9:
        _grant_random_by_cost(player, 5, stars=2)
        _augment_state_set(player, 'birthday_lvl_9_done', True)
        
    return AugmentResult(success=True)


# ---------------------------------------------------------------------------
# CALCULATED LOSS (TFT16_Augment_CalculatedLoss)
# "Thua giao tranh nhận 2 vàng và 1 reroll."
# ---------------------------------------------------------------------------
def _calculated_loss_on_combat_end(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """If combat lost, grant 2 gold and 1 free reroll."""
    if effects.get('combat_lost', False):
        player.gold += 2
        player.free_rerolls = getattr(player, 'free_rerolls', 0) + 1
        return AugmentResult(success=True, gold_delta=2)
    return AugmentResult(success=True)


# ---------------------------------------------------------------------------
# CLEAR MIND (TFT16_Augment_ClearMind)
# "Nếu không có tướng trên hàng chờ, nhận 3 XP cuối vòng."
# ---------------------------------------------------------------------------
def _clear_mind_on_combat_end(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """If bench is empty, grant 3 XP."""
    bench_empty = all(c is None for c in player.bench)
    if bench_empty:
        player.exp += 3
    return AugmentResult(success=True)


# ---------------------------------------------------------------------------
# CLUTTERED MIND (TFT16_Augment_ClutteredMind)
# "Nhận 4 tướng 1 vàng. Nếu hàng chờ đầy cuối vòng, nhận 3 XP."
# ---------------------------------------------------------------------------
def _cluttered_mind_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Grant 4 random 1-cost champions."""
    grants = []
    for _ in range(4):
        name = _grant_random_by_cost(player, 1, stars=1)
        if name: grants.append(name)
    return AugmentResult(success=True, grants=grants)

def _cluttered_mind_on_combat_end(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """If bench is full, grant 3 XP."""
    bench_full = all(c is not None for c in player.bench)
    if bench_full:
        player.exp += 3
    return AugmentResult(success=True)


# ---------------------------------------------------------------------------
# CONSTRUCT A COMPANION (TFT16_Augment_ConstructACompanion)
# "Tướng 1 vàng tiếp theo mua sẽ là 3 sao. Nhận 2 vàng."
# ---------------------------------------------------------------------------
def _construct_companion_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Grant 2 gold. Set flag for shop tracking."""
    player.gold += 2
    player._construct_companion_active = True
    return AugmentResult(success=True, gold_delta=2)


# ---------------------------------------------------------------------------
# COSMIC CALLING (TFT16_Augment_Targon_CosmicCalling)
# "Nhận Ngọn Giáo Shojin và Leona. Vòng 3-7 nhận Taric."
# ---------------------------------------------------------------------------
def _cosmic_calling_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Grant Shojin and Leona."""
    grants = []
    _grant_item(player, "Spear of Shojin")
    if _grant_champion(player, "Leona", stars=1):
        grants.append("Leona")
    return AugmentResult(success=True, grants=grants)

def _cosmic_calling_on_round_start(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Grant Taric on Round 3-7 (represented by absolute round or stage timing)."""
    # Assuming standard round 3-7 logic
    if player.round == 20 and not _augment_state_get(player, 'cosmic_taric_done', False):
        _grant_champion(player, "Taric", stars=1)
        _augment_state_set(player, 'cosmic_taric_done', True)
    return AugmentResult(success=True)


# ---------------------------------------------------------------------------
# CROWN'S WILL (TFT16_Augment_CrownsWill)
# "Nhận Gậy Quá Khổ + Giáp Lưới. Đội nhận 8 SMPT, 6 Giáp."
# ---------------------------------------------------------------------------
def _crowns_will_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Grant Needlessly Large Rod and Chain Vest."""
    _grant_item(player, "Needlessly Large Rod")
    _grant_item(player, "Chain Vest")
    return AugmentResult(success=True)

def _crowns_will_passive(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Apply Team AP and Armor bonuses."""
    affected = []
    for champ in _get_all_champions(player):
        champ.ability_power += 8
        champ.armor += 6
        affected.append(champ.name)
    return AugmentResult(success=True, affected_champions=affected)


# ---------------------------------------------------------------------------
# CRY ME A RIVER (TFT16_Augment_CryMeARiver)
# "Nhận Nước Mắt. Đội hồi 1 Năng lượng (tăng lên 3 sau 12 giây)."
# ---------------------------------------------------------------------------
def _cry_me_a_river_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Grant Tear of the Goddess."""
    _grant_item(player, "Tear of the Goddess")
    return AugmentResult(success=True)

def _cry_me_a_river_passive(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Set flag for combat engine to handle mana regen."""
    for champ in _get_all_champions(player):
        champ._cry_me_a_river_mana_regen = True
    return AugmentResult(success=True)


# ---------------------------------------------------------------------------
# DOUBLE TROUBLE (TFT16_Augment_DoubleTrouble)
# "2 bản sao tướng nhận 30% chỉ số. Lên 3 sao tặng 1 bản sao 2 sao."
# ---------------------------------------------------------------------------
def _double_trouble_passive(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Apply 30% stats if exactly 2 copies are fielded."""
    name_counts = {}
    for champ in player.board.get_all_champions():
        name_counts[champ.name] = name_counts.get(champ.name, 0) + 1
        
    affected = []
    for champ in player.board.get_all_champions():
        if name_counts.get(champ.name, 0) == 2:
            champ.attack_damage *= 1.30
            champ.ability_power += 30
            champ.armor += 30
            champ.magic_resist += 30
            affected.append(champ.name)
            
    return AugmentResult(success=True, affected_champions=affected)


# ---------------------------------------------------------------------------
# DUO QUEUE (TFT16_Augment_DuoQueue)
# "Nhận 2 tướng 5 vàng ngẫu nhiên và 2 bản sao của 1 mảnh trang bị."
# ---------------------------------------------------------------------------
def _duo_queue_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Grant 2 random 5-costs and 2 of the same component."""
    grants = []
    for _ in range(2):
        name = _grant_random_by_cost(player, 5, stars=1)
        if name: grants.append(name)
        
    comp_name = _grant_random_component(player)
    if comp_name:
        _grant_item(player, comp_name)
        
    return AugmentResult(success=True, grants=grants)


# ---------------------------------------------------------------------------
# EPIC ROLLDOWN (TFT16_Augment_EpicRolldown)
# "Đạt cấp 8 nhận 20 reroll."
# ---------------------------------------------------------------------------
def _epic_rolldown_on_round_start(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    """Check if player reached level 8 to grant rerolls."""
    if player.level >= 8 and not _augment_state_get(player, 'epic_rolldown_done', False):
        player.free_rerolls = getattr(player, 'free_rerolls', 0) + 20
        _augment_state_set(player, 'epic_rolldown_done', True)
    return AugmentResult(success=True)


# ---------------------------------------------------------------------------
# EPOCH (TFT16_Augment_Epoch)
# "Now, and at the start of every stage, gain 4 XP and 3 free rerolls."
# ---------------------------------------------------------------------------
def _epoch_apply(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    xp = int(effects.get("XPAmount", 4))
    rerolls = int(effects.get("RerollCount", 3))
    player.exp += xp
    player.free_rerolls = getattr(player, 'free_rerolls', 0) + rerolls
    return AugmentResult(success=True, xp_delta=xp, rerolls_granted=rerolls)

def _epoch_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    return _epoch_apply(player, effects)

def _epoch_on_stage_start(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    return _epoch_apply(player, effects)


# ---------------------------------------------------------------------------
# EPOCH+ (TFT16_Augment_EpochPlus)
# "Now, and at the start of every stage, gain 8 XP and 3 free rerolls."
# ---------------------------------------------------------------------------
def _epoch_plus_on_select(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    return _epoch_apply(player, effects)

def _epoch_plus_on_stage_start(player: "Player", effects: Dict[str, Any]) -> AugmentResult:
    return _epoch_apply(player, effects)


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
    so bonuses never stack across successive passive calls.

    Attributes modified on the champion instance:
        attack_range   — increased by MaxRange (e.g. +7 hexes)
        _fires_missiles (bool) — signals combat engine to enable the
                                 continuous missile barrage, scaled by
                                 the unit's attack_speed
    """
    bonus_range: int = int(effects.get("MaxRange", 0))

    target = _strongest_rumble(player)
    if target is None:
        return AugmentResult(success=False)

    # Direct mutation — same approach as reference project's change_stat().
    # attack_range is already reset to base in apply_all_passives() via _update_base_stats()
    target.attack_range += bonus_range
    target._fires_missiles = True
    return AugmentResult(success=True, affected_champions=[target.name])


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

AUGMENT_REGISTRY: Dict[str, Dict[str, Any]] = {
    # 15 Silver Augments
    "TFT16_Augment_RestartMission": {"on_select": _restart_mission_on_select},
    "TFT16_Augment_RiskyMoves": {"on_select": _risky_moves_on_select, "on_round_start": _risky_moves_on_round_start},
    "TFT16_Augment_RollingForDays1": {"on_select": _rolling_for_days_i_on_select},
    "TFT16_Augment_SecondWind": {"passive": _second_wind_passive},
    "TFT16_Augment_SilverDestiny": {"on_select": _silver_destiny_on_select},
    "TFT16_Augment_SilverSpoon": {"on_select": _silver_spoon_on_select},
    "TFT16_Augment_SliceOfLife": {"on_round_start": _slice_of_life_on_round_start},
    "TFT16_Augment_SmallGrabBag": {"on_select": _small_grab_bag_on_select},
    "TFT16_Augment_SpoilsOfWar1": {"passive": _spoils_of_war_passive},
    "TFT16_Augment_StandUnited": {"passive": _stand_united_passive},
    "TFT16_Augment_Survivor": {"on_select": _survivor_on_select},
    "TFT16_Augment_TableScraps": {"on_select": _table_scraps_on_select, "on_round_start": _table_scraps_on_round_start},
    "TFT16_Augment_TeamBuilding": {"on_select": _team_building_on_select, "on_round_start": _team_building_on_round_start},
    "TFT16_Augment_TeamingUp": {"on_select": _teaming_up_on_select},
    "TFT16_Augment_TitanicTitan": {"on_select": _titanic_titan_on_select},
    
    # 16 Gold Augments
    "TFT16_Augment_ThreeThrees": {"on_select": _3_threes_on_select},
    "TFT16_Augment_AdvancedLoan": {"on_select": _advanced_loan_on_select},
    "TFT16_Augment_AuraFarming": {"on_select": _aura_farming_on_select},
    "TFT16_Augment_BestFriends2": {"passive": _best_friends_passive},
    "TFT16_Augment_BigGrabBag": {"on_select": _big_grab_bag_on_select},
    "TFT16_Augment_BirthdayReunion": {"on_select": _birthday_reunion_on_select, "on_round_start": _birthday_reunion_on_round_start},
    "TFT16_Augment_CalculatedLoss": {"on_combat_end": _calculated_loss_on_combat_end},
    "TFT16_Augment_ClearMind": {"on_combat_end": _clear_mind_on_combat_end},
    "TFT16_Augment_ClutteredMind": {"on_select": _cluttered_mind_on_select, "on_combat_end": _cluttered_mind_on_combat_end},
    "TFT16_Augment_ConstructACompanion": {"on_select": _construct_companion_on_select},
    "TFT16_Augment_Targon_CosmicCalling": {"on_select": _cosmic_calling_on_select, "on_round_start": _cosmic_calling_on_round_start},
    "TFT16_Augment_CrownsWill": {"on_select": _crowns_will_on_select, "passive": _crowns_will_passive},
    "TFT16_Augment_CryMeARiver": {"on_select": _cry_me_a_river_on_select, "passive": _cry_me_a_river_passive},
    "TFT16_Augment_DoubleTrouble": {"passive": _double_trouble_passive},
    "TFT16_Augment_DuoQueue": {"on_select": _duo_queue_on_select},
    "TFT16_Augment_EpicRolldown": {"on_round_start": _epic_rolldown_on_round_start},
    
    "TFT16_Augment_Epoch": {
        "on_select":      _epoch_on_select,
        "on_stage_start": _epoch_on_stage_start,
    },
    "TFT16_Augment_EpochPlus": {
        "on_select":      _epoch_plus_on_select,
        "on_stage_start": _epoch_plus_on_stage_start,
    },

    # Reference
    "TFT16_Augment_RumbleCarry": {"on_select": _artillery_barrage_on_select, "passive": _artillery_barrage_passive},
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
        event:   One of "on_select", "passive", "on_round_start", "on_combat_end".

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
    
    Resets all champions to base stats first to avoid stacking bonuses
    from successive calls.
    """
    for champ in _get_all_champions(player):
        champ._update_base_stats()
        # Reset custom augment flags
        champ._fires_missiles = False
        champ._second_wind_heal = 0.0
        champ._spoils_of_war_chance = 0.0
        champ._cry_me_a_river_mana_regen = False

    for augment in player.selected_augments:
        apply_augment_hook(player, augment, "passive")


def apply_all_round_starts(player: "Player") -> None:
    for augment in player.selected_augments:
        apply_augment_hook(player, augment, "on_round_start")


def apply_all_combat_ends(player: "Player", combat_lost: bool = False) -> None:
    for augment in player.selected_augments:
        handler = AUGMENT_REGISTRY.get(augment.augment_id)
        if handler:
            hook = handler.get("on_combat_end")
            if hook:
                eff = augment.effects.copy() if augment.effects else {}
                eff['combat_lost'] = combat_lost
                hook(player, eff)


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
