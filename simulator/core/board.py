"""
Board management for TFT Set 16.

Handles the hex grid board (4x7) where champions are placed for combat.
"""
from typing import Optional, List, Dict, Tuple
from simulator.core.champion import Champion
from simulator.utils.constants import Position


class Board:
    """
    Represents a TFT hex grid board (4 rows x 7 columns).
    
    The board is where champions are placed during combat.
    Positions are (row, col) where:
    - row: 0-3 (4 rows)
    - col: 0-6 (7 columns)
    """
    
    def __init__(self, rows: int = 4, cols: int = 7):
        """
        Initialize empty board.
        
        Args:
            rows: Number of rows (default: 4)
            cols: Number of columns (default: 7)
        """
        self.rows = rows
        self.cols = cols
        
        # Grid storage: position -> Champion or None
        self.grid: Dict[Tuple[int, int], Optional[Champion]] = {}
        
        # Initialize empty grid
        for row in range(rows):
            for col in range(cols):
                self.grid[(row, col)] = None
    
    def is_valid_position(self, row: int, col: int) -> bool:
        """Check if position is within board bounds."""
        return 0 <= row < self.rows and 0 <= col < self.cols
    
    def is_empty(self, row: int, col: int) -> bool:
        """Check if position is empty."""
        if not self.is_valid_position(row, col):
            return False
        return self.grid[(row, col)] is None
    
    def get(self, row: int, col: int) -> Optional[Champion]:
        """Get champion at position, or None if empty."""
        if not self.is_valid_position(row, col):
            return None
        return self.grid.get((row, col))
    
    def place(self, champion: Champion, row: int, col: int) -> bool:
        """
        Place a champion at position.
        
        Args:
            champion: Champion to place
            row: Row position
            col: Column position
            
        Returns:
            True if successful, False if position invalid or occupied
        """
        if not self.is_valid_position(row, col):
            return False
        
        if not self.is_empty(row, col):
            return False
        
        # Remove from old position if exists
        if champion.position:
            old_row, old_col = champion.position
            if self.grid.get((old_row, old_col)) == champion:
                self.grid[(old_row, old_col)] = None
        
        # Place at new position
        self.grid[(row, col)] = champion
        champion.position = (row, col)
        
        return True
    
    def remove(self, row: int, col: int) -> Optional[Champion]:
        """
        Remove champion from position.
        
        Args:
            row: Row position
            col: Column position
            
        Returns:
            Removed champion or None if position was empty
        """
        if not self.is_valid_position(row, col):
            return None
        
        champion = self.grid.get((row, col))
        if champion:
            self.grid[(row, col)] = None
            champion.position = None
        
        return champion
    
    def move(self, from_row: int, from_col: int, to_row: int, to_col: int) -> bool:
        """
        Move champion from one position to another.
        
        Args:
            from_row, from_col: Source position
            to_row, to_col: Destination position
            
        Returns:
            True if successful, False otherwise
        """
        # Check if source has a champion
        champion = self.get(from_row, from_col)
        if not champion:
            return False
        
        # Check if destination is valid and empty
        if not self.is_valid_position(to_row, to_col):
            return False
        
        if not self.is_empty(to_row, to_col):
            return False
        
        # Move champion
        self.grid[(from_row, from_col)] = None
        self.grid[(to_row, to_col)] = champion
        champion.position = (to_row, to_col)
        
        return True
    
    def swap(self, row1: int, col1: int, row2: int, col2: int) -> bool:
        """
        Swap champions at two positions.
        
        Args:
            row1, col1: First position
            row2, col2: Second position
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_valid_position(row1, col1) or not self.is_valid_position(row2, col2):
            return False
        
        champ1 = self.grid.get((row1, col1))
        champ2 = self.grid.get((row2, col2))
        
        # Swap
        self.grid[(row1, col1)] = champ2
        self.grid[(row2, col2)] = champ1
        
        if champ1:
            champ1.position = (row2, col2)
        if champ2:
            champ2.position = (row1, col1)
        
        return True
    
    def get_all_champions(self) -> List[Champion]:
        """Get list of all champions on board."""
        return [champ for champ in self.grid.values() if champ is not None]
    
    def count_champions(self) -> int:
        """Count total champions on board."""
        return len(self.get_all_champions())
    
    def clear(self):
        """Remove all champions from board."""
        for pos in self.grid:
            champion = self.grid[pos]
            if champion:
                champion.position = None
            self.grid[pos] = None
    
    def find_champion(self, champion: Champion) -> Optional[Tuple[int, int]]:
        """
        Find position of a champion on board.
        
        Args:
            champion: Champion to find
            
        Returns:
            (row, col) tuple or None if not found
        """
        for (row, col), champ in self.grid.items():
            if champ == champion:
                return (row, col)
        return None
    
    def get_empty_positions(self) -> List[Tuple[int, int]]:
        """Get list of all empty positions."""
        return [(row, col) for (row, col), champ in self.grid.items() if champ is None]
    
    def is_full(self) -> bool:
        """Check if board has no empty positions."""
        return len(self.get_empty_positions()) == 0
    
    def to_array(self):
        """
        Convert board to 2D numpy-compatible list.
        
        Returns:
            2D list where each cell is champion_id or None
        """
        import numpy as np
        array = [[None for _ in range(self.cols)] for _ in range(self.rows)]
        
        for row in range(self.rows):
            for col in range(self.cols):
                champion = self.grid[(row, col)]
                if champion:
                    array[row][col] = champion.data.champion_id
        
        return array
    
    def get_hex_neighbors(self, row: int, col: int) -> List[Tuple[int, int]]:
        """
        Return the valid board positions adjacent to (row, col) on the hex grid.

        TFT uses offset hex coordinates where even and odd rows are staggered:

            Even rows (0, 2):          Odd rows (1, 3):
            . N N .                    . . N N .
            N X N  →  offsets          N X N
            . N N .    (-1,c-1),(-1,c)    (-1,c),(-1,c+1)
                       (+1,c-1),(+1,c)    (+1,c),(+1,c+1)
                       (r, c-1),(r, c+1)  (r, c-1),(r, c+1)

        Only positions within board bounds are returned.
        """
        if row % 2 == 0:
            candidates = [
                (row,     col - 1), (row,     col + 1),
                (row - 1, col - 1), (row - 1, col),
                (row + 1, col - 1), (row + 1, col),
            ]
        else:
            candidates = [
                (row,     col - 1), (row,     col + 1),
                (row - 1, col),     (row - 1, col + 1),
                (row + 1, col),     (row + 1, col + 1),
            ]
        return [(r, c) for r, c in candidates if self.is_valid_position(r, c)]

    def __repr__(self):
        champions = self.get_all_champions()
        return f"Board({self.count_champions()}/{self.rows * self.cols} positions filled)"
