"""
Game Round Manager for TFT Set 16.

Orchestrates game rounds including:
- Planning phases (shop, actions)
- Combat phases
- Round transitions
- Win/loss determination
"""
from typing import List, Dict, Tuple
from simulator.core.player import Player
from simulator.engine.combat import CombatSimulator
from simulator.config import TFTConfig, GameConstants
import random


class GameRound:
    """
    Manages game rounds and phases.
    
    Coordinates:
    - Player planning phases
    - Combat matchmaking
    - Damage calculation
    - Round progression
    """
    
    def __init__(self, players: List[Player], combat_sim: CombatSimulator, config: TFTConfig):
        """
        Initialize game round manager.
        
        Args:
            players: List of Player instances
            combat_sim: Combat simulator
            config: Game configuration
        """
        self.players =players
        self.combat_sim = combat_sim
        self.config = config
        
        # Current game state
        self.current_round = 1
        self.current_stage = 1
        
        # Combat history
        self.combat_results: List[Dict] = []
        
        # Matchmaking tracking
        self.recent_opponents: Dict[int, List[int]] = {i: [] for i in range(len(players))}
    
    def start_planning_phase(self):
        """
        Start planning phase for all alive players.
        
        - Generate shops
        - Give gold
        - Reset action counts
        """
        for player in self.players:
            if player.is_alive:
                # Generate new shop
                player._generate_shop()
                
                # Give round gold + interest
                player.start_of_round_gold()
                
                # Track round
                player.rounds_survived += 1
    
    def end_planning_phase(self):
        """End planning phase, prepare for combat."""
        for player in self.players:
            if player.is_alive:
                # Update active traits based on board
                player.update_active_traits()
                
                # Reset champions for combat
                player.reset_for_combat()
    
    def run_combat_phase(self) -> Dict[int, Tuple[int, int]]:
        """
        Run combat for all players.
        
        Returns:
            Dict mapping player_id -> (opponent_id, damage_taken)
        """
        alive_players = [p for p in self.players if p.is_alive]
        
        if len(alive_players) <= 1:
            return {}
        
        # Determine matchups
        matchups = self._determine_matchups(alive_players)
        
        # Run combats
        combat_results = {}
        
        for player1_id, player2_id in matchups:
            player1 = self.players[player1_id]
            player2 = self.players[player2_id]
            
            # Get teams
            team1 = player1.board.get_all_champions()
            team2 = player2.board.get_all_champions()
            
            # Resolve combat
            winner, damage = self.combat_sim.resolve_combat(
                team1, team2, self.current_round
            )
            
            # Apply damage
            if winner == 0:
                # Player 1 wins
                player2.take_damage(damage)
                combat_results[player2_id] = (player1_id, damage)
                combat_results[player1_id] = (player2_id, 0)
            elif winner == 1:
                # Player 2 wins
                player1.take_damage(damage)
                combat_results[player1_id] = (player2_id, damage)
                combat_results[player2_id] = (player1_id, 0)
            else:
                # Draw (no damage)
                combat_results[player1_id] = (player2_id, 0)
                combat_results[player2_id] = (player1_id, 0)
            
            # Track combat
            self.combat_results.append({
                "round": self.current_round,
                "player1": player1_id,
                "player2": player2_id,
                "winner": winner,
                "damage": damage
            })
        
        return combat_results
    
    def _determine_matchups(self, alive_players: List[Player]) -> List[Tuple[int, int]]:
        """
        Determine who fights who.
        
        Uses ghost matchmaking if odd number of players.
        Tries to avoid repeat matchups when possible.
        
        Args:
            alive_players: List of alive players
            
        Returns:
            List of (player1_id, player2_id) tuples
        """
        matchups = []
        available = [p.player_id for p in alive_players]
        random.shuffle(available)
        
        # Pair up players
        while len(available) >= 2:
            p1 = available.pop(0)
            
            # Try to find opponent who hasn't fought recently
            p2 = None
            for candidate in available:
                if candidate not in self.recent_opponents[p1][-3:]:  # Avoid last 3 opponents
                    p2 = candidate
                    break
            
            # If no good candidate, just take next available
            if p2 is None:
                p2 = available.pop(0)
            else:
                available.remove(p2)
            
            matchups.append((p1, p2))
            
            # Track recent opponents
            self.recent_opponents[p1].append(p2)
            self.recent_opponents[p2].append(p1)
        
        # Handle odd player (ghost round)
        if available:
            ghost_player = available[0]
            # Ghost round: fight a random eliminated player or skip
            # For MVP, just skip combat (no damage)
            matchups.append((ghost_player, -1))  # -1 indicates ghost
        
        return matchups
    
    def advance_round(self):
        """Advance to next round."""
        self.current_round += 1
        
        # Update stage (every 7 rounds = new stage in TFT)
        # Round 1-3: Stage 1 (carousel + minions)
        # Round 4-6: Stage 2
        # etc.
        self.current_stage = ((self.current_round - 1) // 7) + 1
    
    def is_game_over(self) -> bool:
        """Check if game is over."""
        alive_count = sum(1 for p in self.players if p.is_alive)
        
        # Game over if only 1 player left or max rounds reached
        return alive_count <= 1 or self.current_round > self.config.max_game_rounds
    
    def get_placements(self) -> Dict[int, int]:
        """
        Get final placements for all players.
        
        Returns:
            Dict mapping player_id -> placement (1-8)
        """
        placements = {}
        
        # Alive players tie for 1st
        alive_players = [p for p in self.players if p.is_alive]
        for player in alive_players:
            placements[player.player_id] = 1
        
        # Dead players ranked by when they died (later = better)
        dead_players = [(p.player_id, p.rounds_survived) for p in self.players if not p.is_alive]
        dead_players.sort(key=lambda x: x[1], reverse=True)
        
        current_placement = len(alive_players) + 1
        for player_id, _ in dead_players:
            placements[player_id] = current_placement
            current_placement += 1
        
        return placements
    
    def reset(self):
        """Reset round state for new game."""
        self.current_round = 1
        self.current_stage = 1
        self.combat_results.clear()
        self.recent_opponents = {i: [] for i in range(len(self.players))}
