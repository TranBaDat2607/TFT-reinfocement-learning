"""
Game Round Manager for TFT Set 16.

Orchestrates game rounds including:
- Planning phases (shop, actions)
- Combat phases (PvP and PvE minion rounds)
- Carousel rounds (item grant)
- Round transitions
- Win/loss determination
"""
import random
from typing import List, Dict, Tuple, Optional
from simulator.core.player import Player
from simulator.engine.combat import CombatSimulator
from simulator.config import TFTConfig, GameConstants


# Item components that can drop from minion rounds / carousel
ITEM_COMPONENTS = [
    "TFT_Item_BFSword",
    "TFT_Item_RecurveBow",
    "TFT_Item_ChainVest",
    "TFT_Item_NegatronCloak",
    "TFT_Item_NeedlesslyLargeRod",
    "TFT_Item_TearOfTheGoddess",
    "TFT_Item_GiantsBelt",
    "TFT_Item_SparringGloves",
]


class GameRound:
    """
    Manages game rounds and phases.

    Coordinates:
    - Player planning phases
    - Combat matchmaking (PvP)
    - Minion round handling (PvE, rounds 1-3)
    - Carousel round handling (rounds 9, 18, 27, 36)
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
        self.players = players
        self.combat_sim = combat_sim
        self.config = config

        # Current game state
        self.current_round = 1
        self.current_stage = 1

        # Combat history
        self.combat_results: List[Dict] = []

        # Matchmaking tracking
        self.recent_opponents: Dict[int, List[int]] = {i: [] for i in range(len(players))}

    # ===== Round type detection =====

    def get_round_type(self, round_number: int) -> str:
        """
        Return the type of the given round.

        Returns one of: "carousel", "minion", "combat"
        """
        if round_number in GameConstants.CAROUSEL_ROUNDS:
            return "carousel"
        if round_number in GameConstants.MINION_ROUNDS:
            return "minion"
        return "combat"

    # ===== Planning phase =====

    def start_planning_phase(self):
        """
        Start planning phase for all alive players.

        - Generate shops
        - Give gold (+ streak bonus)
        - Reset action counts
        - Round 1 special: grant each player 1 free 1-cost champion
        """
        for player in self.players:
            if player.is_alive:
                # Generate new shop
                player._generate_shop()

                # Give round gold + interest + streak bonus
                player.start_of_round_gold()

                # Track round
                player.rounds_survived += 1

        # Round 1 special: grant each alive player 1 free 1-cost champion
        if self.current_round == 1:
            self._grant_round1_champions()

    def _grant_round1_champions(self):
        """
        Grant each alive player 1 free random 1-cost champion drawn from
        the shared pool. Called at the start of round 1 (first minion round).
        """
        # Collect all available 1-cost champion IDs from the pool
        pool = self.players[0].pool  # shared pool reference
        one_cost_ids = [
            champ_id
            for champ_id, count in pool.pool.items()
            if count > 0 and pool.data_loader.get_champion_by_id(champ_id) is not None
            and pool.data_loader.get_champion_by_id(champ_id).cost == 1
        ]

        for player in self.players:
            if not player.is_alive:
                continue

            if not one_cost_ids:
                break

            # Sample one at random (without replacement from the pool)
            champion_id = random.choice(one_cost_ids)
            champion_data = pool.data_loader.get_champion_by_id(champion_id)
            if champion_data is None:
                continue

            # Acquire from pool (may fail if depleted between iterations)
            if not pool.acquire(champion_id):
                # Try to pick another available one
                available = [c for c in one_cost_ids if pool.is_available(c)]
                if not available:
                    break
                champion_id = random.choice(available)
                champion_data = pool.data_loader.get_champion_by_id(champion_id)
                if champion_data is None or not pool.acquire(champion_id):
                    continue

            from simulator.core.champion import create_champion
            new_champ = create_champion(champion_data, stars=1)
            player._add_to_bench(new_champ)

    def end_planning_phase(self):
        """End planning phase, prepare for combat."""
        for player in self.players:
            if player.is_alive:
                # Update active traits based on board
                player.update_active_traits()

                # Reset champions for combat
                player.reset_for_combat()

    # ===== Combat dispatch =====

    def run_combat_phase(self) -> Dict[int, Tuple[int, int]]:
        """
        Run the combat phase for the current round, routing by round type.

        Returns:
            Dict mapping player_id -> (opponent_id, damage_taken)
            (empty dict for carousel rounds)
        """
        round_type = self.get_round_type(self.current_round)

        if round_type == "carousel":
            self._run_carousel_phase()
            return {}

        if round_type == "minion":
            return self._run_minion_phase()

        # Default: PvP combat
        return self._run_pvp_phase()

    # ===== PvP combat =====

    def _run_pvp_phase(self) -> Dict[int, Tuple[int, int]]:
        """
        Run player-vs-player combat.

        Returns:
            Dict mapping player_id -> (opponent_id, damage_taken)
        """
        alive_players = [p for p in self.players if p.is_alive]

        if len(alive_players) <= 1:
            return {}

        matchups = self._determine_matchups(alive_players)
        combat_results = {}

        for player1_id, player2_id in matchups:
            if player2_id == -1:
                # Ghost round: player wins automatically, no damage taken
                combat_results[player1_id] = (-1, 0)
                self.players[player1_id].update_streak(won=True)
                continue

            player1 = self.players[player1_id]
            player2 = self.players[player2_id]

            team1 = player1.board.get_all_champions()
            team2 = player2.board.get_all_champions()

            winner, damage = self.combat_sim.resolve_combat(
                team1, team2, self.current_round
            )

            if winner == 0:
                player2.take_damage(damage)
                combat_results[player2_id] = (player1_id, damage)
                combat_results[player1_id] = (player2_id, 0)
                player1.update_streak(won=True)
                player2.update_streak(won=False)
            elif winner == 1:
                player1.take_damage(damage)
                combat_results[player1_id] = (player2_id, damage)
                combat_results[player2_id] = (player1_id, 0)
                player2.update_streak(won=True)
                player1.update_streak(won=False)
            else:
                # Draw: no damage, streaks reset to 0
                combat_results[player1_id] = (player2_id, 0)
                combat_results[player2_id] = (player1_id, 0)
                player1.update_streak(won=False)
                player2.update_streak(won=False)

            self.combat_results.append({
                "round": self.current_round,
                "player1": player1_id,
                "player2": player2_id,
                "winner": winner,
                "damage": damage
            })

        return combat_results

    # ===== Minion round =====

    def _run_minion_phase(self) -> Dict[int, Tuple[int, int]]:
        """
        Run a PvE minion round.

        All alive players fight minions and win (simplified: always win).
        - Rounds 2-3: winners each receive 1 random item component.

        Returns:
            Dict mapping player_id -> (-1, 0)  (opponent=-1, no player damage)
        """
        combat_results = {}

        for player in self.players:
            if not player.is_alive:
                continue

            # Minion rounds: all players win (simplified PvE)
            combat_results[player.player_id] = (-1, 0)
            player.update_streak(won=True)

            # Rounds 2-3: grant 1 item component on win
            if self.current_round in (2, 3):
                component = random.choice(ITEM_COMPONENTS)
                player.grant_item_component(component)

        return combat_results

    # ===== Carousel round =====

    def _run_carousel_phase(self):
        """
        Run a carousel round (simplified).

        Each alive player receives 1 random item component.
        In a full implementation this would be the pick-a-unit mechanic.
        """
        for player in self.players:
            if player.is_alive:
                component = random.choice(ITEM_COMPONENTS)
                player.grant_item_component(component)

    # ===== Matchmaking =====

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

        while len(available) >= 2:
            p1 = available.pop(0)

            # Try to find opponent who hasn't fought recently
            p2: Optional[int] = None
            for candidate in available:
                if candidate not in self.recent_opponents[p1][-3:]:
                    p2 = candidate
                    break

            if p2 is None:
                p2 = available.pop(0)
            else:
                available.remove(p2)

            matchups.append((p1, p2))

            self.recent_opponents[p1].append(p2)
            self.recent_opponents[p2].append(p1)

        # Handle odd player (ghost round)
        if available:
            ghost_player = available[0]
            matchups.append((ghost_player, -1))

        return matchups

    # ===== Round lifecycle =====

    def advance_round(self):
        """Advance to next round."""
        self.current_round += 1
        self.current_stage = (
            sum(1 for c in GameConstants.CAROUSEL_ROUNDS if self.current_round > c) + 1
        )

    def is_game_over(self) -> bool:
        """Check if game is over."""
        alive_count = sum(1 for p in self.players if p.is_alive)
        return alive_count <= 1 or self.current_round > self.config.max_game_rounds

    def get_placements(self) -> Dict[int, int]:
        """
        Get final placements for all players.

        Returns:
            Dict mapping player_id -> placement (1-8)
        """
        placements = {}

        alive_players = [p for p in self.players if p.is_alive]
        for player in alive_players:
            placements[player.player_id] = 1

        dead_players = [
            (p.player_id, p.rounds_survived)
            for p in self.players if not p.is_alive
        ]
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
