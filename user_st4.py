import streamlit as st
import google.generativeai as genai
import pandas as pd
import json
from PIL import Image
import datetime
import joblib
import os
from backend import EMPLOYEE_DIRECTORY, send_verdict_email, save_report_to_db, reports_collection
import math

# -----------------------------
# STEP 1: CONFIGURATION & SETUP
# -----------------------------
st.set_page_config(page_title="AI Expense Reporter", layout="wide")

# ---- Styling / Alignment fixes ----
st.markdown(
    """
    <style>
      .app-title {text-align:center; margin-top:0.2rem; margin-bottom:0.25rem;}
      .subtle {text-align:center; color: #6b7280; margin-top:0; margin-bottom:1rem;}
      .block-container {padding-top: 1.5rem;}
      div.stButton > button:first-child {
          width: 100%;
          border-radius: 8px;
          height: 3em;
      }
    </style>
    """,
    unsafe_allow_html=True,
)
st.markdown('<h1 class="app-title">🧾 AI-Powered Expense Report Generator</h1>', unsafe_allow_html=True)
st.markdown('<p class="subtle">Upload a receipt → Extract → Validate rules → ML anomaly check → Final verdict</p>', unsafe_allow_html=True)

# ---- API Key ----
API_KEY = "AIzaSyCnWqOP6Utu9lfF4cbCX3v3g_8_wCHFvCg"
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

# -----------------------------
# SESSION STATE INIT (Routing & Auth)
# -----------------------------
if "current_view" not in st.session_state:
    st.session_state.current_view = "Employee" # Default view
if "manager_logged_in" not in st.session_state:
    st.session_state.manager_logged_in = False
if "extracted_data" not in st.session_state:
    st.session_state.extracted_data = None
if "raw_text" not in st.session_state:
    st.session_state.raw_text = None

# -----------------------------
# NAVIGATION BUTTONS (Role Selection)
# -----------------------------
col_nav1, col_nav2, col_nav3, col_nav4 = st.columns([1, 2, 2, 1])
with col_nav2:
    if st.button("🧑‍💼 Employee Portal", type="primary" if st.session_state.current_view == "Employee" else "secondary"):
        st.session_state.current_view = "Employee"
        st.rerun()
with col_nav3:
    if st.button("👔 Manager Dashboard", type="primary" if st.session_state.current_view == "Manager" else "secondary"):
        st.session_state.current_view = "Manager"
        st.rerun()

st.markdown("---")

