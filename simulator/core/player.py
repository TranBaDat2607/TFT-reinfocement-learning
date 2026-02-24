"""
Player state and actions for TFT Set 16.

Manages a single player's state including:
- Economy (gold, level, XP, health)
- Units (board, bench, shop)
- Actions (buy, sell, move, level up, refresh)
"""
from typing import List, Optional, Dict, Tuple
from simulator.core.board import Board
from simulator.core.champion import Champion, create_champion
from simulator.core.pool import ChampionPool
from simulator.config import TFTConfig
from data_loader import TFTDataLoader


class Player:
    """
    Represents one player in TFT.
    
    Manages player state and provides methods for all player actions.
    """
    
    def __init__(
        self,
        player_id: int,
        pool: ChampionPool,
        config: TFTConfig,
        data_loader: Optional[TFTDataLoader] = None
    ):
        """
        Initialize player.
        
        Args:
            player_id: Player identifier (0-7)
            pool: Shared champion pool
            config: Game configuration
            data_loader: Data loader instance
        """
        self.player_id = player_id
        self.pool = pool
        self.config = config
        self.data_loader = data_loader or TFTDataLoader()
        
        # Economy
        self.gold = config.starting_gold
        self.health = config.starting_health
        self.level = config.starting_level
        self.xp = 0
        self.free_rerolls: int = 0

        # Units
        self.board = Board()
        self.bench: List[Optional[Champion]] = [None] * config.bench_size
        self.shop: List[Optional[str]] = [None] * config.shop_size
        
        # Items (Phase 2+)
        self.items: List[str] = []
        
        # Game state
        self.is_alive = True
        self.placement = 0  # Final placement (1-8)
        
        # Stats tracking
        self.gold_spent = 0
        self.total_damage_dealt = 0
        self.total_damage_taken = 0
        self.rounds_survived = 0
        
        # Trait cache (recomputed when board changes)
        self.active_traits: Dict[str, int] = {}

        # Augments (Phase 4+)
        self.selected_augments: List = []  # List[Augment]
    
    # ===== Economy Actions =====
    
    def buy_xp(self) -> bool:
        """
        Buy 4 experience points for 4 gold.
        
        Returns:
            True if successful, False if not enough gold or max level
        """
        if self.gold < self.config.xp_cost:
            return False
        
        if self.level >= self.config.max_level:
            return False
        
        self.gold -= self.config.xp_cost
        self.gold_spent += self.config.xp_cost
        self.xp += 4
        
        # Check for level up
        self._check_level_up()
        
        return True
    
    def _check_level_up(self):
        """Check if player has enough XP to level up."""
        next_level = self.level + 1
        
        if next_level > self.config.max_level:
            return
        
        xp_needed = self.config.xp_to_level.get(next_level, 99999)
        
        if self.xp >= xp_needed:
            self.level = next_level
            # XP doesn't reset in TFT
    
    def gain_interest(self) -> int:
        """
        Calculate and gain interest gold.
        
        Returns:
            Amount of interest gained
        """
        interest = min(self.gold // 10, self.config.interest_cap)
        self.gold += interest
        return interest
    
    def start_of_round_gold(self):
        """Give gold at start of planning phase."""
        self.gold += self.config.gold_per_round
        self.gain_interest()
    
    # ===== Shop Actions =====
    
    def refresh_shop(self) -> bool:
        """
        Refresh shop for 2 gold, or free if the player has free rerolls.

        Returns:
            True if successful, False if not enough gold and no free rerolls
        """
        if self.free_rerolls > 0:
            self.free_rerolls -= 1
            self._generate_shop()
            return True

        if self.gold < self.config.shop_refresh_cost:
            return False

        self.gold -= self.config.shop_refresh_cost
        self.gold_spent += self.config.shop_refresh_cost
        self._generate_shop()
        return True
    
    def _generate_shop(self):
        """Generate new shop based on player level."""
        self.shop = self.pool.sample_shop(
            level=self.level,
            shop_size=self.config.shop_size,
            shop_odds=self.config.shop_odds
        )
    
    def buy_champion_from_shop(self, shop_index: int) -> bool:
        """
        Buy champion from shop.
        
        Args:
            shop_index: Index in shop (0-4)
            
        Returns:
            True if successful, False otherwise
        """
        # Validate shop index
        if not (0 <= shop_index < self.config.shop_size):
            return False
        
        champion_id = self.shop[shop_index]
        if champion_id is None:
            return False
        
        # Get champion data
        champion_data = self.data_loader.get_champion_by_id(champion_id)
        if not champion_data:
            return False
        
        # Check gold
        if self.gold < champion_data.cost:
            return False
        
        # Check if pool has this champion
        if not self.pool.is_available(champion_id):
            return False
        
        # Buy from pool
        if not self.pool.acquire(champion_id):
            return False
        
        # Deduct gold
        self.gold -= champion_data.cost
        self.gold_spent += champion_data.cost
        
        # Create champion
        new_champion = create_champion(champion_data, stars=1)
        
        # Try to add to bench
        added = self._add_to_bench(new_champion)
        
        if not added:
            # Bench full - auto-sell
            self._sell_champion(new_champion)
        
        # Remove from shop
        self.shop[shop_index] = None
        
        return True
    
    def _add_to_bench(self, champion: Champion) -> bool:
        """
        Add champion to bench, handling auto-upgrades.
        
        Returns:
            True if added successfully, False if bench full
        """
        # Check for potential upgrade first
        upgraded = self._check_for_upgrade(champion)
        
        if upgraded:
            # Champion was upgraded, try to find space again
            return self._add_to_bench_no_upgrade(champion)
        else:
            return self._add_to_bench_no_upgrade(champion)
    
    def _add_to_bench_no_upgrade(self, champion: Champion) -> bool:
        """Add champion to first empty bench slot."""
        for i, slot in enumerate(self.bench):
            if slot is None:
                self.bench[i] = champion
                return True
        return False
    
    def _check_for_upgrade(self, new_champion: Champion) -> bool:
        """
        Check if we have 3 copies of a champion and can upgrade.
        
        Returns:
            True if upgrade occurred
        """
        # Count how many of this champion we have (bench + board)
        same_champions = []
        
        # Check bench
        for champ in self.bench:
            if champ and champ.data.champion_id == new_champion.data.champion_id and champ.stars == new_champion.stars:
                same_champions.append(champ)
        
        # Check board
        for champ in self.board.get_all_champions():
            if champ.data.champion_id == new_champion.data.champion_id and champ.stars == new_champion.stars:
                same_champions.append(champ)
        
        # Need 3 total (including new one)
        if len(same_champions) >= 2:  # 2 existing + 1 new = 3
            # Upgrade one of them
            champion_to_upgrade = same_champions[0]
            champion_to_upgrade.upgrade_star()
            
            # Remove the other copy
            other_copy = same_champions[1]
            self._remove_champion_from_bench_or_board(other_copy)
            
            # Don't add new champion (it was "consumed" in upgrade)
            return True
        
        return False
    
    def _remove_champion_from_bench_or_board(self, champion: Champion):
        """Remove champion from wherever it is."""
        # Try bench
        for i, champ in enumerate(self.bench):
            if champ == champion:
                self.bench[i] = None
                return
        
        # Try board
        pos = self.board.find_champion(champion)
        if pos:
            self.board.remove(pos[0], pos[1])
    
    # ===== Unit Management Actions =====
    
    def move_champion(self, from_pos: Tuple[int, int], to_pos: Tuple[int, int]) -> bool:
        """
        Move champion between board and bench.
        
        Positions:
        - Board: (row 0-3, col 0-6)
        - Bench: (row -1, col 0-8)
        
        Args:
            from_pos: Source position (row, col)
            to_pos: Destination position (row, col)
            
        Returns:
            True if successful
        """
        from_row, from_col = from_pos
        to_row, to_col = to_pos
        
        # Get source champion
        if from_row == -1:  # From bench
            if not (0 <= from_col < len(self.bench)):
                return False
            champion = self.bench[from_col]
            if not champion:
                return False
        else:  # From board
            champion = self.board.get(from_row, from_col)
            if not champion:
                return False
        
        # Check destination
        if to_row == -1:  # To bench
            if not (0 <= to_col < len(self.bench)):
                return False
            if self.bench[to_col] is not None:
                return False  # Bench slot occupied
            
            # Remove from source
            if from_row == -1:
                self.bench[from_col] = None
            else:
                self.board.remove(from_row, from_col)
            
            # Place on bench
            self.bench[to_col] = champion
            champion.position = None
            
        else:  # To board
            # Check board size limit
            if self.board.count_champions() >= self.config.max_units_by_level[self.level]:
                if from_row != -1:  # Moving within board is ok
                    pass
                else:  # Adding from bench to full board
                    return False
            
            if not self.board.is_empty(to_row, to_col):
                return False
            
            # Remove from source
            if from_row == -1:
                self.bench[from_col] = None
            else:
                self.board.remove(from_row, from_col)
            
            # Place on board
            self.board.place(champion, to_row, to_col)
        
        return True
    
    def sell_champion(self, position: Tuple[int, int]) -> bool:
        """
        Sell champion and return to pool.
        
        Args:
            position: (row, col) - row=-1 for bench, 0-3 for board
            
        Returns:
            True if successful
        """
        row, col = position
        
        # Get champion
        if row == -1:  # Bench
            if not (0 <= col < len(self.bench)):
                return False
            champion = self.bench[col]
            if not champion:
                return False
            self.bench[col] = None
        else:  # Board
            champion = self.board.remove(row, col)
            if not champion:
                return False
        
        return self._sell_champion(champion)
    
    def _sell_champion(self, champion: Champion) -> bool:
        """Internal method to sell a champion."""
        # Return to pool (based on base champion, not upgraded)
        for _ in range(3 ** (champion.stars - 1)):  # 1→1, 2→3, 3→9
            self.pool.release(champion.data.champion_id)
        
        # Give gold
        sell_value = champion.cost
        self.gold += sell_value
        
        return True
    
    # ===== Combat =====
    
    def take_damage(self, damage: int):
        """Take damage from losing combat."""
        self.health -= damage
        self.total_damage_taken += damage
        
        if self.health <= 0:
            self.health = 0
            self.is_alive = False
    
    def reset_for_combat(self):
        """Reset all units for new combat."""
        for champion in self.board.get_all_champions():
            champion.reset_for_combat()
    
    # ===== Augments =====

    def select_augment(self, augment) -> None:
        """
        Apply an augment to this player (called at rounds 6, 13, 20).

        Fires the augment's on_select hook immediately.
        """
        from simulator.env.augment_effects import apply_augment_hook
        self.selected_augments.append(augment)
        apply_augment_hook(self, augment, "on_select")

    # ===== Traits =====
    
    def update_active_traits(self):
        """Recalculate active traits based on board."""
        trait_counts = {}
        
        # Count traits
        for champion in self.board.get_all_champions():
            for trait in champion.traits:
                trait_counts[trait] = trait_counts.get(trait, 0) + 1
        
        # Check which traits are active
        self.active_traits = {}
        
        for trait_name, count in trait_counts.items():
            trait_data = self.data_loader.get_trait_by_name(trait_name)
            if trait_data:
                effect = trait_data.get_tier_effect(count)
                if effect:
                    self.active_traits[trait_name] = count
    
    # ===== Utilities =====
    
    def get_total_unit_count(self) -> int:
        """Get total units (board + bench)."""
        bench_count = sum(1 for champ in self.bench if champ is not None)
        return self.board.count_champions() + bench_count
    
    def get_state_dict(self) -> Dict:
        """Get player state as dictionary."""
        return {
            "player_id": self.player_id,
            "gold": self.gold,
            "health": self.health,
            "level": self.level,
            "xp": self.xp,
            "is_alive": self.is_alive,
            "board_count": self.board.count_champions(),
            "bench_count": sum(1 for c in self.bench if c),
            "active_traits": list(self.active_traits.keys()),
        }
