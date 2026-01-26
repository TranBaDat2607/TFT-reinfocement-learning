"""
Data Loader for TFT Set 16
Loads and parses all game data from JSON files
"""
import json
from pathlib import Path
from typing import Dict, List, Optional
from .data_models import (
    Champion, ChampionStats, ChampionAbility,
    Item, ItemEffect,
    Trait, TraitEffect,
    Augment, Portal, UnlockCondition
)


class TFTDataLoader:
    """
    Loads TFT Set 16 data from JSON files and provides convenient access methods.
    
    Usage:
        loader = TFTDataLoader(set_id="Set16")
        champions = loader.get_all_champions()
        lulu = loader.get_champion_by_name("Lulu")
        items = loader.get_all_items()
    """
    
    def __init__(self, set_id: str = "Set16", data_dir: Optional[Path] = None):
        """
        Initialize the data loader.
        
        Args:
            set_id: The set identifier (e.g., "Set16")
            data_dir: Path to data directory. If None, uses ../data/set16
        """
        self.set_id = set_id
        
        if data_dir is None:
            # Default to data/set16 relative to this file
            self.data_dir = Path(__file__).parent.parent / "data" / set_id.lower()
        else:
            self.data_dir = Path(data_dir)
        
        # Storage for loaded data
        self.champions: Dict[str, Champion] = {}
        self.items: Dict[str, Item] = {}
        self.traits: Dict[str, Trait] = {}
        self.augments: Dict[str, Augment] = {}
        self.portals: Dict[str, Portal] = {}
        self.unlock_conditions: Dict[str, UnlockCondition] = {}
        
        # Lookup indices
        self.champions_by_name: Dict[str, Champion] = {}
        self.champions_by_cost: Dict[int, List[Champion]] = {}
        self.champions_by_trait: Dict[str, List[Champion]] = {}
        self.items_by_name: Dict[str, Item] = {}
        self.traits_by_name: Dict[str, Trait] = {}
        
        # Load all data
        self._load_all()
    
    def _load_json(self, filename: str) -> dict:
        """Load a JSON file from the data directory"""
        filepath = self.data_dir / filename
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _load_all(self):
        """Load all data files"""
        self._load_champions()
        self._load_items()
        self._load_traits()
        self._load_augments()
        self._load_portals()
        self._load_unlock_conditions()
        self._build_indices()
    
    def _load_champions(self):
        """Load champions from champions.json"""
        data = self._load_json("champions.json")
        
        for champ_data in data.get("champions", []):
            # Parse stats
            stats_raw = champ_data.get("stats", {})
            stats = ChampionStats(
                hp=stats_raw.get("hp", 0),
                armor=stats_raw.get("armor", 0),
                magic_resist=stats_raw.get("magicResist", 0),
                attack_damage=stats_raw.get("damage"),
                attack_speed=stats_raw.get("attackSpeed", 1.0),
                attack_range=stats_raw.get("range", 1),
                initial_mana=stats_raw.get("initialMana", 0),
                max_mana=stats_raw.get("mana", 100),
                crit_chance=stats_raw.get("critChance", 0.25),
                crit_multiplier=stats_raw.get("critMultiplier", 1.4)
            )
            
            # Parse ability
            ability_raw = champ_data.get("ability", {})
            ability = ChampionAbility(
                name=ability_raw.get("name", ""),
                description=ability_raw.get("desc", ""),
                icon=ability_raw.get("icon", ""),
                variables=ability_raw.get("variables", [])
            )
            
            # Create champion
            champion = Champion(
                champion_id=champ_data.get("apiName", ""),
                name=champ_data.get("name", ""),
                cost=champ_data.get("cost", 1),
                traits=champ_data.get("traits", []),
                stats=stats,
                ability=ability,
                role=champ_data.get("role"),
                unlock_conditions=champ_data.get("unlock_conditions")
            )
            
            self.champions[champion.champion_id] = champion
    
    def _load_items(self):
        """Load items from items.json"""
        data = self._load_json("items.json")
        
        for item_data in data.get("items", []):
            item = Item(
                item_id=item_data.get("apiName", ""),
                name=item_data.get("name", ""),
                description=item_data.get("desc", ""),
                composition=item_data.get("composition", []),
                effects=ItemEffect(effects=item_data.get("effects", {})),
                associated_traits=item_data.get("associatedTraits", []),
                tags=item_data.get("tags", []),
                is_unique=item_data.get("unique", False),
                icon=item_data.get("icon", "")
            )
            
            self.items[item.item_id] = item
    
    def _load_traits(self):
        """Load traits from traits.json"""
        data = self._load_json("traits.json")
        
        for trait_data in data.get("traits", []):
            effects = []
            for effect_data in trait_data.get("effects", []):
                effect = TraitEffect(
                    min_units=effect_data.get("minUnits", 0),
                    max_units=effect_data.get("maxUnits", 25000),
                    style=effect_data.get("style", 1),
                    variables=effect_data.get("variables", {})
                )
                effects.append(effect)
            
            trait = Trait(
                trait_id=trait_data.get("apiName", ""),
                name=trait_data.get("name", ""),
                description=trait_data.get("desc", ""),
                effects=effects
            )
            
            self.traits[trait.trait_id] = trait
    
    def _load_augments(self):
        """Load augments from augments.json"""
        data = self._load_json("augments.json")
        
        for aug_data in data.get("augments", []):
            augment = Augment(
                augment_id=aug_data.get("apiName", ""),
                name=aug_data.get("name", ""),
                description=aug_data.get("desc", ""),
                effects=aug_data.get("effects", {}),
                associated_traits=aug_data.get("associatedTraits", []),
                incompatible_traits=aug_data.get("incompatibleTraits", []),
                tags=aug_data.get("tags", []),
                is_unique=aug_data.get("unique", False),
                icon=aug_data.get("icon", "")
            )
            
            self.augments[augment.augment_id] = augment
    
    def _load_portals(self):
        """Load portals from portals.json"""
        data = self._load_json("portals.json")
        
        for portal_data in data.get("portals", []):
            portal = Portal(
                portal_id=portal_data.get("apiName", portal_data.get("id", "")),
                name=portal_data.get("name", ""),
                description=portal_data.get("description", ""),
                odds=portal_data.get("odds", 0),
                unit_id=portal_data.get("unitId")
            )
            
            self.portals[portal.portal_id] = portal
    
    def _load_unlock_conditions(self):
        """Load unlock conditions from unlock_conditions.json"""
        data = self._load_json("unlock_conditions.json")
        
        for unlock_data in data.get("unlocks", []):
            unlock = UnlockCondition(
                champion_name=unlock_data.get("champion", ""),
                tier=unlock_data.get("tier", ""),
                conditions=unlock_data.get("conditions", []),
                condition_count=unlock_data.get("condition_count", 0)
            )
            
            self.unlock_conditions[unlock.champion_name] = unlock
    
    def _build_indices(self):
        """Build lookup indices for fast access"""
        # Champions by name
        for champ in self.champions.values():
            self.champions_by_name[champ.name] = champ
            
            # By cost
            if champ.cost not in self.champions_by_cost:
                self.champions_by_cost[champ.cost] = []
            self.champions_by_cost[champ.cost].append(champ)
            
            # By trait
            for trait in champ.traits:
                if trait not in self.champions_by_trait:
                    self.champions_by_trait[trait] = []
                self.champions_by_trait[trait].append(champ)
        
        # Items by name
        for item in self.items.values():
            self.items_by_name[item.name] = item
        
        # Traits by name
        for trait in self.traits.values():
            self.traits_by_name[trait.name] = trait
    
    def get_all_champions(self) -> List[Champion]:
        """Get all champions"""
        return list(self.champions.values())
    
    def get_champion_by_id(self, champion_id: str) -> Optional[Champion]:
        """Get champion by ID (e.g., 'TFT16_Lulu')"""
        return self.champions.get(champion_id)
    
    def get_champion_by_name(self, name: str) -> Optional[Champion]:
        """Get champion by name (e.g., 'Lulu')"""
        return self.champions_by_name.get(name)
    
    def get_champions_by_cost(self, cost: int) -> List[Champion]:
        """Get all champions of a specific cost"""
        return self.champions_by_cost.get(cost, [])
    
    def get_champions_by_trait(self, trait: str) -> List[Champion]:
        """Get all champions with a specific trait"""
        return self.champions_by_trait.get(trait, [])
    
    def get_all_items(self) -> List[Item]:
        """Get all items"""
        return list(self.items.values())
    
    def get_item_by_id(self, item_id: str) -> Optional[Item]:
        """Get item by ID"""
        return self.items.get(item_id)
    
    def get_item_by_name(self, name: str) -> Optional[Item]:
        """Get item by name"""
        return self.items_by_name.get(name)
    
    def get_all_traits(self) -> List[Trait]:
        """Get all traits"""
        return list(self.traits.values())
    
    def get_trait_by_id(self, trait_id: str) -> Optional[Trait]:
        """Get trait by ID"""
        return self.traits.get(trait_id)
    
    def get_trait_by_name(self, name: str) -> Optional[Trait]:
        """Get trait by name"""
        return self.traits_by_name.get(name)
    
    def get_all_augments(self) -> List[Augment]:
        """Get all augments"""
        return list(self.augments.values())
    
    def get_augment_by_id(self, augment_id: str) -> Optional[Augment]:
        """Get augment by ID"""
        return self.augments.get(augment_id)
    
    def get_all_portals(self) -> List[Portal]:
        """Get all portals"""
        return list(self.portals.values())
    
    def get_portal_by_id(self, portal_id: str) -> Optional[Portal]:
        """Get portal by ID"""
        return self.portals.get(portal_id)
    
    def get_unlock_condition(self, champion_name: str) -> Optional[UnlockCondition]:
        """Get unlock condition for a champion"""
        return self.unlock_conditions.get(champion_name)
    
    def get_unlockable_champions(self) -> List[str]:
        """Get list of all unlockable champion names"""
        return list(self.unlock_conditions.keys())
    
    # ==== Utility Methods ====
    
    def get_stats(self) -> Dict[str, int]:
        """Get statistics about loaded data"""
        return {
            "champions": len(self.champions),
            "items": len(self.items),
            "traits": len(self.traits),
            "augments": len(self.augments),
            "portals": len(self.portals),
            "unlock_conditions": len(self.unlock_conditions)
        }
