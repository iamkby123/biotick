"""Train ML model to predict trial success probability.

Trains on historical trial outcomes (completed vs terminated/withdrawn/suspended)
using features: phase, indication, therapeutic area, sponsor, enrollment, duration.
Saves model + scores all active trials.
"""

import psycopg
import pandas as pd
import numpy as np
import json
import pickle
from datetime import datetime, date
from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import (
    roc_auc_score, classification_report, confusion_matrix,
    precision_recall_curve, average_precision_score,
)

DB = "postgresql://postgres:Biotick2026db@db.bfhmaswnkzoowfxrsfce.supabase.co:5432/postgres"

print("Loading data from Supabase...")
conn = psycopg.connect(DB, options="-c statement_timeout=0")

# Load all trials with outcomes (completed = success, terminated/withdrawn/suspended = failure)
query = """
SELECT
    t.nct_id,
    t.phase,
    t.indication,
    t.therapeutic_area,
    t.company_ticker,
    t.enrollment,
    t.start_date,
    t.primary_completion_date,
    t.completion_date,
    t.overall_status,
    t.has_results,
    t.why_stopped,
    c.market_cap,
    c.revenue,
    c.employees,
    c.runway_months,
    str.total_trials as sponsor_total,
    str.completed_trials as sponsor_completed,
    str.terminated_trials as sponsor_terminated,
    str.approval_count,
    str.overall_success_rate as sponsor_rate,
    isr.success_rate as indication_rate,
    isr.total_trials as indication_sample_size
FROM trials t
LEFT JOIN companies c ON c.ticker = t.company_ticker
LEFT JOIN sponsor_track_records str ON str.company_ticker = t.company_ticker
LEFT JOIN indication_success_rates isr ON isr.indication = t.indication AND isr.phase = t.phase
WHERE t.phase IS NOT NULL
  AND t.indication IS NOT NULL
  AND t.company_ticker IS NOT NULL
"""
df = pd.read_sql(query, conn)
print(f"Loaded {len(df)} trials")

# Only trials with known outcome for training
train_df = df[df["overall_status"].isin(
    ["COMPLETED", "TERMINATED", "WITHDRAWN", "SUSPENDED"]
)].copy()
print(f"Training set: {len(train_df)}")

# Label: 1 = success (completed), 0 = failure (terminated/withdrawn/suspended)
train_df["success"] = (train_df["overall_status"] == "COMPLETED").astype(int)
print(f"Success rate: {train_df['success'].mean()*100:.1f}%")

# Active trials for prediction
active_df = df[df["overall_status"].isin(
    ["RECRUITING", "ACTIVE_NOT_RECRUITING", "NOT_YET_RECRUITING", "ENROLLING_BY_INVITATION"]
)].copy()
print(f"Active trials to score: {len(active_df)}")