# ==========================================
# VIEW 1: EMPLOYEE PORTAL
# ==========================================
if st.session_state.current_view == "Employee":
    st.subheader("1. Employee Info & Upload")
    entered_emp_id = st.text_input("Enter your Employee ID (e.g., E1001):", value="E1001").upper().strip()
    current_emp_details = EMPLOYEE_DIRECTORY.get(entered_emp_id, {"name": "Unknown Employee", "email": "test@example.com"})
    st.info(f"👤 Logged in as: {current_emp_details['name']} ({current_emp_details['email']})")

    uploaded_file = st.file_uploader("Upload a receipt image (JPG, PNG)", type=["jpg", "jpeg", "png"])

    if uploaded_file is not None:
        col1, col2 = st.columns([1, 1.5], gap="large")

        with col1:
            image = Image.open(uploaded_file)
            st.image(image, caption="Uploaded Receipt", use_container_width=True)

        with col2:
            st.subheader("2. AI Extraction & Validation")

            if st.button("Extract Data with AI", type="primary"):
                with st.spinner("Analyzing receipt..."):
                    # UPDATED PROMPT: Forcing the AI to show its math!
                    prompt = """
                    Analyze this receipt and extract the following information.
                    Respond ONLY with a valid JSON object.
                    Use these exact keys:
                    - vendor_name (string)
                    - date (YYYY-MM-DD)
                    - location (string, extract the city or country, e.g., 'Mumbai', 'New York')
                    - total_amount (float)
                    - tax_amount (float)
                    - category (Meals, Travel, Software, Office Supplies, Accommodation, Other)
                    - payment_method (string, choose one: corp_card, personal_card, cash, UPI)
                    - is_price_reasonable (boolean: true if normal, false if wildly overpriced)
                    - expected_market_range (string: state the typical price limit/range for this category of expense in this specific location, using the receipt's currency. e.g. "2000 - 5000 INR")
                    - ai_reasoning (string: briefly explain your logic for evaluating this price in this specific city)
                   
                    
                    """
                    try:
                        response = model.generate_content([image, prompt])
                        raw_text = response.text.strip()

                        if raw_text.startswith("```"):
                            raw_text = raw_text.replace("```json", "").replace("```", "").strip()

                        st.session_state.raw_text = raw_text
                        st.session_state.extracted_data = json.loads(raw_text)
                        st.success("Data extracted successfully!")

                    except Exception as e:
                        st.error(f"Extraction failed: {e}")

            with st.expander("Show raw AI output"):
                st.write(st.session_state.raw_text)

            if st.session_state.extracted_data is not None:
                st.write("### Extracted Details (Editable)")

                defaults = {
                    "vendor_name": "", "date": "", "location": "Unknown", "total_amount": 0.0,
                    "tax_amount": 0.0, "category": "Other", "payment_method": "corp_card",
                    "is_price_reasonable": True,
                    "expected_market_range": "N/A",  # NEW
                    "ai_reasoning": "N/A",            # NEW
                   
                }

                extracted = {**defaults, **st.session_state.extracted_data}

                df = pd.DataFrame([extracted])

                edited_df = st.data_editor(
                    df, use_container_width=True, hide_index=True,
                    column_config={
                        "vendor_name": st.column_config.TextColumn("Vendor", width="medium", required=True),
                        "location": st.column_config.TextColumn("Location", width="medium"),
                        "date": st.column_config.TextColumn("Date", width="small", required=True),
                        "total_amount": st.column_config.NumberColumn("Total Amount", width="small", required=True),
                        "tax_amount": st.column_config.NumberColumn("Tax Amount", width="small"),
                        "category": st.column_config.SelectboxColumn("Category", width="medium", options=["Meals", "Travel", "Software", "Office Supplies", "Accommodation", "Other"], required=True),
                        "payment_method": st.column_config.SelectboxColumn("Payment Method", width="medium", options=["corp_card", "personal_card", "cash", "UPI"], required=True),
                        "is_price_reasonable": st.column_config.CheckboxColumn("AI Fair Price?", width="small"),
                        "expected_market_range": None, # Hide from grid view
                        "ai_reasoning": None           # Hide from grid view
                    },
                )

                amount = float(edited_df["total_amount"].iloc[0])
                tax_amount = float(edited_df["tax_amount"].iloc[0])
                category = str(edited_df["category"].iloc[0])
                date_str = str(edited_df["date"].iloc[0])
                vendor = str(edited_df["vendor_name"].iloc[0]).lower().strip()
                location = str(edited_df["location"].iloc[0]).strip()
                payment = str(edited_df["payment_method"].iloc[0]) if "payment_method" in edited_df.columns else "corp_card"
                price_is_reasonable = bool(edited_df["is_price_reasonable"].iloc[0])
               

                # --- NEW: Extract the reasoning ---
                market_range = st.session_state.extracted_data.get("expected_market_range", "N/A")
                ai_logic = st.session_state.extracted_data.get("ai_reasoning", "N/A")

                # --- NEW: Display the AI's thought process on the screen! ---
                st.write("### 🤖 AI Price Analysis")
                if price_is_reasonable:
                    st.success(f"**Fair Market Value Confirmed** for {location}")
                else:
                    st.error(f"**Overpriced Alert** for {location}")
                
                st.info(f"**Expected Limit:** {market_range}\n\n**AI Reasoning:** {ai_logic}")
                # --------------------------------------------------

                flags = []
                prohibited_vendors = ["casino", "spa", "resort", "massage", "pub"]

                

                # ---- DYNAMIC AI RULE (Replaces hard limit) ----
                original_amount = float(st.session_state.extracted_data.get("total_amount", amount))

                if amount != original_amount:
                    flags.append(f"🚨 Tamper Alert: Amount manually changed from {original_amount} to {amount}. AI approval voided.")
                    price_is_reasonable = False  # Force the AI check to fail
                elif not price_is_reasonable: 
                    flags.append(f"⚠️ Price Alert: AI flagged this amount as unusually high for a '{category}' expense in {location}.")


                if category == "Other": flags.append("⚠️ 'Other' category requires manual justification.")
                if amount > 0 and amount % 1 == 0: flags.append("⚠️ Suspicious: Exact round number.")
                if tax_amount == 0.0 and category in ["Meals", "Office Supplies"]: flags.append("⚠️ Missing tax line item.")
                if any(word in vendor for word in prohibited_vendors): flags.append("🚫 Restricted vendor detected.")

                expense_date = None
                days_old = None
                try:
                    expense_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
                    days_old = (datetime.date.today() - expense_date).days
                    if expense_date.weekday() >= 5: flags.append("⚠️ Weekend expense.")
                    if days_old > 30: flags.append(f"⚠️ Receipt is {days_old} days old.")
                except ValueError:
                    flags.append("⚠️ Invalid date format.")

                st.write("### 🧾 Manual Rules (Visible Output)")
                if flags:
                    for flag in flags: st.warning(flag)
                    manual_status = "FAIL"
                else:
                    st.success("✅ Rule Engine Passed")
                    manual_status = "PASS"

                st.write("### 🧠 Machine Learning Anomaly Detection")
                ml_status = "SKIPPED"
                anomaly_score = None
                prediction = None

                try:
                    anomaly_model = joblib.load("expense_fraud_model.pkl")
                    historical_stats = pd.DataFrame()
                    if os.path.exists("employee_historical_stats.csv"):
                        historical_stats = pd.read_csv("employee_historical_stats.csv")

                    current_employee_id = entered_emp_id 
                    if not historical_stats.empty and "employee_id" in historical_stats.columns:
                        user_stats = historical_stats[historical_stats["employee_id"] == current_employee_id]
                    else:
                        user_stats = pd.DataFrame()

                    if not user_stats.empty:
                        emp_avg = float(user_stats["emp_avg_amount"].values[0])
                        emp_std = float(user_stats["emp_std_amount"].values[0])
                    else:
                        emp_avg = 500.0
                        emp_std = 100.0

                    is_weekend = 0
                    if expense_date is not None: is_weekend = 1 if expense_date.weekday() >= 5 else 0

                    amount_deviation = amount - emp_avg
                    amount_z_score = amount_deviation / emp_std if emp_std > 0 else 0.0

                    ml_input = pd.DataFrame({
                        "total_amount": [amount], "is_weekend": [is_weekend], "emp_avg_amount": [emp_avg],
                        "amount_deviation": [amount_deviation], "amount_z_score": [amount_z_score],
                        "category": [category], "payment_method": [payment],
                    })

                    prediction = anomaly_model.predict(ml_input)[0]
                    raw_score = float(anomaly_model.decision_function(ml_input)[0]) 

                    # --- FIX 2: SIGMOID MATH ---
                    # Converts a raw negative/positive score into a 0.00 to 1.00 scale
                    # Higher risk (negative raw score) gets pushed closer to 1.00
                    risk_score = 1.0 / (1.0 + math.exp(raw_score * 10))

                    if prediction == -1:
                        ml_status = "ANOMALY"
                        st.error(f"🚨 ML Anomaly Detected (Risk Score: {risk_score:.2f} / 1.00)")
                    else:
                        ml_status = "NORMAL"
                        st.success(f"✅ Behavioral Check Passed (Risk Score: {risk_score:.2f} / 1.00)")

                except FileNotFoundError:
                    st.info("⚠️ ML model or historical stats not found. Run train_anomaly_model.py first.")
                except Exception as e:
                    st.error(f"⚠️ ML Prediction Error: {e}")

                st.write("### ✅ Final Verdict (Rules + ML)")
                needs_review = False
                reasons = []

                if manual_status == "FAIL":
                    needs_review = True
                    reasons.append("Manual rules raised flags.")
                if ml_status == "ANOMALY":
                    needs_review = True
                    reasons.append("ML model detected anomaly.")
                if ml_status == "SKIPPED" and manual_status == "PASS":
                    reasons.append("ML check skipped (missing model/files).")

                if needs_review:
                    st.error("VERDICT: NEEDS REVIEW / APPROVAL")
                else:
                    st.success("VERDICT: OK TO SUBMIT")

                if reasons:
                    st.write("Reasons:")
                    for r in reasons: st.write(f"- {r}")

                if st.button("Submit Final Expense Report", type="primary", use_container_width=True):
                    with st.spinner("Saving to database and sending notifications..."):
                        final_status = "NEEDS REVIEW" if needs_review else "APPROVED"
                        db_record = {
                            "employee_id": entered_emp_id, "employee_name": current_emp_details["name"],
                            "employee_email": current_emp_details["email"], "submission_date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "vendor": vendor, "location": location, "date": date_str, "category": category, "payment_method": payment,
                            "total_amount": amount, "tax_amount": tax_amount, "manual_rules_status": manual_status,
                            "ml_anomaly_status": ml_status, "ml_anomaly_score": anomaly_score, "final_verdict": final_status,
                            "flag_reasons": reasons
                        }

                        try:
                            db_success = save_report_to_db(db_record)
                            email_success = send_verdict_email(
                                emp_email=current_emp_details["email"], emp_name=current_emp_details["name"],
                                status=final_status, amount=amount, reasons=reasons
                            )
                            
                            if db_success: st.success("✅ Report successfully saved to MongoDB database!")
                            else: st.error("❌ Failed to connect to MongoDB.")

                            if email_success: st.success(f"📧 Notification email sent to {current_emp_details['email']}")
                            else: st.warning("⚠️ Email delivery failed. Check your App Password credentials.")

                            st.session_state.extracted_data = None
                            st.session_state.raw_text = None

                        except Exception as e:
                            st.error(f"❌ System Error: {e}")


