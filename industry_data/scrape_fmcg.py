import json
import time
import random
import re
from curl_cffi import requests
from bs4 import BeautifulSoup

# Define base URL and target URL
BASE_URL = "https://www.screener.in"
FMCG_URL = "https://www.screener.in/market/IN04/?sort=market+capitalization&order=desc"

def clean_numeric(val):
    """
    Cleans a string representation of a numeric value.
    Removes commas and percent signs, and converts to float if possible.
    """
    if not val:
        return None
    val = val.replace(',', '').replace('%', '').strip()
    if not val or val == '' or val == '-' or val == '—':
        return 0.0
    try:
        return float(val)
    except ValueError:
        return val

def clean_row_name(name):
    """
    Cleans row headers by removing trailing symbols like \xa0+ or +.
    """
    return re.sub(r'[\xa0\s\+]+$', '', name).strip()

def scrape_fmcg_top_10():
    print(f"Fetching FMCG industry top companies from: {FMCG_URL}")
    session = requests.Session(impersonate="chrome120")
    
    try:
        response = session.get(FMCG_URL, timeout=15)
        response.raise_for_status()
    except Exception as e:
        print(f"Error fetching the FMCG market page: {e}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    table = soup.find('table', class_='data-table')
    if not table:
        print("Error: Could not find the data table on the page.")
        return []

    tbody = table.find('tbody')
    rows = tbody.find_all('tr') if tbody else table.find_all('tr')
    
    top_10 = []
    
    for row in rows:
        tds = row.find_all('td')
        if not tds:
            # Skip header rows (e.g. Row with <th>)
            continue
            
        if len(top_10) >= 10:
            break
            
        # Parse fields from the row
        s_no = tds[0].text.strip().replace('.', '')
        name_td = tds[1]
        a_tag = name_td.find('a')
        
        company_name = name_td.text.strip()
        company_path = a_tag['href'] if a_tag else ""
        
        # Ensure company URL is absolute and consolidated if possible
        if company_path:
            # Ensure it ends with /consolidated/ if the link doesn't already have it
            # and it's a valid link format.
            if not company_path.endswith('/consolidated/') and not company_path.endswith('/consolidated'):
                # Strip trailing slash and append /consolidated/
                company_path = company_path.rstrip('/') + '/consolidated/'
            company_url = BASE_URL + company_path
        else:
            company_url = ""

        cmp_rs = clean_numeric(tds[2].text)
        pe = clean_numeric(tds[3].text)
        market_cap_cr = clean_numeric(tds[4].text)
        div_yield_pct = clean_numeric(tds[5].text)
        net_profit_qtr_cr = clean_numeric(tds[6].text)
        qtr_profit_var_pct = clean_numeric(tds[7].text)
        sales_qtr_cr = clean_numeric(tds[8].text)
        qtr_sales_var_pct = clean_numeric(tds[9].text)
        roce_pct = clean_numeric(tds[10].text)

        top_10.append({
            "s_no": int(s_no) if s_no.isdigit() else s_no,
            "name": company_name,
            "url": company_url,
            "cmp_rs": cmp_rs,
            "pe": pe,
            "market_cap_cr": market_cap_cr,
            "div_yield_pct": div_yield_pct,
            "net_profit_qtr_cr": net_profit_qtr_cr,
            "qtr_profit_var_pct": qtr_profit_var_pct,
            "sales_qtr_cr": sales_qtr_cr,
            "qtr_sales_var_pct": qtr_sales_var_pct,
            "roce_pct": roce_pct
        })
        
    return top_10

def scrape_quarterly_data(session, company):
    url = company['url']
    name = company['name']
    
    if not url:
        print(f"Skipping {name}: No URL found")
        return []

    print(f"Fetching quarterly results for {name} from {url}...")
    
    # Polite jitter delay to prevent rate limiting
    sleep_time = random.uniform(2.5, 4.5)
    time.sleep(sleep_time)
    
    try:
        response = session.get(url, timeout=15)
        if response.status_code != 200:
            print(f"  -> Error: Received HTTP status code {response.status_code} for {name}")
            # Try without /consolidated/ if /consolidated/ failed
            if "/consolidated/" in url:
                fallback_url = url.replace("/consolidated/", "/")
                print(f"  -> Retrying fallback URL: {fallback_url}...")
                time.sleep(2)
                response = session.get(fallback_url, timeout=15)
                if response.status_code != 200:
                    print(f"  -> Fallback also failed (HTTP {response.status_code})")
                    return []
            else:
                return []
    except Exception as e:
        print(f"  -> Error connecting to {url}: {e}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Extract company metadata
    h1 = soup.find('h1')
    full_name = h1.text.strip() if h1 else ""
    
    bse_code = None
    nse_symbol = None
    company_links = soup.find('div', class_='company-links')
    if company_links:
        for a in company_links.find_all('a'):
            a_text = a.text.strip()
            if 'BSE:' in a_text:
                bse_code = a_text.replace('BSE:', '').strip()
            elif 'NSE:' in a_text:
                nse_symbol = a_text.replace('NSE:', '').strip()
                
    company['full_name'] = full_name
    company['nse_symbol'] = nse_symbol
    company['bse_code'] = bse_code

    # Generate BSE URL with /brsr suffix
    bse_url = None
    if bse_code:
        name_slug = full_name.lower()
        name_slug = re.sub(r'[^a-z0-9\s-]', '', name_slug)
        name_slug = name_slug.replace(' ', '-')
        
        if nse_symbol:
            symbol_slug = nse_symbol.lower()
            symbol_slug = re.sub(r'[^a-z0-9-]', '', symbol_slug)
        else:
            symbol_slug = "scrip"
            
        bse_url = f"https://www.bseindia.com/stock-share-price/{name_slug}/{symbol_slug}/{bse_code}/brsr"
    company['bse_url'] = bse_url

    quarters_section = soup.find('section', id='quarters')
    if not quarters_section:
        print(f"  -> Error: Could not find quarterly section for {name}")
        return []

    table = quarters_section.find('table')
    if not table:
        print(f"  -> Error: Could not find table in quarterly section for {name}")
        return []

    thead = table.find('thead')
    if not thead:
        print(f"  -> Error: Could not find thead in quarterly table for {name}")
        return []

    # Get quarter headers, e.g., ['Jun 2025', 'Sep 2025', ...]
    # The first column header is usually empty or "Mobiles/Sales" label.
    headers = [th.text.strip() for th in thead.find_all('th')]
    if not headers or len(headers) < 2:
        print(f"  -> Error: No columns found in quarterly table for {name}")
        return []
        
    quarter_names = headers[1:]  # Skip the first label column
    
    # Locate Sales (Revenue), Expenses (Expenditure), Net Profit (Profit)
    tbody = table.find('tbody')
    if not tbody:
        print(f"  -> Error: Could not find tbody in quarterly table for {name}")
        return []

    sales_values = []
    expenses_values = []
    net_profit_values = []
    operating_profit_values = []

    for tr in tbody.find_all('tr'):
        tds = tr.find_all('td')
        if not tds:
            continue
        
        row_name = clean_row_name(tds[0].text)
        row_values = [clean_numeric(td.text) for td in tds[1:]]

        if row_name == "Sales":
            sales_values = row_values
        elif row_name == "Expenses":
            expenses_values = row_values
        elif row_name == "Net Profit":
            net_profit_values = row_values
        elif row_name == "Operating Profit":
            operating_profit_values = row_values

    # Determine last 5 quarters
    num_quarters = len(quarter_names)
    start_idx = max(0, num_quarters - 5)
    
    last_5_quarters = []
    for idx in range(start_idx, num_quarters):
        q_name = quarter_names[idx]
        
        # Safely fetch values, fallback to None if index is out of bounds
        revenue = sales_values[idx] if idx < len(sales_values) else None
        expenditure = expenses_values[idx] if idx < len(expenses_values) else None
        profit = net_profit_values[idx] if idx < len(net_profit_values) else None
        op_profit = operating_profit_values[idx] if idx < len(operating_profit_values) else None

        last_5_quarters.append({
            "quarter": q_name,
            "revenue": revenue,
            "expenditure": expenditure,
            "profit": profit,
            "operating_profit": op_profit
        })

    return last_5_quarters

def main():
    print("=== Screener FMCG Scraper Script ===")
    
    # 1. Get top 10 companies
    top_10 = scrape_fmcg_top_10()
    if not top_10:
        print("Failed to scrape any company. Exiting.")
        return

    print(f"Successfully scraped top {len(top_10)} companies from the market list.\n")

    # 2. Setup session for deep scraping
    session = requests.Session(impersonate="chrome120")
    
    # 3. Fetch quarterly results for each company
    for company in top_10:
        quarterly_data = scrape_quarterly_data(session, company)
        company['quarterly_financials'] = quarterly_data
        
    # 4. Save results to JSON file in the industry directory
    import os
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    output_filepath = os.path.join(SCRIPT_DIR, "industry", "fmcg_scraped_data.json")
    try:
        with open(output_filepath, 'w', encoding='utf-8') as f:
            json.dump(top_10, f, indent=4, ensure_ascii=False)
        print(f"\nSuccessfully saved detailed financial data to {output_filepath}")
    except Exception as e:
        print(f"Error saving to {output_filepath}: {e}")

if __name__ == "__main__":
    main()
