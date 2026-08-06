import os
import json
import re

def generate_bse_url(full_name, nse_symbol, bse_code):
    if not bse_code:
        return None
    
    # 1. Clean the full name for the first slug
    name_slug = full_name.lower()
    name_slug = re.sub(r'[^a-z0-9\s-]', '', name_slug)
    name_slug = name_slug.replace(' ', '-')
    
    # 2. Clean the nse symbol for the second slug
    if nse_symbol:
        symbol_slug = nse_symbol.lower()
        symbol_slug = re.sub(r'[^a-z0-9-]', '', symbol_slug)
    else:
        symbol_slug = "scrip"
        
    # 3. Construct the URL with /brsr suffix
    return f"https://www.bseindia.com/stock-share-price/{name_slug}/{symbol_slug}/{bse_code}/brsr"

def main():
    # Path to the industry JSON folder
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    industry_dir = os.path.join(SCRIPT_DIR, "industry")
    if not os.path.isdir(industry_dir):
        print(f"Error: Directory not found: {industry_dir}")
        return
        
    files = [f for f in os.listdir(industry_dir) if f.endswith(".json")]
    print(f"Found {len(files)} JSON files in {industry_dir}. Starting local update...")
    
    total_updated = 0
    for filename in files:
        filepath = os.path.join(industry_dir, filename)
        
        with open(filepath, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
            except Exception as e:
                print(f"  Error reading {filename}: {e}")
                continue
                
        # Check if the structure is a list of companies
        if not isinstance(data, list):
            print(f"  Skipping {filename}: Not a company list format.")
            continue
            
        modified = False
        for company in data:
            full_name = company.get('full_name')
            nse_symbol = company.get('nse_symbol')
            bse_code = company.get('bse_code')
            
            if full_name and bse_code:
                bse_url = generate_bse_url(full_name, nse_symbol, bse_code)
                if company.get('bse_url') != bse_url:
                    company['bse_url'] = bse_url
                    modified = True
                    
        if modified:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            print(f"  Updated and saved: {filename}")
            total_updated += 1
        else:
            print(f"  No updates needed for: {filename}")
            
    print(f"\nLocal update complete! {total_updated} files updated.")

if __name__ == "__main__":
    main()
