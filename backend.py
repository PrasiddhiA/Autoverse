import pymongo
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import datetime
import certifi
import streamlit as st

# --- CONFIGURATION ---
MONGO_URI = st.secrets["MONGO_URI"] 
SENDER_EMAIL = "greprep512@gmail.com"
SENDER_PASSWORD = st.secrets["EMAIL_PASSWORD"]

# Mock Employee Directory (UPDATED WITH DEPARTMENTS)
EMPLOYEE_DIRECTORY = {
    "E1001": {"name": "Aryan Satam", "email": "aryansatam22@gmail.com", "department": "IT"},
    "E1002": {"name": "Prasiddhi Agarwal", "email": "studentpras03@gmail.com", "department": "Finance"},
    "E1003": {"name": "Charlie Day", "email": "charlie@example.com", "department": "Sales"},
    "E1004": {"name": "Aditi Sharma", "email": "aditi@example.com", "department": "Management"}
}

# --- DATABASE CONNECTION ---
try:
    # We are using the active SSL bypass logic here so your Wi-Fi doesn't block it!
    client = pymongo.MongoClient(
        MONGO_URI, 
        tlsCAFile=certifi.where(), 
        tlsAllowInvalidCertificates=True,
        serverSelectionTimeoutMS=10000 
    )
    
    db = client["ExpenseSystem"]
    reports_collection = db["expense_reports"]

    # Optional: Ping the database to confirm it works immediately
    client.admin.command('ping')
    print("✅ Successfully connected to MongoDB!")

except Exception as e:
    print(f"❌ Database Connection Error: {e}")
    reports_collection = None

# --- EMAIL FUNCTION ---
def send_verdict_email(emp_email, emp_name, status, amount, reasons):
    """Sends an automated email to the employee with their expense report verdict."""
    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = emp_email
        msg['Subject'] = f"Expense Report Update: {status}"
        
        body = f"Hello {emp_name},\n\nYour expense report for ₹{amount} has been processed.\n\nStatus: {status}\n\n"
        if reasons:
            body += "Review Notes:\n"
            for r in reasons:
                body += f"- {r}\n"
        
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"Email failed to send: {e}")
        return False

# --- DATABASE HELPER FUNCTION ---
def save_report_to_db(db_record):
    """Saves the record to MongoDB."""
    if reports_collection is not None:
        reports_collection.insert_one(db_record)
        return True
    return False