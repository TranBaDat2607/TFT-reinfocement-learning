"""
Helper utilities for working with TFT data
"""
from typing import Dict, List
from .data_models import Champion, Trait


def calculate_active_traits(champions: List[Champion], traits_dict: Dict[str, Trait]) -> Dict[str, dict]:
    """
    Calculate which traits are active given a list of champions.
    
    Args:
        champions: List of Champion objects on the board
        traits_dict: Dictionary of trait_id -> Trait objects
    
    Returns:
        Dictionary of active traits with their tier info
        Format: {trait_name: {"count": int, "tier": TraitEffect, "style": str}}
    """
    # Count trait occurrences
    trait_counts = {}
    for champion in champions:
        for trait in champion.traits:
            trait_counts[trait] = trait_counts.get(trait, 0) + 1
    
    # Determine active traits
    active_traits = {}
    for trait_name, count in trait_counts.items():
        # Find matching trait object
        trait_obj = None
        for trait in traits_dict.values():
            if trait.name == trait_name:
                trait_obj = trait
                break
        
        if trait_obj:
            effect = trait_obj.get_tier_effect(count)
            if effect:
                style_name = {1: "Bronze", 3: "Silver", 5: "Gold", 4: "Unique"}.get(effect.style, "Unknown")
                active_traits[trait_name] = {
                    "count": count,
                    "tier": effect,
                    "style": style_name,
                    "variables": effect.variables
                }
    
    return active_traits


def get_champion_power_score(champion: Champion) -> float:
    """
    Calculate a rough power score for a champion based on stats.
    This is a simple heuristic for estimating champion strength.
    
    Args:
        champion: Champion object
    
    Returns:
        Power score (higher = stronger)
    """
    stats = champion.stats
    
    # Simple power formula
    power = (
        stats.hp * 0.5 +
        (stats.attack_damage or 50) * 2.0 +
        stats.armor * 3.0 +
        stats.magic_resist * 3.0 +
        stats.attack_speed * 50 +
        champion.cost * 100  # Cost is a major factor
    )
    
    return power


def find_best_items_for_champion(champion: Champion, available_items: List) -> List:
    """
    Suggest best items for a champion based on their role.
    This is a simple heuristic - a real implementation would be more sophisticated.
    
    Args:
        champion: Champion object
        available_items: List of Item objects
    
    Returns:
        List of recommended items (up to 3)
    """
    recommendations = []
    
    role = champion.role
    if not role:
        return recommendations
    
    # Simple role-based item recommendations
    role_preferences = {
        "APCaster": ["AP", "Mana"],
        "ADCaster": ["AD", "AS"],
        "APTank": ["Health", "Armor", "MR", "AP"],
        "Tank": ["Health", "Armor", "MR"],
        "Fighter": ["AD", "AS", "Health"],
        "Support": ["Mana", "Health"],
    }
    
    preferred_stats = role_preferences.get(role, [])
    
    # Score items based on role
    scored_items = []
    for item in available_items:
        score = 0
        for stat in preferred_stats:
            if stat in str(item.effects.effects):
                score += 1
        if score > 0:
            scored_items.append((item, score))
    
    # Sort by score and return top 3
    scored_items.sort(key=lambda x: x[1], reverse=True)
    recommendations = [item for item, _ in scored_items[:3]]
    
    return recommendations


def get_team_cost(champions: List[Champion]) -> int:
    """Calculate total cost of all champions on board"""
    return sum(champ.cost for champ in champions)


def get_star_distribution(champions: List[Champion]) -> Dict[int, int]:
    """
    Get distribution of star levels.
    Note: This assumes all champions are 1-star. In actual game, track star levels separately.
    
    Returns:
        Dictionary of {star_level: count}
    """
    # Placeholder - in real implementation, track actual star levels
    return {1: len(champions), 2: 0, 3: 0}
