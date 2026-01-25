import requests
from bs4 import BeautifulSoup
import json
import os
import re


def scrape_portals():
    """
    Scrape TFT Set 16 portal information from tactics.tools
    Extracts portal data from embedded JSON in the page
    """
    url = "https://tactics.tools/info/portals"
    
    print(f"Fetching portal data from {url}...")
    response = requests.get(url)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Try to extract JSON data from <script> tags
    script_tags = soup.find_all('script', type='application/json')
    
    if not script_tags:
        return None
    
    # Look for portal data in script tags
    for i, script in enumerate(script_tags):
        script_content = script.string
        if not script_content:
            continue
            
        # Check if this script contains portal data
        if 'portal' not in script_content.lower():
            continue
        
        try:
            # Parse JSON
            json_data = json.loads(script_content)
            
            # Navigate to portals array
            if isinstance(json_data, dict) and 'props' in json_data:
                page_props = json_data.get('props', {}).get('pageProps', {})
                if 'portals' in page_props:
                    portals_raw = page_props['portals']

                    # Transform to our format
                    portals = []
                    for portal in portals_raw:
                        transformed = {
                            'id': portal['id'],
                            'name': portal['name'],
                            'description': portal['desc'],
                            'odds': portal['odds'],
                            'unitId': portal.get('unitId'),  # Some don't have a unit
                            'apiName': portal['id'],
                        }
                        portals.append(transformed)
                    
                    return {
                        'portals': portals,
                        'total_portals': len(portals),
                        'source': url,
                        'note': 'Portal spawn probabilities. Only one portal activates per game.'
                    }
        
        except json.JSONDecodeError as e:
            continue
    
    return None


def main():
    try:
        portals_data = scrape_portals()
        
        if portals_data and portals_data['portals']:
            # Save to organized data directory
            output_dir = os.path.join('..', 'data', 'set16')
            output_file = os.path.join(output_dir, 'portals.json')
            
            # Ensure directory exists
            os.makedirs(output_dir, exist_ok=True)
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(portals_data, f, indent=2, ensure_ascii=False)
            
            print(f"Successfully crawled {portals_data['total_portals']} Set 16 Portals")
            print(f"Data saved to: {output_file}")
            
            for portal in portals_data['portals']:
                unit_name = portal.get('unitId', 'None')
                if unit_name:
                    unit_name = unit_name.replace('TFT16_', '')
                odds_str = f"{portal['odds']}%"
                print(f"{portal['name']:<30} {odds_str:<8} {unit_name:<15}")
            
        else:
            print("No portals found or scraping failed")
    
    except Exception as e:
        print(f"Error scraping portals: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
