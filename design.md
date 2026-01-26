Game Loop:
├── Planning Phase
│   ├── Shop Actions (buy, reroll, lock)
│   ├── Board Actions (move, sell)
│   └── Economy Actions (buy XP, hold gold)
├── Combat Phase
│   ├── Auto-resolve combat
│   └── Calculate damage
└── Transition Phase
    ├── Update gold/XP
    ├── Refresh shop
    └── Check game over