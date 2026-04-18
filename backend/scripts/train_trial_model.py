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
from scipy.stats import rankdata
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

# Active trials for prediction.
# EXCLUDE Phase 4 — those are post-approval surveillance trials. Nearly all
# complete (their base rate is ~97%), so including them just saturates the
# output distribution with spurious 100-scores.
active_df = df[
    df["overall_status"].isin(
        ["RECRUITING", "ACTIVE_NOT_RECRUITING", "NOT_YET_RECRUITING", "ENROLLING_BY_INVITATION"]
    )
    & (df["phase"] != "PHASE4")
].copy()
print(f"Active trials to score (Phase 1-3 only): {len(active_df)}")


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
# Balance the classes: COMPLETED dominates ~82% of the training data, so the
# default output is heavily biased toward 1.0 ("will complete"). scale_pos_weight
# puts more gradient on the minority (failure) class so the model has to actually
# discriminate instead of predicting the majority.
neg = int((y_train == 0).sum())
pos = int((y_train == 1).sum())
spw = neg / max(pos, 1)  # typical value around 0.22 here (majority = success, so we weight FAILURES more)
# Invert: we want the minority class (failures) to weigh more. y=1 is the majority here.
spw = pos / max(neg, 1)
print(f"\nClass balance — success={pos}, failure={neg}, scale_pos_weight={spw:.3f}")

print("\nTraining XGBoost...")
model = XGBClassifier(
    n_estimators=400,
    max_depth=5,
    learning_rate=0.05,
    subsample=0.85,
    colsample_bytree=0.85,
    min_child_weight=5,
    scale_pos_weight=spw,
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
# We convert raw probabilities to a PERCENTILE RANK (0-100) so the score is
# interpretable as "top X%" rather than a raw probability. This also makes the
# UI distribution meaningful: 100 = best-ranked trial, 50 = median, 0 = worst.
# The model's AUC is unchanged because rank is monotonic in probability.
print(f"\n=== SCORING ACTIVE TRIALS ===")
X_active = active_df[features].fillna(0)
probs = model.predict_proba(X_active)[:, 1]
active_df["ml_success_prob"] = probs

if len(probs) > 0:
    # "average" method splits ties by the average rank; divide by n to get a
    # percentile in (0, 1], then multiply to 0-100.
    ranks = rankdata(probs, method="average")
    percentile = ranks / len(probs) * 100.0
    active_df["ml_score"] = np.clip(percentile.round().astype(int), 1, 100)
else:
    active_df["ml_score"] = []

print(f"Score distribution (percentile rank):")
print(f"  Mean: {active_df['ml_score'].mean():.1f}")
print(f"  Min:  {active_df['ml_score'].min()}")
print(f"  Max:  {active_df['ml_score'].max()}")
print(f"  Top decile (>=90): {(active_df['ml_score'] >= 90).sum()}")
print(f"  Top quartile (>=75): {(active_df['ml_score'] >= 75).sum()}")
print(f"  Bottom quartile (<25): {(active_df['ml_score'] < 25).sum()}")

# Also show the raw-prob sanity check so we can see the model isn't saturating.
print(f"\nRaw probability distribution:")
print(f"  Mean: {probs.mean():.3f}, Min: {probs.min():.3f}, Max: {probs.max():.3f}")
print(f"  Prob >= 0.9: {(probs >= 0.9).sum()} / {len(probs)}")
print(f"  Prob <= 0.1: {(probs <= 0.1).sum()} / {len(probs)}")

# --- Update DB with ML scores ---
# Risk level is now based on percentile rank:
#   - LOW risk (green)  = top quartile, rank >= 75
#   - HIGH risk (red)   = bottom quartile, rank < 25
#   - MEDIUM otherwise
print(f"\n=== UPDATING trial_predictions TABLE ===")
cur = conn.cursor()

# First: blank out scores for any Phase 4 rows still in the predictions table —
# we no longer predict those. Leaving stale values would make the table lie.
cur.execute("""
    UPDATE trial_predictions tp
    SET shot_on_goal = NULL, risk_level = NULL, updated_at = now()
    FROM trials t
    WHERE t.nct_id = tp.nct_id AND t.phase = 'PHASE4'
""")
print(f"Cleared scores on {cur.rowcount} Phase-4 rows (not predicted)")

updated = 0
for _, row in active_df.iterrows():
    try:
        score = int(row["ml_score"])
        cur.execute("""
            UPDATE trial_predictions
            SET shot_on_goal = %s, risk_level = %s, updated_at = now()
            WHERE nct_id = %s
        """, (
            score,
            "LOW" if score >= 75 else ("HIGH" if score < 25 else "MEDIUM"),
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
