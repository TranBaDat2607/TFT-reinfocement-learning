# TFT Set 16 Data Crawling Scripts

This directory contains scripts to crawl and collect TFT Set 16 data from various sources.

## Requirements

Install required Python packages:

```bash
pip install requests beautifulsoup4
```

## Available Scripts

### 1. Champions Data (Recommended)

```bash
python get_champions_detailed.py
```

Fetches champion data from Community Dragon API and merges unlock conditions from op.gg.

Output: `../data/set16/champions.json`

Contains:
- Champion stats, abilities, traits
- Unlock conditions for unlockable champions (40 champions)
- Cost, role, and other metadata

### 2. Unlock Conditions

```bash
python get_unlock_conditions.py
```

Scrapes unlock conditions directly from op.gg.

Output: `../data/set16/unlock_conditions.json`

Note: This is automatically merged by `get_champions_detailed.py`, so you only need to run this separately if you want the standalone unlock data.

### 3. Items Data

```bash
python get_items_detailed.py
```

Fetches item data from Community Dragon API.

Output: `../data/set16/items.json`

### 4. Traits Data

```bash
python get_traits_detailed.py
```

Fetches trait/synergy data from Community Dragon API.

Output: `../data/set16/traits.json`

### 5. Augments Data

```bash
python get_augments_detailed.py
```

Fetches augment data from Community Dragon API.

Output: `../data/set16/augments.json`

### 6. Portals Data

```bash
python get_portals_detailed.py
```

Fetches portal data from Community Dragon API.

Output: `../data/set16/portals.json`

## Quick Start

To get all essential data for Set 16:

```bash
python get_champions_detailed.py
python get_items_detailed.py
python get_traits_detailed.py
python get_augments_detailed.py
python get_portals_detailed.py
```

All output files will be saved to `../data/set16/`

## Data Structure

### Champions JSON

Each champion has:
- `name`: Champion name
- `cost`: Gold cost (1-8)
- `ability`: Ability description and stats
- `stats`: HP, armor, damage, mana, etc.
- `traits`: List of trait names
- `role`: Champion role (e.g., "ADCaster", "Tank")
- `unlock_conditions`: Unlock requirements (null for regular champions)
  - `conditions`: List of unlock requirement strings
  - `tier`: Champion tier
  - `condition_count`: Number of conditions

### Unlock Conditions Structure

For unlockable champions, the `unlock_conditions` field contains:

```json
{
  "conditions": ["Condition description"],
  "tier": "5",
  "condition_count": 1
}
```

For regular champions: `"unlock_conditions": null`

## Notes

- All data is fetched from Community Dragon (cdragon) API
- Unlock conditions are scraped from op.gg
- Data is saved in JSON format with UTF-8 encoding
- Scripts will create the `../data/set16/` directory automatically if it doesn't exist
