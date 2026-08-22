"""
Fraud Detection Model Training.

Design notes / what changed and why
-----------------------------------
The previous version reported F1 = AUC = 1.0. That was not a model result: the
generator drew fraud and legit from disjoint ranges, so five hand-written
thresholds recovered 96.3% of fraud with zero false positives. This script is
built so that such a result can never again be mistaken for success:

1. LEAKAGE AUDIT GATE. Before training, every candidate feature is tested for
   single-feature separability and for pure one-sided regions (a threshold with
   100% class purity over a non-trivial share of rows). If anything trips the
   gate, training stops with a loud failure and names the offending feature.
2. METADATA BLOCKLIST. attack_family, campaign_id, meta_* and friends are
   blocked structurally, not by remembering to leave them out of a list.
3. TIME-BASED SPLIT, not random. Fraud arrives in campaigns; a random split puts
   transactions from the same campaign on both sides of the boundary, so the
   model memorises campaigns instead of generalising. Campaigns are also kept
   whole, and encoders are fit on train only.
4. IMBALANCE-HONEST METRICS. Accuracy and raw F1 on a 50/50 dataset say almost
   nothing about deployment. Primary metric is PR-AUC; the report also gives
   recall at fixed false-positive rates, precision at realistic prevalence,
   review-queue precision, and calibration.
5. BASELINES. A majority-class guess, a single decision stump and logistic
   regression are trained alongside. If the stump matches the boosted trees,
   the data is trivial and the boosted trees are decoration.
6. DIAGNOSTIC BREAKDOWNS. Recall per attack family and per evasion level, so
   it is visible which fraud is actually being caught rather than only the
   headline number.

Usage:
    python train_model.py
    python train_model.py --allow-leakage      # audit warns instead of stopping
"""

import argparse
import json
import os
import sys
import warnings
from collections import OrderedDict

import matplotlib
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score, brier_score_loss, confusion_matrix, f1_score,
    precision_score, recall_score, roc_auc_score, roc_curve,
    precision_recall_curve,
)
from sklearn.tree import DecisionTreeClassifier

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# LightGBM is a nice-to-have second opinion, not a requirement. It is not
# installed in every environment, and the script should not die over it.
try:
    import lightgbm as lgb
    HAVE_LGB = True
except ImportError:
    lgb = None
    HAVE_LGB = False

warnings.filterwarnings("ignore")

# ============================================================
# CONFIGURATION
# ============================================================

DATA_PATH = "master_dataset.json"
MODEL_DIR = os.environ.get("FRAUDSHIELD_MODEL_DIR", os.path.join("data", "models"))

# Features available BEFORE the current transaction is authorised. Historical
# aggregates are included now because the generator computes them from strictly
# prior transactions in timestamp order; previously they were all zeros.
CANDIDATE_FEATURES = [
    # transaction surface
    "amount", "payment_rail", "transaction_type", "authentication_method",
    "card_present", "auth_success", "currency",
    # counterparty
    "merchant_category_code", "merchant_risk_score", "merchant_familiarity_score",
    # identity / tenure
    "device_age_days", "account_age_days", "is_new_device", "is_new_beneficiary",
    # behaviour, derived from prior transactions only
    "velocity_score", "transaction_count_last_1h", "transaction_count_last_24h",
    "avg_amount_last_1d", "avg_amount_last_7d", "amount_to_avg_7d_ratio",
    "amount_zscore_account", "seconds_since_prev_tx",
    "distinct_beneficiaries_last_24h", "distinct_devices_last_7d",
    "account_tx_count_to_date", "campaign_step",
    # geography and time
    "location_country", "location_region", "hour_of_day", "day_of_week", "is_night",
]

CATEGORICAL_FEATURES = [
    "payment_rail", "transaction_type", "authentication_method", "currency",
    "location_country", "location_region", "merchant_category_code",
]

