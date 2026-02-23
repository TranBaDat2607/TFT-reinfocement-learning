"""
Observation encoder for TFT Set 16 RL environment.

Translates raw game state (Player, Board, Champion) into structured
numpy arrays for the policy network defined in model_design.md.

Output shapes:
  global    [32]    — scalar game state, normalized [0, 1]
  units     [20,32] — board (compact, row-major) + bench (fixed mapping)
  shop      [5,16]  — per-slot shop features
  opponents [7,24]  — public opponent info
  flat      [920]   — all of the above concatenated
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from data_loader.data_loader import TFTDataLoader
from simulator.config import TFTConfig


@dataclass
class ObservationConfig:
    champion_to_idx: Dict[str, int]   # champion_id  → int (1..N, 0=empty)
    item_to_idx: Dict[str, int]       # item_id      → int (1..N, 0=empty)
    trait_to_idx: Dict[str, int]      # trait_name   → int (1..N, 0=empty)
    num_champions: int
    num_items: int
    num_traits: int


def build_lookup_tables(data_loader: TFTDataLoader) -> ObservationConfig:
    """
    Build deterministic lookup tables from loaded game data.

    Filtering rules:
      Champions : cost 1-6, has at least one trait; sorted by champion_id
      Items     : exclude augments (TFT16_Augment_ prefix); sorted by item_id
      Traits    : all unique trait names from playable champions; sorted
    """
    # --- Champions ---
    playable = sorted(
        [c for c in data_loader.get_all_champions() if 1 <= c.cost <= 6 and c.traits],
        key=lambda c: c.champion_id,
    )
    champion_to_idx: Dict[str, int] = {c.champion_id: i + 1 for i, c in enumerate(playable)}

    # --- Items (equippable only) ---
    equippable = sorted(
        [item for item in data_loader.get_all_items()
         if not item.item_id.startswith("TFT16_Augment_")],
        key=lambda item: item.item_id,
    )
    item_to_idx: Dict[str, int] = {item.item_id: i + 1 for i, item in enumerate(equippable)}

    # --- Traits (collected from playable champions) ---
    all_trait_names = sorted({trait for c in playable for trait in c.traits})
    trait_to_idx: Dict[str, int] = {name: i + 1 for i, name in enumerate(all_trait_names)}

    return ObservationConfig(
        champion_to_idx=champion_to_idx,
        item_to_idx=item_to_idx,
        trait_to_idx=trait_to_idx,
        num_champions=len(champion_to_idx),
        num_items=len(item_to_idx),
        num_traits=len(trait_to_idx),
    )


class PlayerObservation:
    """
    Encodes a single player's game state into structured numpy arrays.

    One instance is typically created per player (shared lookup tables via
    ObservationConfig) and reused across all steps of the game.
    """

    GLOBAL_DIM = 32
    UNIT_DIM = 32
    MAX_BOARD_UNITS = 11   # maximum at level 11
    MAX_BENCH_UNITS = 9
    MAX_UNITS = MAX_BOARD_UNITS + MAX_BENCH_UNITS  # 20
    SHOP_DIM = 16
    SHOP_SLOTS = 5
    OPPONENT_DIM = 24
    NUM_OPPONENTS = 7
    FLAT_SIZE = 920        # 32 + 640 + 80 + 168

    def __init__(self, obs_config: ObservationConfig, tft_config: TFTConfig) -> None:
        self.obs_config = obs_config
        self.tft_config = tft_config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def encode(
        self, player, opponents: List, stage: int, round_in_stage: int
    ) -> Dict[str, np.ndarray]:
        """
        Encode full observation for one player.

        Args:
            player:          Player instance (the agent being observed)
            opponents:       List of all *other* Player instances (up to 7)
            stage:           Current game stage (1-7)
            round_in_stage:  Current round within stage (1-7)

        Returns:
            Dict with keys 'global' (32,), 'units' (20,32),
            'shop' (5,16), 'opponents' (7,24).
        """
        return {
            "global":    self._encode_global(player, opponents, stage, round_in_stage),
            "units":     self._encode_units(player),
            "shop":      self._encode_shop(player),
            "opponents": self._encode_opponents(player, opponents),
        }

    def to_flat(
        self, player, opponents: List, stage: int, round_in_stage: int
    ) -> np.ndarray:
        """Return flattened observation vector of shape [920]."""
        obs = self.encode(player, opponents, stage, round_in_stage)
        return np.concatenate([
            obs["global"],
            obs["units"].flatten(),
            obs["shop"].flatten(),
            obs["opponents"].flatten(),
        ]).astype(np.float32)

    @staticmethod
    def flat_size() -> int:
        return PlayerObservation.FLAT_SIZE

    def encode_dead(self) -> Dict[str, np.ndarray]:
        """All-zero observation for eliminated players."""
        return {
            "global":    np.zeros(self.GLOBAL_DIM,                          dtype=np.float32),
            "units":     np.zeros((self.MAX_UNITS, self.UNIT_DIM),          dtype=np.float32),
            "shop":      np.zeros((self.SHOP_SLOTS, self.SHOP_DIM),         dtype=np.float32),
            "opponents": np.zeros((self.NUM_OPPONENTS, self.OPPONENT_DIM),  dtype=np.float32),
        }

    # ------------------------------------------------------------------
    # Private encoders
    # ------------------------------------------------------------------

    def _encode_global(
        self, player, opponents: List, stage: int, round_in_stage: int
    ) -> np.ndarray:
        """Encode global state into [32] float32 array (all values [0, 1])."""
        vec = np.zeros(self.GLOBAL_DIM, dtype=np.float32)

        # XP progress toward next level
        next_level = player.level + 1
        if player.level >= self.tft_config.max_level:
            xp_progress = 1.0
        else:
            xp_to_next = self.tft_config.xp_to_level.get(next_level, 99999)
            xp_progress = min(player.xp / xp_to_next, 1.0) if xp_to_next > 0 else 1.0

        # Alive opponent count
        alive_opponents = sum(1 for opp in opponents if opp.is_alive)

        # Approximate placement by health rank (rank 1 = highest HP = best)
        all_players = [player] + list(opponents)
        sorted_by_hp = sorted(all_players, key=lambda p: p.health, reverse=True)
        my_rank = 1
        for rank, p in enumerate(sorted_by_hp):
            if p is player:
                my_rank = rank + 1
                break

        # Interest gold earned next round
        interest = min(player.gold // 10, self.tft_config.interest_cap)

        vec[0] = stage / 7.0
        vec[1] = round_in_stage / 7.0
        vec[2] = player.health / 100.0
        vec[3] = min(player.gold, 100) / 100.0
        vec[4] = player.level / 11.0
        vec[5] = xp_progress
        vec[6] = 0.0                      # time_in_phase: 0.0 in MVP
        vec[7] = alive_opponents / 7.0
        vec[8] = my_rank / 8.0
        vec[9] = 0.0                      # streak_level: 0.0 in MVP
        vec[10] = interest / 5.0
        # dims 11-31: reserved zeros
        return vec

    def _encode_units(self, player) -> np.ndarray:
        """
        Encode all units into [20, 32] float32 array.

        Layout:
          slots 0-10  : board champions in row-major order (compact, occupied only)
          slots 11-19 : bench slots (fixed mapping: bench[i] → slot 11+i)
        Empty slots are all-zero rows.
        """
        arr = np.zeros((self.MAX_UNITS, self.UNIT_DIM), dtype=np.float32)

        # --- Board: compact, row-major ---
        slot = 0
        rows, cols = self.tft_config.board_size
        for row in range(rows):
            if slot >= self.MAX_BOARD_UNITS:
                break
            for col in range(cols):
                if slot >= self.MAX_BOARD_UNITS:
                    break
                champ = player.board.get(row, col)
                if champ is not None:
                    arr[slot] = self._encode_champion(champ, is_on_board=True, row=row, col=col)
                    slot += 1

        # --- Bench: fixed mapping bench[i] → unit slot 11+i ---
        for bench_idx, champ in enumerate(player.bench):
            unit_slot = self.MAX_BOARD_UNITS + bench_idx
            if unit_slot >= self.MAX_UNITS:
                break
            if champ is not None:
                arr[unit_slot] = self._encode_champion(
                    champ, is_on_board=False, row=-1, col=bench_idx
                )
            # else: already zeros

        return arr

    def _encode_champion(
        self, champ, is_on_board: bool, row: int, col: int
    ) -> np.ndarray:
        """Encode a single champion into [32] float32 vector."""
        vec = np.zeros(self.UNIT_DIM, dtype=np.float32)
        obs_cfg = self.obs_config

        # Integer IDs (float32) — fed into embedding layers
        champ_idx = float(obs_cfg.champion_to_idx.get(champ.data.champion_id, 0))

        item_indices = [float(obs_cfg.item_to_idx.get(item_id, 0))
                        for item_id in champ.items[:3]]
        while len(item_indices) < 3:
            item_indices.append(0.0)

        trait_indices = [float(obs_cfg.trait_to_idx.get(t, 0))
                         for t in champ.data.traits[:3]]
        while len(trait_indices) < 3:
            trait_indices.append(0.0)

        # HP ratio [0, 1]
        hp_ratio = champ.current_hp / champ.max_hp if champ.max_hp > 0 else 0.0

        # Frontline: board rows 2-3 (closer to opponent)
        is_frontline = 1.0 if (is_on_board and row >= 2) else 0.0

        vec[0]  = champ_idx
        vec[1]  = float(champ.stars)
        vec[2]  = float(champ.cost)
        vec[3]  = float(row)
        vec[4]  = float(col)
        vec[5]  = item_indices[0]
        vec[6]  = item_indices[1]
        vec[7]  = item_indices[2]
        vec[8]  = hp_ratio
        vec[9]  = champ.max_hp           # raw float — Transformer handles via LayerNorm
        vec[10] = champ.attack_damage    # raw float
        vec[11] = champ.armor            # raw float
        vec[12] = champ.magic_resist     # raw float
        vec[13] = champ.attack_speed     # raw float
        vec[14] = trait_indices[0]
        vec[15] = trait_indices[1]
        vec[16] = trait_indices[2]
        vec[17] = 1.0 if is_on_board else 0.0
        vec[18] = is_frontline
        # dims 19-31: reserved zeros

        return vec

    def _encode_shop(self, player) -> np.ndarray:
        """Encode shop slots into [5, 16] float32 array."""
        arr = np.zeros((self.SHOP_SLOTS, self.SHOP_DIM), dtype=np.float32)
        shop_odds = self.tft_config.shop_odds.get(player.level, [0.0] * 5)

        for i, champion_id in enumerate(player.shop[:self.SHOP_SLOTS]):
            if champion_id is None:
                continue

            champ_data = player.data_loader.get_champion_by_id(champion_id)
            if champ_data is None:
                continue

            cost = champ_data.cost
            champ_idx = float(self.obs_config.champion_to_idx.get(champion_id, 0))
            can_afford = 1.0 if player.gold >= cost else 0.0
            copies_owned = float(self._count_copies(player, champion_id))
            is_available = 1.0 if player.pool.is_available(champion_id) else 0.0

            # tier_probability: shop_odds[level] is indexed by (cost - 1)
            tier_idx = cost - 1
            tier_prob = shop_odds[tier_idx] if 0 <= tier_idx < len(shop_odds) else 0.0

            arr[i, 0] = champ_idx
            arr[i, 1] = float(cost)
            arr[i, 2] = can_afford
            arr[i, 3] = copies_owned
            arr[i, 4] = is_available
            arr[i, 5] = tier_prob
            # dims 6-15: reserved zeros

        return arr

    def _encode_opponents(self, player, opponents: List) -> np.ndarray:
        """Encode opponent public info into [7, 24] float32 array."""
        arr = np.zeros((self.NUM_OPPONENTS, self.OPPONENT_DIM), dtype=np.float32)

        # Health-based rank map for all players (rank 1 = highest HP)
        all_players = [player] + list(opponents)
        sorted_by_hp = sorted(all_players, key=lambda p: p.health, reverse=True)
        hp_rank_map = {id(p): rank + 1 for rank, p in enumerate(sorted_by_hp)}

        for i, opp in enumerate(opponents[:self.NUM_OPPONENTS]):
            board_count = opp.board.count_champions()

            # Estimated strength: sum(cost * stars) / 50.0, capped [0, 1]
            strength_sum = sum(c.cost * c.stars for c in opp.board.get_all_champions())
            estimated_strength = min(strength_sum / 50.0, 1.0)

            hp_rank = hp_rank_map.get(id(opp), 8)

            arr[i, 0]  = opp.health / 100.0
            arr[i, 1]  = float(opp.level)
            arr[i, 2]  = 1.0 if opp.is_alive else 0.0
            arr[i, 3]  = float(board_count)
            arr[i, 4]  = estimated_strength
            arr[i, 5]  = 0.0   # rounds_since_scouted: 0.0 in MVP
            arr[i, 6]  = 0.0   # comp_archetype_id: 0.0 in MVP
            arr[i, 7]  = hp_rank / 8.0
            arr[i, 8]  = 0.5   # last_combat_result: 0.5 (unknown) in MVP
            arr[i, 9]  = 0.0   # win_streak: 0.0 in MVP
            arr[i, 10] = float(hp_rank)   # placement_rank approximated by hp_rank
            # dims 11-23: reserved zeros

        return arr

    def _count_copies(self, player, champion_id: str) -> int:
        """Count copies of a champion owned by player (board + bench)."""
        count = sum(
            1 for c in player.board.get_all_champions()
            if c.data.champion_id == champion_id
        )
        count += sum(
            1 for c in player.bench
            if c is not None and c.data.champion_id == champion_id
        )
        return count


def create_observation_encoder(
    data_loader: TFTDataLoader, tft_config: TFTConfig
) -> PlayerObservation:
    """Convenience factory: build lookup tables then construct PlayerObservation."""
    obs_config = build_lookup_tables(data_loader)
    return PlayerObservation(obs_config, tft_config)
