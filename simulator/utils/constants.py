"""
Game constants and enumerations for TFT Set 16.
"""

from enum import IntEnum, auto


class ActionType(IntEnum):
    """Enumeration of all possible action types."""
    PASS = 0
    BUY_XP = 1
    REFRESH_SHOP = 2
    BUY_CHAMPION = 3
    SELL_CHAMPION = 4
    MOVE_CHAMPION = 5
    # Future actions
    PLACE_ITEM = 6
    LOCK_SHOP = 7


class RoundType(IntEnum):
    """Types of rounds in TFT."""
    CAROUSEL = auto()
    MINION = auto()
    PVP = auto()
    PORTAL = auto()


class Position:
    """Board position representation."""
    def __init__(self, row: int, col: int):
        self.row = row
        self.col = col
    
    def __eq__(self, other):
        return self.row == other.row and self.col == other.col
    
    def __hash__(self):
        return hash((self.row, self.col))
    
    def __repr__(self):
        return f"Position({self.row}, {self.col})"
    
    @property
    def is_board(self) -> bool:
        """Check if position is on board (not bench)."""
        return 0 <= self.row < 4 and 0 <= self.col < 7
    
    @property
    def is_bench(self) -> bool:
        """Check if position is on bench."""
        return self.row == -1 and 0 <= self.col < 9


# Trait tier styles (for visualization)
TRAIT_STYLES = {
    1: "bronze",
    2: "bronze",
    3: "silver",
    4: "gold",
    5: "chromatic",
}

# Special champion flags
CHAMPION_FLAGS = {
    "UNLOCKABLE": "unlockable",
    "PORTAL_EXCLUSIVE": "portal_exclusive",
}