# Anything matching these is label metadata and must never become a feature.
BLOCKED_EXACT = {
    "is_fraud", "attack_family", "attack_variant", "lifecycle_stage",
    "campaign_id", "source_document", "transaction_id", "account_id",
    "device_id", "session_id", "merchant_id", "beneficiary_account_id",
    "beneficiary_merchant_id", "beneficiary_is_new", "ip_address",
    "user_agent", "timestamp",
}
BLOCKED_PREFIXES = ("meta_",)

# Audit thresholds.
MAX_SINGLE_FEATURE_AUC = 0.90     # no one feature should nearly solve the task
MIN_PURE_REGION_COVERAGE = 0.01   # a pure region covering >=1% of rows is a leak
MIN_CATEGORY_SUPPORT = 40         # rows needed before calling a pure category a leak

TRAIN_FRAC, VAL_FRAC = 0.70, 0.15  # remainder is test, split chronologically

# Deployment prevalences to report precision at. The dataset is 50/50 so that
# every attack family is represented; real card-fraud prevalence is far lower,
# and precision is brutally sensitive to it.
REPORT_PREVALENCES = [0.005, 0.015]

REVIEW_CAPACITY = 0.01  # analysts can review the top 1% of scored volume


def banner(text, char="="):
    print("\n" + char * 78)
    print(text)
    print(char * 78)


# ============================================================
# 1. LOAD
# ============================================================

