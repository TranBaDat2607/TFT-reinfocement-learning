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

def extract_set16_traits(cdragon_data, set_number=16):
    """
    Extract ALL fields for traits in Set 16
    """
    sets = cdragon_data.get('sets', {})
    set_key = str(set_number)
    
    if set_key not in sets:
        print(f"Set {set_number} not found!")
        print(f"Available sets: {list(sets.keys())}")
        return None
    
    current_set = sets[set_key]
    raw_traits = current_set.get('traits', [])
    
    # Filter out 'icon' field
    traits_data = []
    for trait in raw_traits:
        filtered_trait = {k: v for k, v in trait.items() if k != 'icon'}
        traits_data.append(filtered_trait)
    
    return {
        'set_name': current_set.get('name'),
        'set_number': set_number,
        'traits': traits_data,  # Contains all fields
        'total_traits': len(traits_data)
    }

def main():
    print("Fetching Community Dragon data...")
    cdragon_data = get_community_dragon_data()
    
    print("Extracting Set 16 traits...")
    traits_info = extract_set16_traits(cdragon_data, set_number=16)
    
    if traits_info:
        # Save to organized data directory
        output_dir = os.path.join('..', 'data', 'set16')
        output_file = os.path.join(output_dir, 'traits.json')
        
        # Ensure directory exists
        os.makedirs(output_dir, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(traits_info, f, indent=2, ensure_ascii=False)
        
        print(f"\nSuccessfully crawled {traits_info['total_traits']} traits from {traits_info['set_name']}")
        print(f"Data saved to: {output_file}")
    else:
        print("Failed to fetch Set 16 traits data")

if __name__ == "__main__":
    main()
