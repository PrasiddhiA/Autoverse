import streamlit as st
import google.generativeai as genai
import pandas as pd
import json
from PIL import Image
import datetime
import joblib
import os
import math
from backend import EMPLOYEE_DIRECTORY, send_verdict_email, save_report_to_db, reports_collection
import plotly.express as px
from fpdf import FPDF
from bson.objectid import ObjectId
import io
import ast
import fitz  # This is the PyMuPDF library
import io
# -----------------------------
# STEP 1: CONFIGURATION & SETUP
# -----------------------------
st.set_page_config(page_title="AI Expense Reporter", layout="wide")

st.markdown(
    """
    <style>
      .app-title {text-align:center; margin-top:0.2rem; margin-bottom:0.25rem;}
      .subtle {text-align:center; color: #6b7280; margin-top:0; margin-bottom:1rem;}
      .block-container {padding-top: 1.5rem;}
      div.stButton > button:first-child { width: 100%; border-radius: 8px; height: 3em; }
    </style>
    """,
    unsafe_allow_html=True,
)
st.markdown('<h1 class="app-title"> AI-Powered Expense Report Generator</h1>', unsafe_allow_html=True)
st.markdown('<p class="subtle">Intelligent expense automation: From receipt capture to manager approval in seconds</p>', unsafe_allow_html=True)

# ---- API Key ----
API_KEY = "AIzaSyCnWqOP6Utu9lfF4cbCX3v3g_8_wCHFvCg"
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

# -----------------------------
# SESSION STATE INIT
# -----------------------------
if "current_view" not in st.session_state: st.session_state.current_view = "Employee"
if "manager_logged_in" not in st.session_state: st.session_state.manager_logged_in = False
# CHANGE: Now a list to hold multiple receipts
if "extracted_records" not in st.session_state: st.session_state.extracted_records = []

col_nav1, col_nav2, col_nav3, col_nav4 = st.columns([2, 2, 2, 1])
with col_nav2:
    if st.button("Employee Portal", type="primary" if st.session_state.current_view == "Employee" else "secondary"):
        st.session_state.current_view = "Employee"
        st.rerun()
with col_nav3:
    if st.button("Manager Dashboard", type="primary" if st.session_state.current_view == "Manager" else "secondary"):
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

# --- BATCH UPLOAD LOGIC ---
    uploaded_files = st.file_uploader("Upload receipt images (Max 3, JPG/PNG/PDF)", type=["jpg", "jpeg", "png", "pdf"], accept_multiple_files=True)
    
    if uploaded_files:
        if len(uploaded_files) > 3:
            st.error(" Maximum of 3 receipts allowed per batch. Please remove excess files.")
            st.stop() 

        # 1. Convert everything (Images & PDFs) into a standard format
        processed_receipts = []
        for file in uploaded_files:
            file_bytes = file.getvalue() # <-- FIXED: Uses getvalue() so it never reads empty!
            
            if file.name.lower().endswith('.pdf'):
                # Handle PDF: Convert first page to image
                doc = fitz.open(stream=file_bytes, filetype="pdf")
                page = doc.load_page(0) 
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2)) 
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                processed_receipts.append({"name": file.name, "image": img})
            else:
                # Handle standard JPG/PNG
                img = Image.open(io.BytesIO(file_bytes))
                processed_receipts.append({"name": file.name, "image": img})

        # 2. Display the newly processed images side-by-side safely
        img_cols = st.columns(len(processed_receipts))
        for idx, item in enumerate(processed_receipts):
            with img_cols[idx]:
                st.image(item["image"], caption=item["name"], use_container_width=True)

        st.markdown("---")
        st.subheader("2. AI Batch Extraction & Validation")

        if st.button("Extract Data with AI", type="primary"):
            st.session_state.extracted_records = []
            
            # --- BATCH PROCESSING LOOP ---
            progress_text = "Analyzing receipts with AI..."
            my_bar = st.progress(0, text=progress_text)

            for idx, item in enumerate(processed_receipts):
                image = item["image"]
                file_name = item["name"]

                prompt = """
                Analyze this receipt and extract the following information.
                Respond ONLY with a valid JSON object.
                Use these exact keys:
                - vendor_name (string)
                - invoice_number (string, extract the bill/invoice/receipt number if visible, otherwise return "")
                - date (YYYY-MM-DD)
                - location (string, extract the city or country)
                - total_amount (float)
                - tax_amount (float)
                - category (Meals, Travel, Software, Office Supplies, Accommodation, Other)
                - payment_method (string, choose one: corp_card, personal_card, cash, UPI)
                - is_price_reasonable (boolean)
                - expected_market_range (string)
                - ai_reasoning (string)
                
                """
