# Reinforcement Learning Pipeline for TFT Set 16 (and Beyond)

## Table of Contents
1. [Project Overview](#project-overview)
2. [Game State Representation](#game-state-representation)
3. [Action Space Design](#action-space-design)
4. [Reward Function](#reward-function)
5. [Model Architecture](#model-architecture)
6. [Training Pipeline](#training-pipeline)
7. [Evaluation & Validation](#evaluation--validation)
8. [Set-Agnostic & Patch-Adaptive Design](#set-agnostic--patch-adaptive-design)
9. [Infrastructure & Scalability](#infrastructure--scalability)
10. [Phase-by-Phase Implementation Plan](#phase-by-phase-implementation-plan)

---

## Project Overview

### Goal
Build a reinforcement learning agent that can:
- **Primary**: Master TFT Set 16 gameplay
- **Secondary**: Generalize to all TFT sets with minimal retraining
- **Tertiary**: Adapt to patch changes automatically by updating strategy embeddings

### Key Challenges
1. **Partial Observability**: Cannot see opponent boards/items until combat
2. **High Action Space**: Hundreds of possible actions per turn (positioning, itemization, econ management)
3. **Long Horizon**: Games last 20-35 rounds with delayed rewards
4. **Stochasticity**: Shop RNG, combat variance, carousel order
5. **Meta Evolution**: Patches change champion/item/augment balance every 2-4 weeks
6. **Set Changes**: New sets introduce entirely new mechanics (e.g., Set 16 Unlockables, Portals)

---

## Game State Representation

### 1. Global Game State Features
```python
GlobalState = {
    # Stage & Round Info
    "stage": int,                    # Current stage (1-7+)
    "round": int,                    # Current round within stage (1-7)
    "time_remaining": float,         # Planning phase time left
    
    # Player Status
    "player_health": int,            # Current HP (0-100)
    "gold": int,                     # Current gold (0-∞)
    "level": int,                    # Player level (1-11)
    "xp": int,                       # Current XP
    "win_streak": int,               # Current win streak
    "loss_streak": int,              # Current loss streak
    "placement": int,                # Current rank (1-8)
    "alive_players": int,            # Number of players still alive
    
    # Set-Specific Context
    "set_id": str,                   # "Set16", "Set17", etc.
    "portal_active": str,            # Current portal (Set 16+)
    "chosen_augments": List[str],    # Augments selected this game
    
    # Economy
    "interest": int,                 # Gold from interest this round
    "streak_gold": int,              # Gold from streak
    "rounds_until_carousel": int,   # Planning for carousel
}
```

### 2. Player Board State (My Board)
```python
BoardState = {
    # Units on Board (7 max, 11 at level 11)
    "units": List[{
        "champion_id": str,          # e.g., "TFT16_Lulu"
        "position": (int, int),      # (row, col) on 7x4 hex grid
        "star_level": int,           # 1, 2, 3
        "items": List[str],          # Up to 3 items
        "traits": List[str],         # Champion traits
        "cost": int,                 # Champion cost (1-5, 7, 8+)
        "current_hp": float,         # In combat (if observable)
        "current_mana": float,       # In combat (if observable)
        
        # Set 16 Specific
        "unlockable": bool,          # Is this an unlocked champion?
        "combined_champion": bool,   # Is this a dual champion (Lucian&Senna)?
    }],
    
    # Active Traits
    "active_traits": List[{
        "trait_id": str,
        "tier": int,                 # Bronze/Silver/Gold/Prismatic
        "units_count": int,
        "bonus_values": Dict,        # Trait-specific bonuses
    }],
    
    # Bench State (9 slots)
    "bench": List[{
        "champion_id": str,
        "star_level": int,
        "items": List[str],
        "slot_index": int,
    }],
    
    # Item Components
    "available_items": Dict[str, int],  # Item ID -> count
}
```

### 3. Shop State
```python
ShopState = {
    "shop_champions": List[{
        "champion_id": str,
        "cost": int,
        "slot_index": int,
    }],
    "reroll_cost": int,              # Usually 2 gold
    "shop_locked": bool,
    
    # Set 16: Unlockables
    "unlockable_in_shop": List[{
        "champion_id": str,
        "unlock_condition": str,     # e.g., "Field 3 Piltover"
        "unlock_progress": float,    # 0.0 to 1.0
    }],
}
```

### 4. Opponent States (Updated Every Round)

**Important**: Opponent states are **continuously tracked and updated every round**, not just when you face them. Information visibility has three levels:

#### Public Information (Always Visible)
```python
OpponentPublicInfo = List[{  # 7 opponents
    "player_id": int,
    "player_name": str,
    "current_health": int,           # Updated every round
    "current_level": int,            # Updated every round
    "current_placement": int,        # Current rank (1-8)
    "is_alive": bool,
    
    # Streak information (observable from HP changes)
    "estimated_win_streak": int,     # Inferred from HP pattern
    "estimated_loss_streak": int,
    "estimated_gold": int,           # Rough estimate from level + streaks
    
    # Round history
    "rounds_won": int,               # Total wins this game
    "rounds_lost": int,              # Total losses this game
    "last_round_result": str,        # "win", "loss", or "unknown"
}]
```

#### Scoutable Information (Visible if Scouting)
During planning phase, you can click on any opponent to scout their board:

```python
OpponentScoutInfo = List[{
    "player_id": int,
    "scout_timestamp": int,          # Which round this was scouted
    
    # Current board state (if scouted this round)
    "current_board": List[{
        "champion_id": str,
        "position": (int, int),      # Exact position
        "star_level": int,
        "items": List[str],          # All items visible
        "traits": List[str],
    }],
    
    # Active traits (if scouted)
    "active_traits": List[{
        "trait_id": str,
        "tier": int,
        "units_count": int,
    }],
    
    # Bench (partially visible - can see champions, not items)
    "bench_champions": List[str],    # What's on bench
    
    # Board strength metrics
    "estimated_power": float,        # Based on units + items
    "comp_archetype": str,           # "Slayer", "Void", "Arcanist", etc.
}]
```

#### Post-Combat Information (After Fighting)
When you fight an opponent, you get detailed combat data:

```python
OpponentCombatInfo = {
    "opponent_id": int,
    "round_fought": int,             # Which round you fought them
    
    # Their exact board state during that combat
    "combat_board": List[{
        "champion_id": str,
        "position": (int, int),
        "star_level": int,
        "items": List[str],
        "starting_hp": float,
        "starting_mana": float,
    }],
    
    # Combat results
    "won": bool,                     # Did we win?
    "damage_dealt": int,
    "damage_taken": int,
    "units_alive_end": int,          # How many survived
    "combat_duration": float,        # How long combat lasted
    
    # Unit-level performance (theirs)
    "opponent_unit_stats": List[{
        "champion_id": str,
        "damage_dealt": float,
        "damage_taken": float,
        "healing_done": float,
        "cc_applied": float,
        "survived": bool,
    }],
}
```

#### Aggregated Opponent Tracking (Memory Across Rounds)
```python
OpponentMemory = List[{
    "player_id": int,
    
    # Historical tracking
    "scout_history": List[{
        "round": int,
        "board_snapshot": BoardState,
        "comp_type": str,
    }],
    
    # Combat history against this opponent
    "combat_history": List[{
        "round": int,
        "result": str,                # "win" or "loss"
        "their_board": BoardState,
        "damage": int,
    }],
    
    # Composition evolution
    "comp_transitions": List[{
        "round": int,
        "old_comp": str,
        "new_comp": str,              # Track pivots
    }],
    
    # Threat assessment (updated each round)
    "threat_level": float,           # 0.0 to 1.0 (how dangerous)
    "matchup_win_rate": float,       # Historical win rate vs them
    "likely_next_opponent": float,   # Probability of facing them next
}]
```

### Update Frequency
```python
# Pseudo-code for state updates
def update_opponent_states(game, round):
    for opponent in game.opponents:
        # Update public info EVERY round
        opponent.current_health = get_health(opponent)
        opponent.current_level = get_level(opponent)
        opponent.current_placement = get_placement(opponent)
        
        # Update scoutable info IF we scout this round
        if agent.should_scout(opponent):
            opponent.current_board = scout_board(opponent)
            opponent.active_traits = calculate_traits(opponent.current_board)
        
        # Update combat info IF we fight this round
        if opponent == game.current_opponent:
            opponent.combat_board = get_combat_board(opponent)
            opponent.combat_stats = get_combat_stats()
        
        # Update memory/history
        opponent.scout_history.append({
            "round": round,
            "board": opponent.current_board,
        })
        
        # Update threat assessment
        opponent.threat_level = calculate_threat(opponent)
    
    return opponent_states
```

This ensures the agent has **up-to-date information** about all opponents every round, enabling better decision-making (e.g., "Player 3 is weak, I can level aggressively" or "Player 5 has the same comp as me, I should pivot").

### 5. Set 16 Specific Features
```python
Set16Features = {
    # Portals (modify game start)
    "portal_type": str,              # e.g., "Poppy", "Twisted Fate", "Tahm Kench"
    "portal_effects": Dict,
    
    # Unlockables Progress
    "unlocked_champions": Set[str],  # Champions unlocked this game
    "unlock_quests": List[{
        "champion_id": str,
        "condition": str,
        "progress": float,
    }],
    
    # Combined Champions
    "combined_champion_states": List[{
        "champions": Tuple[str, str], # e.g., ("Lucian", "Senna")
        "active_champion": str,       # Which one is currently active
        "swap_cooldown": float,
    }],
}
```

### 6. Combat Result Features
```python
CombatResult = {
    "won": bool,
    "damage_dealt": int,
    "damage_taken": int,
    "units_alive": int,
    "opponent_units_killed": int,
    "time_to_win": float,            # How fast we won/lost
    
    # Unit-level combat stats
    "unit_performance": List[{
        "champion_id": str,
        "damage_dealt": float,
        "damage_taken": float,
        "healing_done": float,
        "cc_duration": float,
        "survived": bool,
    }],
}
```

### Encoding Strategy

#### Categorical Features
- **Champion IDs**: Use learned embeddings (256-512 dimensions)
  - Pre-train embeddings on champion stats, traits, abilities
  - Fine-tune during RL training
  - Share embeddings across sets (transfer learning)

- **Item IDs**: Learned embeddings (128-256 dimensions)
  - Encode item effects (AD, AP, HP, special effects)
  - Group similar items (e.g., all AP items cluster together)

- **Trait IDs**: Learned embeddings (128 dimensions)
  - Encode trait effects at different tiers

#### Positional Features
- **Hex Grid Encoding**: 
  - Use 7×4 spatial grid
  - Multi-channel representation:
    - Channel 1: Champion presence (0/1)
    - Channel 2: Champion cost (1-8)
    - Channel 3: Star level (1-3)
    - Channels 4-6: Item embeddings
    - Channels 7+: Trait encodings

#### Temporal Features
- **Stage/Round**: Cyclical encoding (sin/cos) to capture game progression
- **Streak Information**: Normalized (0-1) with sign for win/loss

---

## Action Space Design

### Action Categories

#### 1. Economy Actions
```python
EconomyActions = {
    "buy_xp": bool,                  # Spend 4 gold for 4 XP
    "reroll_shop": bool,             # Spend 2 gold to reroll
    "lock_shop": bool,               # Lock/unlock shop
    "hold_gold": bool,               # Do nothing (eco for interest)
}
```

#### 2. Shop Purchase Actions
```python
PurchaseActions = {
    "buy_champion": int,             # Shop slot index (0-4), -1 for none
    "sell_champion": int,            # Bench/board slot, -1 for none
}
```

#### 3. Board Management Actions
```python
BoardActions = {
    # Unit Positioning
    "move_unit": {
        "unit_id": int,              # Index of unit to move
        "target_position": (int, int),  # Target hex
    },
    
    # Bench <-> Board
    "swap_bench_board": {
        "bench_slot": int,           # -1 for none
        "board_position": (int, int), # or None
    },
}
```

#### 4. Itemization Actions
```python
ItemActions = {
    "combine_items": {
        "item1_id": int,             # Component 1
        "item2_id": int,             # Component 2
        "target_unit": int,          # Unit index
    },
    
    "move_item": {
        "item_id": int,
        "from_unit": int,
        "to_unit": int,
    },
}
```

#### 5. Augment Selection
```python
AugmentActions = {
    "select_augment": int,           # Index (0-2) of offered augments
}
```

#### 6. Set 16: Unlockable Actions
```python
UnlockableActions = {
    "prioritize_unlock": str,        # Champion ID to work towards
    "unlock_strategy": str,          # "aggressive", "passive", "conditional"
}
```

#### 7. Set 16: Portal Actions
```python
PortalActions = {
    "portal_choice": int,            # If portal offers choices
}
```

### Action Space Implementation

**Approach**: Hierarchical action space with action masking

```python
# Level 1: Action Type
ActionType = [
    "economy",      # 0
    "purchase",     # 1
    "position",     # 2
    "item",         # 3
    "augment",      # 4
    "unlock",       # 5 (Set 16+)
]

# Level 2: Specific Action (depends on ActionType)
# Use action masking to disable invalid actions
# E.g., can't buy XP if gold < 4, can't buy from empty shop slot
```

**Action Masking**: Critical for sample efficiency
- Mask invalid actions (e.g., can't buy with insufficient gold)
- Reduces action space from ~10,000 to ~50-200 valid actions per step
- Implemented as binary mask over action logits

### Action Abstraction Levels

**Micro Actions** (per decision point):
- Individual champion purchases
- Single item placements
- Unit movements

**Macro Actions** (high-level strategies):
- "Roll down to find carry"
- "Level to 8 and stabilize"
- "Sell board and pivot to [comp]"
- Use options framework or hierarchical RL

---

## Reward Function

### Immediate Rewards

#### Combat Rewards
```python
combat_reward = {
    "win_reward": +1.0,
    "loss_penalty": -0.5,
    "damage_dealt_bonus": damage_dealt * 0.01,  # Encourage aggressive wins
    "health_preservation": (hp_after / hp_before) * 0.2,  # Don't take unnecessary damage
}
```

#### Economy Rewards
```python
economy_reward = {
    "interest_bonus": interest_gold * 0.05,     # Reward good econ
    "efficient_spending": -abs(gold - 50) * 0.02,  # Penalty for hoarding/overspending
}
```

#### Synergy Rewards
```python
synergy_reward = {
    "trait_activation": sum(trait_tier * trait_strength),  # Reward active traits
    "power_spike_timing": +0.5 if (level == 8 and stage == 4),  # Reward hitting key timings
}
```

### Shaped Rewards (to encourage learning)

```python
shaped_reward = {
    # Milestone rewards
    "top_4_bonus": +5.0 if placement <= 4 else 0,
    "win_bonus": +10.0 if placement == 1 else 0,
    
    # Progression rewards (per round)
    "hp_differential": (my_hp - avg_opponent_hp) * 0.01,
    "board_strength": estimated_board_power * 0.05,
    
    # Strategic rewards
    "good_pivot_timing": +1.0,  # If pivoting comp at right time
    "3_star_carry": +2.0,       # Successfully 3-starring key unit
    "perfect_items": +0.5,      # BiS items on carry
}
```

### Terminal Rewards

```python
terminal_reward = {
    1: +100,   # 1st place
    2: +50,    # 2nd place
    3: +25,    # 3rd place
    4: +10,    # 4th place
    5: -10,    # 5th place
    6: -25,    # 6th place
    7: -50,    # 7th place
    8: -100,   # 8th place
}
```

### Reward Balancing
- **Early game**: Focus on economy and board strength
- **Mid game**: Emphasize synergies and power spikes
- **Late game**: Maximize placement and combat wins

### Curriculum Learning Rewards
- Start with simpler reward (just placement)
- Gradually add shaped rewards as agent improves
- Anneal shaped rewards over training to avoid reward hacking

---

## Model Architecture

### Option 1: Transformer-based Architecture

```python
class TFTTransformer(nn.Module):
    def __init__(self):
        # Input Processing
        self.champion_embedding = nn.Embedding(num_champions, 256)
        self.item_embedding = nn.Embedding(num_items, 128)
        self.trait_embedding = nn.Embedding(num_traits, 128)
        
        # Spatial Encoding for Board
        self.position_encoding = PositionalEncoding2D(7, 4)
        
        # Board Encoder (Transformer)
        self.board_encoder = TransformerEncoder(
            d_model=512,
            nhead=8,
            num_layers=6,
            dim_feedforward=2048
        )
        
        # Shop/Bench Encoder
        self.shop_encoder = TransformerEncoder(
            d_model=256,
            nhead=4,
            num_layers=3
        )
        
        # Global State Encoder
        self.global_encoder = nn.Sequential(
            nn.Linear(global_dim, 256),
            nn.ReLU(),
            nn.Linear(256, 512)
        )
        
        # Cross-Attention (board, shop, global)
        self.cross_attention = MultiHeadAttention(...)
        
        # Policy Head (actor)
        self.policy_head = nn.Sequential(
            nn.Linear(512, 1024),
            nn.ReLU(),
            nn.Linear(1024, action_dim)
        )
        
        # Value Head (critic)
        self.value_head = nn.Sequential(
            nn.Linear(512, 256),
            nn.ReLU(),
            nn.Linear(256, 1)
        )
    
    def forward(self, state):
        # Encode board, shop, global state
        board_features = self.encode_board(state.board)
        shop_features = self.encode_shop(state.shop)
        global_features = self.global_encoder(state.global_state)
        
        # Combine via cross-attention
        combined = self.cross_attention(
            query=global_features,
            key=torch.cat([board_features, shop_features], dim=1),
            value=torch.cat([board_features, shop_features], dim=1)
        )
        
        # Output policy and value
        action_logits = self.policy_head(combined)
        value = self.value_head(combined)
        
        return action_logits, value
```

### Option 2: Graph Neural Network (GNN)

```python
class TFTGraphNetwork(nn.Module):
    """
    Represent game state as a graph:
    - Nodes: Champions (on board, bench, shop, opponents)
    - Edges: Traits, positional adjacency, item relationships
    """
    def __init__(self):
        self.node_encoder = GCNConv(in_channels, hidden_channels)
        self.edge_encoder = EdgeConv(...)
        
        # Graph Attention Network
        self.gat_layers = nn.ModuleList([
            GATConv(hidden_channels, hidden_channels, heads=4)
            for _ in range(4)
        ])
        
        # Global pooling
        self.global_pool = GlobalAttentionPooling(...)
        
        # Policy and Value heads (same as above)
```

### Option 3: Hybrid CNN + Transformer

```python
class TFTHybrid(nn.Module):
    """
    - Use CNN for spatial board representation
    - Use Transformer for sequential shop/bench
    - Combine with global state
    """
    def __init__(self):
        # Board CNN (treat 7x4 hex grid as image)
        self.board_cnn = nn.Sequential(
            nn.Conv2d(in_channels, 64, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.Conv2d(64, 128, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.AdaptiveAvgPool2d((1, 1))
        )
        
        # Shop Transformer (sequence of 5 champions)
        self.shop_transformer = TransformerEncoder(...)
        
        # Fusion layer
        self.fusion = nn.Linear(512, 1024)
```

### Recommended Architecture
**Start with Transformer** (Option 1):
- Good at capturing relationships (traits, synergies)
- Flexible for variable-length inputs (different board sizes)
- Easier to add set-specific features via attention

**Consider GNN** for:
- Explicit modeling of champion-trait-item relationships
- Better interpretability (can visualize attention on graph)

---

## Training Pipeline

### 1. Self-Play Training Loop

```
Initialize policy π_θ randomly

For episode = 1 to N:
    # Play a game
    game_state = initialize_game()
    trajectory = []
    
    while not game_over:
        # Planning phase
        action, log_prob, value = π_θ.sample_action(game_state)
        
        # Apply action masking
        valid_actions = get_valid_actions(game_state)
        masked_action = apply_mask(action, valid_actions)
        
        # Execute action
        next_state, reward, done = env.step(masked_action)
        
        # Store transition
        trajectory.append((game_state, masked_action, reward, log_prob, value))
        
        # Combat phase (simulated or via TFT API)
        if round_combat:
            combat_result = simulate_combat(game_state)
            reward += compute_combat_reward(combat_result)
        
        game_state = next_state
    
    # Compute returns (GAE or n-step)
    returns = compute_returns(trajectory, γ=0.99, λ=0.95)
    
    # Update policy (PPO)
    update_policy_ppo(π_θ, trajectory, returns, clip_ratio=0.2)
    
    # Update opponent pool (every K episodes)
    if episode % K == 0:
        opponent_pool.add(copy(π_θ))
```

### 2. RL Algorithm: Proximal Policy Optimization (PPO)

**Why PPO?**
- Stable for complex, high-dimensional spaces
- Sample-efficient (reuse data via mini-batches)
- Good balance between exploration and exploitation

**PPO Update**:
```python
def ppo_update(policy, old_policy, trajectories, clip_ratio=0.2):
    for epoch in range(K_epochs):
        for batch in get_batches(trajectories):
            # Compute ratio
            new_log_prob = policy.log_prob(batch.actions | batch.states)
            old_log_prob = old_policy.log_prob(batch.actions | batch.states)
            ratio = torch.exp(new_log_prob - old_log_prob)
            
            # Compute advantages
            advantages = batch.returns - batch.values
            advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)
            
            # Clipped objective
            surr1 = ratio * advantages
            surr2 = torch.clamp(ratio, 1 - clip_ratio, 1 + clip_ratio) * advantages
            policy_loss = -torch.min(surr1, surr2).mean()
            
            # Value loss
            value_loss = F.mse_loss(policy.value(batch.states), batch.returns)
            
            # Entropy bonus (for exploration)
            entropy = policy.entropy(batch.states).mean()
            
            # Total loss
            loss = policy_loss + 0.5 * value_loss - 0.01 * entropy
            
            # Backprop
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
```

### 3. Training Environment

**Option A: TFT Game Simulator**
- Build a Python simulator of TFT mechanics
  - Champion stats, abilities, combat logic
  - Item effects, trait bonuses
  - Shop probabilities, carousel logic
- **Pros**: Fast, parallelizable, no API limits
- **Cons**: Requires extensive game knowledge, difficult to keep updated

**Option B: API Integration (Riot API)**
- Use Riot's TFT API for real game data
- Train via behavioral cloning → RL fine-tuning
- **Pros**: Real game data, accurate mechanics
- **Cons**: API rate limits, slower training

**Option C: Hybrid Approach** (Recommended)
- Use simulator for early training (fast iterations)
- Fine-tune on real games via API
- Use human game data for imitation learning warmstart

### 4. Parallelization Strategy

```python
# Distributed training with Ray
import ray

@ray.remote
class TFTWorker:
    def __init__(self, policy):
        self.env = TFTSimulator()
        self.policy = policy
    
    def rollout(self, num_episodes):
        trajectories = []
        for _ in range(num_episodes):
            trajectory = self.play_game()
            trajectories.append(trajectory)
        return trajectories

# Main training loop
num_workers = 64
workers = [TFTWorker.remote(policy) for _ in range(num_workers)]

for iteration in range(num_iterations):
    # Parallel rollouts
    trajectory_futures = [worker.rollout.remote(16) for worker in workers]
    all_trajectories = ray.get(trajectory_futures)
    
    # Aggregate and update
    policy.update(all_trajectories)
```

### 5. Opponent Modeling

**Population-Based Training**:
- Maintain a pool of opponent policies at different skill levels
- Sample opponents from pool during training
- Prevents overfitting to a single strategy

```python
class OpponentPool:
    def __init__(self):
        self.policies = []
        self.win_rates = []
    
    def add_policy(self, policy):
        self.policies.append(copy.deepcopy(policy))
    
    def sample_opponents(self, num_opponents=7):
        # Sample diverse opponents
        # - Mix of strong (recent) and weak (old) policies
        # - Weighted by diversity (avoid all same strategy)
        return random.sample(self.policies, num_opponents)
```

### 6. Curriculum Learning

```python
curriculum_stages = [
    {
        "name": "Early Game",
        "rounds": [1, 2, 3],
        "focus": "Economy management, unit acquisition",
        "reward_weight": {"economy": 1.0, "combat": 0.5},
    },
    {
        "name": "Mid Game",
        "rounds": [4, 5],
        "focus": "Leveling, trait synergies, itemization",
        "reward_weight": {"economy": 0.5, "combat": 1.0, "synergy": 1.0},
    },
    {
        "name": "Late Game",
        "rounds": [6, 7],
        "focus": "Positioning, final comp optimization",
        "reward_weight": {"combat": 1.0, "positioning": 1.0},
    },
    {
        "name": "Full Game",
        "rounds": [1, 7],
        "focus": "End-to-end performance",
        "reward_weight": {"placement": 1.0},
    },
]

# Train on each stage sequentially
for stage in curriculum_stages:
    env.set_curriculum(stage)
    train_n_iterations(stage.num_iterations)
```

---

## Evaluation & Validation

### 1. Performance Metrics

**Primary Metrics**:
- **Average Placement**: Target < 4.0 (top 4 consistency)
- **Win Rate**: % of 1st place finishes
- **Top 4 Rate**: % of top 4 finishes (target > 50%)

**Secondary Metrics**:
- **Economy Efficiency**: Gold spent vs. interest earned
- **Combat Win Rate**: % of rounds won
- **Item Optimization Score**: % of BiS items on carries
- **Trait Activation Rate**: % of active synergies
- **Strategic Diversity**: Number of different comps played

### 2. Evaluation Protocol

```python
def evaluate_agent(policy, num_games=100):
    results = []
    
    for game_id in range(num_games):
        # Play against 7 human-like bots or real players
        game = TFTGame(opponents=get_evaluation_opponents())
        
        placement, stats = policy.play_game(game)
        
        results.append({
            "placement": placement,
            "gold_efficiency": stats.gold_efficiency,
            "combat_wins": stats.combat_wins,
            "comp_played": stats.final_comp,
            "hp_at_end": stats.final_hp,
        })
    
    # Aggregate metrics
    avg_placement = np.mean([r["placement"] for r in results])
    top4_rate = np.mean([r["placement"] <= 4 for r in results])
    win_rate = np.mean([r["placement"] == 1 for r in results])
    
    return {
        "avg_placement": avg_placement,
        "top4_rate": top4_rate,
        "win_rate": win_rate,
        "results": results,
    }
```

### 3. Ablation Studies

Test individual components:
- **Without item optimization**: How much does BiS items matter?
- **Without positioning**: Random positioning vs. learned
- **Without opponent modeling**: Self-play only vs. diverse opponents
- **Without reward shaping**: Sparse rewards only

### 4. Human Baseline Comparison

- Compare against human replays at different skill levels:
  - **Iron/Bronze**: Beginner
  - **Gold/Platinum**: Intermediate
  - **Diamond/Master**: Advanced
  - **Grandmaster/Challenger**: Expert

### 5. Interpretability Analysis

**Attention Visualization**:
- What units does the model focus on when making decisions?
- Which traits are most influential?

**Decision Explainability**:
- Log reasoning for key decisions (e.g., "Leveling to 8 because strong board")
- Use SHAP values to explain action choices

---

## Set-Agnostic & Patch-Adaptive Design

### 1. Set-Agnostic Architecture

**Key Idea**: Separate game-specific data from model architecture

```python
class SetAgnosticTFTAgent:
    def __init__(self):
        # Core model (set-independent)
        self.encoder = TransformerEncoder(...)
        self.policy_head = PolicyHead(...)
        self.value_head = ValueHead(...)
        
        # Set-specific embedding tables (swappable)
        self.champion_embeddings = {}  # Per-set champion embeddings
        self.item_embeddings = {}      # Per-set item embeddings
        self.trait_embeddings = {}     # Per-set trait embeddings
        
    def load_set_data(self, set_id):
        """Load embeddings and data for a specific set"""
        self.current_set = set_id
        self.champions = load_champions(set_id)
        self.items = load_items(set_id)
        self.traits = load_traits(set_id)
        
        # Initialize embeddings (or load pre-trained)
        if set_id not in self.champion_embeddings:
            self.champion_embeddings[set_id] = nn.Embedding(
                len(self.champions), 256
            )
```

### 2. Transfer Learning Between Sets

**Approach 1: Fine-tuning**
1. Train on Set 16 to convergence
2. When Set 17 releases:
   - Freeze core encoder layers
   - Only update embedding tables and policy head
   - Fine-tune for N games (much faster than from scratch)

**Approach 2: Meta-Learning (MAML)**
- Train agent to quickly adapt to new sets
- Inner loop: Adapt to a specific set
- Outer loop: Optimize for fast adaptation

**Approach 3: Multi-Task Learning**
- Train on multiple sets simultaneously
- Shared encoder, set-specific heads
- Encourages learning general TFT principles

```python
# Multi-task training
for batch in dataloader:
    set_id = batch.set_id
    
    # Forward pass with set-specific embeddings
    embeddings = self.champion_embeddings[set_id]
    features = self.encoder(batch.state, embeddings)
    
    # Set-specific policy head
    policy_logits = self.policy_heads[set_id](features)
    
    # Shared value head
    value = self.value_head(features)
    
    # Compute loss and backprop
    loss = compute_loss(policy_logits, value, batch)
    loss.backward()
```

### 3. Patch Adaptation

**Problem**: Patches change champion/item/augment balance every 2-4 weeks

**Solution 1: Rapid Fine-tuning**
- Detect patch via metadata
- Fine-tune embeddings on new patch data for 1-2 days
- Use human games from new patch as supervised learning signal

**Solution 2: Meta-Embeddings**
- Learn a "meta-embedding" function that maps champion stats → embedding
- When patch changes stats, embedding auto-updates

```python
def meta_embedding(champion_stats):
    """
    Input: Champion stats (HP, AD, AS, etc.)
    Output: 256-dim embedding
    """
    return nn.Sequential(
        nn.Linear(stats_dim, 128),
        nn.ReLU(),
        nn.Linear(128, 256)
    )(champion_stats)

# On patch change
new_stats = load_champion_stats(patch="14.23")
updated_embeddings = meta_embedding(new_stats)
```

**Solution 3: Strategy Database**
- Maintain a database of successful comps per patch
- Use retrieval-augmented generation (RAG) to adapt strategy

```python
class StrategyDatabase:
    def __init__(self):
        self.strategies = {}  # patch_id -> List[comp_strategy]
    
    def update_from_games(self, patch_id, games):
        # Extract successful comps from games
        successful_comps = extract_top4_comps(games)
        self.strategies[patch_id] = successful_comps
    
    def retrieve_strategy(self, game_state, patch_id):
        # Find similar game states in database
        similar_states = self.find_similar(game_state, self.strategies[patch_id])
        return most_successful(similar_states)
```

### 4. Scalability to All Sets

**Data Pipeline**:
```python
# Automated data ingestion
class TFTDataPipeline:
    def monitor_new_sets(self):
        # Check for new sets via Riot API
        if new_set_detected():
            self.crawl_new_set_data()
            self.update_embeddings()
            self.trigger_fine_tuning()
    
    def crawl_new_set_data(self):
        # Crawl champions, items, traits (like you already have)
        champions = crawl_champions()
        items = crawl_items()
        traits = crawl_traits()
        augments = crawl_augments()
        portals = crawl_portals()  # Set 16+
        
        # Store in database
        self.db.save_set_data(champions, items, traits, augments, portals)
    
    def update_embeddings(self):
        # Initialize new embedding tables
        # Transfer knowledge from previous sets
        self.agent.initialize_new_set_embeddings(
            previous_set="Set16",
            new_set="Set17"
        )
```

---

## Infrastructure & Scalability

### 1. Training Infrastructure

**Hardware Requirements**:
- **Minimum**: 1x GPU (RTX 3090, A100), 32 GB RAM, 8 CPU cores
- **Recommended**: 4-8x GPUs, 128 GB RAM, 64 CPU cores
- **Large-scale**: Kubernetes cluster with 50+ GPU nodes

**Software Stack**:
```
- Environment: TFT Simulator (Python)
- RL Framework: Ray RLlib, Stable-Baselines3, or custom PPO
- Model Framework: PyTorch
- Distributed Training: Ray, Horovod
- Experiment Tracking: Weights & Biases, TensorBoard
- Deployment: Docker, Kubernetes
```

### 2. Simulation Environment

**Key Components**:
```python
class TFTSimulator:
    def __init__(self):
        self.game_data = load_game_data()  # Champions, items, traits
        self.combat_engine = CombatEngine()
        self.shop_manager = ShopManager()
        self.trait_calculator = TraitCalculator()
    
    def reset(self):
        # Initialize new game
        self.stage = 1
        self.round = 1
        self.players = [Player() for _ in range(8)]
        return self.get_state()
    
    def step(self, player_id, action):
        # Execute action
        self.execute_action(player_id, action)
        
        # If all players ready, run combat
        if self.all_ready():
            combat_results = self.run_combat_round()
            rewards = self.compute_rewards(combat_results)
            self.update_game_state()
        
        return self.get_state(), rewards, self.is_done()
    
    def run_combat_round(self):
        # Simulate 8-player round-robin or bracket combat
        matchups = self.generate_matchups()
        results = []
        
        for p1, p2 in matchups:
            winner, stats = self.combat_engine.simulate(
                board1=self.players[p1].board,
                board2=self.players[p2].board
            )
            results.append((p1, p2, winner, stats))
        
        return results
```

**Combat Engine**:
- Implement TFT combat mechanics:
  - Turn-based attacks
  - Ability casting (mana system)
  - Positioning & targeting
  - Crowd control, healing, shields
  - Trait effects

**Fidelity Levels**:
- **Simplified** (Phase 1): Deterministic combat, no RNG
- **Medium** (Phase 2): Add RNG (crit, dodge), basic abilities
- **High** (Phase 3): Full ability simulations, exact TFT rules

### 3. Data Storage

**Game Logs**:
- Store all training games for analysis
- Schema:
  ```json
  {
    "game_id": "uuid",
    "set_id": "Set16",
    "patch": "14.23",
    "players": [...],
    "rounds": [
      {
        "round_id": 1,
        "actions": [...],
        "board_states": [...],
        "combat_results": {...},
      }
    ],
    "final_placements": [...]
  }
  ```

**Database**: PostgreSQL or MongoDB for structured queries

**Replay System**:
- Store trajectories for imitation learning
- Use top-performing games as training data

### 4. Monitoring & Debugging

**Metrics to Track**:
- Training loss (policy, value, entropy)
- Average reward per episode
- Placement distribution
- Action distribution (are we exploring?)
- Gradient norms (detect instability)

**Alerts**:
- Policy collapse (low entropy)
- Reward hacking (unintended behavior)
- Training divergence (NaN gradients)

---

## Phase-by-Phase Implementation Plan

### Phase 1: Foundation (Months 1-2)

**Goal**: Build basic RL agent that can play simplified TFT

**Tasks**:
1. **Data Preparation**:
   - [x] Crawl Set 16 champions, items, traits, augments
   - [ ] Crawl portals, unlockable conditions
   - [ ] Parse and structure data into usable format

2. **Environment Setup**:
   - [ ] Build simplified TFT simulator:
     - Basic shop logic (purchase, reroll, lock)
     - Simple economy (gold, interest, leveling)
     - Deterministic combat (based on board power)
   - [ ] Define state representation (start with global + board)
   - [ ] Define action space (economy + purchase only)

3. **Baseline Model**:
   - [ ] Implement simple MLP policy:
     ```python
     class SimpleTFTPolicy(nn.Module):
         def __init__(self):
             self.fc = nn.Sequential(
                 nn.Linear(state_dim, 256),
                 nn.ReLU(),
                 nn.Linear(256, action_dim)
             )
     ```
   - [ ] Train with PPO on simplified environment
   - [ ] Target: Achieve top 4 in 30% of games (8 random bots)

**Deliverables**:
- Working TFT simulator (simplified)
- Baseline RL agent
- Training pipeline (local, single GPU)

---

### Phase 2: Advanced Mechanics (Months 3-4)

**Goal**: Add positioning, itemization, and realistic combat

**Tasks**:
1. **Enhanced Simulator**:
   - [ ] Implement hex grid positioning
   - [ ] Add item combinations and effects
   - [ ] Implement combat engine with abilities:
     - Attack damage calculation
     - Ability power scaling
     - Mana system
     - Basic CC (stun, knockback)

2. **Improved Model**:
   - [ ] Upgrade to Transformer architecture
   - [ ] Add learned embeddings for champions/items/traits
   - [ ] Implement action masking

3. **Training Enhancements**:
   - [ ] Curriculum learning (early → mid → late game)
   - [ ] Opponent pool (population-based training)
   - [ ] Reward shaping (synergies, itemization)

**Deliverables**:
- Realistic combat simulator
- Transformer-based agent
- Top 4 rate > 50%

---

### Phase 3: Set 16 Mastery (Months 5-6)

**Goal**: Fully master Set 16 mechanics (unlockables, portals, augments)

**Tasks**:
1. **Set 16 Features**:
   - [ ] Implement unlockable champions system
   - [ ] Implement portals (Poppy, TF, Tahm, Zoe, etc.)
   - [ ] Augment selection logic
   - [ ] Combined champions (Lucian & Senna, etc.)

2. **Model Refinement**:
   - [ ] Add set-specific embedding layers
   - [ ] Fine-tune on human game data (imitation learning)
   - [ ] Optimize positioning with RL

3. **Evaluation**:
   - [ ] Test against human players (API integration)
   - [ ] Benchmark vs. Diamond+ players
   - [ ] Analyze failure cases and iterate

**Deliverables**:
- Full Set 16 agent
- Top 4 rate > 60%, avg placement < 3.5
- Interpretable decision logs

---

### Phase 4: Generalization (Months 7-8)

**Goal**: Extend to all sets and adapt to patches

**Tasks**:
1. **Set-Agnostic Design**:
   - [ ] Refactor model to use dynamic embeddings
   - [ ] Train on multiple sets (Set 14, 15, 16) simultaneously
   - [ ] Implement transfer learning pipeline

2. **Patch Adaptation**:
   - [ ] Build automated patch detection system
   - [ ] Implement rapid fine-tuning (1-day turnaround)
   - [ ] Test on historical patches (retroactive evaluation)

3. **Meta-Learning**:
   - [ ] Experiment with MAML for fast adaptation
   - [ ] Build strategy database (RAG for comps)

**Deliverables**:
- Set- and patch-agnostic agent
- Automated retraining pipeline
- Documentation for adding new sets

---

### Phase 5: Deployment & Optimization (Months 9-10)

**Goal**: Deploy agent for real-time play and optimize performance

**Tasks**:
1. **API Integration**:
   - [ ] Integrate with TFT game client (if possible)
   - [ ] Build web interface for monitoring
   - [ ] Real-time decision making (< 1 second latency)

2. **Model Optimization**:
   - [ ] Quantization (FP16, INT8) for faster inference
   - [ ] Model pruning (remove unnecessary parameters)
   - [ ] ONNX export for deployment

3. **Scalability**:
   - [ ] Deploy on cloud (AWS, GCP, Azure)
   - [ ] Kubernetes orchestration for distributed training
   - [ ] CI/CD pipeline for auto-retraining

**Deliverables**:
- Production-ready agent
- Cloud deployment
- Auto-update system for patches

---

### Phase 6: Research Extensions (Months 11+)

**Optional Advanced Features**:

1. **Multi-Agent Collaboration**:
   - Train a team of 8 agents that learn to counter each other
   - Adversarial training for robustness

2. **Explainable AI**:
   - Build UI to visualize agent's decision-making
   - Generate natural language explanations ("I'm rolling down to find Jinx")

3. **Human-in-the-Loop**:
   - Interactive mode where human can override agent decisions
   - Learn from human corrections (active learning)

4. **Meta-Game Analysis**:
   - Discover new S-tier comps automatically
   - Predict meta shifts based on patch notes

---

## Appendix: Technical Details

### A. Hex Grid Coordinate System

TFT uses a hexagonal grid (7 columns × 4 rows). Coordinate conversion:

```python
# Hex to pixel (for visualization)
def hex_to_pixel(col, row):
    x = col * hex_width + (row % 2) * hex_width / 2
    y = row * hex_height
    return (x, y)

# Adjacency (6 neighbors in hex grid)
def get_neighbors(col, row):
    if row % 2 == 0:
        # Even row
        neighbors = [
            (col-1, row), (col+1, row),
            (col-1, row-1), (col, row-1),
            (col-1, row+1), (col, row+1),
        ]
    else:
        # Odd row
        neighbors = [
            (col-1, row), (col+1, row),
            (col, row-1), (col+1, row-1),
            (col, row+1), (col+1, row+1),
        ]
    return [(c, r) for c, r in neighbors if 0 <= c < 7 and 0 <= r < 4]
```

### B. Combat Simulation Pseudocode

```python
def simulate_combat(board1, board2, max_duration=30):
    # Initialize units
    units1 = initialize_units(board1)
    units2 = initialize_units(board2)
    
    time = 0
    while time < max_duration:
        # Update all units (attacks, mana, abilities)
        for unit in units1 + units2:
            unit.update(dt=0.1)
            
            # Check if ready to attack
            if unit.attack_ready():
                target = unit.find_target(units2 if unit in units1 else units1)
                damage = unit.calculate_damage(target)
                target.take_damage(damage)
            
            # Check if ready to cast
            if unit.mana >= unit.max_mana:
                unit.cast_ability(units1, units2)
                unit.mana = 0
        
        # Remove dead units
        units1 = [u for u in units1 if u.hp > 0]
        units2 = [u for u in units2 if u.hp > 0]
        
        # Check win condition
        if not units1 or not units2:
            break
        
        time += 0.1
    
    # Determine winner
    if units1 and not units2:
        return "player1", len(units1)
    elif units2 and not units1:
        return "player2", len(units2)
    else:
        return "draw", 0
```

### C. PPO Hyperparameters (Recommended Starting Point)

```python
ppo_config = {
    "learning_rate": 3e-4,
    "gamma": 0.99,              # Discount factor
    "lambda_": 0.95,            # GAE parameter
    "clip_ratio": 0.2,          # PPO clip
    "entropy_coef": 0.01,       # Exploration bonus
    "value_coef": 0.5,          # Value loss weight
    "max_grad_norm": 0.5,       # Gradient clipping
    "num_epochs": 10,           # Epochs per update
    "batch_size": 256,
    "num_workers": 64,          # Parallel envs
}
```

### D. Estimated Training Costs

**Assumptions**:
- 1 game = 25 rounds = ~5 minutes (real-time) = ~10 seconds (simulated)
- Need ~100K games to reach competence
- Need ~1M games for mastery

**Time Estimates**:
- Local (1 GPU): 100K games × 10s = 11 days
- Distributed (64 GPUs): 100K games / 64 = 4 hours
- Cloud cost (AWS p3.2xlarge): $3/hr × 64 × 4 = ~$768

**Optimization**:
- Use vectorized environments (run 8 games in parallel per GPU)
- Reduce to ~1 hour distributed, or ~$200 cloud cost

---

## Conclusion

This pipeline provides a comprehensive roadmap for building a TFT RL agent that can:
1. Master Set 16 gameplay
2. Generalize to all future sets
3. Adapt to patch changes rapidly

**Key Success Factors**:
- **Good Simulator**: Accurate TFT mechanics → better training
- **Smart Representations**: Embeddings for champions/items/traits → transfer learning
- **Diverse Training**: Opponent pool, curriculum learning → robustness
- **Continuous Improvement**: Auto-retraining on new patches → stay competitive

**Next Steps**:
1. Start with Phase 1 (simplified simulator)
2. Validate on basic metrics (top 4 rate)
3. Iterate rapidly and expand to full game

Good luck building your TFT AI! 🎮🤖
