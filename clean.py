from backend import reports_collection

def wipe_database():
    if reports_collection is not None:
        # Count how many are there right now
        before_count = reports_collection.count_documents({})
        print(f"🗑️ Found {before_count} records in the database.")
        
        if before_count > 0:
            # This is the command that deletes EVERYTHING
            result = reports_collection.delete_many({})
            print(f"✅ BOOM! Successfully deleted {result.deleted_count} records.")
        else:
            print("The database is already empty!")
    else:
        print("❌ Could not connect to MongoDB. Check your backend.py.")

if __name__ == "__main__":
    wipe_database()