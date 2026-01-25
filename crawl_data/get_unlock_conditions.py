import requests
from bs4 import BeautifulSoup
import json
import os

def scrape_unlock_conditions():
    """
    Scrape unlock conditions from op.gg TFT Set 16 page
    Champion names are in span.text-gray-0 and unlock conditions are in p.text-purple-200
    """
    url = "https://op.gg/tft/set/16"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    
    print(f"Fetching unlock conditions from {url}...")
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Find all unlock condition containers
    # Each unlock is in a div with class "flex min-h-[86px] w-[326px]"
    unlock_containers = soup.find_all('div', class_=lambda x: x and 'min-h-[86px]' in x and 'w-[326px]' in x)
    
    unlocks = []
    
    for container in unlock_containers:
        # Find champion name (in span with text-gray-0)
        champ_name_elem = container.find('span', class_=lambda x: x and 'text-gray-0' in x and 'font-bold' in x)
        
        # Find unlock conditions (in p with text-purple-200)
        condition_elems = container.find_all('p', class_='text-purple-200')
        
        if champ_name_elem:
            champ_name = champ_name_elem.get_text(strip=True)
            
            # Some champions have multiple conditions (like level requirement + other)
            conditions = [p.get_text(strip=True) for p in condition_elems if p.get_text(strip=True)]
            
            # Get champion tier from border class
            img = container.find('img', alt=lambda x: x and champ_name in x)
            tier = None
            if img and img.get('class'):
                for cls in img.get('class', []):
                    if 'border-champion-' in cls:
                        tier = cls.split('-')[-1]  # Extract tier number
                        break
            
            unlock_info = {
                'champion': champ_name,
                'conditions': conditions,
                'tier': tier,
                'condition_count': len(conditions)
            }
            
            unlocks.append(unlock_info)
    
    return {
        'url': url,
        'total_unlocks': len(unlocks),
        'unlocks': unlocks,
        'note': 'Unlock conditions for TFT Set 16 champions from op.gg',
        'timestamp': '2026-01-25T23:37:23+07:00'
    }

if __name__ == "__main__":
    try:
        unlock_data = scrape_unlock_conditions()
        
        print(f"\n✓ Successfully crawled {unlock_data['total_unlocks']} unlock conditions!\n")
        
        # Display the unlocks
        for unlock in unlock_data['unlocks']:
            print(f"[Tier {unlock['tier']}] {unlock['champion']}")
            for condition in unlock['conditions']:
                print(f"  - {condition}")
            print()
        
        # Save to file
        output_dir = os.path.join('..', 'data', 'set16')
        output_file = os.path.join(output_dir, 'unlock_conditions.json')
        os.makedirs(output_dir, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(unlock_data, f, indent=2, ensure_ascii=False)
        
        print(f"✓ Data saved to: {output_file}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
