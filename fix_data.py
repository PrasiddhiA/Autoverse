import pandas as pd

# 1. Load your raw dataset
print("Loading raw dataset...")
df = pd.read_csv("expense_receipts_fraud_detection_2000.csv")

# 2. Calculate the historical spending for each employee
print("Calculating historical stats...")
employee_stats = df.groupby('employee_id')['total_amount'].agg(['mean', 'std']).reset_index()

# 3. CRITICAL STEP: Rename the columns so Streamlit can find them!
employee_stats = employee_stats.rename(columns={
    'mean': 'emp_avg_amount', 
    'std': 'emp_std_amount'
})

# Fill any missing standard deviations with 0 (for employees with only 1 receipt)
employee_stats['emp_std_amount'] = employee_stats['emp_std_amount'].fillna(0)

# 4. Save the file that Streamlit reads
employee_stats.to_csv('employee_historical_stats.csv', index=False)
print("✅ Fixed! 'employee_historical_stats.csv' has been generated with the correct column names.")