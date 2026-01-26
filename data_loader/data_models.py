"""
Data models for TFT Set 16
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any


@dataclass
class ChampionStats:
    """Champion base statistics"""
    hp: float
    armor: float
    magic_resist: float
    attack_damage: Optional[float]
    attack_speed: float
    attack_range: float
    initial_mana: float
    max_mana: float
    crit_chance: Optional[float] = 0.25
    crit_multiplier: Optional[float] = 1.4


@dataclass
class ChampionAbility:
    """Champion ability information"""
    name: str
    description: str
    icon: str
    variables: List[Dict[str, Any]]


@dataclass
class Champion:
    """TFT Champion data"""
    champion_id: str
    name: str
    cost: int
    traits: List[str]
    stats: ChampionStats
    ability: ChampionAbility
    role: Optional[str] = None
    unlock_conditions: Optional[str] = None
    
    def __repr__(self):
        return f"Champion(name='{self.name}', cost={self.cost}, traits={self.traits})"


@dataclass
class ItemEffect:
    """Item effects and stats"""
    effects: Dict[str, Any]
    
    def get_stat(self, stat_name: str, default=0):
        """Get a specific stat value"""
        return self.effects.get(stat_name, default)


@dataclass
class Item:
    """TFT Item data"""
    item_id: str
    name: str
    description: str
    composition: List[str]  # Component IDs
    effects: ItemEffect
    associated_traits: List[str]
    tags: List[str]
    is_unique: bool
    icon: str
    
    def __repr__(self):
        return f"Item(name='{self.name}', components={len(self.composition)})"


@dataclass
class TraitEffect:
    """Trait effect at a specific tier"""
    min_units: int
    max_units: int
    style: int  # 1=Bronze, 3=Silver, 5=Gold, 4=Unique
    variables: Dict[str, Any]


@dataclass
class Trait:
    """TFT Trait data"""
    trait_id: str
    name: str
    description: str
    effects: List[TraitEffect]
    
    def get_tier_effect(self, num_units: int) -> Optional[TraitEffect]:
        """Get the trait effect for a given number of units"""
        for effect in self.effects:
            if effect.min_units <= num_units <= effect.max_units:
                return effect
        return None
    
    def __repr__(self):
        return f"Trait(name='{self.name}', tiers={len(self.effects)})"


@dataclass
class Augment:
    """TFT Augment data"""
    augment_id: str
    name: str
    description: str
    effects: Dict[str, Any]
    associated_traits: List[str]
    incompatible_traits: List[str]
    tags: List[str]
    is_unique: bool
    icon: str
    
    def __repr__(self):
        return f"Augment(name='{self.name}', unique={self.is_unique})"


@dataclass
class Portal:
    """TFT Portal data (Set 16 specific)"""
    portal_id: str
    name: str
    description: str
    odds: int
    unit_id: Optional[str]
    
    def __repr__(self):
        return f"Portal(name='{self.name}', odds={self.odds})"


@dataclass
class UnlockCondition:
    """Unlockable champion conditions"""
    champion_name: str
    tier: str
    conditions: List[str]
    condition_count: int
    
    def __repr__(self):
        return f"Unlock(champion='{self.champion_name}', tier={self.tier}, conditions={self.condition_count})"
