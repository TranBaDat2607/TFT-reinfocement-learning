# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Reinforcement Learning project to build an AI agent for Teamfight Tactics (TFT) Set 16. It implements a multi-agent RL training pipeline via self-play, using PyTorch, Gymnasium, Stable-Baselines3, and PettingZoo.

## Setup & Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
python tests/test_action.py
python tests/test_event_engine.py

# Crawl/refresh game data (run from crawl_data/ directory)
cd crawl_data
python get_champions_detailed.py
python get_items_detailed.py
python get_traits_detailed.py
python get_augments_detailed.py
python get_portals_detailed.py

# Run example scripts
python scripts/example_event_engine.py
```

There is no dedicated linter config — the project uses standard Python conventions.

## Architecture

### High-Level Flow

```
Policy Network (PyTorch)
    ↕
RL Environment (tft_env.py — TODO)
    ↕ observations / actions / rewards
Event Engine (rl_env/event_engine.py)   ← event-driven, priority queue
    ↕
Core Simulator (simulator/)
    ├── config.py        — phased config: MVP → Training → Full
    ├── core/            — Player, Board (4×7 hex), Champion, Pool
    ├── engine/          — combat.py (statistical mode), game_round.py
    └── env/action.py    — hierarchical action space + masking
```

### Key Design Decisions

- **Hierarchical action space** (7 types: PASS, BUY_XP, REFRESH_SHOP, BUY_CHAMPION, SELL_CHAMPION, MOVE_CHAMPION, LOCK_SHOP) reduces valid actions from ~10,000 to 50–200 per step.
- **Action masking** is enforced at the `ActionSpace` level — always call `get_action_mask(player)` before sampling.
- **Event-driven engine** (not time-step based) schedules phases via a priority queue (EventType: START_PLANNING, END_PLANNING, START_COMBAT, etc.).
- **Independent critic** (not centralized) to fit within 8 GB VRAM (RTX 5060 target hardware).
- **Phased config** via `get_mvp_config()` / `get_training_config()` in `simulator/config.py`.

### Data Layer

Game data (champions, items, traits, augments, portals) lives in `data/set16/*.json`, crawled from Community Dragon API and op.gg. Loaded via `TFTDataLoader` in `data_loader/data_loader.py`.

### Position Encoding

37 total positions: 28 board (4×7 hex grid) + 9 bench slots. Used consistently across `Board`, `Player`, and `ActionSpace`.

## Implementation Status

**Completed:** Config system, core game mechanics (Player/Board/Champion/Pool), action space with masking, event engine, data crawling scripts, data loader/models, unit tests.

**TODO (next priorities):**
- `simulator/env/observation.py` — encode game state to tensors
- `simulator/env/reward.py` — placement-based reward shaping
- `simulator/env/tft_env.py` — PettingZoo multi-agent environment wrapper
- Policy network (Transformer-based encoder + PPO/MAPPO training loop)

## Key Reference Files

- `model_design.md` — complete architecture blueprint (encoder dims, network layers, training config)
- `RL_PIPELINE.md` — phased implementation roadmap with code scaffolds
- `architecture_critique.md` — hardware feasibility analysis and design recommendations
- `simulator/env/README.md` — environment development status and notes
- `output_format/` — example JSON schemas for observations, action masks, env step returns
