import pandas as pd
import numpy as np
import joblib
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.metrics import classification_report

# --- STEP 1: LOAD & CLEAN DATA ---
print("Loading dataset...")
# Make sure the path matches where you saved your CSV
df = pd.read_csv("expense_receipts_fraud_detection_2000.csv")

# Drop any rows where critical data is missing
df = df.dropna(subset=['payment_method', 'total_amount', 'employee_id'])

# --- STEP 2: FEATURE ENGINEERING (Contextual Behavior) ---
print("Engineering features...")
# 2a. Date Features: Fraudsters often submit claims on weekends
df['date'] = pd.to_datetime(df['date'])
df['is_weekend'] = (df['date'].dt.weekday >= 5).astype(int)

# 2b. Historical Spending Behavior per Employee
# Calculate the mean and standard deviation of what each employee usually spends
employee_stats = df.groupby('employee_id')['total_amount'].agg(['mean', 'std']).reset_index()
employee_stats = employee_stats.rename(columns={'mean': 'emp_avg_amount', 'std': 'emp_std_amount'})
employee_stats['emp_std_amount'] = employee_stats['emp_std_amount'].fillna(0) # Fix NaN for 1-transaction employees

# Merge these historical stats back onto the main dataframe
df = df.merge(employee_stats, on='employee_id', how='left')

# 2c. Deviation Features: How weird is this specific transaction?
df['amount_deviation'] = df['total_amount'] - df['emp_avg_amount']

# Calculate a Z-Score (how many standard deviations away from the norm)
df['amount_z_score'] = np.where(df['emp_std_amount'] > 0, 
                                (df['total_amount'] - df['emp_avg_amount']) / df['emp_std_amount'], 
                                0)

# --- STEP 3: PREPROCESSING PIPELINE ---
print("Building preprocessing pipeline...")
# Define which columns the ML model is allowed to look at
num_features = ['total_amount', 'is_weekend', 'emp_avg_amount', 'amount_deviation', 'amount_z_score']
cat_features = ['category', 'payment_method']

# Create a transformer that scales numbers and encodes text simultaneously
preprocessor = ColumnTransformer(
    transformers=[
        ('num', StandardScaler(), num_features),
        ('cat', OneHotEncoder(handle_unknown='ignore', sparse_output=False), cat_features)
    ])

# --- STEP 4: ISOLATION FOREST MODEL ---
print("Training Anomaly Detection Model...")
# Create a pipeline that pre-processes the data, then passes it to the ML algorithm
# Contamination=0.05 assumes roughly 5% of corporate expenses are anomalous/fraudulent
ml_pipeline = Pipeline(steps=[
    ('preprocessor', preprocessor),
    ('classifier', IsolationForest(contamination=0.15, random_state=42, n_estimators=100))
])

# Fit (Train) the model on the data
ml_pipeline.fit(df)

# Evaluate the model against the 'is_fraud' column in your dataset to see how it did
df['predictions'] = ml_pipeline.predict(df)
# Isolation Forest returns -1 for anomaly and 1 for normal. Let's map it to 1 (Fraud) and 0 (Normal)
df['ml_fraud_flag'] = np.where(df['predictions'] == -1, 1, 0)

print("\n--- Model Evaluation ---")
print("How well the unsupervised model found the labeled fraud in the dataset:")
print(classification_report(df['is_fraud'], df['ml_fraud_flag']))

# --- STEP 5: SAVE THE MODEL FOR STREAMLIT ---
print("Saving model to 'expense_fraud_model.pkl'...")
joblib.dump(ml_pipeline, 'expense_fraud_model.pkl')
print("Phase 2 Complete! Model is ready for dashboard integration.")