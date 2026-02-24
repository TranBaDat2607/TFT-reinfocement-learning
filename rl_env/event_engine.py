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
from enum import Enum, auto

from simulator.core.player import Player
from simulator.core.pool import ChampionPool
from simulator.engine.combat import CombatSimulator
from simulator.engine.game_round import GameRound
from simulator.config import TFTConfig


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
                # Check if this is a decision point
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
    
    def reset(self) -> Dict[str, Any]:
        """
        Reset the game to initial state.
        
        Returns:
            Initial game state for all players
        """
        # Clear event queue
        self.clear_queue()
        
        # Initialize game components
        from data_loader import TFTDataLoader
        data_loader = TFTDataLoader()
        
        self.pool = ChampionPool(data_loader=data_loader)
        self.combat_sim = CombatSimulator(self.config)
        
        # Create players
        self.players = [
            Player(
                player_id=i,
                pool=self.pool,
                config=self.config,
                data_loader=data_loader
            )
            for i in range(self.config.num_players)
        ]
        
        # Create game round manager
        self.game_round = GameRound(self.players, self.combat_sim, self.config)
        
        # Reset state
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
    
    def _handle_start_planning(self, event: Event) -> Dict[str, Any]:
        """Handle start of planning phase."""
        self.current_round += 1
        new_stage = ((self.current_round - 1) // 7) + 1
        is_new_stage = new_stage != self.current_stage
        self.current_stage = new_stage

        # Start planning for all alive players
        self.game_round.current_round = self.current_round
        self.game_round.current_stage = self.current_stage
        self.game_round.start_planning_phase()

        # Fire on_stage_start hooks for every player when the stage changes
        if is_new_stage:
            from simulator.env.augment_effects import apply_all_stage_start_hooks
            for player in self.players:
                if player.is_alive:
                    apply_all_stage_start_hooks(player)
        
        # Schedule decision point for each player
        # In event-driven, we ask each player to act sequentially
        alive_players = [p for p in self.players if p.is_alive]
        
        if alive_players:
            # Schedule action required for first player
            self.schedule_event(
                self.current_time + 0.1,
                EventType.PLAYER_ACTION_REQUIRED,
                alive_players[0].player_id,
                {'phase': 'planning', 'players_remaining': [p.player_id for p in alive_players]}
            )
        else:
            # No players alive, end game
            self.schedule_event(self.current_time + 0.1, EventType.GAME_END, -1)
        
        return {
            'event': 'start_planning',
            'round': self.current_round,
            'stage': self.current_stage
        }
    
    def _handle_player_action(self, event: Event) -> Dict[str, Any]:
        """Handle player action required (decision point)."""
        player_id = event.player_id
        player = self.players[player_id]
        
        # This is a decision point - return control to RL agent
        return {
            'requires_decision': True,
            'player_id': player_id,
            'round': self.current_round,
            'stage': self.current_stage,
            'observation': self._get_observation(player_id),
            'valid_actions': self._get_valid_actions(player_id),
            'phase': event.data.get('phase', 'planning')
        }
    
    def _handle_end_planning(self, event: Event) -> Dict[str, Any]:
        """Handle end of planning phase."""
        self.game_round.end_planning_phase()
        
        # Schedule combat
        self.schedule_event(
            self.current_time + 0.1,
            EventType.START_COMBAT,
            -1
        )
        
        return {'event': 'end_planning'}
    
    def _handle_start_combat(self, event: Event) -> Dict[str, Any]:
        """Handle start of combat phase."""
        # Run all combats
        combat_results = self.game_round.run_combat_phase()
        
        # Schedule end combat
        self.schedule_event(
            self.current_time + 1.0,  # Simulate 1 second combat duration
            EventType.END_COMBAT,
            -1,
            {'combat_results': combat_results}
        )
        
        return {'event': 'start_combat', 'combat_results': combat_results}
    
    def _handle_end_combat(self, event: Event) -> Dict[str, Any]:
        """Handle end of combat phase."""
        combat_results = event.data.get('combat_results', {})
        
        # Schedule end of round
        self.schedule_event(
            self.current_time + 0.1,
            EventType.END_ROUND,
            -1,
            {'combat_results': combat_results}
        )
        
        return {'event': 'end_combat'}
    
    def _handle_end_round(self, event: Event) -> Dict[str, Any]:
        """Handle end of round."""
        # Check if game is over
        if self.game_round.is_game_over():
            self.schedule_event(self.current_time + 0.1, EventType.GAME_END, -1)
        else:
            # Schedule next planning phase
            self.schedule_event(
                self.current_time + 0.1,
                EventType.START_PLANNING,
                -1
            )
        
        return {'event': 'end_round', 'round': self.current_round}
    
    def _handle_game_end(self, event: Event) -> Dict[str, Any]:
        """Handle game end."""
        self.game_over_flag = True
        placements = self.game_round.get_placements()
        
        return {
            'game_over': True,
            'placements': placements,
            'round': self.current_round
        }
    
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
        
        # Execute action based on type
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
        
        # Check if all players have acted this planning phase
        # For now, simplified: after each action, schedule next player or end planning
        alive_players = [p for p in self.players if p.is_alive]
        current_index = alive_players.index(player)
        
        if current_index < len(alive_players) - 1:
            # Schedule next player
            next_player = alive_players[current_index + 1]
            self.schedule_event(
                self.current_time + 0.1,
                EventType.PLAYER_ACTION_REQUIRED,
                next_player.player_id,
                {'phase': 'planning'}
            )
        else:
            # All players acted, end planning
            self.schedule_event(
                self.current_time + 0.1,
                EventType.END_PLANNING,
                -1
            )
        
        return result
    
    def _get_observation(self, player_id: int) -> Dict[str, Any]:
        """
        Get observation for a specific player (partial observability).
        
        This will be expanded in Phase 3 with proper encoding.
        For now, returns raw state.
        """
        player = self.players[player_id]
        
        # Get opponent states (public info only)
        opponents = []
        for p in self.players:
            if p.player_id != player_id:
                opponents.append({
                    'player_id': p.player_id,
                    'health': p.health,
                    'level': p.level,
                    'is_alive': p.is_alive,
                    # Board visible (can scout)
                    'board_units': len(p.board.get_all_champions()),
                })
        
        return {
            'round': self.current_round,
            'stage': self.current_stage,
            'my_state': player.get_state_dict(),
            'opponents': opponents,
        }
    
    def _get_valid_actions(self, player_id: int) -> List[str]:
        """
        Get list of valid actions for a player.
        
        This will be expanded in Phase 2 with proper action masking.
        """
        player = self.players[player_id]
        valid_actions = ['pass']
        
        if player.gold >= 4:
            valid_actions.append('buy_xp')
        
        if player.gold >= 2 or player.free_rerolls > 0:
            valid_actions.append('refresh_shop')
        
        # Can buy from shop if affordable
        for i, champ_id in enumerate(player.shop):
            if champ_id:
                champ_data = player.data_loader.get_champion_by_id(champ_id)
                if champ_data and player.gold >= champ_data.cost:
                    valid_actions.append(f'buy_champion_{i}')
        
        # Can sell units
        if player.board.get_all_champions() or player.bench:
            valid_actions.append('sell_champion')
        
        # Can move units
        if player.board.get_all_champions():
            valid_actions.append('move_champion')
        
        return valid_actions
    
    def is_game_over(self) -> bool:
        """Check if game is finished."""
        return self.game_over_flag
    
    def get_game_state(self) -> Dict[str, Any]:
        """Get complete game state (for debugging/logging)."""
        return {
            'round': self.current_round,
            'stage': self.current_stage,
            'game_over': self.game_over_flag,
            'players': [p.get_state_dict() for p in self.players],
            'next_event': str(self.peek_next_event()) if self.event_queue else None,
        }