# ... [Your existing prompt block remains exactly the same] ...
                
            try:
                    response = model.generate_content([image, prompt])
                    raw_text = response.text.strip()
                    if raw_text.startswith("```"): raw_text = raw_text.replace("```json", "").replace("```", "").strip()
                    
                    data = json.loads(raw_text)
                    data['filename'] = file_name # <-- MAKE SURE THIS SAYS file_name
                    data['original_ai_amount'] = data.get('total_amount', 0.0) 
                    st.session_state.extracted_records.append(data)
            except Exception as e:
                    st.error(f"Failed to extract {file_name}: {e}")
                
            my_bar.progress((idx + 1) / len(processed_receipts), text=f"Processed {idx + 1} of {len(processed_receipts)}")
            
            st.success("Batch extraction complete!")

        # --- BATCH DATA EDITING ---
        if len(st.session_state.extracted_records) > 0:
            st.write("### Extracted Details (Editable)")
            
            df = pd.DataFrame(st.session_state.extracted_records)
            
            # Define column config for the multi-row grid
            edited_df = st.data_editor(
                df, use_container_width=True, hide_index=True,
                column_order=["filename", "vendor_name", "location", "date", "category", "payment_method", "total_amount", "tax_amount"],
                column_config={
                    "filename": st.column_config.TextColumn("File", disabled=True),
                    "vendor_name": st.column_config.TextColumn("Vendor", required=True),
                    "invoice_number": st.column_config.TextColumn("Invoice #"),
                    "location": st.column_config.TextColumn("Location"),
                    "date": st.column_config.TextColumn("Date", required=True),
                    "category": st.column_config.SelectboxColumn("Category", options=["Meals", "Travel", "Software", "Office Supplies", "Accommodation", "Other"], required=True),
                    "payment_method": st.column_config.SelectboxColumn("Payment", options=["corp_card", "personal_card", "cash", "UPI"], required=True),
                    "total_amount": st.column_config.NumberColumn("Total Amount", required=True),
                    "tax_amount": st.column_config.NumberColumn("Tax Amount"),
                }
            )

            # --- BATCH VALIDATION LOOP (Rules + ML) ---
            st.write("### ⚙️ System Validation (Rules & ML)")
            
            final_submission_data = [] # Stores fully processed rows for the DB
            seen_in_batch = set() # <-- ADD THIS HERE
            
            try:
                anomaly_model = joblib.load("expense_fraud_model.pkl")
                historical_stats = pd.read_csv("employee_historical_stats.csv") if os.path.exists("employee_historical_stats.csv") else pd.DataFrame()
            except:
                anomaly_model = None
                historical_stats = pd.DataFrame()

            
            # Iterate through each row in the edited dataframe
            for index, row in edited_df.iterrows():
                with st.expander(f"Analysis for: {row['filename']} ({row['vendor_name']})", expanded=True):
                    
                    amount = float(row["total_amount"])
                    category = str(row["category"])
                    location = str(row["location"])
                    
                    flags = []
                    prohibited_vendors = ["casino", "spa", "resort", "massage", "pub"]

                    # Original AI context checks
                    original_amount = float(row.get("original_ai_amount", amount))
                    price_is_reasonable = bool(row.get("is_price_reasonable", True))
                 
                    ai_logic = row.get("ai_reasoning", "N/A")
                    
                    st.info(f"**AI Price Logic:** {ai_logic}")

                    # 1. Rules Engine
                    if amount != original_amount:
                        flags.append(f"Tamper Alert: Amount manually changed from {original_amount} to {amount}.")
                    elif not price_is_reasonable: 
                        flags.append(f"⚠️ Price Alert: AI flagged this as unusually high for {location}.")

                   
                    if category == "Other": flags.append("⚠️ 'Other' category requires manual justification.")
                    if amount > 0 and amount % 1 == 0: flags.append("⚠️ Suspicious: Exact round number.")
                    if float(row["tax_amount"]) == 0.0 and category in ["Meals", "Office Supplies"]: flags.append("⚠️ Missing tax line item.")
                    if any(word in str(row["vendor_name"]).lower() for word in prohibited_vendors): flags.append("🚫 Restricted vendor detected.")

                    try:
                        expense_date = datetime.datetime.strptime(str(row["date"]), "%Y-%m-%d").date()
                        if expense_date.weekday() >= 5: flags.append("⚠️ Weekend expense.")
                        if (datetime.date.today() - expense_date).days > 30: flags.append("⚠️ Receipt is >30 days old.")
                    except:
                        flags.append("⚠️ Invalid date format.")
                        expense_date = None

                    # --- NEW & IMPROVED: CROSS-EMPLOYEE & BATCH DUPLICATE CHECK ---
                    is_duplicate = False
                    dup_emp = ""
                    
                    # Clean up the invoice number
                    invoice_num = str(row.get("invoice_number", "None")).strip()
                    if invoice_num.lower() in ["", "none", "null", "nan"]:
                        invoice_num = None 

                    # 1. Check if it's duplicated INSIDE this exact same batch upload
                    batch_key = f"{row['date']}_{str(row['vendor_name']).lower()}_{amount}"
                    if batch_key in seen_in_batch:
                        is_duplicate = True
                        dup_emp = "you (Duplicate found in this exact same upload batch)"
                    else:
                        seen_in_batch.add(batch_key) # Remember it for the next image in the loop
                        
                        # 2. Check the MongoDB Database (Case-Insensitive)
                        if reports_collection is not None:
                            # A) Check by Invoice Number first
                            if invoice_num:
                                dup_inv = reports_collection.find_one({
                                    "invoice_number": invoice_num,
                                    "vendor": {"$regex": f"^{row['vendor_name']}$", "$options": "i"} # Ignores capital letters
                                })
                                if dup_inv:
                                    is_duplicate = True
                                    dup_emp = dup_inv.get("employee_name", "another employee")
                            
                            # B) Fallback: Check Exact Date + Amount + Vendor (if no Invoice ID exists)
                            if not is_duplicate:
                                dup_exact = reports_collection.find_one({
                                    "date": str(row["date"]),
                                    "total_amount": amount,
                                    "vendor": {"$regex": f"^{row['vendor_name']}$", "$options": "i"}
                                })
                                if dup_exact:
                                    is_duplicate = True
                                    dup_emp = dup_exact.get("employee_name", "another employee")

                    if is_duplicate:
                        flags.append(f"⚠️ FRAUD/DUPLICATE ALERT: This receipt is already claimed by {dup_emp}.")
                        st.error(f"⚠️ DUPLICATE DETECTED: This exact receipt is already in the system under {dup_emp}.")

                    if flags:
                        for f in flags: st.warning(f)
                        manual_status = "FAIL"
                    else:
                        st.success("Manual Policy: Passed")
                        manual_status = "PASS"

                    # 2. Machine Learning Check
                    ml_status = "SKIPPED"
                    risk_score = 0.0
                    if anomaly_model is not None:
                        user_stats = historical_stats[historical_stats["employee_id"] == entered_emp_id] if not historical_stats.empty and "employee_id" in historical_stats.columns else pd.DataFrame()
                        emp_avg = float(user_stats["emp_avg_amount"].values[0]) if not user_stats.empty else 500.0
                        emp_std = float(user_stats["emp_std_amount"].values[0]) if not user_stats.empty else 100.0

                        is_weekend = 1 if expense_date and expense_date.weekday() >= 5 else 0
                        amt_dev = amount - emp_avg
                        amt_z = amt_dev / emp_std if emp_std > 0 else 0.0

                        ml_input = pd.DataFrame({
                            "total_amount": [amount], "is_weekend": [is_weekend], "emp_avg_amount": [emp_avg],
                            "amount_deviation": [amt_dev], "amount_z_score": [amt_z],
                            "category": [category], "payment_method": [row["payment_method"]]
                        })

                        prediction = anomaly_model.predict(ml_input)[0]
                        raw_score = float(anomaly_model.decision_function(ml_input)[0]) 
                        risk_score = 1.0 / (1.0 + math.exp(raw_score * 10)) # Sigmoid smoothing

                        if prediction == -1:
                            ml_status = "ANOMALY"
                            st.error(f"⚠️ ML Anomaly Detected (Risk Score: {risk_score:.2f} / 1.00)")
                        else:
                            ml_status = "NORMAL"
                            st.success(f"ML Behavioral Check: Normal (Risk Score: {risk_score:.2f} / 1.00)")

                    # 3. Final Verdict for this specific row
                    if is_duplicate:
                        final_status = "REJECTED"  
                        st.error(f"**Verdict:** {final_status} (Auto-Rejected)")
                    else:
                        needs_review = (manual_status == "FAIL" or ml_status == "ANOMALY")
                        final_status = "NEEDS REVIEW" if needs_review else "APPROVED"
                        if needs_review: st.warning(f"**Verdict:** {final_status}")
                        else: st.success(f"**Verdict:** {final_status}")

                    # Append to final batch list
                    final_submission_data.append({
                        "employee_id": entered_emp_id, "employee_name": current_emp_details["name"],
                        "employee_email": current_emp_details["email"], "department": current_emp_details.get("department", "Unknown"),
                        "submission_date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "invoice_number": invoice_num, # Saves to database!
                        "vendor": row["vendor_name"], "location": location, "date": row["date"], "category": category, 
                        "payment_method": row["payment_method"], "total_amount": amount, "tax_amount": row["tax_amount"], 
                        "manual_rules_status": manual_status, "ml_anomaly_status": ml_status, "ml_anomaly_score": risk_score, 
                        "final_verdict": final_status, "flag_reasons": flags
                    })

            # --- SUBMIT BATCH ---
            st.markdown("---")
            if st.button(f"Submit All {len(final_submission_data)} Expenses", type="primary", use_container_width=True):
                with st.spinner("Saving batch to database..."):
                    db_errors = 0
                    for record in final_submission_data:
                        try:
                            # Save to DB
                            save_report_to_db(record)
                            # Send individual emails
                            send_verdict_email(
                                emp_email=record["employee_email"], emp_name=record["employee_name"],
                                status=record["final_verdict"], amount=record["total_amount"], reasons=record["flag_reasons"]
                            )
                        except:
                            db_errors += 1
                    
                    if db_errors == 0:
                        st.success(" Entire batch successfully saved and notifications sent!")
                        st.session_state.extracted_records = [] # Clear the queue
                    else:
                        st.warning(f"⚠️ Processed with {db_errors} errors. Check console.")


