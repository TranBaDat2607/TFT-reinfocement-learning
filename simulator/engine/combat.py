"""
Combat Simulator for TFT Set 16.

Provides combat resolution between two teams.
Phase 1 MVP: Statistical approximation (fast)
Phase 2+: Can upgrade to more detailed simulation
"""
import random
from typing import List, Tuple, Dict
from simulator.core.champion import Champion
from simulator.config import TFTConfig


class CombatSimulator:
    """
    Resolves combat between two teams.
    
    Phase 1 MVP uses statistical approximation for speed.
    This allows fast training while capturing core dynamics.
    """
    
    def __init__(self, config: TFTConfig):
        """
        Initialize combat simulator.
        
        Args:
            config: Game configuration
        """
        self.config = config
    
    def resolve_combat(
        self, 
        team1: List[Champion], 
        team2: List[Champion],
        round_number: int = 1
    ) -> Tuple[int, int]:
        """
        Resolve combat between two teams.
        
        Args:
            team1: List of champions for team 1
            team2: List of champions for team 2
            round_number: Current round number (affects damage)
            
        Returns:
            Tuple of (winner, damage_dealt)
            - winner: 0 for team1, 1 for team2, -1 for draw
            - damage_dealt: Damage to losing player's health
        """
        if self.config.combat_mode == "statistical":
            return self._statistical_combat(team1, team2, round_number)
        elif self.config.combat_mode == "simplified":
            # TODO: Phase 2 - simplified simulation
            return self._statistical_combat(team1, team2, round_number)
        else:
            # TODO: Phase 4 - full simulation
            return self._statistical_combat(team1, team2, round_number)
    
    def _statistical_combat(
        self,
        team1: List[Champion],
        team2: List[Champion],
        round_number: int
    ) -> Tuple[int, int]:
        """
        Statistical approximation of combat.
        
        Uses team power to determine win probability, then calculates damage.
        Fast but reasonably accurate for core dynamics.
        
        Args:
            team1: Team 1 champions
            team2: Team 2 champions
            round_number: Current round
            
        Returns:
            (winner, damage)
        """
        # Handle empty teams
        if not team1 and not team2:
            return (-1, 0)  # Draw
        if not team1:
            return (1, self._calculate_damage(team2, round_number))
        if not team2:
            return (0, self._calculate_damage(team1, round_number))
        
        # Calculate team power
        power1 = self._calculate_team_power(team1)
        power2 = self._calculate_team_power(team2)
        
        # Determine winner probabilistically
        total_power = power1 + power2
        win_prob_team1 = power1 / total_power if total_power > 0 else 0.5
        
        # Add some randomness (20% variance)
        win_prob_team1 = max(0.1, min(0.9, win_prob_team1 + random.gauss(0, 0.1)))
        
        winner = 0 if random.random() < win_prob_team1 else 1
        
        # Calculate damage based on winning team
        winning_team = team1 if winner == 0 else team2
        damage = self._calculate_damage(winning_team, round_number)
        
        return (winner, damage)
    
    def _calculate_team_power(self, team: List[Champion]) -> float:
        """
        Calculate total team power score.
        
        Factors in:
        - Raw stats (HP, AD, AS)
        - Champion costs (higher cost = stronger baseline)
        - Star levels (implicit in stats)
        - Items (TODO: Phase 2)
        - Traits (TODO: Phase 2)
        
        Args:
            team: List of champions
            
        Returns:
            Team power score
        """
        total_power = 0.0
        
        for champion in team:
            # Base power from stats
            champ_power = (
                champion.max_hp * 0.5 +           # HP contributes to tankiness
                champion.attack_damage * 2.0 +    # AD is main damage source
                champion.ability_power * 0.3 +    # AP for casters
                champion.armor * 2.0 +            # Defense matters
                champion.magic_resist * 2.0 +
                champion.attack_speed * 100       # AS multiplier
            )
            
            # Cost scaling (higher cost champions are stronger)
            cost_bonus = champion.cost * 150
            
            # Item bonus (TODO: Phase 2 - calculate based on items)
            item_bonus = len(champion.items) * 200  # Simplified for MVP
            
            total_power += champ_power + cost_bonus + item_bonus
        
        # Team size bonus (more units = better)
        team_size_bonus = len(team) * 100
        total_power += team_size_bonus
        
        return total_power
    
    def _calculate_damage(self, winning_team: List[Champion], round_number: int) -> int:
        """
        Calculate damage dealt to losing player.
        
        Damage formula:
        - Base damage from round number
        - Bonus damage from surviving units
        - Bonus damage from unit stars
        
        Args:
            winning_team: The team that won combat
            round_number: Current round number
            
        Returns:
            Damage to deal to losing player
        """
        # Base damage from round (increases over time)
        base_damage = self.config.round_damage.get(round_number, 0)
        
        # Bonus damage from surviving units
        unit_damage = 0
        for champion in winning_team:
            if champion.is_alive:
                # Each unit adds damage based on star level
                unit_damage += champion.stars
        
        total_damage = base_damage + unit_damage
        
        return max(0, total_damage)
