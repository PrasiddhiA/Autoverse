from backend import reports_collection

# Put the correct emails here
NEW_EMAIL_E1001 = "aryansatam22@gmail.com"
NEW_EMAIL_E1002 = "studentpras03@gmail.com"

def fix_emails():
    if reports_collection is not None:
        print("🔗 Connected to MongoDB. Updating emails...")

        # Find all E1001 records and update the email field
        result_1 = reports_collection.update_many(
            {"employee_id": "E1001"},
            {"$set": {"employee_email": NEW_EMAIL_E1001}}
        )
        print(f"✅ Updated {result_1.modified_count} historical records for Aryan (E1001).")

        # Find all E1002 records and update the email field
        result_2 = reports_collection.update_many(
            {"employee_id": "E1002"},
            {"$set": {"employee_email": NEW_EMAIL_E1002}}
        )
        print(f"✅ Updated {result_2.modified_count} historical records for Prasiddhi (E1002).")

    else:
        print("❌ Could not connect to MongoDB.")

if __name__ == "__main__":
    fix_emails()