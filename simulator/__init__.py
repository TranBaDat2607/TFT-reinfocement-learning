"""
TFT Set 16 Simulator Package

A data-driven, modular TFT simulation environment for reinforcement learning.
Built using PettingZoo framework for multi-agent self-play training.
"""

from .config import TFTConfig, get_mvp_config, get_training_config, get_full_config, GameConstants

__version__ = "0.1.0"
__all__ = [
    "TFTConfig",
    "get_mvp_config",
    "get_training_config", 
    "get_full_config",
    "GameConstants",
]
