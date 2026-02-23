"""
Champion representation for TFT Set 16.

This is a lightweight, data-driven champion class that uses
the TFTDataLoader for all champion information instead of hardcoding.
"""
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field

from data_loader.data_models import Champion as ChampionData


@dataclass
class Champion:
    """
    Lightweight champion instance for TFT simulation.
    
    This class represents a champion ON THE BOARD or BENCH, not the
    champion template. It tracks current stats, items, and state.
    
    The actual champion data (base stats, ability, traits) comes from
    the TFTDataLoader and is stored in the `data` field.
    """
    
    data: ChampionData
    """Champion data from TFTDataLoader (immutable template)"""
    
    stars: int = 1
    """Star level (1-4, following Riot's 1.8x scaling per upgrade)"""
    
    position: Optional[tuple] = None
    """Current position: (row, col) or None if not placed"""
    
    items: List[str] = field(default_factory=list)
    """List of item IDs equipped on this champion (max 3)"""
    
    # Combat stats (modified by items/traits)
    current_hp: float = 0
    max_hp: float = 0
    attack_damage: float = 0
    ability_power: float = 0
    armor: float = 0
    magic_resist: float = 0
    attack_speed: float = 0
    critical_chance: float = 0
    critical_damage: float = 0
    attack_range: float = 0

    # Mana
    current_mana: float = 0
    max_mana: float = 0
    
    # Combat flags
    is_alive: bool = True
    is_stunned: bool = False
    is_channeling: bool = False
    
    def __post_init__(self):
        """Initialize combat stats from base data."""
        self._update_base_stats()
    
    def _update_base_stats(self):
        """
        Calculate base stats from champion data and star level.
        
        Uses official Riot scaling formula: multiply by 1.8 for each star upgrade.
        
        Star multipliers (HP and AD):
        - 1 star: 100% (1.0x base)
        - 2 stars: 180% (1.8x base)
        - 3 stars: 324% (3.24x base = 1.8^2)
        - 4 stars: 583.2% (5.832x base = 1.8^3)
        
        Source: Official TFT scaling, all champions can reach 4-star.
        """
        star_multipliers = {1: 1.0, 2: 1.8, 3: 3.24, 4: 5.832}
        multiplier = star_multipliers.get(self.stars, 1.0)
        
        # HP
        base_hp = self.data.stats.hp or 500
        self.max_hp = base_hp * multiplier
        self.current_hp = self.max_hp
        
        # Attack damage
        base_ad = self.data.stats.attack_damage or 40
        self.attack_damage = base_ad * multiplier
        
        # Defensive stats
        self.armor = self.data.stats.armor or 20
        self.magic_resist = self.data.stats.magic_resist or 20
        
        # Attack speed, range, and crit
        self.attack_speed = self.data.stats.attack_speed or 0.6
        self.attack_range = self.data.stats.attack_range or 1
        self.critical_chance = self.data.stats.crit_chance or 0.25
        self.critical_damage = self.data.stats.crit_multiplier or 1.4
        
        # Mana
        self.current_mana = self.data.stats.initial_mana or 0
        self.max_mana = self.data.stats.max_mana or 100
        
        # Ability power (base = 100, can be increased by items)
        self.ability_power = 100.0
    
    def add_item(self, item_id: str) -> bool:
        """
        Equip an item on this champion.
        
        Args:
            item_id: Item API ID
            
        Returns:
            True if successful, False if champion already has 3 items
        """
        if len(self.items) >= 3:
            return False
        
        self.items.append(item_id)
        # TODO: Apply item effects (Phase 2)
        return True
    
    def remove_item(self, item_id: str) -> bool:
        """
        Remove an item from this champion.
        
        Args:
            item_id: Item API ID
            
        Returns:
            True if successful, False if item not found
        """
        if item_id in self.items:
            self.items.remove(item_id)
            # TODO: Remove item effects (Phase 2)
            return True
        return False
    
    def can_cast_ability(self) -> bool:
        """Check if champion has enough mana to cast ability."""
        return self.current_mana >= self.max_mana and self.is_alive
    
    def take_damage(self, damage: float, is_physical: bool = True) -> float:
        """
        Apply damage to champion.
        
        Args:
            damage: Raw damage amount
            is_physical: If True, reduce by armor. If False, reduce by MR.
            
        Returns:
            Actual damage dealt after reductions
        """
        if not self.is_alive:
            return 0.0
        
        # Damage reduction formula: damage * 100 / (100 + armor)
        if is_physical:
            actual_damage = damage * 100 / (100 + self.armor)
        else:
            actual_damage = damage * 100 / (100 + self.magic_resist)
        
        self.current_hp -= actual_damage
        
        if self.current_hp <= 0:
            self.current_hp = 0
            self.is_alive = False
        
        return actual_damage
    
    def heal(self, amount: float) -> float:
        """
        Heal champion.
        
        Args:
            amount: Heal amount
            
        Returns:
            Actual amount healed (capped at max HP)
        """
        if not self.is_alive:
            return 0.0
        
        old_hp = self.current_hp
        self.current_hp = min(self.current_hp + amount, self.max_hp)
        
        return self.current_hp - old_hp
    
    def gain_mana(self, amount: float):
        """Gain mana, capped at max mana."""
        self.current_mana = min(self.current_mana + amount, self.max_mana)
    
    def reset_for_combat(self):
        """Reset champion state for new combat round."""
        self.current_hp = self.max_hp
        self.current_mana = self.data.stats.initial_mana or 0
        self.is_alive = True
        self.is_stunned = False
        self.is_channeling = False
    
    def upgrade_star(self) -> bool:
        """
        Upgrade champion to next star level.
        
        All champions can reach 4-star (following official TFT mechanics).
        
        Returns:
            True if successful, False if already 4-star
        """
        if self.stars >= 4:
            return False
        
        self.stars += 1
        self._update_base_stats()
        return True
    
    def get_power_score(self) -> float:
        """
        Calculate approximate power level of this champion.
        Used for simple combat approximation.
        
        Returns:
            Power score (higher = stronger)
        """
        return (
            self.max_hp * 0.5 +
            self.attack_damage * 2.0 +
            self.ability_power * 0.5 +
            self.armor * 3.0 +
            self.magic_resist * 3.0 +
            self.cost * 100  # Cost is a major factor
        )
    
    @property
    def name(self) -> str:
        """Get champion display name."""
        return self.data.name
    
    @property
    def cost(self) -> int:
        """Get champion cost."""
        return self.data.cost
    
    @property
    def traits(self) -> List[str]:
        """Get champion traits."""
        return self.data.traits
    
    @property
    def ability_name(self) -> str:
        """Get ability name."""
        return self.data.ability.name
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "champion_id": self.data.champion_id,
            "name": self.name,
            "cost": self.cost,
            "stars": self.stars,
            "position": self.position,
            "items": self.items,
            "hp": f"{self.current_hp:.0f}/{self.max_hp:.0f}",
            "mana": f"{self.current_mana:.0f}/{self.max_mana:.0f}",
            "traits": self.traits,
            "is_alive": self.is_alive
        }
    
    def __repr__(self):
        stars_str = "*" * self.stars
        items_str = f" [{len(self.items)} items]" if self.items else ""
        return f"{self.name} {stars_str}{items_str} (Cost: {self.cost})"


# Helper function to create champion from data
def create_champion(champion_data: ChampionData, stars: int = 1, items: Optional[List[str]] = None) -> Champion:
    """
    Factory function to create a Champion instance.
    
    Args:
        champion_data: Champion data from TFTDataLoader
        stars: Star level (1-4, all champions can reach 4-star)
        items: Item IDs to equip
        
    Returns:
        Champion instance
    """
    champion = Champion(data=champion_data, stars=stars)
    
    if items:
        for item_id in items[:3]:  # Max 3 items
            champion.add_item(item_id)
    
    return champion