# ==========================================
# VIEW 2: MANAGER DASHBOARD
# ==========================================
elif st.session_state.current_view == "Manager":
    
    # --- Login Screen ---
    if not st.session_state.manager_logged_in:
        st.subheader("🔒 Manager Login")
        with st.container(border=True):
            m_user = st.text_input("Username")
            m_pass = st.text_input("Password", type="password")
            
            if st.button("Login", type="primary"):
                if m_user == "admin" and m_pass == "admin123":
                    st.session_state.manager_logged_in = True
                    st.rerun()
                else:
                    st.error("Incorrect username or password.")
                    
    # --- Protected Dashboard ---
    else:
        st.subheader("📊 Manager Review Dashboard")
        
        # Logout button
        if st.button("Logout", key="logout_btn"):
            st.session_state.manager_logged_in = False
            st.rerun()

        # Fetch live data from MongoDB
        st.write("Fetching live data from MongoDB...")
        if reports_collection is not None:
            records = list(reports_collection.find({}, {"_id": 0}).sort("submission_date", -1))
            
            if len(records) > 0:
                df_reports = pd.DataFrame(records)
                
                # KPIs
                col1, col2, col3 = st.columns(3)
                col1.metric("Total Submissions", len(df_reports))
                col2.metric("Pending Review", len(df_reports[df_reports['final_verdict'] == 'NEEDS REVIEW']))
                col3.metric("Auto-Approved", len(df_reports[df_reports['final_verdict'] == 'APPROVED']))
                
                st.markdown("---")
                st.write("### All Expense Submissions")
                
                # Show Location column in the manager's view
                cols_to_show = [
                    'submission_date', 'employee_id', 'employee_name', 'vendor', 'location', 
                    'total_amount', 'final_verdict', 'manual_rules_status', 'ml_anomaly_status'
                ]
                
                # Safely filter columns in case old DB records don't have 'location'
                cols_to_show = [c for c in cols_to_show if c in df_reports.columns]

                st.dataframe(
                    df_reports[cols_to_show], 
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("No expense reports have been submitted yet.")
        else:
            st.error("❌ Cannot connect to MongoDB. Ensure your backend connection is active.")