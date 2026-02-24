"""
TFT Set 16 Simulator Configuration
Defines all configurable parameters for the environment
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, List
from pathlib import Path


@dataclass
class TFTConfig:
    """
    Main configuration for TFT Set 16 environment.
    
    This configuration is used to initialize the TFT simulator with
    different settings for training, evaluation, or experimentation.
    """
    
    # ===== Environment Settings =====
    num_players: int = 8
    """Number of players in each game (default: 8)"""
    
    max_actions_per_round: int = 20
    """Maximum actions a player can take per planning phase"""
    
    max_game_rounds: int = 48
    """Maximum number of rounds before game ends (stage 7-6)"""
    
    # ===== Data Settings =====
    set_name: str = "set16"
    """TFT set identifier (e.g., 'set16')"""
    
    data_dir: Optional[Path] = None
    """Path to game data directory. If None, uses default from data_loader"""
    
    # ===== Reward Settings =====
    reward_type: str = "placement"
    """
    Reward calculation method:
    - 'placement': Reward based on final placement (1st=40, 2nd=35, ..., 8th=5)
    - 'health': Reward based on health changes each round
    - 'combined': Combination of placement and health
    """
    
    damage_reward_scale: float = 0.1
    """Scale factor for damage-based rewards (used in 'health' mode)"""
    
    placement_rewards: Dict[int, int] = field(default_factory=lambda: {
        1: 40,  # 1st place
        2: 35,
        3: 30,
        4: 25,
        5: 20,
        6: 15,
        7: 10,
        8: 5    # 8th place
    })
    """Reward values for each placement"""
    
    # ===== Combat Settings =====
    combat_mode: str = "statistical"
    """
    Combat resolution mode:
    - 'statistical': Fast approximate combat (MVP)
    - 'simplified': Lightweight simulation (Phase 2)
    - 'full': Detailed simulation (Phase 4)
    """
    
    combat_timeout: float = 30.0
    """Maximum combat duration in seconds (game time)"""
    
    # ===== Game Mechanics Settings =====
    starting_gold: int = 0
    """Gold at game start"""
    
    starting_health: int = 100
    """Health at game start"""
    
    starting_level: int = 1
    """Player level at game start"""
    
    interest_cap: int = 5
    """Maximum gold from interest (1 gold per 10, max 5)"""
    
    gold_per_round: int = 5
    """Base gold given at start of each round"""
    
    max_level: int = 11
    """Maximum player level"""
    
    xp_cost: int = 4
    """Gold cost to buy 4 XP"""
    
    shop_refresh_cost: int = 2
    """Gold cost to reroll shop"""
    
    # ===== Shop Odds =====
    shop_odds: Dict[int, List[float]] = field(default_factory=lambda: {
        # Level: [1-cost%, 2-cost%, 3-cost%, 4-cost%, 5-cost%]
        1: [1.00, 0.00, 0.00, 0.00, 0.00],
        2: [1.00, 0.00, 0.00, 0.00, 0.00],
        3: [0.75, 0.25, 0.00, 0.00, 0.00],
        4: [0.55, 0.30, 0.15, 0.00, 0.00],
        5: [0.45, 0.33, 0.20, 0.02, 0.00],
        6: [0.30, 0.40, 0.25, 0.05, 0.00],
        7: [0.19, 0.30, 0.35, 0.15, 0.01],
        8: [0.16, 0.20, 0.35, 0.25, 0.04],
        9: [0.09, 0.15, 0.30, 0.30, 0.16],
        10: [0.05, 0.10, 0.20, 0.40, 0.25],
        11: [0.01, 0.02, 0.12, 0.50, 0.35],
    })
    """Shop champion tier probabilities by player level"""
    
    # ===== Pool Settings =====
    champion_pool_size: Dict[int, int] = field(default_factory=lambda: {
        1: 29,  # 29 copies of each 1-cost
        2: 22,  # 22 copies of each 2-cost
        3: 18,  # 18 copies of each 3-cost
        4: 12,  # 12 copies of each 4-cost
        5: 10,  # 10 copies of each 5-cost
        6: 9,   # 9 copies of each 6-cost (Set 16)
        7: 8,   # 8 copies (if any)
        8: 7,   # 7 copies (if any)
    })
    """Number of copies of each champion in the shared pool"""
    
    # ===== Board Settings =====
    board_size: tuple = (4, 7)
    """Board dimensions (rows, cols) for hex grid"""
    
    bench_size: int = 9
    """Number of bench slots"""
    
    shop_size: int = 5
    """Number of champions shown in shop"""
    
    max_items_per_champion: int = 3
    """Maximum items each champion can hold"""
    
    # ===== XP Requirements =====
    xp_to_level: Dict[int, int] = field(default_factory=lambda: {
        1: 0,   # Start at level 1
        2: 2,   # Need 2 XP to reach level 2
        3: 6,   # Need 6 XP total to reach level 3
        4: 10,
        5: 20,
        6: 36,
        7: 56,
        8: 80,
        9: 108,
        10: 136,
        11: 99999,  # Can't level past 11
    })
    """Total XP needed to reach each level"""
    
    max_units_by_level: Dict[int, int] = field(default_factory=lambda: {
        1: 1, 2: 2, 3: 3, 4: 4, 5: 5,
        6: 6, 7: 7, 8: 8, 9: 9, 10: 10, 11: 11
    })
    """Maximum units on board by player level"""
    
    # ===== Round Damage =====
    round_damage: Dict[int, int] = field(default_factory=lambda: {
        # Round: base damage for losing
        1: 0, 2: 0, 3: 0,  # Stage 1: carousel + minions
        4: 2, 5: 2, 6: 2,  # Stage 2
        7: 3, 8: 3, 9: 3,  # Stage 3
        10: 4, 11: 4, 12: 4, 13: 4,  # Stage 4
        14: 5, 15: 5, 16: 5, 17: 5,  # Stage 5
        18: 6, 19: 6, 20: 6, 21: 6,  # Stage 6
        22: 7, 23: 7, 24: 7, 25: 7,  # Stage 7
    })
    """Base damage for losing at each round"""
    
    # ===== Feature Flags =====
    enable_items: bool = False
    """Enable item system (Phase 2+)"""
    
    enable_traits: bool = False
    """Enable trait bonuses (Phase 2+)"""
    
    enable_augments: bool = False
    """Enable augments (Phase 4+)"""
    
    enable_portals: bool = False
    """Enable portals (Phase 4+)"""
    
    enable_carousel: bool = False
    """Enable carousel rounds (Phase 2+)"""
    
    # ===== Rendering Settings =====
    render_mode: Optional[str] = None
    """
    Rendering mode:
    - None: No rendering
    - 'human': Console output
    - 'json': JSON game logs
    """
    
    render_path: Path = Path("./games")
    """Directory to save rendered games"""
    
    # ===== Training Settings =====
    enable_action_masking: bool = True
    """Use action masking (highly recommended)"""
    
    observation_type: str = "token"
    """
    Observation encoding:
    - 'token': Token-based for transformers
    - 'vector': Flat vector for MLPs
    """
    
    normalize_observations: bool = True
    """Normalize observation values to [0, 1] or [-1, 1]"""
    
    # ===== Debug Settings =====
    debug_mode: bool = False
    """Enable debug logging"""
    
    seed: Optional[int] = None
    """Random seed for reproducibility"""
    
    log_level: str = "INFO"
    """Logging level: DEBUG, INFO, WARNING, ERROR"""


# ===== Preset Configurations =====

def get_mvp_config() -> TFTConfig:
    """
    Configuration for Phase 1 MVP.
    Minimal features for fast iteration.
    """
    return TFTConfig(
        num_players=8,
        max_actions_per_round=15,
        combat_mode="statistical",
        enable_items=False,
        enable_traits=False,
        enable_augments=False,
        enable_portals=False,
        enable_carousel=False,
        debug_mode=True,
    )


def get_training_config() -> TFTConfig:
    """
    Configuration for Phase 2+ training.
    Includes items and traits.
    """
    return TFTConfig(
        num_players=8,
        max_actions_per_round=20,
        combat_mode="simplified",
        enable_items=True,
        enable_traits=True,
        enable_augments=False,
        enable_portals=False,
        enable_carousel=True,
        debug_mode=False,
    )


def get_full_config() -> TFTConfig:
    """
    Configuration for Phase 4 full simulation.
    All features enabled.
    """
    return TFTConfig(
        num_players=8,
        max_actions_per_round=25,
        combat_mode="full",
        enable_items=True,
        enable_traits=True,
        enable_augments=True,
        enable_portals=True,
        enable_carousel=True,
        debug_mode=False,
    )


def get_fast_config() -> TFTConfig:
    """
    Configuration for fast testing.
    Fewer players, faster combat.
    """
    return TFTConfig(
        num_players=4,
        max_actions_per_round=10,
        max_game_rounds=20,
        combat_mode="statistical",
        enable_items=False,
        enable_traits=False,
        debug_mode=True,
    )


# ===== Game Constants =====

class GameConstants:
    """
    Hard-coded game constants that don't change.
    """
    
    # Star multipliers
    STAR_HP_MULTIPLIER = {1: 1.0, 2: 1.8, 3: 3.24}
    STAR_AD_MULTIPLIER = {1: 1.0, 2: 1.8, 3: 3.24}
    
    # Gold mechanics
    INTEREST_RATE = 0.1  # 1 gold per 10
    MAX_INTEREST = 5
    
    # Combat
    MAX_COMBAT_TIME = 30.0  # seconds
    
    # Carousel
    CAROUSEL_ROUNDS = [9, 18, 27, 36]  # Rounds with carousel (no opening carousel in Set 16)

    # Minion rounds (rounds 1-3 are PvE minion rounds)
    MINION_ROUNDS = [1, 2, 3]
    
    # Augment rounds (Set 16 specific)
    AUGMENT_ROUNDS = [6, 13, 20]  # 2-1, 3-2, 4-1


if __name__ == "__main__":
    # Example usage
    config = get_mvp_config()
    print(f"TFT Config for {config.set_name}")
    print(f"Players: {config.num_players}")
    print(f"Combat mode: {config.combat_mode}")
    print(f"Items enabled: {config.enable_items}")
    print(f"Traits enabled: {config.enable_traits}")
