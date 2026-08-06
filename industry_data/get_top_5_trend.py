import os
import yfinance as yf
import pandas as pd

def main():
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    # Configure custom tz cache folder to prevent SQLite lockups in parallel downloads
    yf.set_tz_cache_location(os.path.join(SCRIPT_DIR, 'yf_cache'))
    
    # 1. Define tickers with .BO suffix
    tickers = [
        'ADANIENT.BO',
        'ULTRACEMCO.BO',
        'JSWSTEEL.BO',
        'TATASTEEL.BO',
        'HINDZINC.BO'
    ]
    
    # 2 & 3. Download 1-year historical data grouped by ticker using threads
    print(f"Downloading 1-year historical stock trend for: {', '.join(tickers)}")
    data = yf.download(
        tickers=tickers,
        period="1y",
        group_by="ticker",
        threads=True
    )
    
    # 4. Extract 'Close' prices for each company and combine them
    close_data = {}
    for ticker in tickers:
        try:
            # Check if downloaded data is valid and has sufficient rows
            series = None
            if ticker in data.columns.levels[0]:
                series = data[ticker]['Close'].dropna().squeeze()
                
            if series is not None and len(series) >= 10:
                close_data[ticker] = series
            else:
                # Fallback to NSE (.NS)
                fallback_ticker = ticker.replace('.BO', '.NS')
                print(f"BSE ticker {ticker} has insufficient data ({len(series) if series is not None else 0} rows). Falling back to NSE: {fallback_ticker}...")
                fallback_data = yf.download(fallback_ticker, period="1y")
                if not fallback_data.empty:
                    close_data[fallback_ticker] = fallback_data['Close'].squeeze()
                else:
                    print(f"Error: Fallback for {ticker} also failed.")
        except Exception as e:
            print(f"Error processing {ticker}: {e}")
            
    # Combine into a single pandas DataFrame
    df_close = pd.DataFrame(close_data)
    
    # Drop any rows with missing values
    df_close_cleaned = df_close.dropna()
    
    # 5. Print first 5 and last 5 rows of the combined DataFrame
    print("\n=== Combined Close Prices (First 5 Rows) ===")
    print(df_close_cleaned.head())
    
    print("\n=== Combined Close Prices (Last 5 Rows) ===")
    print(df_close_cleaned.tail())
    
    # Save the output to a JSON file
    output_filepath = os.path.join(SCRIPT_DIR, "top_5_trend.json")
    try:
        # Convert index (Dates) to string format for neatness in JSON
        df_to_save = df_close_cleaned.copy()
        df_to_save.index = df_to_save.index.strftime('%Y-%m-%d')
        df_to_save.to_json(output_filepath, orient="index", indent=4)
        print(f"\nSuccessfully saved historical trends to {output_filepath}")
    except Exception as e:
        print(f"Error saving historical trends to JSON: {e}")

if __name__ == "__main__":
    main()