# ==========================================
# VIEW 2: MANAGER DASHBOARD (BI & ADMIN PANEL)
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
        col_header1, col_header2 = st.columns([4, 1])
        with col_header1:
            st.subheader("📊 Manager Review & Analytics Dashboard")
        with col_header2:
            if st.button("Logout", key="logout_btn", use_container_width=True):
                st.session_state.manager_logged_in = False
                st.rerun()

        if reports_collection is not None:
            # 1. FETCH DATA (Keep _id for updating records later)
            records = list(reports_collection.find({}).sort("submission_date", -1))
            
            if len(records) > 0:
                # Convert MongoDB ObjectId to string so Pandas can handle it
                for r in records:
                    r['_id'] = str(r['_id'])
                    
                df_reports = pd.DataFrame(records)
                
                # Convert date strings to actual datetime objects for filtering
                df_reports['submission_date_dt'] = pd.to_datetime(df_reports['submission_date'])
                
                # --- 2. DYNAMIC FILTERS ---
                st.markdown("### Filter Records")
                col_f1, col_f2, col_f3 = st.columns(3)
                
                with col_f1:
                    departments = ["All"] + list(df_reports['department'].dropna().unique()) if 'department' in df_reports.columns else ["All"]
                    selected_dept = st.selectbox("Department", departments)
                
                with col_f2:
                    employees = ["All"] + list(df_reports['employee_name'].unique())
                    selected_emp = st.selectbox("Employee", employees)
                
                with col_f3:
                    timeframes = ["All Time", "Past Week", "Past Month", "Past Year"]
                    selected_time = st.selectbox("Timeframe", timeframes)

                # Apply Filters
                df_filtered = df_reports.copy()
                
                if selected_dept != "All":
                    df_filtered = df_filtered[df_filtered['department'] == selected_dept]
                
                if selected_emp != "All":
                    df_filtered = df_filtered[df_filtered['employee_name'] == selected_emp]
                
                now = datetime.datetime.now()
                if selected_time == "Past Week":
                    df_filtered = df_filtered[df_filtered['submission_date_dt'] >= (now - datetime.timedelta(days=7))]
                elif selected_time == "Past Month":
                    df_filtered = df_filtered[df_filtered['submission_date_dt'] >= (now - datetime.timedelta(days=30))]
                elif selected_time == "Past Year":
                    df_filtered = df_filtered[df_filtered['submission_date_dt'] >= (now - datetime.timedelta(days=365))]

                # --- 3. KPIs ---
                st.markdown("---")
                col_kpi1, col_kpi2, col_kpi3, col_kpi4 = st.columns(4)
                col_kpi1.metric("Total Filtered", len(df_filtered))
                col_kpi2.metric("Total Spend", f"₹{df_filtered['total_amount'].sum():,.2f}")
                col_kpi3.metric("Pending Review", len(df_filtered[df_filtered['final_verdict'] == 'NEEDS REVIEW']))
                col_kpi4.metric("Approved", len(df_filtered[df_filtered['final_verdict'] == 'APPROVED']))

