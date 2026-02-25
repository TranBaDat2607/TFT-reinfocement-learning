"""
simulator.env.augment_effects
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Augment effect system for TFT Set 16.

Public API — re-exported from registry.py so all existing import paths
(e.g. ``from simulator.env.augment_effects import apply_augment_hook``)
continue to work without any changes at the call sites.

To add a new augment:
  1. Create simulator/env/augment_effects/<name>.py
     (export AUGMENT_ID, HOOKS, SYNTHETIC_AUGMENT, ELIGIBLE_ROUNDS)
  2. Import it in registry.py and add it to _AUGMENT_MODULES.
"""

from simulator.env.augment_effects._base import AugmentResult
from simulator.env.augment_effects.registry import (
    AUGMENT_ELIGIBLE_ROUNDS,
    AUGMENT_REGISTRY,
    SYNTHETIC_AUGMENTS,
    apply_augment_hook,
    apply_all_passives,
    apply_all_stage_start_hooks,
    get_eligible_augments,
)

__all__ = [
    "AugmentResult",
    "AUGMENT_REGISTRY",
    "SYNTHETIC_AUGMENTS",
    "AUGMENT_ELIGIBLE_ROUNDS",
    "apply_augment_hook",
    "apply_all_passives",
    "apply_all_stage_start_hooks",
    "get_eligible_augments",
]
