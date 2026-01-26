"""
Champion Pool Management for TFT Set 16.

Manages the shared pool of champions that all players draw from.
When a player buys a champion, it's removed from the pool.
When a player sells a champion, it's returned to the pool.
"""
import random
from typing import Dict, List, Optional
from collections import defaultdict

from data_loader import TFTDataLoader


class ChampionPool:
    """
    Shared pool of champions for all players.
    
    In TFT, all 8 players share the same champion pool. When you buy a
    champion, it's removed from the pool. When you sell, it's returned.
    This creates strategic tension around contested compositions.
    """
    
    def __init__(self, data_loader: Optional[TFTDataLoader] = None, pool_size_config: Optional[Dict[int, int]] = None):
        """
        Initialize the champion pool.
        
        Args:
            data_loader: TFTDataLoader instance. If None, creates new one.
            pool_size_config: Dict mapping cost -> number of copies.
                            If None, uses default Set 16 values.
        """
        self.data_loader = data_loader or TFTDataLoader()
        
        # Default pool sizes for Set 16
        self.pool_size_config = pool_size_config or {
            1: 29,  # 29 copies of each 1-cost
            2: 22,
            3: 18,
            4: 12,
            5: 10,
            6: 9,   # Set 16 has 6-costs
        }
        
        # Pool state: {champion_id: {cost: available_count}}
        self.pool: Dict[str, int] = {}
        
        # Track total champions per tier
        self.tier_totals: Dict[int, int] = defaultdict(int)
        
        self._initialize_pool()
    
    def _initialize_pool(self):
        """
        Initialize the pool with all champions from data loader.
        """
        all_champions = self.data_loader.get_all_champions()
        
        for champion in all_champions:
            champion_id = champion.champion_id
            cost = champion.cost
            
            # Get number of copies for this cost tier
            num_copies = self.pool_size_config.get(cost, 10)
            
            # Add to pool
            self.pool[champion_id] = num_copies
            self.tier_totals[cost] += num_copies
    
    def get_available(self, champion_id: str) -> int:
        """
        Get number of available copies of a champion.
        
        Args:
            champion_id: Champion API ID (e.g., "TFT16_Lulu")
            
        Returns:
            Number of available copies (0 if none left)
        """
        return self.pool.get(champion_id, 0)
    
    def is_available(self, champion_id: str) -> bool:
        """Check if at least one copy of champion is available."""
        return self.get_available(champion_id) > 0
    
    def acquire(self, champion_id: str) -> bool:
        """
        Acquire (buy) a champion from the pool.
        
        Args:
            champion_id: Champion API ID
            
        Returns:
            True if successful, False if champion not available
        """
        if not self.is_available(champion_id):
            return False
        
        self.pool[champion_id] -= 1
        
        # Update tier total
        champion = self.data_loader.get_champion_by_id(champion_id)
        if champion:
            self.tier_totals[champion.cost] -= 1
        
        return True
    
    def release(self, champion_id: str) -> bool:
        """
        Release (sell) a champion back to the pool.
        
        Args:
            champion_id: Champion API ID
            
        Returns:
            True if successful, False if champion not found
        """
        if champion_id not in self.pool:
            return False
        
        # Get original pool size for this champion
        champion = self.data_loader.get_champion_by_id(champion_id)
        if not champion:
            return False
        
        max_copies = self.pool_size_config.get(champion.cost, 10)
        
        # Don't exceed max copies
        if self.pool[champion_id] < max_copies:
            self.pool[champion_id] += 1
            self.tier_totals[champion.cost] += 1
            return True
        
        return False
    
    def sample_shop(self, level: int, shop_size: int = 5, shop_odds: Optional[Dict[int, List[float]]] = None) -> List[str]:
        """
        Sample champions for a shop based on player level.
        
        Args:
            level: Player level (1-11)
            shop_size: Number of champions to sample (default: 5)
            shop_odds: Dict mapping level -> tier probabilities.
                      If None, uses default Set 16 odds.
        
        Returns:
            List of champion IDs for the shop
        """
        # Default shop odds for Set 16
        if shop_odds is None:
            shop_odds = {
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
            }
        
        # Get tier probabilities for this level
        tier_probs = shop_odds.get(level, shop_odds[1])
        
        # Extend probabilities for 6-cost if needed (Set 16)
        if len(tier_probs) == 5:
            tier_probs = list(tier_probs) + [0.0]
        
        shop = []
        
        for _ in range(shop_size):
            # Sample a tier based on probabilities
            cost = random.choices(
                population=[1, 2, 3, 4, 5, 6],
                weights=tier_probs,
                k=1
            )[0]
            
            # Get all available champions of this cost
            available_champions = [
                champ_id for champ_id, count in self.pool.items()
                if count > 0 and self.data_loader.get_champion_by_id(champ_id).cost == cost
            ]
            
            # If no champions available at this cost, try next highest
            while not available_champions and cost > 1:
                cost -= 1
                available_champions = [
                    champ_id for champ_id, count in self.pool.items()
                    if count > 0 and self.data_loader.get_champion_by_id(champ_id).cost == cost
                ]
            
            # Sample a random champion from available
            if available_champions:
                champion_id = random.choice(available_champions)
                shop.append(champion_id)
            else:
                # No champions available at all (edge case)
                shop.append(None)
        
        return shop
    
    def get_pool_state(self) -> Dict[int, Dict[str, int]]:
        """
        Get current pool state organized by cost tier.
        
        Returns:
            Dict[cost -> Dict[champion_id -> count]]
        """
        pool_by_tier = defaultdict(dict)
        
        for champion_id, count in self.pool.items():
            champion = self.data_loader.get_champion_by_id(champion_id)
            if champion:
                pool_by_tier[champion.cost][champion_id] = count
        
        return dict(pool_by_tier)
    
    def reset(self):
        """Reset the pool to initial state."""
        self.pool.clear()
        self.tier_totals.clear()
        self._initialize_pool()
    