def load_data(path):
    banner("1. LOADING DATA")
    with open(path, "r") as f:
        payload = json.load(f)
    df = pd.DataFrame(payload["transactions"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.sort_values("timestamp").reset_index(drop=True)

    n, n_fraud = len(df), int(df["is_fraud"].sum())
    print(f"  Rows:      {n:,}")
    print(f"  Fraud:     {n_fraud:,} ({n_fraud/n*100:.2f}%)")
    print(f"  Legit:     {n-n_fraud:,} ({(n-n_fraud)/n*100:.2f}%)")
    print(f"  Window:    {df['timestamp'].min():%Y-%m-%d} to {df['timestamp'].max():%Y-%m-%d}")
    print(f"  Accounts:  {df['account_id'].nunique():,} "
          f"({n/max(df['account_id'].nunique(),1):.1f} tx/account)")
    if "meta_evasion_level" in df:
        print("  Evasion mix (fraud rows):")
        mix = df.loc[df.is_fraud == 1, "meta_evasion_level"].value_counts(normalize=True)
        for k, v in mix.items():
            print(f"     {k:<12s} {v*100:5.1f}%")
    return df


# ============================================================
# 2. FEATURE SELECTION + BLOCKLIST
# ============================================================

def select_features(df):
    banner("2. FEATURE SELECTION")
    blocked_present = [c for c in df.columns
                       if c in BLOCKED_EXACT or c.startswith(BLOCKED_PREFIXES)]
    features = []
    for col in CANDIDATE_FEATURES:
        if col in BLOCKED_EXACT or col.startswith(BLOCKED_PREFIXES):
            raise ValueError(f"{col!r} is on the metadata blocklist; remove it "
                             "from CANDIDATE_FEATURES.")
        if col not in df.columns:
            print(f"  ! missing from dataset, skipping: {col}")
            continue
        # A constant column carries no information; the old run shipped
        # campaign_step, currency and location_country as constants.
        if df[col].nunique(dropna=False) <= 1:
            print(f"  ! constant, skipping: {col}")
            continue
        features.append(col)

    cats = [c for c in CATEGORICAL_FEATURES if c in features]
    print(f"  Using {len(features)} features ({len(cats)} categorical)")
    print(f"  Blocked as label metadata ({len(blocked_present)}): "
          f"{', '.join(sorted(blocked_present))}")
    return features, cats


# ============================================================
# 3. LEAKAGE AUDIT
# ============================================================

def _pure_region(x, y, min_cov):
    """Largest pure one-sided region: a threshold where one side is 100% one class.

    This is the exact test the original dataset failed - `amount > 50000` was
    100% fraud across 26% of all rows.
    """
    ok = ~np.isnan(x)
    x, y = x[ok], y[ok]
    if len(x) < 100:
        return 0.0, None
    cuts = np.unique(np.nanquantile(x, np.linspace(0.01, 0.99, 60)))
    best_cov, best_desc = 0.0, None
    n = len(x)
    for c in cuts:
        for side, mask in (("_>_", x > c), ("_<_", x < c)):
            cov = mask.sum() / n
            if cov < min_cov:
                continue
            purity = y[mask].mean()
            if (purity == 1.0 or purity == 0.0) and cov > best_cov:
                best_cov = cov
                label = "fraud" if purity == 1.0 else "legit"
                best_desc = f"x {side.strip('_')} {c:,.4g}  ->  100% {label}"
    return best_cov, best_desc


def leakage_audit(df, features, cats, y, strict=True):
    banner("3. LEAKAGE AUDIT")
    print("  Any single feature that nearly solves the task, or carves out a\n"
          "  region of pure class, means the data encodes the label.\n")
    print(f"  {'feature':32s} {'AUC':>7s} {'stump':>7s} {'pure region':>12s}  note")
    print("  " + "-" * 90)

    findings = []
    for col in features:
        s = df[col]
        if col in cats or s.dtype == object or s.dtype == bool:
            x = pd.Categorical(s.astype(str).fillna("NA")).codes.astype(float)
        else:
            x = pd.to_numeric(s, errors="coerce").astype(float).values

        finite = np.nan_to_num(x, nan=-999999.0)
        auc = roc_auc_score(y, finite)
        auc = max(auc, 1 - auc)

        stump = DecisionTreeClassifier(max_depth=1, random_state=0)
        stump.fit(finite.reshape(-1, 1), y)
        stump_acc = (stump.predict(finite.reshape(-1, 1)) == y).mean()

        cov, desc = _pure_region(x.copy(), y.values, MIN_PURE_REGION_COVERAGE)

        notes = []
        if auc > MAX_SINGLE_FEATURE_AUC:
            notes.append(f"AUC>{MAX_SINGLE_FEATURE_AUC}")
        if cov > 0:
            notes.append(f"pure: {desc}")

        # Class-exclusive categories: a value only one class ever takes.
        if col in cats:
            vals = s.astype(str).fillna("NA")
            grp = pd.DataFrame({"v": vals, "y": y}).groupby("v")["y"].agg(["mean", "size"])
            pure = grp[(grp["size"] >= MIN_CATEGORY_SUPPORT) &
                       ((grp["mean"] == 1.0) | (grp["mean"] == 0.0))]
            if len(pure):
                notes.append(f"{len(pure)} class-exclusive values "
                             f"({int(pure['size'].sum()):,} rows)")

        flag = "; ".join(notes)
        print(f"  {col:32s} {auc:7.4f} {stump_acc:7.4f} {cov:11.1%}  {flag}")
        if flag:
            findings.append((col, auc, cov, flag))

    print("  " + "-" * 90)
    if not findings:
        print("  ✅ PASS - no feature individually separates the classes.")
        return True

    print(f"\n  ❌ {len(findings)} feature(s) leak the label:")
    for col, auc, cov, flag in sorted(findings, key=lambda r: -r[1]):
        print(f"     {col:32s} AUC={auc:.4f} pure_region={cov:.1%}  {flag}")
    print("\n  Fix the GENERATOR, not the feature list: dropping a leaking\n"
          "  feature hides the symptom while the disjoint distributions remain.")
    if strict:
        print("\n  Stopping. Re-run with --allow-leakage to train anyway.")
        sys.exit(1)
    print("\n  --allow-leakage set: continuing, but the metrics below are not "
          "trustworthy.")
    return False


# ============================================================
# 4. SPLIT
# ============================================================

def time_split(df):
    """Chronological split, keeping each campaign wholly on one side.

    A random split lets the model see part of a fraud campaign in training and
    the rest in test, which inflates every metric. Sorting by time also matches
    how the model is used: fit on the past, score the future.
    """
    banner("4. CHRONOLOGICAL GROUP SPLIT")
    n = len(df)

    # Group = campaign / recurring series, or the transaction itself when it
    # belongs to no series. Groups are ordered by their earliest timestamp and
    # filled into train, then val, then test, so a campaign never straddles a
    # boundary AND the row proportions are exact. Assigning each campaign to the
    # split of its first row instead lets one long campaign drag thousands of
    # rows across, which previously left test at 94% fraud against a 41% train.
    if "campaign_id" in df.columns:
        group = df["campaign_id"].fillna(pd.Series("solo_" + df.index.astype(str),
                                                   index=df.index))
    else:
        group = pd.Series("solo_" + df.index.astype(str), index=df.index)

    order = (pd.DataFrame({"g": group, "t": df["timestamp"]})
             .groupby("g")["t"].min().sort_values())
    sizes = group.value_counts()
    cum = sizes.reindex(order.index).cumsum()

    assign = {}
    for g, c in cum.items():
        if c <= n * TRAIN_FRAC:
            assign[g] = "train"
        elif c <= n * (TRAIN_FRAC + VAL_FRAC):
            assign[g] = "val"
        else:
            assign[g] = "test"
    df = df.assign(_split=group.map(assign).values)
    print(f"  {len(order):,} groups (campaigns / recurring series / singletons)")
    straddle = df.groupby(group.values)["_split"].nunique().gt(1).sum()
    print(f"  Campaigns straddling a boundary: {straddle}")

    for name in ("train", "val", "test"):
        part = df[df._split == name]
        print(f"  {name:<6s} {len(part):>7,} rows  "
              f"fraud {part.is_fraud.mean()*100:5.2f}%  "
              f"{part.timestamp.min():%Y-%m-%d} -> {part.timestamp.max():%Y-%m-%d}")
    return df


def encode(df, features, cats):
    """Ordinal-encode categoricals, fitting on TRAIN ONLY.

    The previous version fit LabelEncoder on the whole dataframe, which leaks
    test-set vocabulary into training and produces an encoder that cannot handle
    an unseen category at serving time. Unseen values map to -1.
    """
    train_mask = df._split == "train"
    mappings = {}
    X = pd.DataFrame(index=df.index)
    for col in features:
        if col in cats:
            vals = df[col].astype(str).fillna("NA")
            classes = sorted(vals[train_mask].unique())
            mapping = {v: i for i, v in enumerate(classes)}
            mappings[col] = mapping
            X[col] = vals.map(mapping).fillna(-1).astype(int)
        else:
            X[col] = pd.to_numeric(df[col], errors="coerce").astype(float)

    unseen = {c: int((X.loc[df._split == "test", c] == -1).sum())
              for c in cats if c in X}
    if any(unseen.values()):
        print("  Unseen categories in test (encoded as -1): "
              + ", ".join(f"{k}={v}" for k, v in unseen.items() if v))
    return X, mappings


# ============================================================
# 5. METRICS
# ============================================================

def recall_at_fpr(y, proba, target_fpr):
    fpr, tpr, _ = roc_curve(y, proba)
    return float(np.interp(target_fpr, fpr, tpr))


def precision_at_prevalence(y, proba, threshold, prevalence):
    """Precision this model would show at a different fraud base rate.

    Derived from TPR/FPR, which are prevalence-invariant:
        precision = pi*TPR / (pi*TPR + (1-pi)*FPR)
    """
    pred = proba >= threshold
    tpr = pred[y == 1].mean() if (y == 1).any() else 0.0
    fpr = pred[y == 0].mean() if (y == 0).any() else 0.0
    num = prevalence * tpr
    den = num + (1 - prevalence) * fpr
    return float(num / den) if den > 0 else 0.0, tpr, fpr


def queue_precision(y, proba, capacity):
    """Precision among the highest-scoring `capacity` share of transactions."""
    k = max(1, int(len(proba) * capacity))
    idx = np.argsort(proba)[::-1][:k]
    return float(y.iloc[idx].mean() if hasattr(y, "iloc") else y[idx].mean()), k


def best_f1_threshold(y, proba):
    prec, rec, thr = precision_recall_curve(y, proba)
    f1 = 2 * prec * rec / np.clip(prec + rec, 1e-12, None)
    return float(thr[max(0, int(np.nanargmax(f1)) - 1)])


def evaluate(name, y, proba, threshold):
    pred = (proba >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    q_prec, k = queue_precision(y, proba, REVIEW_CAPACITY)
    return OrderedDict(
        model=name,
        pr_auc=average_precision_score(y, proba),
        roc_auc=roc_auc_score(y, proba),
        f1=f1_score(y, pred, zero_division=0),
        precision=precision_score(y, pred, zero_division=0),
        recall=recall_score(y, pred, zero_division=0),
        recall_at_1pct_fpr=recall_at_fpr(y, proba, 0.01),
        recall_at_0p1pct_fpr=recall_at_fpr(y, proba, 0.001),
        queue_precision_top1pct=q_prec,
        brier=brier_score_loss(y, proba),
        threshold=threshold,
        tn=int(tn), fp=int(fp), fn=int(fn), tp=int(tp),
        review_queue_size=k,
    )


# ============================================================
# 6. MAIN
# ============================================================

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--allow-leakage", action="store_true",
                    help="warn instead of stopping when the audit finds leakage")
    ap.add_argument("--data", default=DATA_PATH)
    args = ap.parse_args()

    df = load_data(args.data)
    features, cats = select_features(df)
    y_all = df["is_fraud"].astype(int)

    audit_passed = leakage_audit(df, features, cats, y_all,
                                 strict=not args.allow_leakage)

    df = time_split(df)
    X_all, mappings = encode(df, features, cats)

    tr, va, te = (df._split == "train").values, (df._split == "val").values, (df._split == "test").values
    X_tr, y_tr = X_all[tr], y_all[tr]
    X_va, y_va = X_all[va], y_all[va]
    X_te, y_te = X_all[te], y_all[te]

    pos_weight = float((y_tr == 0).sum() / max((y_tr == 1).sum(), 1))

    # ---------- baselines ----------
    banner("5. BASELINES")
    print("  If a boosted forest cannot beat a single threshold, the task is\n"
          "  trivial and the headline number is meaningless.\n")
    baselines = {}

    dummy = DummyClassifier(strategy="prior").fit(X_tr, y_tr)
    baselines["majority_class"] = dummy.predict_proba(X_te)[:, 1]

    stump = DecisionTreeClassifier(max_depth=1, random_state=42)
    stump.fit(X_tr.fillna(-999999), y_tr)
    baselines["decision_stump"] = stump.predict_proba(X_te.fillna(-999999))[:, 1]

    tree = DecisionTreeClassifier(max_depth=4, random_state=42)
    tree.fit(X_tr.fillna(-999999), y_tr)
    baselines["depth4_tree"] = tree.predict_proba(X_te.fillna(-999999))[:, 1]

    med = X_tr.median()
    logit = LogisticRegression(max_iter=2000, class_weight="balanced")
    logit.fit(((X_tr.fillna(med) - med) / (X_tr.std() + 1e-9)), y_tr)
    baselines["logistic_regression"] = logit.predict_proba(
        ((X_te.fillna(med) - med) / (X_tr.std() + 1e-9)))[:, 1]

    # ---------- gradient boosting ----------
    banner("6. TRAINING GRADIENT-BOOSTED MODELS")
    xgb_model = xgb.XGBClassifier(
        n_estimators=2000, max_depth=6, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, min_child_weight=5,
        reg_alpha=0.1, reg_lambda=2.0,
        scale_pos_weight=pos_weight,
        objective="binary:logistic", eval_metric="aucpr",
        early_stopping_rounds=100, tree_method="hist",
        random_state=42, n_jobs=-1,
    )
    xgb_model.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
    print(f"  XGBoost:  stopped at {xgb_model.best_iteration} trees "
          f"(best val aucpr = {xgb_model.best_score:.4f})")

    models = {"XGBoost": xgb_model}
    if HAVE_LGB:
        lgb_model = lgb.LGBMClassifier(
            n_estimators=2000, max_depth=6, num_leaves=48, learning_rate=0.05,
            subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
            min_child_samples=40, reg_alpha=0.1, reg_lambda=2.0,
            scale_pos_weight=pos_weight, random_state=42, n_jobs=-1, verbose=-1,
        )
        lgb_model.fit(X_tr, y_tr, eval_set=[(X_va, y_va)],
                      eval_metric="average_precision",
                      categorical_feature=[c for c in cats if c in X_tr.columns],
                      callbacks=[lgb.early_stopping(100, verbose=False),
                                 lgb.log_evaluation(0)])
        print(f"  LightGBM: stopped at {lgb_model.best_iteration_} trees")
        models["LightGBM"] = lgb_model
    else:
        print("  LightGBM: not installed, skipping (pip install lightgbm)")

    # ---------- evaluation ----------
    banner("7. EVALUATION (chronological hold-out)")
    rows = []
    for name, proba in baselines.items():
        thr = best_f1_threshold(y_va, np.full(va.sum(), proba.mean())) if name == "majority_class" else None
        if thr is None:
            # tune each baseline's threshold on validation, like the real models
            if name == "decision_stump":
                pv = stump.predict_proba(X_va.fillna(-999999))[:, 1]
            elif name == "depth4_tree":
                pv = tree.predict_proba(X_va.fillna(-999999))[:, 1]
            else:
                pv = logit.predict_proba(((X_va.fillna(med) - med) / (X_tr.std() + 1e-9)))[:, 1]
            thr = best_f1_threshold(y_va, pv)
        rows.append(evaluate(name, y_te, proba, thr))

    probas = {}
    for name, model in models.items():
        pv = model.predict_proba(X_va)[:, 1]
        thr = best_f1_threshold(y_va, pv)
        pt = model.predict_proba(X_te)[:, 1]
        probas[name] = pt
        rows.append(evaluate(name, y_te, pt, thr))

    table = pd.DataFrame(rows)
    show = ["model", "pr_auc", "roc_auc", "recall_at_1pct_fpr",
            "recall_at_0p1pct_fpr", "queue_precision_top1pct", "f1",
            "precision", "recall", "brier"]
    print(table[show].to_string(index=False, float_format=lambda v: f"{v:.4f}"))

    best_row = table[table.model.isin(models)].sort_values("pr_auc").iloc[-1]
    best_name = best_row["model"]
    best_model = models[best_name]
    best_proba = probas[best_name]
    thr = float(best_row["threshold"])
    print(f"\n  🏆 Best by PR-AUC: {best_name}")

    stump_pr = table.loc[table.model == "decision_stump", "pr_auc"].iloc[0]
    lift = best_row["pr_auc"] - stump_pr
    print(f"  Lift over a single threshold: {lift:+.4f} PR-AUC "
          f"({stump_pr:.4f} -> {best_row['pr_auc']:.4f})")
    if lift < 0.05:
        print("  ⚠  The boosted model barely beats one threshold - the data is "
              "probably still too easy.")

    # ---------- confusion matrix and prevalence ----------
    banner("8. OPERATING POINT")
    print(f"  Threshold {thr:.4f} (tuned on validation, not test)\n")
    print(f"   True negatives:  {int(best_row['tn']):>7,}")
    print(f"   False positives: {int(best_row['fp']):>7,}  (legit flagged)")
    print(f"   False negatives: {int(best_row['fn']):>7,}  (fraud missed)")
    print(f"   True positives:  {int(best_row['tp']):>7,}")

    print(f"\n  This dataset is {y_te.mean()*100:.1f}% fraud. Real prevalence is "
          "far lower, and precision collapses with it:")
    for pi in REPORT_PREVALENCES:
        p, tpr, fpr = precision_at_prevalence(y_te, best_proba, thr, pi)
        print(f"     at {pi*100:>4.1f}% prevalence:  precision {p*100:5.1f}%  "
              f"(recall {tpr*100:.1f}%, FPR {fpr*100:.2f}%)")
    qp, k = queue_precision(y_te, best_proba, REVIEW_CAPACITY)
    print(f"\n  Review queue (top {REVIEW_CAPACITY*100:.0f}% = {k:,} transactions): "
          f"{qp*100:.1f}% of them are fraud")

    # ---------- breakdowns ----------
    banner("9. WHAT IS ACTUALLY BEING CAUGHT")
    test_df = df[te].copy()
    test_df["_pred"] = (best_proba >= thr).astype(int)
    test_df["_score"] = best_proba

    if "meta_evasion_level" in test_df:
        print("  Recall by fraud sophistication:")
        sub = test_df[test_df.is_fraud == 1]
        for lvl, g in sub.groupby("meta_evasion_level"):
            if lvl == "n/a":
                continue
            print(f"     {lvl:<12s} n={len(g):>6,}  recall {g._pred.mean()*100:5.1f}%")
    if "meta_hard_negative" in test_df:
        hn = test_df[(test_df.is_fraud == 0) & (test_df.meta_hard_negative == True)]  # noqa: E712
        cn = test_df[(test_df.is_fraud == 0) & (test_df.meta_hard_negative == False)]  # noqa: E712
        if len(hn) and len(cn):
            print(f"\n  False-positive rate on hard negatives: {hn._pred.mean()*100:5.2f}% "
                  f"(n={len(hn):,})")
            print(f"  False-positive rate on ordinary legit:  {cn._pred.mean()*100:5.2f}% "
                  f"(n={len(cn):,})")

    if "attack_family" in test_df:
        fam = (test_df[test_df.is_fraud == 1]
               .groupby("attack_family")["_pred"]
               .agg(["mean", "size"]).sort_values("mean"))
        fam = fam[fam["size"] >= 20]
        print("\n  Hardest attack families (lowest recall):")
        for f, r in fam.head(10).iterrows():
            print(f"     {f:<14s} n={int(r['size']):>5,}  recall {r['mean']*100:5.1f}%")
        print("  Easiest:")
        for f, r in fam.tail(5).iterrows():
            print(f"     {f:<14s} n={int(r['size']):>5,}  recall {r['mean']*100:5.1f}%")

    # ---------- importance ----------
    banner("10. FEATURE IMPORTANCE")
    imp = (pd.DataFrame({"feature": X_tr.columns,
                         "importance": best_model.feature_importances_})
           .sort_values("importance", ascending=False))
    imp["importance"] = imp["importance"] / imp["importance"].sum()
    for _, r in imp.head(15).iterrows():
        bar = "#" * int(r["importance"] * 120)
        print(f"  {r['feature']:32s} {r['importance']:6.3f}  {bar}")

    # ---------- save ----------
    banner("11. SAVING ARTIFACTS")
    os.makedirs(MODEL_DIR, exist_ok=True)

    if best_name == "XGBoost":
        model_path = os.path.join(MODEL_DIR, "fraudshield_v1.json")
        best_model.save_model(model_path)
        stale = os.path.join(MODEL_DIR, "fraudshield_v1.txt")
    else:
        model_path = os.path.join(MODEL_DIR, "fraudshield_v1.txt")
        best_model.booster_.save_model(model_path)
        stale = os.path.join(MODEL_DIR, "fraudshield_v1.json")

    if os.path.exists(stale):
        os.remove(stale)
        print(f"  removed stale {stale} from a previous run")

    features_path = os.path.join(MODEL_DIR, "features.json")
    with open(features_path, "w") as f:
        json.dump({
            "model_file": os.path.basename(model_path),
            "model_type": best_name,
            "version": "v1",
            "feature_order": list(X_tr.columns),
            "categorical_features": cats,
            "categorical_mappings": mappings,
            "unseen_category_code": -1,
            "decision_threshold": thr,
            "threshold_tuned_on": "validation split (chronological)",
            "leakage_audit_passed": bool(audit_passed),
        }, f, indent=2)

    metrics_path = os.path.join(MODEL_DIR, "model_metrics.json")
    with open(metrics_path, "w") as f:
        json.dump({
            "leakage_audit_passed": bool(audit_passed),
            "test_fraud_rate": float(y_te.mean()),
            "results": [{k: (float(v) if isinstance(v, (int, float, np.floating)) else v)
                         for k, v in r.items()} for r in rows],
            "precision_at_prevalence": {
                str(pi): precision_at_prevalence(y_te, best_proba, thr, pi)[0]
                for pi in REPORT_PREVALENCES},
        }, f, indent=2)

    print(f"  {model_path}          - trained model")
    print(f"  {features_path}       - feature order, encodings, threshold")
    print(f"  {metrics_path}        - full metric set")

    # ---------- plots ----------
    fig, axes = plt.subplots(2, 2, figsize=(13, 10))

    for name, p in list(probas.items()) + [("stump", baselines["decision_stump"])]:
        fpr, tpr, _ = roc_curve(y_te, p)
        axes[0, 0].plot(fpr, tpr, label=f"{name} (AUC={roc_auc_score(y_te, p):.3f})")
    axes[0, 0].plot([0, 1], [0, 1], "k--", lw=0.8)
    axes[0, 0].set(xlabel="False positive rate", ylabel="True positive rate",
                   title="ROC")
    axes[0, 0].legend(fontsize=8)

    for name, p in list(probas.items()) + [("stump", baselines["decision_stump"])]:
        pr, rc, _ = precision_recall_curve(y_te, p)
        axes[0, 1].plot(rc, pr, label=f"{name} (AP={average_precision_score(y_te, p):.3f})")
    axes[0, 1].axhline(y_te.mean(), color="k", ls="--", lw=0.8, label="random")
    axes[0, 1].set(xlabel="Recall", ylabel="Precision",
                   title="Precision-Recall (primary metric)")
    axes[0, 1].legend(fontsize=8)

    cm = confusion_matrix(y_te, (best_proba >= thr).astype(int))
    axes[1, 0].imshow(cm, cmap="Blues")
    for (i, j), v in np.ndenumerate(cm):
        axes[1, 0].text(j, i, f"{v:,}", ha="center", va="center",
                        color="white" if v > cm.max() / 2 else "black")
    axes[1, 0].set(xticks=[0, 1], yticks=[0, 1],
                   xticklabels=["legit", "fraud"], yticklabels=["legit", "fraud"],
                   xlabel="Predicted", ylabel="Actual",
                   title=f"Confusion matrix @ {thr:.3f}")

    top = imp.head(12).iloc[::-1]
    axes[1, 1].barh(top["feature"], top["importance"])
    axes[1, 1].set(xlabel="Relative importance", title="Top features")
    axes[1, 1].tick_params(labelsize=8)

    plt.tight_layout()
    plt.savefig("model_evaluation.png", dpi=150, bbox_inches="tight")
    print("  model_evaluation.png           - ROC, PR, confusion, importance")

    banner("SUMMARY")
    print(f"  Model:                  {best_name}")
    print(f"  PR-AUC:                 {best_row['pr_auc']:.4f}   <- primary metric")
    print(f"  ROC-AUC:                {best_row['roc_auc']:.4f}")
    print(f"  Recall @ 1% FPR:        {best_row['recall_at_1pct_fpr']:.4f}")
    print(f"  Recall @ 0.1% FPR:      {best_row['recall_at_0p1pct_fpr']:.4f}")
    print(f"  F1 @ tuned threshold:   {best_row['f1']:.4f}")
    print(f"  Lift over one split:    {lift:+.4f} PR-AUC")
    print(f"  Leakage audit:          {'PASS' if audit_passed else 'FAIL'}")
    print()


if __name__ == "__main__":
    main()
