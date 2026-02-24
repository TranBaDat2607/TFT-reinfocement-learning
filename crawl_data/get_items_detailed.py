import requests
import json
import os
import re


# ──────────────────────────────────────────────────────────────────────────────
# Keyword / path exclusion lists
# ──────────────────────────────────────────────────────────────────────────────

# apiName substrings that disqualify an entry immediately
_EXCL_API_KEYWORDS = [
    'Augment',          # augments (all variants)
    'TeamupAugment',
    'Grant',            # GrantOrbs*, GrantOrnn*, GrantRadiant* (loot bundles)
    'Carousel',         # CarouselOfChaos_* novelty items
    'CarouselOfChaos',
    'Selector',         # FreljordSelector and other trait-event selectors
    'SystemItem',       # internal engine objects
    'Portal',           # portal objects
    'Unlock',           # unlock-condition tokens
]

# icon path substrings that disqualify an entry
_EXCL_ICON_PATHS = [
    '/Augments/',               # augment icons
    'Characters/',              # champion portrait used as icon (e.g. Ornn anvil)
    'Particles/TFT/Item_Icons/TFT16/',  # Set-16 trait-event selector icons
    'TFT_CT/',                  # Choncc's trophy / CT meta items
    '/CT/',
    'Pairs/Assist',             # loot-orb carousel icons
]


def is_equippable_item(item: dict) -> bool:
    """
    Return True only for items that can actually be equipped on a champion:
      - Standard components       (TFT_Item_BFSword, TFT_Item_ChainVest …)
      - Completed / crafted items (TFT_Item_InfinityEdge …)
      - Artifact / Ornn items     (TFT_Item_Artifact_*)
      - Support items             (TFT_Item_Support*)
      - Corrupted / dark items    (TFT_Item_Corrupted*)
      - Set-16 trait emblems      (TFT16_Item_*EmblemItem)

    Everything else is excluded: augments, loot orbs, grant-effect tokens,
    carousel novelties, champion/trait buffs, portal objects, etc.
    """
    api_name  = item.get('apiName', '')
    icon_path = item.get('icon',    '') or ''

    # 1. Keyword exclusions on apiName
    if any(kw in api_name for kw in _EXCL_API_KEYWORDS):
        return False

    # 2. Icon-path exclusions
    if any(p in icon_path for p in _EXCL_ICON_PATHS):
        return False

    # 3. Must live in the game's real Items asset folder
    #    e.g.  ASSETS/Maps/TFT/Icons/Items/Hexcore/TFT_Item_BFSword.TFT_Set13.tex
    #    Emblems live elsewhere but have a clear apiName pattern.
    in_items_folder = '/Items/' in icon_path
    is_emblem       = api_name.startswith('TFT16_Item_') and 'EmblemItem' in api_name

    if not (in_items_folder or is_emblem):
        return False

    # 4. apiName must match a known equippable prefix
    if not re.match(r'^(TFT_Item_|TFT16_Item_\w+EmblemItem)', api_name):
        return False

    return True


def get_community_dragon_data() -> dict:
    """Fetch the full TFT data blob from Community Dragon."""
    url = "https://raw.communitydragon.org/latest/cdragon/tft/en_us.json"
    response = requests.get(url)
    response.raise_for_status()
    return response.json()


def extract_equippable_items(cdragon_data: dict) -> dict:
    """
    Filter the raw Community Dragon items array down to only the items that
    a player can equip on a champion in Set 16:

      1. Standard components      — BF Sword, Chain Vest, Recurve Bow …
      2. Completed (crafted) items — Infinity Edge, Warmog's Armor …
      3. Artifact / Ornn items    — Zz'Rot Portal, Deathfire Grasp …
      4. Support items            — Knight's Vow, Zeke's Herald …
      5. Corrupted / dark items   — alternate stat variants
      6. Trait emblems            — Spatula-crafted emblem items (Set 16 only)
    """
    all_items  = cdragon_data.get('items', [])
    equippable = [item for item in all_items if is_equippable_item(item)]
    return {
        'items':       equippable,
        'total_items': len(equippable),
    }


def main():
    print("Fetching Community Dragon data...")
    cdragon_data = get_community_dragon_data()

    print("Extracting equippable items only...")
    items_info = extract_equippable_items(cdragon_data)

    if items_info['items']:
        output_dir  = os.path.join('..', 'data', 'set16')
        output_file = os.path.join(output_dir, 'items.json')
        os.makedirs(output_dir, exist_ok=True)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(items_info, f, indent=2, ensure_ascii=False)

        print(f"\nSuccessfully saved {items_info['total_items']} equippable items")
        print(f"Data saved to: {output_file}")

        # Quick category breakdown for verification
        cats = {}
        for it in items_info['items']:
            n = it.get('apiName','')
            if 'Artifact' in n:    cats['Artifact/Ornn'] = cats.get('Artifact/Ornn',0)+1
            elif 'Support' in n:   cats['Support']       = cats.get('Support',0)+1
            elif 'Emblem' in n:    cats['Emblem']        = cats.get('Emblem',0)+1
            elif 'Corrupted' in n: cats['Corrupted']     = cats.get('Corrupted',0)+1
            elif it.get('composition'):
                cats['Completed']  = cats.get('Completed',0)+1
            else:
                cats['Component']  = cats.get('Component',0)+1
        print("\nCategory breakdown:")
        for cat, cnt in sorted(cats.items()):
            print(f"  {cat:20s}: {cnt}")
    else:
        print("No items found — check filter logic or network connection.")


if __name__ == "__main__":
    main()
