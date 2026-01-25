import requests
import json
import os
import re

def get_community_dragon_data():
    """
    Get detailed TFT data from Community Dragon
    """
    url = "https://raw.communitydragon.org/latest/cdragon/tft/en_us.json"
    response = requests.get(url)
    return response.json()

def extract_set16_augments(cdragon_data):
    """
    Extract Set 16 Augments from the items list.
    Augments are technically items in the CDragon API structure.
    """
    all_items = cdragon_data.get('items', [])
    augments = []
    
    for item in all_items:
        api_name = item.get('apiName', '')
        icon_path = item.get('icon', '') or ''
        
        # 1. Must be an Augment
        if 'Augment' not in api_name:
            continue
            
        # 2. Must be Set 16 specific
        # Check for TFT16 prefix or Set16 in name/icon
        is_set16 = 'TFT16' in api_name or 'Set16' in api_name or 'Set16' in icon_path
        
        # Exclude other sets if they accidentally sneak in (e.g. TFT13_Augment)
        # Though 'TFT16' check above usually handles this, we double check
        is_other_set = False
        set_match = re.search(r'TFT(\d+)', api_name)
        if set_match:
            set_num = int(set_match.group(1))
            if set_num != 16:
                is_other_set = True
        
        if is_set16 and not is_other_set:
            # Add basic metadata or just keep raw
            augments.append(item)

    return {
        'augments': augments,
        'total_augments': len(augments)
    }

def main():
    print("Fetching Community Dragon data...")
    cdragon_data = get_community_dragon_data()
    
    print("Extracting Set 16 Augments...")
    augments_info = extract_set16_augments(cdragon_data)
    
    if augments_info['augments']:
        # Save to organized data directory
        output_dir = os.path.join('..', 'data', 'set16')
        output_file = os.path.join(output_dir, 'augments.json')
        
        # Ensure directory exists
        os.makedirs(output_dir, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(augments_info, f, indent=2, ensure_ascii=False)
        
        print(f"\nSuccessfully crawled {augments_info['total_augments']} Set 16 Augments")
        print(f"Data saved to: {output_file}")
    else:
        print("No Set 16 Augments found")

if __name__ == "__main__":
    main()
