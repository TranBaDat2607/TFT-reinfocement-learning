import requests
import json
import os

def get_community_dragon_data():
    """
    Get detailed TFT data from Community Dragon
    """
    url = "https://raw.communitydragon.org/latest/cdragon/tft/en_us.json"
    response = requests.get(url)
    return response.json()

def extract_all_items(cdragon_data):
    """
    Extract Set 16 and Standard Items
    Filters based on apiName patterns:
    - Include: 'TFT16' (Set 16 specific) or 'TFT_Item' (Standard/Core items)
    - Exclude: Other set prefixes like 'TFT13', 'TFT14', 'TFT15', 'Set13', etc.
    """
    all_items = cdragon_data.get('items', [])
    filtered_items = []
    
    # Prefixes to explicitly exclude (older sets)
    # We'll check if an item starts with these, but NOT if it also matches our include criteria
    # Actually, simpler logic:
    # 1. Must match include patterns
    # 2. Must NOT be clearly part of another set (unless it's a standard reuse, but apiName usually changes if it's set-specific)
    
    for item in all_items:
        api_name = item.get('apiName', '')
        icon_path = item.get('icon', '') or ''
        
        # Criteria for Set 16 Relevance:
        # A. Clearly Set 16 specific
        is_set16 = 'TFT16' in api_name or 'Set16' in api_name or 'Set16' in icon_path
        
        # B. Standard/Core Item (usually starts with TFT_Item_)
        # Note: Some standard items might maintain old IDs (e.g. TFT5_Item_Redemption), but usually standard items are TFT_Item
        # Let's keep things that look like core items and aren't augment-specific from old sets
        is_standard = 'TFT_Item_' in api_name
        
        # C. Exclude items that are definitely from other sets and NOT standard
        # (e.g. TFT13_Augment, TFT4_Item)
        # If it has a specific set number that ISN'T 16, and ISN'T a standard prefix we trust
        is_other_set = False
        import re
        # Look for TFT[number] where number is NOT 16
        # Matches TFT13, TFT5, etc.
        set_match = re.search(r'TFT(\d+)', api_name)
        if set_match:
            set_num = int(set_match.group(1))
            if set_num != 16:
                is_other_set = True
                
        # Special case: Some standard items have old set tags but are reused (like TFT5_Item_Redemption might be the standard ID)
        # However, usually there's a TFT_Item version for the generic one.
        # Let's stick to: Keep if Set16 OR (Standard AND NOT Other Set specific augment/trait item)
        
        # Refined Logic:
        # Keep if matches Set 16
        # OR matches TFT_Item (Standard)
        if is_set16 or (is_standard and not is_other_set):
             filtered_items.append(item)
        # Also include items that might be standard but have old set prefixes IF they are core items?
        # For safety, let's stick to the cleanest filter first. 
        # If the user sees missing items, we can broaden.
        
        # Check for 'TFT_Item' but exclude if it has another set number in it?
        # Actually, standard items are usually just 'TFT_Item_...'. 
        
        # Let's add one more catch: items with no numeric set code in apiName might be standard
        elif 'TFT_Item' in api_name:
             # This catches TFT_Item_... that don't have a number
             filtered_items.append(item)

    return {
        'items': filtered_items,
        'total_items': len(filtered_items)
    }

def main():
    print("Fetching Community Dragon data...")
    cdragon_data = get_community_dragon_data()
    
    print("Extracting items...")
    items_info = extract_all_items(cdragon_data)
    
    if items_info['items']:
        # Save to organized data directory
        output_dir = os.path.join('..', 'data', 'set16')
        output_file = os.path.join(output_dir, 'items.json')
        
        # Ensure directory exists
        os.makedirs(output_dir, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(items_info, f, indent=2, ensure_ascii=False)
        
        print(f"\nSuccessfully crawled {items_info['total_items']} items")
        print(f"Data saved to: {output_file}")
    else:
        print("Failed to fetch items data")

if __name__ == "__main__":
    main()
