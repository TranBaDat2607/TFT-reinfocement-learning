import subprocess
import os
import sys
import time

def run_step(script_name):
    """Run a single python script and wait for it to finish"""
    print(f"Running {script_name}...")
    
    # Get the directory where this script is located
    current_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(current_dir, script_name)
    
    if not os.path.exists(script_path):
        print(f"Error: File {script_name} not found!")
        return False
        
    try:
        # Run the script using the same python interpreter
        result = subprocess.run(
            [sys.executable, script_name], 
            cwd=current_dir,  # Run inside crawl_data directory
            check=True
        )
        print(f"✓ {script_name} completed successfully.")
        return True
    except subprocess.CalledProcessError as e:
        return False

def main():
    print("STARTING DATA PREPROCESSING PIPELINE")
    print("This script will fetch and process all TFT Set 16 data.")
    
    # Order matters! 
    # unlock_conditions must be first because champions might need it (if logic depends on it)
    scripts = [
        "get_unlock_conditions.py",
        "get_champions_detailed.py",
        "get_items_detailed.py",
        "get_traits_detailed.py",
        "get_augments_detailed.py",
        "get_portals_detailed.py"
    ]
    
    start_time = time.time()
    success_count = 0
    
    for script in scripts:
        if run_step(script):
            success_count += 1
        else:
            print("Stopping pipeline due to error.")
            break
            
    end_time = time.time()
    duration = end_time - start_time
    print(f"Pipeline finished in {duration:.2f} seconds.")
    print(f"Successfully ran {success_count}/{len(scripts)} scripts.")
    
    if success_count == len(scripts):
        print("\nAll raw data fetched successfully!")
        
        # Consolidation Step
        print("Step 2: Consolidating data into single archive...")
        
        try:
            # Add project root to path to import data_loader
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            sys.path.append(project_root)
            
            from data_loader.data_loader import TFTDataLoader
            import pickle
            
            # Initialize loader (this verifies all files are readable)
            loader = TFTDataLoader(set_id="Set16")
            
            # Create a dictionary of all data
            full_data = {
                "champions": loader.champions,
                "items": loader.items,
                "traits": loader.traits,
                "augments": loader.augments,
                "portals": loader.portals,
                "unlocks": loader.unlock_conditions,
                "metadata": {
                    "generated_at": time.time(),
                    "version": "1.0"
                }
            }
            
            # Save as pickle
            output_pkl = os.path.join(project_root, 'data', 'set16', 'tft_data_complete.pkl')
            with open(output_pkl, 'wb') as f:
                pickle.dump(full_data, f)
                
            print(f"Consolidated data saved to: {output_pkl}")
            print(f"  - Champions: {len(full_data['champions'])}")
            print(f"  - Items: {len(full_data['items'])}")
            print(f"  - Traits: {len(full_data['traits'])}")
            
            print("\nPREPROCESSING COMPLETE! You are ready to train.")
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            
    else:
        print("\nSome data is missing. Please check the errors above.")

if __name__ == "__main__":
    main()
