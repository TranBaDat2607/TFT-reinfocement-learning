"""
Event-Driven Game Engine for TFT Set 16.

This module provides an event-driven architecture for the TFT simulator,
replacing time-step based execution with priority-based event scheduling.

Key benefits:
- Efficient: Skip idle periods, only process meaningful events
- Modular: Easy to add new event types and mechanics
- Extensible: New game features just add new event types
- RL-friendly: Clear decision points for agent actions
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple
import heapq
import random
from enum import Enum, auto

from simulator.core.player import Player
from simulator.core.pool import ChampionPool
from simulator.engine.combat import CombatSimulator
from simulator.engine.game_round import GameRound
from simulator.config import TFTConfig, GameConstants


class EventType(Enum):
    """Types of events in the game."""
    # Round events
    START_PLANNING = auto()
    END_PLANNING = auto()
    START_COMBAT = auto()
    END_COMBAT = auto()
    END_ROUND = auto()

    # Player decision events
    PLAYER_ACTION_REQUIRED = auto()

    # Game events
    CAROUSEL = auto()
    AUGMENT_SELECTION = auto()
    GAME_END = auto()

    # Phase 2+ events (placeholders)
    PORTAL_ACTIVATE = auto()
    UNLOCK_CHAMPION = auto()


@dataclass(order=True)
class Event:
    """
    Represents a game event with priority-based scheduling.

    Events are ordered by timestamp (earlier events have higher priority).
    Uses dataclass ordering to automatically work with heapq.

    Attributes:
        timestamp: When the event should occur (lower = sooner)
        event_type: Type of event (from EventType enum)
        player_id: Which player this event affects (-1 for all players)
        data: Additional event-specific data
        handler: Optional custom event handler function
    """
    timestamp: float
    event_type: EventType = field(compare=False)
    player_id: int = field(compare=False)
    data: Dict[str, Any] = field(default_factory=dict, compare=False)
    handler: Optional[Callable] = field(default=None, compare=False)

    def __repr__(self):
        return f"Event(t={self.timestamp:.2f}, type={self.event_type.name}, player={self.player_id})"


class EventEngine:
    """
    Base event-driven engine using priority queue.

    This is a generic event engine that can be extended for different games.
    For TFT-specific logic, use TFTEventEngine.
    """

    def __init__(self):
        self.event_queue: List[Event] = []  # Min-heap priority queue
        self.current_time: float = 0.0
        self.handlers: Dict[EventType, Callable] = {}

    def schedule_event(self, timestamp: float, event_type: EventType,
                       player_id: int = -1, data: Optional[Dict] = None,
                       handler: Optional[Callable] = None):
        """
        Schedule an event to occur at a specific time.

        Args:
            timestamp: When the event should occur
            event_type: Type of event
            player_id: Which player (-1 for all/none)
            data: Event-specific data
            handler: Optional custom handler (overrides registered handler)
        """
        if data is None:
            data = {}

        event = Event(
            timestamp=timestamp,
            event_type=event_type,
            player_id=player_id,
            data=data,
            handler=handler
        )
        heapq.heappush(self.event_queue, event)

    def register_handler(self, event_type: EventType, handler: Callable):
        """Register a handler function for an event type."""
        self.handlers[event_type] = handler

    def process_next_event(self) -> Optional[Dict[str, Any]]:
        """
        Process the next event in the queue.

        Returns:
            Result dictionary from event handler, or None if queue empty
        """
        if not self.event_queue:
            return None

        event = heapq.heappop(self.event_queue)
        self.current_time = event.timestamp

        # Use custom handler if provided, otherwise use registered handler
        handler = event.handler or self.handlers.get(event.event_type)

        if handler:
            return handler(event)
        else:
            print(f"Warning: No handler for event type {event.event_type}")
            return None

    def run_until_decision_point(self) -> Dict[str, Any]:
        """
        Process events until a decision point is reached.

        A decision point is when:
        - A player needs to take an action
        - The game ends
        - No more events in queue

        Returns:
            Dictionary with decision point information:
            - 'requires_decision': bool - Does a player need to act?
            - 'player_id': int - Which player needs to act
            - 'game_over': bool - Is the game finished?
            - 'round': int - Current round number
            - Other context data
        """
        while self.event_queue:
            result = self.process_next_event()

            if result:
                if result.get('requires_decision'):
                    return result

                if result.get('game_over'):
                    return result

        # Queue exhausted
        return {'game_over': True, 'reason': 'no_more_events'}

    def peek_next_event(self) -> Optional[Event]:
        """Look at next event without removing it."""
        return self.event_queue[0] if self.event_queue else None

    def clear_queue(self):
        """Remove all events from queue."""
        self.event_queue.clear()
        self.current_time = 0.0


class TFTEventEngine(EventEngine):
    """
    TFT-specific event-driven game engine.

    Manages game state and coordinates between:
    - Players (economy, units, actions)
    - Combat (battle resolution)
    - Rounds (phase progression)
    - Pool (shared champion pool)

    Round routing:
    - Carousel rounds (9, 18, 27, 36): no planning/combat, grant items
    - Minion rounds  (1, 2, 3):        planning + PvE combat + loot
    - Augment rounds (6, 13, 20):      planning + augment selection + PvP combat
    - All other rounds:                planning + PvP combat

    Usage:
        engine = TFTEventEngine(config)
        engine.reset()  # Start new game

        while not engine.is_game_over():
            result = engine.run_until_decision_point()
            if result['requires_decision']:
                action = agent.get_action(result['observation'])
                engine.apply_action(result['player_id'], action)
    """

    def __init__(self, config: TFTConfig):
        super().__init__()
        self.config = config

        # Game components (initialized in reset())
        self.players: List[Player] = []
        self.pool: Optional[ChampionPool] = None
        self.combat_sim: Optional[CombatSimulator] = None
        self.game_round: Optional[GameRound] = None

        # Game state
        self.current_round: int = 0
        self.current_stage: int = 1
        self.game_over_flag: bool = False

        # Register event handlers
        self._register_handlers()

    def _register_handlers(self):
        """Register all TFT event handlers."""
        self.register_handler(EventType.START_PLANNING, self._handle_start_planning)
        self.register_handler(EventType.END_PLANNING, self._handle_end_planning)
        self.register_handler(EventType.START_COMBAT, self._handle_start_combat)
        self.register_handler(EventType.END_COMBAT, self._handle_end_combat)
        self.register_handler(EventType.END_ROUND, self._handle_end_round)
        self.register_handler(EventType.PLAYER_ACTION_REQUIRED, self._handle_player_action)
        self.register_handler(EventType.GAME_END, self._handle_game_end)
        self.register_handler(EventType.CAROUSEL, self._handle_carousel)
        self.register_handler(EventType.AUGMENT_SELECTION, self._handle_augment_selection)

    def reset(self) -> Dict[str, Any]:
        """
        Reset the game to initial state.

        Returns:
            Initial game state for all players
        """
        self.clear_queue()

        from data_loader import TFTDataLoader
        data_loader = TFTDataLoader()

        self.pool = ChampionPool(data_loader=data_loader)
        self.combat_sim = CombatSimulator(self.config)

        self.players = [
            Player(
                player_id=i,
                pool=self.pool,
                config=self.config,
                data_loader=data_loader
            )
            for i in range(self.config.num_players)
        ]

        self.game_round = GameRound(self.players, self.combat_sim, self.config)

        self.current_round = 0
        self.current_stage = 1
        self.game_over_flag = False

        # Schedule first event
        self.schedule_event(0.0, EventType.START_PLANNING, -1)

        return {
            'round': self.current_round,
            'stage': self.current_stage,
            'players': [p.get_state_dict() for p in self.players]
        }

    # ===== Event handlers =====

    @staticmethod
    def _compute_stage(round_number: int) -> int:
        """
        Compute the current stage from the round number.

        Stage boundaries are defined by carousel rounds.  Every time a
        carousel round is passed the stage increments:
            Stage 1 = rounds  1-9   (before first carousel at round 9)
            Stage 2 = rounds 10-18  (between carousels 9 and 18)
            Stage 3 = rounds 19-27  (between carousels 18 and 27)
            Stage 4 = rounds 28-36  (between carousels 27 and 36)
            ...
        """
        return sum(1 for c in GameConstants.CAROUSEL_ROUNDS if round_number > c) + 1

    def _handle_start_planning(self, event: Event) -> Dict[str, Any]:
        """Handle start of planning phase."""
        self.current_round += 1
        new_stage = self._compute_stage(self.current_round)
        is_new_stage = new_stage != self.current_stage
        self.current_stage = new_stage

        # Sync round/stage into GameRound
        self.game_round.current_round = self.current_round
        self.game_round.current_stage = self.current_stage

        # Fire on_stage_start hooks when stage changes
        if is_new_stage:
            from simulator.env.augment_effects import apply_all_stage_start_hooks
            for player in self.players:
                if player.is_alive:
                    apply_all_stage_start_hooks(player)

        round_type = self.game_round.get_round_type(self.current_round)

        # Carousel rounds skip the planning phase entirely
        if round_type == "carousel" and self.config.enable_carousel:
            self.schedule_event(
                self.current_time + 0.1,
                EventType.CAROUSEL,
                -1,
                {'round': self.current_round}
            )
            return {
                'event': 'start_planning',
                'round': self.current_round,
                'stage': self.current_stage,
                'round_type': round_type,
            }

        # Run planning setup: gold, shops, round-1 champion grant, etc.
        self.game_round.start_planning_phase()

        alive_players = [p for p in self.players if p.is_alive]

        if not alive_players:
            self.schedule_event(self.current_time + 0.1, EventType.GAME_END, -1)
        elif (self.current_round in GameConstants.AUGMENT_ROUNDS
              and self.config.enable_augments):
            # Augment selection fires at the START of the planning phase,
            # before players take any shop/unit actions.
            self.schedule_event(
                self.current_time + 0.1,
                EventType.AUGMENT_SELECTION,
                -1,
                {'round': self.current_round, 'round_type': round_type}
            )
        else:
            self.schedule_event(
                self.current_time + 0.1,
                EventType.PLAYER_ACTION_REQUIRED,
                alive_players[0].player_id,
                {
                    'phase': 'planning',
                    'players_remaining': [p.player_id for p in alive_players],
                    'round_type': round_type,
                }
            )

        return {
            'event': 'start_planning',
            'round': self.current_round,
            'stage': self.current_stage,
            'round_type': round_type,
        }

    def _handle_player_action(self, event: Event) -> Dict[str, Any]:
        """Handle player action required (decision point)."""
        player_id = event.player_id

        return {
            'requires_decision': True,
            'player_id': player_id,
            'round': self.current_round,
            'stage': self.current_stage,
            'observation': self._get_observation(player_id),
            'valid_actions': self._get_valid_actions(player_id),
            'phase': event.data.get('phase', 'planning'),
            'round_type': event.data.get('round_type', 'combat'),
        }

    def _handle_end_planning(self, event: Event) -> Dict[str, Any]:
        """Handle end of planning phase."""
        self.game_round.end_planning_phase()

        # Augment selection always fires at START_PLANNING, so by the time
        # END_PLANNING fires the augments have already been chosen.
        # Always proceed straight to combat.
        self.schedule_event(
            self.current_time + 0.1,
            EventType.START_COMBAT,
            -1
        )

        return {'event': 'end_planning'}

    def _handle_start_combat(self, event: Event) -> Dict[str, Any]:
        """Handle start of combat phase (routes to correct round type handler)."""
        combat_results = self.game_round.run_combat_phase()

        self.schedule_event(
            self.current_time + 1.0,
            EventType.END_COMBAT,
            -1,
            {'combat_results': combat_results}
        )

        return {
            'event': 'start_combat',
            'round_type': self.game_round.get_round_type(self.current_round),
            'combat_results': combat_results,
        }

    def _handle_end_combat(self, event: Event) -> Dict[str, Any]:
        """Handle end of combat phase."""
        combat_results = event.data.get('combat_results', {})

        self.schedule_event(
            self.current_time + 0.1,
            EventType.END_ROUND,
            -1,
            {'combat_results': combat_results}
        )

        return {'event': 'end_combat'}

    def _handle_end_round(self, event: Event) -> Dict[str, Any]:
        """Handle end of round."""
        if self.game_round.is_game_over():
            self.schedule_event(self.current_time + 0.1, EventType.GAME_END, -1)
        else:
            self.schedule_event(
                self.current_time + 0.1,
                EventType.START_PLANNING,
                -1
            )

        return {'event': 'end_round', 'round': self.current_round}

    def _handle_carousel(self, event: Event) -> Dict[str, Any]:
        """
        Handle a carousel round.

        Simplified: grant each alive player 1 random item component, then
        schedule the next round (carousel has no planning/combat phase).
        """
        self.game_round.current_round = self.current_round
        # run_combat_phase() routes to _run_carousel_phase() for carousel rounds
        self.game_round.run_combat_phase()

        # Carousel doesn't check game-over on its own; jump straight to END_ROUND
        self.schedule_event(
            self.current_time + 0.1,
            EventType.END_ROUND,
            -1
        )

        return {'event': 'carousel', 'round': self.current_round}

    def _handle_augment_selection(self, event: Event) -> Dict[str, Any]:
        """
        Handle augment selection at rounds 10, 20, 29 (2-1, 3-2, 4-2).

        Augment selection fires at the START of the planning phase, before
        players take any shop or unit-management actions.  After all players
        have picked, the normal planning phase continues (PLAYER_ACTION_REQUIRED).

        Eligible augments are filtered by round number so that, e.g., Epoch
        only appears at 2-1 and Epoch+ only at 3-2.  Synthetic augments
        (implemented in code but absent from the data JSON) are merged in.

        For MVP: each alive player auto-selects a random augment from 3 offered.
        Fires the augment's on_select hook immediately.
        """
        from simulator.env.augment_effects import get_eligible_augments

        data_augments = list(self.pool.data_loader.augments.values()) if self.pool else []
        eligible = get_eligible_augments(self.current_round, data_augments)

        for player in self.players:
            if not player.is_alive:
                continue

            if not eligible:
                break

            # Offer 3 distinct augments
            sample_size = min(3, len(eligible))
            offered = random.sample(eligible, sample_size)

            # Auto-select a random one
            chosen = random.choice(offered)
            player.select_augment(chosen)

        # After augment selection, hand control back to players for the
        # rest of the planning phase (shop, buy/sell/move units).
        alive_players = [p for p in self.players if p.is_alive]
        round_type = event.data.get('round_type', 'combat')

        if alive_players:
            self.schedule_event(
                self.current_time + 0.1,
                EventType.PLAYER_ACTION_REQUIRED,
                alive_players[0].player_id,
                {
                    'phase': 'planning',
                    'players_remaining': [p.player_id for p in alive_players],
                    'round_type': round_type,
                }
            )
        else:
            self.schedule_event(self.current_time + 0.1, EventType.GAME_END, -1)

        return {
            'event': 'augment_selection',
            'round': self.current_round,
        }

    def _handle_game_end(self, event: Event) -> Dict[str, Any]:
        """Handle game end."""
        self.game_over_flag = True
        placements = self.game_round.get_placements()

        return {
            'game_over': True,
            'placements': placements,
            'round': self.current_round
        }

    # ===== Action application =====

    def apply_action(self, player_id: int, action: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply a player's action and continue event processing.

        Args:
            player_id: Which player is acting
            action: Action dictionary with 'action_type' and parameters

        Returns:
            Result of action application
        """
        player = self.players[player_id]
        action_type = action.get('action_type')

        result = {'success': False, 'player_id': player_id}

        if action_type == 'buy_xp':
            result['success'] = player.buy_xp()

        elif action_type == 'refresh_shop':
            result['success'] = player.refresh_shop()

        elif action_type == 'buy_champion':
            shop_index = action.get('shop_index', 0)
            result['success'] = player.buy_champion_from_shop(shop_index)

        elif action_type == 'sell_champion':
            position = action.get('position', (0, 0))
            result['success'] = player.sell_champion(position)

        elif action_type == 'move_champion':
            from_pos = action.get('from_pos', (0, 0))
            to_pos = action.get('to_pos', (0, 0))
            result['success'] = player.move_champion(from_pos, to_pos)

        elif action_type == 'pass':
            result['success'] = True

        else:
            print(f"Unknown action type: {action_type}")

        # Schedule next player or end planning
        alive_players = [p for p in self.players if p.is_alive]
        current_index = alive_players.index(player)

        if current_index < len(alive_players) - 1:
            next_player = alive_players[current_index + 1]
            self.schedule_event(
                self.current_time + 0.1,
                EventType.PLAYER_ACTION_REQUIRED,
                next_player.player_id,
                {'phase': 'planning'}
            )
        else:
            self.schedule_event(
                self.current_time + 0.1,
                EventType.END_PLANNING,
                -1
            )

        return result

    # ===== Observation / valid actions =====

    def _get_observation(self, player_id: int) -> Dict[str, Any]:
        """
        Get observation for a specific player (partial observability).

        This will be expanded in Phase 3 with proper encoding.
        """
        player = self.players[player_id]

        opponents = []
        for p in self.players:
            if p.player_id != player_id:
                opponents.append({
                    'player_id': p.player_id,
                    'health': p.health,
                    'level': p.level,
                    'is_alive': p.is_alive,
                    'board_units': len(p.board.get_all_champions()),
                })

        return {
            'round': self.current_round,
            'stage': self.current_stage,
            'my_state': player.get_state_dict(),
            'opponents': opponents,
        }

    def _get_valid_actions(self, player_id: int) -> List[str]:
        """Get list of valid actions for a player."""
        player = self.players[player_id]
        valid_actions = ['pass']

        if player.gold >= 4:
            valid_actions.append('buy_xp')

        if player.gold >= 2 or player.free_rerolls > 0:
            valid_actions.append('refresh_shop')

        for i, champ_id in enumerate(player.shop):
            if champ_id:
                champ_data = player.data_loader.get_champion_by_id(champ_id)
                if champ_data and player.gold >= champ_data.cost:
                    valid_actions.append(f'buy_champion_{i}')

        if player.board.get_all_champions() or any(c for c in player.bench if c):
            valid_actions.append('sell_champion')

        if player.board.get_all_champions():
            valid_actions.append('move_champion')

        return valid_actions

    # ===== Game state =====

    def is_game_over(self) -> bool:
        """Check if game is finished."""
        return self.game_over_flag

    def get_game_state(self) -> Dict[str, Any]:
        """Get complete game state (for debugging/logging)."""
        return {
            'round': self.current_round,
            'stage': self.current_stage,
            'game_over': self.game_over_flag,
            'round_type': self.game_round.get_round_type(self.current_round) if self.game_round else 'unknown',
            'players': [p.get_state_dict() for p in self.players],
            'next_event': str(self.peek_next_event()) if self.event_queue else None,
        }
