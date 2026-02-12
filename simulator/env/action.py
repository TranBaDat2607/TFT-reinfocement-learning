"""
Action space definition and execution for TFT RL environment.

Implements hierarchical action space with masking:
- Level 1: Action type (7 options)
- Level 2: Action parameters (conditional on type)
"""
from typing import Dict, Tuple, Optional
from enum import IntEnum
import numpy as np

from simulator.core.player import Player
from simulator.config import TFTConfig


class ActionType(IntEnum):
    """
    Top-level action types.

    Each action type may have associated parameters that are
    chosen after the action type is selected.
    """
    PASS = 0              # Do nothing, end turn
    BUY_XP = 1            # Spend 4 gold to buy XP
    REFRESH_SHOP = 2      # Spend 2 gold to reroll shop
    BUY_CHAMPION = 3      # Purchase from shop (requires shop_slot parameter)
    SELL_CHAMPION = 4     # Sell unit (requires position parameter)
    MOVE_CHAMPION = 5     # Reposition unit (requires from_pos, to_pos parameters)
    LOCK_SHOP = 6         # Toggle shop lock (Phase 2+)


class ActionSpace:
    """
    Defines the action space and provides action masking.

    The action space is hierarchical:
    1. Choose action type (0-6)
    2. Choose parameters based on action type:
       - BUY_CHAMPION: shop_slot (0-4)
       - SELL_CHAMPION: position (0-37: 28 board + 9 bench + 1 null)
       - MOVE_CHAMPION: from_pos (0-37), to_pos (0-37)

    Action masking prevents invalid actions from being selected.
    """

    def __init__(self, config: TFTConfig):
        """
        Initialize action space.

        Args:
            config: TFT configuration
        """
        self.config = config

        # Action space sizes
        self.num_action_types = len(ActionType)
        self.num_shop_slots = config.shop_size  # 5
        self.num_board_positions = config.board_size[0] * config.board_size[1]  # 4*7 = 28
        self.num_bench_positions = config.bench_size  # 9
        self.num_total_positions = self.num_board_positions + self.num_bench_positions  # 37

    def get_action_mask(self, player: Player) -> Dict[str, np.ndarray]:
        """
        Generate action mask for current player state.

        Invalid actions are masked (set to False/0) to prevent the agent
        from selecting them. This significantly speeds up learning.

        Args:
            player: Current player state

        Returns:
            Dictionary of boolean masks:
            - 'action_type': [num_action_types] - which action types are valid
            - 'shop_slot': [num_shop_slots] - which shop slots can be bought
            - 'sell_position': [num_total_positions] - which positions have units to sell
            - 'move_from': [num_total_positions] - which positions have units to move
            - 'move_to': [num_total_positions] - which positions can receive units
        """
        mask = {}

        # Action type mask
        action_type_mask = np.ones(self.num_action_types, dtype=bool)

        # PASS is always valid
        action_type_mask[ActionType.PASS] = True

        # BUY_XP: requires 4 gold and not max level
        action_type_mask[ActionType.BUY_XP] = (
            player.gold >= self.config.xp_cost and
            player.level < self.config.max_level
        )

        # REFRESH_SHOP: requires 2 gold
        action_type_mask[ActionType.REFRESH_SHOP] = (
            player.gold >= self.config.shop_refresh_cost
        )

        # BUY_CHAMPION: at least one affordable champion in shop
        has_buyable_champion = self._has_buyable_champion(player)
        action_type_mask[ActionType.BUY_CHAMPION] = has_buyable_champion

        # SELL_CHAMPION: has at least one unit
        has_units = player.get_total_unit_count() > 0
        action_type_mask[ActionType.SELL_CHAMPION] = has_units

        # MOVE_CHAMPION: has at least one unit
        action_type_mask[ActionType.MOVE_CHAMPION] = has_units

        # LOCK_SHOP: disabled for now (Phase 2+)
        action_type_mask[ActionType.LOCK_SHOP] = False

        mask['action_type'] = action_type_mask

        # Shop slot mask (for BUY_CHAMPION)
        mask['shop_slot'] = self._get_shop_mask(player)

        # Position masks (for SELL_CHAMPION and MOVE_CHAMPION)
        sell_mask, move_from_mask, move_to_mask = self._get_position_masks(player)
        mask['sell_position'] = sell_mask
        mask['move_from'] = move_from_mask
        mask['move_to'] = move_to_mask

        return mask

    def _has_buyable_champion(self, player: Player) -> bool:
        """Check if player can afford any champion in shop."""
        for champion_id in player.shop:
            if champion_id is not None:
                champ_data = player.data_loader.get_champion_by_id(champion_id)
                if champ_data and player.gold >= champ_data.cost:
                    if player.pool.is_available(champion_id):
                        return True
        return False

    def _get_shop_mask(self, player: Player) -> np.ndarray:
        """
        Generate mask for shop slots.

        A slot is valid if:
        1. Champion exists in that slot
        2. Player can afford it
        3. Champion is available in pool

        Returns:
            Boolean array of shape [num_shop_slots]
        """
        mask = np.zeros(self.num_shop_slots, dtype=bool)

        for i, champion_id in enumerate(player.shop):
            if champion_id is None:
                mask[i] = False
                continue

            # Check if can afford
            champ_data = player.data_loader.get_champion_by_id(champion_id)
            if not champ_data:
                mask[i] = False
                continue

            if player.gold < champ_data.cost:
                mask[i] = False
                continue

            # Check if available in pool
            if not player.pool.is_available(champion_id):
                mask[i] = False
                continue

            mask[i] = True

        return mask

    def _get_position_masks(self, player: Player) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Generate position masks for SELL and MOVE actions.

        Position encoding:
        - Positions 0-27: Board (row-major order: row0col0, row0col1, ..., row3col6)
        - Positions 28-36: Bench (bench slot 0-8)

        Returns:
            Tuple of (sell_mask, move_from_mask, move_to_mask)
        """
        sell_mask = np.zeros(self.num_total_positions, dtype=bool)
        move_from_mask = np.zeros(self.num_total_positions, dtype=bool)
        move_to_mask = np.zeros(self.num_total_positions, dtype=bool)

        # Board positions (0-27)
        board_rows, board_cols = self.config.board_size
        for row in range(board_rows):
            for col in range(board_cols):
                pos_idx = row * board_cols + col

                champion = player.board.get(row, col)
                if champion is not None:
                    # Can sell or move from this position
                    sell_mask[pos_idx] = True
                    move_from_mask[pos_idx] = True
                else:
                    # Can move to this position if board not full
                    current_board_count = player.board.count_champions()
                    max_units = self.config.max_units_by_level[player.level]
                    if current_board_count < max_units:
                        move_to_mask[pos_idx] = True

        # Bench positions (28-36)
        for bench_idx, champion in enumerate(player.bench):
            pos_idx = self.num_board_positions + bench_idx

            if champion is not None:
                # Can sell or move from bench
                sell_mask[pos_idx] = True
                move_from_mask[pos_idx] = True
            else:
                # Can move to empty bench slot
                move_to_mask[pos_idx] = True

        return sell_mask, move_from_mask, move_to_mask

    def execute_action(
        self,
        player: Player,
        action_type: int,
        shop_slot: int = 0,
        sell_position: int = 0,
        move_from: int = 0,
        move_to: int = 0
    ) -> bool:
        """
        Execute an action on the player.

        Args:
            player: Player to execute action on
            action_type: Action type (0-6)
            shop_slot: Shop slot index (for BUY_CHAMPION)
            sell_position: Position to sell from (for SELL_CHAMPION)
            move_from: Source position (for MOVE_CHAMPION)
            move_to: Destination position (for MOVE_CHAMPION)

        Returns:
            True if action executed successfully, False otherwise
        """
        action_type = ActionType(action_type)

        if action_type == ActionType.PASS:
            return True

        elif action_type == ActionType.BUY_XP:
            return player.buy_xp()

        elif action_type == ActionType.REFRESH_SHOP:
            return player.refresh_shop()

        elif action_type == ActionType.BUY_CHAMPION:
            return player.buy_champion_from_shop(shop_slot)

        elif action_type == ActionType.SELL_CHAMPION:
            row, col = self._position_to_coords(sell_position)
            return player.sell_champion((row, col))

        elif action_type == ActionType.MOVE_CHAMPION:
            from_row, from_col = self._position_to_coords(move_from)
            to_row, to_col = self._position_to_coords(move_to)
            return player.move_champion((from_row, from_col), (to_row, to_col))

        elif action_type == ActionType.LOCK_SHOP:
            # Not implemented yet
            return False

        else:
            raise ValueError(f"Unknown action type: {action_type}")

    def _position_to_coords(self, position: int) -> Tuple[int, int]:
        """
        Convert flat position index to (row, col) coordinates.

        Position encoding:
        - 0-27: Board positions (row-major)
        - 28-36: Bench positions (row=-1, col=bench_idx)

        Args:
            position: Flat position index (0-36)

        Returns:
            (row, col) tuple where row=-1 indicates bench
        """
        if position < self.num_board_positions:
            # Board position
            board_cols = self.config.board_size[1]
            row = position // board_cols
            col = position % board_cols
            return (row, col)
        else:
            # Bench position
            bench_idx = position - self.num_board_positions
            return (-1, bench_idx)

    def coords_to_position(self, row: int, col: int) -> int:
        """
        Convert (row, col) coordinates to flat position index.

        Args:
            row: Row index (0-3 for board, -1 for bench)
            col: Column index

        Returns:
            Flat position index (0-36)
        """
        if row == -1:
            # Bench position
            return self.num_board_positions + col
        else:
            # Board position
            board_cols = self.config.board_size[1]
            return row * board_cols + col

    def get_action_space_sizes(self) -> Dict[str, int]:
        """
        Get the size of each action component.

        Returns:
            Dictionary with sizes of each action space component
        """
        return {
            'action_type': self.num_action_types,
            'shop_slot': self.num_shop_slots,
            'position': self.num_total_positions,
        }

    def sample_valid_action(self, player: Player) -> Dict[str, int]:
        """
        Sample a random valid action for testing.

        Args:
            player: Current player state

        Returns:
            Dictionary with sampled action components
        """
        mask = self.get_action_mask(player)

        # Sample valid action type
        valid_actions = np.where(mask['action_type'])[0]
        if len(valid_actions) == 0:
            # Fallback to PASS
            action_type = ActionType.PASS
        else:
            action_type = np.random.choice(valid_actions)

        # Sample parameters based on action type
        action = {'action_type': int(action_type)}

        if action_type == ActionType.BUY_CHAMPION:
            valid_slots = np.where(mask['shop_slot'])[0]
            if len(valid_slots) > 0:
                action['shop_slot'] = int(np.random.choice(valid_slots))
            else:
                action['shop_slot'] = 0

        elif action_type == ActionType.SELL_CHAMPION:
            valid_positions = np.where(mask['sell_position'])[0]
            if len(valid_positions) > 0:
                action['sell_position'] = int(np.random.choice(valid_positions))
            else:
                action['sell_position'] = 0

        elif action_type == ActionType.MOVE_CHAMPION:
            valid_from = np.where(mask['move_from'])[0]
            valid_to = np.where(mask['move_to'])[0]

            if len(valid_from) > 0 and len(valid_to) > 0:
                action['move_from'] = int(np.random.choice(valid_from))
                action['move_to'] = int(np.random.choice(valid_to))
            else:
                action['move_from'] = 0
                action['move_to'] = 0

        return action


def create_action_space(config: TFTConfig) -> ActionSpace:
    """
    Factory function to create ActionSpace.

    Args:
        config: TFT configuration

    Returns:
        ActionSpace instance
    """
    return ActionSpace(config)
