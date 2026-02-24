"""
RL Environment package for TFT Set 16.

This package provides the reinforcement learning environment layer,
including event-driven simulation, PettingZoo wrapper, and observation/action encoders.
"""

from .event_engine import Event, EventEngine, TFTEventEngine

__all__ = [
    'Event',
    'EventEngine', 
    'TFTEventEngine',
]