# --- 4. VISUALIZATIONS (Graphs) ---
                st.markdown("---")
                st.markdown("### 📈 Spend Analytics")
                
                if not df_filtered.empty:
                    # Logic: Only show the department bar chart if viewing "All" departments AND "All" employees
                    show_dept_bar_chart = (selected_dept == "All" and selected_emp == "All")
                    
                    if show_dept_bar_chart:
                        # Show BOTH charts side-by-side
                        col_chart1, col_chart2 = st.columns(2)
                        
                        with col_chart1:
                            if 'department' in df_filtered.columns:
                                dept_spend = df_filtered.groupby('department')['total_amount'].sum().reset_index()
                                fig_bar = px.bar(dept_spend, x='department', y='total_amount', title="Total Spend by Department", color='department')
                                st.plotly_chart(fig_bar, use_container_width=True)
                        
                        with col_chart2:
                            time_spend = df_filtered.copy()
                            time_spend['date_only'] = time_spend['submission_date_dt'].dt.date
                            daily_spend = time_spend.groupby('date_only')['total_amount'].sum().reset_index()
                            fig_line = px.line(daily_spend, x='date_only', y='total_amount', title="Spending Trend Over Time", markers=True)
                            st.plotly_chart(fig_line, use_container_width=True)
                    else:
                        # Show ONLY the line chart, taking up the full width of the screen
                        time_spend = df_filtered.copy()
                        time_spend['date_only'] = time_spend['submission_date_dt'].dt.date
                        daily_spend = time_spend.groupby('date_only')['total_amount'].sum().reset_index()
                        
                        # Dynamic title based on filter
                        chart_title = f"Spending Trend Over Time"
                        if selected_emp != "All":
                            chart_title += f" for {selected_emp}"
                        elif selected_dept != "All":
                            chart_title += f" for {selected_dept} Department"
                            
                        fig_line = px.line(daily_spend, x='date_only', y='total_amount', title=chart_title, markers=True)
                        st.plotly_chart(fig_line, use_container_width=True)
                        
                # --- 5. DATA GRID & PDF EXPORT ---
                st.markdown("---")
                col_table_head, col_export = st.columns([3, 1])
                with col_table_head:
                    st.markdown("### 📑 Expense Records")
                
                with col_export:
                    # PDF Generation Logic
                    def generate_pdf(dataframe, dept, emp, time):
                        pdf = FPDF()
                        pdf.add_page()
                        pdf.set_font("Arial", 'B', 16)
                        
                        # Dynamic Title
                        title = f"Expense Report: {time}"
                        if emp != "All": title += f" for {emp}"
                        if dept != "All": title += f" ({dept} Dept)"
                        
                        pdf.cell(0, 10, title, ln=True, align='C')
                        pdf.ln(10)
                        
                        pdf.set_font("Arial", 'B', 10)
                        pdf.cell(40, 10, "Date", border=1)
                        pdf.cell(40, 10, "Employee", border=1)
                        pdf.cell(40, 10, "Vendor", border=1)
                        pdf.cell(30, 10, "Amount", border=1)
                        pdf.cell(30, 10, "Status", border=1, ln=True)
                        
                        pdf.set_font("Arial", size=9)
                        for index, row in dataframe.iterrows():
                            # Clean unicode characters for FPDF
                            vendor = str(row['vendor']).encode('latin-1', 'replace').decode('latin-1')
                            emp_name = str(row['employee_name']).encode('latin-1', 'replace').decode('latin-1')
                            
                            pdf.cell(40, 10, str(row['date']), border=1)
                            pdf.cell(40, 10, emp_name[:15], border=1)
                            pdf.cell(40, 10, vendor[:15], border=1)
                            pdf.cell(30, 10, f"{row['total_amount']:.2f}", border=1)
                            pdf.cell(30, 10, str(row['final_verdict']), border=1, ln=True)
                        
                        return pdf.output(dest='S').encode('latin-1')

                    if not df_filtered.empty:
                        pdf_bytes = generate_pdf(df_filtered, selected_dept, selected_emp, selected_time)
                        st.download_button(
                            label="📄 Export to PDF",
                            data=pdf_bytes,
                            file_name=f"Expense_Report_{datetime.datetime.now().strftime('%Y%m%d')}.pdf",
                            mime="application/pdf",
                            use_container_width=True
                        )

                cols_to_show = ['submission_date', 'employee_id', 'employee_name', 'department', 'vendor', 'location', 'total_amount', 'final_verdict', 'ml_anomaly_status']
                cols_to_show = [c for c in cols_to_show if c in df_filtered.columns]
                
                # Show newest entries at the top
                st.dataframe(df_filtered[cols_to_show], use_container_width=True, hide_index=True)

                # --- 6. MANUAL ACTION PANEL (ACCEPT/REJECT) ---
                st.markdown("---")
                st.markdown("### Pending Approvals Action Center")
                
                pending_df = df_filtered[df_filtered['final_verdict'] == 'NEEDS REVIEW']
                
                if not pending_df.empty:
                    st.info(f"There are {len(pending_df)} reports requiring manual review in this filtered view.")
                    
                    # Create a selection dropdown for the manager to pick a report to action
                    # Format: "Aryan Satam - Starbucks - ₹500 (2026-02-25)"
                    pending_options = pending_df.apply(lambda r: f"{r['employee_name']} - {r['vendor']} - ₹{r['total_amount']} ({r['date']}) | ID: {r['_id']}", axis=1).tolist()
                    
                    selected_action_string = st.selectbox("Select a flagged report to review:", pending_options)
                    
                    if selected_action_string:
                        # Extract the _id from the selected string
                        selected_id = selected_action_string.split("ID: ")[-1]
                        
                        # Find the full record
                        record_to_action = pending_df[pending_df['_id'] == selected_id].iloc[0]
                        
                        st.write("**Flag Reasons:**")
                        
                        raw_reasons = record_to_action.get('flag_reasons', [])
                        
                        
                        # 1. Handle actual Python lists first (Prevents the Pandas array error)
                        if isinstance(raw_reasons, list):
                            if len(raw_reasons) == 0:
                                # Fallbacks if the list is empty
                                if record_to_action.get('manual_rules_status') == 'FAIL':
                                    st.warning("⚠️ Manual rules raised flags.")
                                elif record_to_action.get('ml_anomaly_status') == 'ANOMALY':
                                    st.error("⚠️ ML model detected anomaly.")
                                else:
                                    st.info("No specific manual flags.")
                            else:
                                for reason in raw_reasons:
                                    st.warning(reason)

                        # 2. Handle Strings (from CSV uploads)
                        elif isinstance(raw_reasons, str):
                            if raw_reasons.strip() == "" or raw_reasons.strip() == "[]":
                                if record_to_action.get('manual_rules_status') == 'FAIL':
                                    st.warning("⚠️ Manual rules raised flags.")
                                elif record_to_action.get('ml_anomaly_status') == 'ANOMALY':
                                    st.error("⚠️ ML model detected anomaly.")
                                else:
                                    st.info("No specific manual flags.")
                            else:
                                try:
                                    # Parse JSON string
                                    parsed_list = json.loads(raw_reasons.replace("'", '"'))
                                    if isinstance(parsed_list, list):
                                        for reason in parsed_list:
                                            st.warning(reason)
                                    else:
                                        st.warning(str(parsed_list))
                                except:
                                    try:
                                        # Parse AST string
                                        parsed_list = ast.literal_eval(raw_reasons)
                                        if isinstance(parsed_list, list):
                                            for reason in parsed_list:
                                                st.warning(reason)
                                        else:
                                            st.warning(str(parsed_list))
                                    except:
                                        # Just print the string cleanly
                                        clean_str = raw_reasons.strip("[]'\"")
                                        st.warning(clean_str)

                        # 3. Handle Pandas NaN (Empty CSV cells) or anything else
                        else:
                            if record_to_action.get('manual_rules_status') == 'FAIL':
                                st.warning("⚠️ Manual rules raised flags.")
                            elif record_to_action.get('ml_anomaly_status') == 'ANOMALY':
                                st.error("⚠️ ML model detected anomaly.")
                            else:
                                st.info("No specific manual flags.")
                        
                        col_acc, col_rej = st.columns(2)
                        
                        with col_acc:
                            if st.button(" Accept & Approve", use_container_width=True):
                                # Update DB
                                reports_collection.update_one({"_id": ObjectId(selected_id)}, {"$set": {"final_verdict": "APPROVED"}})
                                # Send Email
                                send_verdict_email(record_to_action['employee_email'], record_to_action['employee_name'], "APPROVED (Manual Override)", record_to_action['total_amount'], ["Your manager has manually reviewed and approved this expense."])
                                st.success("Report Approved! Email sent to employee.")
                                st.rerun()
                                
                        with col_rej:
                            if st.button(" Reject", type="primary", use_container_width=True):
                                # Update DB
                                reports_collection.update_one({"_id": ObjectId(selected_id)}, {"$set": {"final_verdict": "REJECTED"}})
                                # Send Email
                                send_verdict_email(record_to_action['employee_email'], record_to_action['employee_name'], "REJECTED", record_to_action['total_amount'], ["Your manager has reviewed this expense and it does not meet company policy."])
                                st.error("Report Rejected! Email sent to employee.")
                                st.rerun()
                else:
                    st.success(" No pending reviews in this filtered view! You're all caught up.")

            else:
                st.info("No expense reports have been submitted yet.")
        else:
            st.error("Cannot connect to MongoDB. Ensure your backend connection is active.")