import pandas as pd
from backend import reports_collection

# --- CONFIGURATION ---
FILE_NAME = "expenses_dataset.csv"

def upload_dataset():
    print(f"📂 Step 1: Attempting to read {FILE_NAME}...")
    try:
        # 1. Load the CSV into pandas
        df = pd.read_csv(FILE_NAME)
        print(f"📊 Step 2: Successfully read {len(df)} rows from the CSV file!")

        # 2. Clean up empty cells 
        df = df.fillna("")
        records = df.to_dict(orient="records")

        # 3. Inject into MongoDB
        if reports_collection is not None:
            print("🔗 Step 3: Connected to MongoDB! Pushing data now (this might take 5-10 seconds)...")
            reports_collection.insert_many(records)
            print(f"✅ SUCCESS! Injected {len(records)} records into MongoDB!")
        else:
            print("❌ ERROR: Not connected to MongoDB. Your backend.py is failing to connect.")

    except FileNotFoundError:
        print(f"❌ ERROR: Could not find '{FILE_NAME}'. Is it saved in the exact same folder as this script?")
    except Exception as e:
        print(f"❌ SCRIPT FAILED: {e}")

if __name__ == "__main__":
    upload_dataset()