# --- Feature engineering ---
def engineer(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()

    # Trial duration (days) — start to primary completion
    for col in ["start_date", "primary_completion_date", "completion_date"]:
        d[col] = pd.to_datetime(d[col], errors="coerce")
    d["planned_duration_days"] = (
        d["primary_completion_date"] - d["start_date"]
    ).dt.days

    # Ensure numeric cols are float
    for col in ["enrollment", "market_cap", "revenue", "employees", "runway_months",
                "sponsor_total", "sponsor_completed", "sponsor_terminated",
                "approval_count", "sponsor_rate", "indication_rate", "indication_sample_size"]:
        if col in d.columns:
            d[col] = pd.to_numeric(d[col], errors="coerce")

    # Enrollment log-transformed (handles wide range)
    d["enrollment_log"] = np.log1p(d["enrollment"].fillna(0).astype(float))
    d["has_enrollment"] = d["enrollment"].notna().astype(int)

    # Market cap log
    d["mcap_log"] = np.log1p(d["market_cap"].fillna(0).astype(float))
    d["has_mcap"] = d["market_cap"].notna().astype(int)

    # Profitability
    d["has_revenue"] = (d["revenue"] > 0).fillna(False).astype(int)
    d["employees_log"] = np.log1p(d["employees"].fillna(0).astype(float))

    # Cash runway — shorter = riskier
    d["low_runway"] = (d["runway_months"] < 12).fillna(False).astype(int)

    # Sponsor features
    d["sponsor_rate"] = d["sponsor_rate"].fillna(0.5)
    d["sponsor_total"] = d["sponsor_total"].fillna(0)
    d["approval_count"] = d["approval_count"].fillna(0)
    d["has_sponsor_history"] = (d["sponsor_total"] >= 3).astype(int)

    # Indication features
    d["indication_rate"] = d["indication_rate"].fillna(0.5)
    d["indication_sample_size"] = d["indication_sample_size"].fillna(0)

    # Phase encoding (ordinal)
    phase_order = {"EARLY_PHASE1": 0, "PHASE1": 1, "PHASE2": 2, "PHASE3": 3, "PHASE4": 4}
    d["phase_ord"] = d["phase"].map(phase_order).fillna(1)

    return d


train_df = engineer(train_df)
active_df = engineer(active_df)

# Select features
numeric_features = [
    "phase_ord",
    "enrollment_log", "has_enrollment",
    "mcap_log", "has_mcap",
    "has_revenue", "employees_log", "low_runway",
    "sponsor_rate", "sponsor_total", "approval_count", "has_sponsor_history",
    "indication_rate", "indication_sample_size",
    "planned_duration_days",
]

# Encode therapeutic_area
le_area = LabelEncoder()
all_areas = pd.concat([train_df["therapeutic_area"], active_df["therapeutic_area"]]).fillna("Unknown")
le_area.fit(all_areas)
train_df["area_enc"] = le_area.transform(train_df["therapeutic_area"].fillna("Unknown"))
active_df["area_enc"] = le_area.transform(active_df["therapeutic_area"].fillna("Unknown"))

features = numeric_features + ["area_enc"]
X = train_df[features].fillna(0)
y = train_df["success"]

# --- Train/test split ---
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
print(f"\nTrain: {len(X_train)}, Test: {len(X_test)}")

# --- Train XGBoost ---
print("\nTraining XGBoost...")
model = XGBClassifier(
    n_estimators=400,
    max_depth=5,
    learning_rate=0.05,
    subsample=0.85,
    colsample_bytree=0.85,
    min_child_weight=5,
    random_state=42,
    eval_metric="auc",
    n_jobs=-1,
)
model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

# --- Evaluate ---
y_pred_proba = model.predict_proba(X_test)[:, 1]
y_pred = model.predict(X_test)

auc = roc_auc_score(y_test, y_pred_proba)
ap = average_precision_score(y_test, y_pred_proba)
print(f"\n=== MODEL PERFORMANCE ===")
print(f"AUC:              {auc:.3f}")
print(f"Avg Precision:    {ap:.3f}")
print(f"\nClassification report:")
print(classification_report(y_test, y_pred, target_names=["Failure", "Success"]))
cm = confusion_matrix(y_test, y_pred)
print("Confusion matrix:")
print(f"  Predicted:     Fail   Succeed")
print(f"  Actual Fail:  {cm[0,0]:5d}  {cm[0,1]:5d}")
print(f"  Actual Succ:  {cm[1,0]:5d}  {cm[1,1]:5d}")

# Cross-validation
cv_scores = cross_val_score(model, X, y, cv=5, scoring="roc_auc", n_jobs=-1)
print(f"\n5-fold CV AUC: {cv_scores.mean():.3f} (+/- {cv_scores.std():.3f})")

# --- Feature importance ---
importance = pd.DataFrame({
    "feature": features,
    "importance": model.feature_importances_,
}).sort_values("importance", ascending=False)
print(f"\n=== FEATURE IMPORTANCE ===")
print(importance.to_string(index=False))

# --- Score all active trials ---
print(f"\n=== SCORING ACTIVE TRIALS ===")
X_active = active_df[features].fillna(0)
probs = model.predict_proba(X_active)[:, 1]
active_df["ml_success_prob"] = probs
active_df["ml_score"] = (probs * 100).round().astype(int)

print(f"Score distribution:")
print(f"  Mean: {active_df['ml_score'].mean():.1f}")
print(f"  Min:  {active_df['ml_score'].min()}")
print(f"  Max:  {active_df['ml_score'].max()}")
print(f"  >70 (high conviction): {(active_df['ml_score'] >= 70).sum()}")
print(f"  40-70 (medium): {((active_df['ml_score'] >= 40) & (active_df['ml_score'] < 70)).sum()}")
print(f"  <40 (low): {(active_df['ml_score'] < 40).sum()}")

# --- Update DB with ML scores ---
print(f"\n=== UPDATING trial_predictions TABLE ===")
cur = conn.cursor()
updated = 0
for _, row in active_df.iterrows():
    try:
        cur.execute("""
            UPDATE trial_predictions
            SET shot_on_goal = %s, risk_level = %s, updated_at = now()
            WHERE nct_id = %s
        """, (
            int(row["ml_score"]),
            "LOW" if row["ml_score"] >= 65 else ("HIGH" if row["ml_score"] < 40 else "MEDIUM"),
            row["nct_id"],
        ))
        if cur.rowcount > 0:
            updated += 1
    except Exception as e:
        conn.rollback()

conn.commit()
print(f"Updated {updated} trial predictions with ML scores")

# --- Save model + metadata ---
model.save_model("backend/scripts/trial_model.json")
with open("backend/scripts/trial_model_meta.json", "w") as f:
    json.dump({
        "features": features,
        "auc": float(auc),
        "avg_precision": float(ap),
        "cv_auc_mean": float(cv_scores.mean()),
        "cv_auc_std": float(cv_scores.std()),
        "training_size": len(X_train),
        "test_size": len(X_test),
        "success_rate": float(y.mean()),
        "feature_importance": importance.to_dict(orient="records"),
        "trained_at": datetime.utcnow().isoformat(),
    }, f, indent=2)
print("\nModel saved to backend/scripts/trial_model.json")
print("Metadata saved to backend/scripts/trial_model_meta.json")

conn.close()
