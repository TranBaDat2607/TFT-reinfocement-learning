import requests
import json
import os

def get_community_dragon_data():
    """
    Get detailed TFT data from Community Dragon
    This includes champion abilities, stats, traits, and more
    """
    url = "https://raw.communitydragon.org/latest/cdragon/tft/en_us.json"
    response = requests.get(url)
    return response.json()

def filter_set16_champions(cdragon_data, set_number=16):
    """
    Filter champions for a specific set and extract selected fields
    Fields: ability, apiName, characterName, cost, name, role, stats, traits
    """
    sets = cdragon_data.get('sets', {})
    
    # Sets is a dictionary with string keys like '16', '15', etc.
    set_key = str(set_number)
    
    if set_key not in sets:
        print(f"Set {set_number} not found!")
        print(f"Available sets: {list(sets.keys())}")
        return None
    
    current_set = sets[set_key]
    champions_data = []
    
    for champion in current_set.get('champions', []):
        champ_info = {
            'ability': champion.get('ability', {}),
            'apiName': champion.get('apiName'),
            'characterName': champion.get('characterName'),
            'cost': champion.get('cost'),
            'name': champion.get('name'),
            'role': champion.get('role'),
            'stats': champion.get('stats', {}),
            'traits': champion.get('traits', [])
        }
        champions_data.append(champ_info)
    
    return {
        'set_name': current_set.get('name'),
        'set_number': set_number,
        'champions': champions_data,
        'traits': current_set.get('traits', []),
        'total_champions': len(champions_data)
    }

def load_and_merge_unlock_conditions(set_data):
    """
    Load unlock conditions from unlock_conditions.json and merge into champion data
    Adds 'unlock_conditions' field to each champion
    """
    unlock_file = os.path.join('..', 'data', 'set16', 'unlock_conditions.json')
    
    # Check if unlock conditions file exists
    if not os.path.exists(unlock_file):
        # Mark all as non-unlockable
        for champion in set_data['champions']:
            champion['unlock_conditions'] = None
        return set_data
    
    # Load unlock conditions
    with open(unlock_file, 'r', encoding='utf-8') as f:
        unlock_data = json.load(f)
    
    # Create mapping: champion name -> unlock info (strip whitespace for matching)
    unlock_map = {}
    for unlock in unlock_data.get('unlocks', []):
        champ_name = unlock['champion'].strip()
        unlock_map[champ_name] = {
            'conditions': unlock['conditions'],
            'tier': unlock['tier'],
            'condition_count': unlock['condition_count']
        }
    
    # Merge unlock conditions into champions
    merged_count = 0
    for champion in set_data['champions']:
        champ_name = champion['name'].strip()
        
        if champ_name in unlock_map:
            champion['unlock_conditions'] = unlock_map[champ_name]
            merged_count += 1
        else:
            champion['unlock_conditions'] = None

    return set_data

cdragon_data = get_community_dragon_data()

# Extract Set 16 champions
set16_data = filter_set16_champions(cdragon_data, set_number=16)

if set16_data:
    set16_data = load_and_merge_unlock_conditions(set16_data)
    
    # Save complete data
    output_dir = os.path.join('..', 'data', 'set16')
    output_file = os.path.join(output_dir, 'champions.json')
    
    os.makedirs(output_dir, exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(set16_data, f, indent=2, ensure_ascii=False)
    
    unlockable_count = sum(1 for c in set16_data['champions'] if c.get('unlock_conditions'))
    
    print(f"Total champions: {set16_data['total_champions']}")
    print(f"Unlockable champions: {unlockable_count}")
    print(f"Regular champions: {set16_data['total_champions'] - unlockable_count}")
    print(f"\nData saved to: {output_file}")

else:
    print("\nFailed to fetch Set 16 data from Community Dragon")
