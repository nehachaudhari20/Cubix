"""
realism.py - post-generation realism layer for the fraud dataset.

WHY THIS EXISTS
---------------
dataset_generator.py assigns risk signals per attack family with hardcoded
random.uniform() bounds, while LegitimateGenerator uses *narrower* bounds for
the same fields. Fraud and legit therefore occupy disjoint regions of feature
space. Measured on the original master_dataset.json (107,100 rows):

    amount > 50,000                  -> 100% fraud (27,614 rows)
    velocity_score > 0.30            -> 100% fraud (45,821 rows)
    merchant_risk_score > 0.30       -> 100% fraud (21,520 rows)
    merchant_familiarity_score < .30 -> 100% fraud (15,991 rows)
    22 of 28 transaction_type values -> fraud-only
    campaign_id non-null             -> 100% fraud

Five hand-written thresholds recover 96.3% of fraud with ZERO false positives.
That is why XGBoost reported F1 = 1.0: it is reading the generator's constants,
not learning fraud. Every account_id and device_id was also unique, so the
"historical" columns were all zeros and velocity_score was a free-floating
random draw rather than anything earned from behaviour.

WHAT THIS FIXES
---------------
1. SHARED ENTITIES  - accounts, devices, merchants and beneficiaries are drawn
   from pools used by both classes, so identity is never a label. Fraud runs on
   compromised accounts that also have legitimate history (account takeover),
   which is what actually makes detection hard.
2. EARNED HISTORY   - velocity, familiarity and novelty are computed from prior
   transactions in timestamp order, using the SAME formula for both classes.
   No lookahead: a transaction only ever sees transactions strictly before it.
3. SHARED SUPPORT   - legit samples the full vocabulary and a heavy-tailed
   amount distribution (both tails), so no value and no threshold is
   class-exclusive. Distributions differ in shape - which is the signal - but
   never in support, which is the leak.
4. EVASION MIX      - a substantial share of fraud is made to look ordinary.
   This is not softening the problem; the taxonomy's own families
   ("Behavioral_Camouflage", "Threshold_Conscious_Structuring", "Low_And_Slow",
   "Risk_Score_Evasion") explicitly describe fraud that hides in the legit
   distribution. The old generator gave those families loud signals anyway.
5. HARD NEGATIVES   - legit transactions that genuinely look risky (new device
   + new payee + large amount + high-risk merchant). These are the false
   positives every real fraud system pays for.
6. LABEL NOISE      - a little undetected fraud labelled legit, and a little
   mislabelled legit, because ground truth is never clean.

Run apply_realism(transactions) on the combined transaction list.
"""

import math
import random
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Any, Dict, List

# ============================================================
# CONFIGURATION
# ============================================================

DEFAULTS = {
    # ~27 transactions/account over the window. Enough history per account that
    # counterparties genuinely repeat; with 8000 accounts the wallet was spread
    # so thin that legit familiarity was always 0 while fraud's was not.
    "n_accounts": 4000,
    "n_merchants": 1200,
    "n_beneficiaries": 6000,
    # Accounts that are predominantly criminal. This looks high against real
    # prevalence, and it is - but the dataset is deliberately ~50% fraud so that
    # every attack family has volume. With only 7.5% mule accounts, those few
    # accounts had to absorb ~29k fraud transactions (about 57 each against 22
    # for a normal account), which turned account_tx_count_to_date into a
    # 0.91-AUC fraud proxy. Per-account volume has to stay comparable across
    # both populations or the count features leak.
    "mule_account_fraction": 0.30,
    "window_days": 90,

    # Share of fraud drawn from mule accounts vs. compromised-but-real accounts.
    # The remainder is account takeover, where the account has legit history.
    "fraud_on_mule_accounts": 0.45,

    # Fraud sophistication mix. "crude" keeps the family's loud signals,
    # "evasive" draws its risk surface from the legitimate distribution.
    "evasion_mix": {"crude": 0.32, "moderate": 0.40, "evasive": 0.28},

    # Legit transactions deliberately given a risky-looking surface.
    "hard_negative_rate": 0.11,

    # Ground-truth noise.
    "fraud_labelled_legit": 0.012,
    "legit_labelled_fraud": 0.004,

    "seed": 1337,
}

# ============================================================
# SHARED VOCABULARIES
# ============================================================
# Every value below is reachable by BOTH classes. Legit samples the whole list
# with the weights given here; evasive fraud samples from the same distribution.
# Fraud additionally keeps its family-assigned value, which is always in-list.

TRANSACTION_TYPE_WEIGHTS = {
    # everyday money movement
    "purchase": 20.0, "bill_payment": 9.0, "transfer": 12.0, "subscription": 5.0,
    "salary_deposit": 3.5, "refund": 2.5,
    # session / auth events - every user logs in and occasionally fails
    "login_attempt": 7.0, "session_login": 5.0, "auth_attempt": 4.0,
    "password_reset": 1.6, "account_recovery": 1.1,
    # onboarding - real customers open accounts and register devices
    "account_creation": 2.2, "device_registration": 2.6,
    "identity_verification": 1.8, "document_submission": 1.5,
    "biometric_verification": 1.4, "video_kyc": 0.9,
    # open banking / fintech - legitimate aggregator traffic
    "consent_grant": 1.5, "scope_access": 1.2, "api_access": 2.0,
    "token_usage": 1.6, "tpp_onboarding": 0.5, "webhook_event": 1.3,
    "data_harvesting": 0.35,          # bulk read by a consented aggregator
    "protocol_message": 0.8,
    # cross-border and crypto - legitimate remitters and traders do these
    "cross_border_transfer": 2.4, "crypto_transfer": 1.5, "crypto_conversion": 1.1,
}

PAYMENT_RAIL_WEIGHTS = {
    "upi": 26.0, "card": 22.0, "bank_transfer": 16.0, "wallet": 8.0,
    "authentication": 8.0, "device_session": 5.0, "account_opening": 3.0,
    "account_recovery": 1.8, "data_access": 3.2, "token": 2.6,
    "swift": 2.4, "crypto": 2.0, "protocol": 1.2,
}

AUTH_METHOD_WEIGHTS = {
    "otp": 30.0, "password": 26.0, "biometric": 22.0,
    "document_upload": 6.0, "video_verification": 4.0,
    "voice_verification": 3.5, "unknown": 8.5,
}

# Merchant category codes come from the merchant entity, so both classes draw
# from an identical MCC vocabulary by construction.
MCC_POOL = [
    (5411, 14.0, "grocery"), (5812, 11.0, "restaurant"), (5814, 7.0, "fast_food"),
    (5311, 6.0, "department_store"), (5732, 5.0, "electronics"),
]

# Country/currency: the original data was 100% IN/INR, making both columns dead
# features. Both classes now span the same corridors.
COUNTRY_WEIGHTS = {
    "IN": 68.0, "AE": 6.0, "SG": 5.0, "US": 5.5, "GB": 4.0, "HK": 2.5,
    "MY": 2.2, "SA": 2.0, "AU": 1.8, "CA": 1.5, "DE": 1.0,
}
COUNTRY_CURRENCY = {
    "IN": "INR", "AE": "AED", "SG": "SGD", "US": "USD", "GB": "GBP",
    "HK": "HKD", "MY": "MYR", "SA": "SAR", "AU": "AUD", "CA": "CAD", "DE": "EUR",
}
REGIONS = ["MH", "KA", "TN", "DL", "UP", "GJ", "RJ", "WB", "TG", "KL", "PB", "HR"]

# Transaction types that involve a merchant at all.
MERCHANT_TYPES = {"purchase", "refund", "subscription", "bill_payment"}
# Transaction types that move money to a beneficiary account.
BENEFICIARY_TYPES = {
    "transfer", "cross_border_transfer", "crypto_transfer", "crypto_conversion",
    "salary_deposit",
}

# ============================================================
# PERSONAS
# ============================================================
# Amount is a lognormal mixture per persona. The union across personas spans
# roughly 0.5 to 10,000,000 - the same range fraud spans - so `amount` alone
# cannot separate the classes in either direction.

PERSONAS = {
    #                weight  amount mixture: (prob, mu, sigma)                        activity  rail bias
    "retail_shopper": dict(weight=26, amounts=[(.60, 6.6, 1.0), (.33, 8.3, .9), (.07, 10.0, 1.0)],
                           rate=0.30, rails={"upi": 3.0, "card": 2.5, "wallet": 1.8}),
    "salaried":       dict(weight=20, amounts=[(.45, 7.2, 1.0), (.40, 9.2, .8), (.15, 11.0, .9)],
                           rate=0.22, rails={"upi": 2.5, "bank_transfer": 2.2, "card": 1.8}),
    "small_business": dict(weight=14, amounts=[(.30, 8.5, 1.1), (.45, 10.8, 1.0), (.25, 12.6, 1.0)],
                           rate=0.55, rails={"bank_transfer": 3.0, "upi": 2.0, "swift": 1.2}),
    "hnw":            dict(weight=6,  amounts=[(.25, 9.5, 1.1), (.45, 12.0, 1.0), (.30, 14.0, 1.0)],
                           rate=0.18, rails={"bank_transfer": 2.5, "card": 2.0, "swift": 1.5}),
    "crypto_trader":  dict(weight=5,  amounts=[(.35, 8.8, 1.2), (.45, 11.2, 1.1), (.20, 13.0, 1.1)],
                           rate=0.60, rails={"crypto": 3.5, "bank_transfer": 1.5, "card": 1.0}),
    "remitter":       dict(weight=8,  amounts=[(.40, 9.8, .9), (.50, 11.3, .8), (.10, 12.8, .9)],
                           rate=0.15, rails={"swift": 2.8, "bank_transfer": 2.2, "upi": 1.0}),
    "gig_worker":     dict(weight=12, amounts=[(.65, 6.2, 1.1), (.30, 8.0, .9), (.05, 9.5, 1.0)],
                           rate=0.45, rails={"upi": 3.5, "wallet": 2.0, "card": 1.0}),
    "new_customer":   dict(weight=9,  amounts=[(.70, 6.0, 1.2), (.25, 8.2, 1.0), (.05, 10.2, 1.1)],
                           rate=0.35, rails={"account_opening": 2.5, "authentication": 2.5,
                                             "upi": 2.0, "card": 1.2}),
}


# ============================================================
# HELPERS
# ============================================================

def _wchoice(rng: random.Random, weights: Dict[str, float]) -> str:
    keys = list(weights)
    return rng.choices(keys, weights=[weights[k] for k in keys], k=1)[0]


def _lognormal_mixture(rng: random.Random, mixture) -> float:
    r, acc = rng.random(), 0.0
    mu, sigma = mixture[-1][1], mixture[-1][2]
    for prob, m, s in mixture:
        acc += prob
        if r <= acc:
            mu, sigma = m, s
            break
    return math.exp(rng.gauss(mu, sigma))


def _clip(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def _beta_like(rng: random.Random, a: float, b: float) -> float:
    """Beta sample via two gammas - avoids a numpy dependency here."""
    x = rng.gammavariate(a, 1.0)
    y = rng.gammavariate(b, 1.0)
    return x / (x + y)


# ============================================================
# ENTITY POOLS
# ============================================================

class Merchant:
    __slots__ = ("id", "mcc", "risk_score", "popularity")

    def __init__(self, mid, mcc, risk_score, popularity):
        self.id = mid
        self.mcc = mcc
        self.risk_score = risk_score
        self.popularity = popularity


class Account:
    __slots__ = ("id", "persona", "age_days_at_end", "region", "country",
                 "devices", "is_mule", "rate", "amounts", "rails", "tx_indices",
                 "fav_merchants", "fav_beneficiaries")

    def __init__(self, aid, persona, spec, rng, window_days):
        self.id = aid
        self.persona = persona
        # Account age at the END of the window. Age at transaction time is
        # derived per transaction so it is internally consistent.
        if persona == "new_customer":
            self.age_days_at_end = rng.randint(1, 120)
        else:
            self.age_days_at_end = rng.randint(60, 2200)
        self.region = rng.choice(REGIONS)
        self.country = _wchoice(rng, COUNTRY_WEIGHTS)
        # 1-4 devices, each with its own first-seen offset inside the window.
        n_dev = rng.choices([1, 2, 3, 4], weights=[52, 30, 13, 5], k=1)[0]
        self.devices = []
        for i in range(n_dev):
            # Primary device predates the window; extras appear part-way through.
            first_seen = -rng.randint(30, 900) if i == 0 else rng.uniform(0, window_days)
            self.devices.append((f"dev_{uuid.uuid4().hex[:10]}", first_seen))
        self.is_mule = False
        self.rate = spec["rate"] * rng.uniform(0.5, 1.9)
        self.amounts = spec["amounts"]
        self.rails = spec["rails"]
        self.tx_indices = []
        # Counterparty "wallet": the handful of merchants and payees this
        # account actually uses. Real people shop at the same grocery store and
        # pay the same landlord every month. Without this, legit transactions
        # drew from the global pool at random and so almost never repeated a
        # counterparty - which made is_new_beneficiary an inverted label
        # (98.8% new for legit vs 41.7% for fraud). Populated in _build_accounts,
        # which has the merchant list.
        self.fav_merchants = []
        self.fav_beneficiaries = []


def _build_merchants(rng: random.Random, cfg) -> List[Merchant]:
    merchants = []
    mcc_keys = [m[0] for m in MCC_POOL]
    mcc_w = [m[1] for m in MCC_POOL]
    for _ in range(cfg["n_merchants"]):
        # Risk is a property of the MERCHANT, not of the label. Fraud prefers
        # high-risk merchants, but legit customers use them too - which is the
        # whole reason merchant risk is a useful-but-imperfect signal.
        bucket = rng.choices(["low", "mid", "high"], weights=[74, 19, 7], k=1)[0]
        if bucket == "low":
            risk = _beta_like(rng, 2.0, 9.0)
        elif bucket == "mid":
            risk = _beta_like(rng, 4.0, 4.0)
        else:
            risk = _clip(_beta_like(rng, 8.0, 2.2), 0.0, 0.97)
        merchants.append(Merchant(
            f"mch_{uuid.uuid4().hex[:10]}",
            rng.choices(mcc_keys, weights=mcc_w, k=1)[0],
            round(risk, 4),
            # Popularity is Zipf-ish: a few merchants take most of the traffic.
            1.0 / (rng.uniform(1.0, 40.0) ** 1.1),
        ))
    return merchants


def _build_accounts(rng: random.Random, cfg, merchants, beneficiaries) -> List[Account]:
    names = list(PERSONAS)
    weights = [PERSONAS[n]["weight"] for n in names]
    merchant_w = [m.popularity for m in merchants]
    accounts = []
    for _ in range(cfg["n_accounts"]):
        persona = rng.choices(names, weights=weights, k=1)[0]
        acc = Account(f"acc_{uuid.uuid4().hex[:10]}", persona,
                      PERSONAS[persona], rng, cfg["window_days"])
        # A small, sticky set of counterparties per account.
        # Small wallets: an account with ~27 transactions must revisit these
        # often enough for familiarity to actually accumulate.
        acc.fav_merchants = rng.choices(merchants, weights=merchant_w,
                                        k=rng.randint(2, 6))
        acc.fav_beneficiaries = [rng.choice(beneficiaries)
                                 for _ in range(rng.randint(2, 5))]
        accounts.append(acc)
    n_mule = max(1, int(cfg["n_accounts"] * cfg["mule_account_fraction"]))
    for acc in rng.sample(accounts, n_mule):
        acc.is_mule = True
    return accounts


# ============================================================
# STAGE 0: REAL CAMPAIGNS
# ============================================================

def _rebuild_campaigns(txs, rng, cfg):
    """Group fraud transactions into genuine multi-transaction campaigns.

    The generator assigned a fresh uuid campaign_id inside each per-transaction
    loop, so every "campaign" had exactly one transaction. campaign_step was
    therefore always 1 for fraud and 0 for legit - a 0.847-AUC label proxy - and
    the campaign-coherent account/beneficiary logic had nothing to bind.

    Real campaigns are a handful to a few dozen transactions from one operator
    against one or a few accounts, which is what makes them detectable as a
    pattern rather than as individual transactions.
    """
    by_family: Dict[str, List] = defaultdict(list)
    for tx in txs:
        if tx["is_fraud"] == 1:
            by_family[tx.get("attack_family") or "UNKNOWN"].append(tx)

    n_campaigns = 0
    for family, rows in by_family.items():
        rng.shuffle(rows)
        i = 0
        while i < len(rows):
            # Campaign sizes are heavy-tailed: many small probes, a few large
            # coordinated pushes.
            size = rng.choices([1, 2, 3, 5, 8, 14, 25],
                               weights=[18, 20, 18, 16, 13, 10, 5], k=1)[0]
            chunk = rows[i:i + size]
            cid = f"camp_{family.lower().replace('-', '')}_{uuid.uuid4().hex[:8]}"
            for step, tx in enumerate(chunk):
                tx["campaign_id"] = cid
                tx["campaign_step"] = step + 1
            n_campaigns += 1
            i += size
    return n_campaigns


# ============================================================
# STAGE 1: ENTITY ASSIGNMENT
# ============================================================

def _assign_accounts(txs, accounts, rng, cfg):
    """Replace the per-transaction UUID identities with pooled entities.

    Originally every transaction had a unique account_id and device_id, so no
    account had any history and every novelty/velocity feature was fabricated.
    """
    mules = [a for a in accounts if a.is_mule]
    normals = [a for a in accounts if not a.is_mule]

    # Legit traffic is spread over all accounts by activity rate. Mules transact
    # legitimately too - that is how they stay open and how they blend in - so
    # their streams must not be almost purely fraud, or the account's own
    # transaction count gives the label away.
    legit_pool = accounts
    legit_w = [a.rate * (0.85 if a.is_mule else 1.0) for a in legit_pool]

    mule_w = [a.rate for a in mules]
    normal_w = [a.rate for a in normals]

    # Campaign-level coherence: all transactions in one fraud campaign share an
    # account, which is a large part of what makes them a campaign.
    campaign_account: Dict[str, Account] = {}

    for tx in txs:
        is_fraud = tx["is_fraud"] == 1
        camp = tx.get("campaign_id")

        if is_fraud:
            if camp and camp in campaign_account:
                acc = campaign_account[camp]
            else:
                if rng.random() < cfg["fraud_on_mule_accounts"]:
                    acc = rng.choices(mules, weights=mule_w, k=1)[0]
                else:
                    # Account takeover: a real account with real prior history.
                    acc = rng.choices(normals, weights=normal_w, k=1)[0]
                if camp:
                    campaign_account[camp] = acc
        else:
            acc = rng.choices(legit_pool, weights=legit_w, k=1)[0]

        tx["account_id"] = acc.id
        tx["_acc"] = acc
        acc.tx_indices.append(tx)
        tx["session_id"] = f"ses_{uuid.uuid4().hex[:10]}"


def _assign_counterparties(txs, merchants, beneficiaries, rng, cfg):
    """Attach merchant / beneficiary / geography to each transaction.

    Must run AFTER the transaction_type is final. Running it before the legit
    resample left merchant_id set on transactions whose final type had no
    merchant at all, which made merchant_risk_score missingness a 0.70-AUC
    proxy for the label.
    """
    ben_w = [1.0 / (rng.uniform(1.0, 25.0) ** 1.05) for _ in beneficiaries]
    merchant_w = [m.popularity for m in merchants]
    # Fraud skews toward high-risk merchants without ever excluding low-risk ones.
    fraud_merchant_w = [m.popularity * (0.4 + 3.2 * m.risk_score) for m in merchants]
    campaign_beneficiary: Dict[str, str] = {}

    for tx in txs:
        is_fraud = tx["is_fraud"] == 1
        camp = tx.get("campaign_id")
        acc = tx["_acc"]

        # Merchant, only for merchant-facing transaction types.
        ttype = tx.get("transaction_type", "unknown")
        if ttype in MERCHANT_TYPES:
            # Mostly a merchant the account already uses; sometimes a new one.
            # Both classes get the same wallet mechanic, so familiarity stays a
            # genuine behavioural signal rather than a class marker.
            if not is_fraud and rng.random() < 0.80:
                m = rng.choice(acc.fav_merchants)
            elif is_fraud and rng.random() < 0.35:
                m = rng.choice(acc.fav_merchants)
            else:
                weights = fraud_merchant_w if is_fraud else merchant_w
                m = rng.choices(merchants, weights=weights, k=1)[0]
            tx["merchant_id"] = m.id
            tx["merchant_category_code"] = m.mcc
            tx["merchant_risk_score"] = m.risk_score
        else:
            # Honestly missing rather than a fake 0.0 - a transfer has no
            # merchant, and 0.0 would be indistinguishable from a zero-risk one.
            tx["merchant_id"] = None
            tx["merchant_category_code"] = None
            tx["merchant_risk_score"] = None

        # Beneficiary.
        if ttype in BENEFICIARY_TYPES:
            if camp and camp in campaign_beneficiary and rng.random() < 0.6:
                # Campaigns push money to the same drop account.
                ben = campaign_beneficiary[camp]
            elif not is_fraud and rng.random() < 0.78:
                # Salary, rent, EMI, family - legit transfers repeat payees.
                ben = rng.choice(acc.fav_beneficiaries)
            elif is_fraud and rng.random() < 0.25:
                # Some fraud does route through a payee the account knows.
                ben = rng.choice(acc.fav_beneficiaries)
            else:
                ben = rng.choices(beneficiaries, weights=ben_w, k=1)[0]
                if camp:
                    campaign_beneficiary.setdefault(camp, ben)
            tx["beneficiary_account_id"] = ben
            tx["beneficiary_merchant_id"] = None
        else:
            tx["beneficiary_account_id"] = None
            tx["beneficiary_merchant_id"] = tx["merchant_id"]

        # Geography follows the account, with occasional travel/cross-border.
        if ttype in ("cross_border_transfer",) or rng.random() < 0.06:
            tx["location_country"] = _wchoice(rng, COUNTRY_WEIGHTS)
        else:
            tx["location_country"] = acc.country
        tx["currency"] = COUNTRY_CURRENCY.get(tx["location_country"], "INR")
        tx["location_region"] = acc.region if rng.random() < 0.88 else rng.choice(REGIONS)


# ============================================================
# STAGE 2: TIMESTAMPS
# ============================================================

def _assign_timestamps(txs, accounts, rng, cfg):
    """Give each account a coherent, bursty timeline inside the window.

    Both classes burst: legit bursts are payroll runs, bill day and shopping
    sprees; fraud bursts are campaigns. Because both burst, velocity stays
    informative without becoming a label.
    """
    window = cfg["window_days"]
    end = datetime.now().replace(microsecond=0)
    start = end - timedelta(days=window)

    # A campaign or recurring series occupies a contiguous slice of time, not
    # the whole window. Without this, _rebuild_campaigns' shuffle scattered each
    # campaign's transactions across all 90 days, so keeping campaigns whole in
    # the train/test split dragged ~18k rows across the boundary and left the
    # test set 94% fraud against a 41% train set.
    #
    # Duration mixture, in days. Both classes can produce all four modes - fraud
    # skews to bursts, legit to monthly recurrence - so the shape carries signal
    # while the support stays shared.
    DURATIONS = [(0.0007, 0.01), (0.01, 0.25), (0.5, 5.0), (10.0, 80.0)]
    W_FRAUD = [25, 35, 28, 12]
    W_LEGIT = [12, 25, 28, 35]

    for acc in accounts:
        if not acc.tx_indices:
            continue
        groups: Dict[str, List] = defaultdict(list)
        for i, tx in enumerate(acc.tx_indices):
            groups[tx.get("campaign_id") or f"solo_{i}"].append(tx)

        for rows in groups.values():
            rows.sort(key=lambda t: t.get("campaign_step") or 0)
            if len(rows) == 1:
                offsets = [rng.uniform(0, window)]
                span = 0.0
            else:
                w = W_FRAUD if rows[0]["is_fraud"] == 1 else W_LEGIT
                lo, hi = rng.choices(DURATIONS, weights=w, k=1)[0]
                span = rng.uniform(lo, hi)
                begin = rng.uniform(0, max(window - span, 0.0001))
                offsets = sorted(_clip(begin + rng.uniform(0, span), 0.0, window)
                                 for _ in rows)

            for off, tx in zip(offsets, rows):
                ts = start + timedelta(days=off)
                # Diurnal shaping, but only for series spread over days -
                # rewriting the hour inside a minutes-long burst would destroy
                # the burst that makes it a burst.
                if span > 0.5 and rng.random() < 0.78:
                    ts = ts.replace(hour=rng.choices(
                        range(24),
                        weights=[2, 1, 1, 1, 1, 2, 4, 6, 7, 8, 9, 9,
                                 8, 8, 8, 7, 7, 7, 6, 6, 5, 4, 3, 2],
                        k=1)[0])
                tx["timestamp"] = ts.isoformat()
                tx["_ts"] = ts


# ============================================================
# STAGE 3: LEGITIMATE SURFACE
# ============================================================

def _sample_legit_surface(tx, rng, acc):
    """Draw vocabulary + amount from the legitimate distribution.

    Used for legit rows and for evasive fraud, which is exactly what makes
    evasive fraud hard: it is drawn from the same distribution as legit.
    """
    ttype = _wchoice(rng, TRANSACTION_TYPE_WEIGHTS)
    # Rail is persona-biased but every rail keeps non-zero probability.
    rail_w = dict(PAYMENT_RAIL_WEIGHTS)
    for r, boost in acc.rails.items():
        rail_w[r] = rail_w.get(r, 1.0) * (1.0 + boost)
    rail = _wchoice(rng, rail_w)
    auth = _wchoice(rng, AUTH_METHOD_WEIGHTS)
    amount = _lognormal_mixture(rng, acc.amounts)
    # Low tail: micro-payments and autopay verifications are ordinary. Without
    # this, `amount < 100` would imply fraud (card testing) - the same leak
    # inverted.
    if rng.random() < 0.035:
        amount = rng.uniform(0.5, 100.0)
    amount = _clip(amount, 0.02, 10_000_000.0)

    tx["transaction_type"] = ttype
    tx["payment_rail"] = rail
    tx["authentication_method"] = auth
    tx["amount"] = round(amount, 2)


def _resample_legit(txs, rng, cfg):
    for tx in txs:
        if tx["is_fraud"] == 1:
            continue
        _sample_legit_surface(tx, rng, tx["_acc"])


# ============================================================
# STAGE 4: FRAUD EVASION MIX
# ============================================================

def _apply_evasion(txs, rng, cfg):
    """Assign each fraud row a sophistication level and dampen it accordingly.

    crude     - keep the family's loud signals as generated.
    moderate  - pull the risk surface halfway toward a legitimate draw.
    evasive   - draw the risk surface from the legitimate distribution outright
                and keep the amount inside the ordinary range (structuring).
    """
    mix = cfg["evasion_mix"]
    levels, weights = list(mix), [mix[k] for k in mix]

    for tx in txs:
        if tx["is_fraud"] != 1:
            tx["meta_evasion_level"] = "n/a"
            continue

        level = rng.choices(levels, weights=weights, k=1)[0]
        tx["meta_evasion_level"] = level
        acc = tx["_acc"]

        if level == "crude":
            continue

        if level == "moderate":
            # Blend the amount toward a legitimate draw for this persona.
            legit_amt = _lognormal_mixture(rng, acc.amounts)
            w = rng.uniform(0.35, 0.65)
            tx["amount"] = round(_clip(
                math.exp((1 - w) * math.log(max(tx["amount"], 0.02)) + w * math.log(legit_amt)),
                0.02, 10_000_000.0), 2)
            # Half the time, switch to an ordinary rail/auth method.
            if rng.random() < 0.5:
                tx["payment_rail"] = _wchoice(rng, PAYMENT_RAIL_WEIGHTS)
            if rng.random() < 0.5:
                tx["authentication_method"] = _wchoice(rng, AUTH_METHOD_WEIGHTS)
            # Prefer a merchant the account already knows.
            tx["_prefer_known_counterparty"] = rng.random() < 0.4
            tx["_prefer_known_device"] = rng.random() < 0.5
        else:  # evasive
            _sample_legit_surface(tx, rng, acc)
            # Threshold-conscious structuring: stay inside the ordinary band.
            tx["amount"] = round(min(tx["amount"], rng.uniform(4_000, 190_000)), 2)
            tx["_prefer_known_counterparty"] = True
            tx["_prefer_known_device"] = True


# ============================================================
# STAGE 5: HARD NEGATIVES
# ============================================================

def _apply_hard_negatives(txs, rng, cfg, merchants_by_risk):
    """Make a share of legit transactions genuinely look like fraud.

    These are the false positives a real fraud system pays for every day: the
    customer who buys a new phone, pays a brand-new payee a large amount, on a
    high-risk merchant, at 3am, while travelling.
    """
    rate = cfg["hard_negative_rate"]
    for tx in txs:
        if tx["is_fraud"] != 0 or rng.random() >= rate:
            continue
        tx["meta_hard_negative"] = True
        # Brand-new device -> is_new_device will be derived as True.
        tx["_force_new_device"] = True
        # Brand-new payee.
        if tx["transaction_type"] in BENEFICIARY_TYPES or rng.random() < 0.5:
            tx["transaction_type"] = rng.choice(
                ["transfer", "cross_border_transfer", "crypto_transfer"])
            tx["beneficiary_account_id"] = f"ben_{uuid.uuid4().hex[:10]}"
            tx["merchant_id"] = None
            tx["merchant_category_code"] = None
            tx["merchant_risk_score"] = None
        else:
            # High-risk merchant, which legit customers do use.
            m = rng.choice(merchants_by_risk)
            tx["merchant_id"] = m.id
            tx["merchant_category_code"] = m.mcc
            tx["merchant_risk_score"] = m.risk_score
        # Upper-tail amount.
        tx["amount"] = round(_clip(_lognormal_mixture(
            rng, [(0.5, 11.5, 1.0), (0.5, 13.2, 1.0)]), 0.02, 10_000_000.0), 2)
        # Odd hour.
        ts = tx["_ts"].replace(hour=rng.choice([0, 1, 2, 3, 4]))
        tx["_ts"] = ts
        tx["timestamp"] = ts.isoformat()


# ============================================================
# STAGE 6: DERIVED HISTORY (STRICTLY PRIOR-ONLY)
# ============================================================

def _derive_history(txs, rng, cfg):
    """Compute behavioural features from prior transactions only.

    Every transaction is processed in timestamp order and sees only the state
    accumulated from transactions strictly before it. State is updated after
    the features are written, so there is no lookahead by construction. The
    same formula is applied to both classes.
    """
    txs.sort(key=lambda t: t["_ts"])
    window_end = max(t["_ts"] for t in txs)

    hist_amt: Dict[str, deque] = defaultdict(deque)       # (ts, amount)
    seen_devices: Dict[str, Dict[str, datetime]] = defaultdict(dict)
    seen_counterparty: Dict[str, Dict[str, int]] = defaultdict(dict)
    ben_hist: Dict[str, deque] = defaultdict(deque)       # (ts, beneficiary)
    dev_hist: Dict[str, deque] = defaultdict(deque)       # (ts, device)
    acc_count: Dict[str, int] = defaultdict(int)
    acc_sum: Dict[str, float] = defaultdict(float)
    acc_sumsq: Dict[str, float] = defaultdict(float)

    for tx in txs:
        acc = tx["_acc"]
        aid = acc.id
        ts = tx["_ts"]
        amount = float(tx["amount"])

        # ---- device selection, then novelty derived from it ----
        if tx.pop("_force_new_device", False):
            device = f"dev_{uuid.uuid4().hex[:10]}"
        else:
            # Only devices that already existed by now are eligible.
            available = [d for d, first in acc.devices
                         if (window_end - timedelta(days=cfg["window_days"])
                             + timedelta(days=max(first, 0))) <= ts or first < 0]
            if not available:
                available = [acc.devices[0][0]]
            if tx.pop("_prefer_known_device", False):
                known = [d for d in available if d in seen_devices[aid]]
                device = known[0] if known else available[0]
            else:
                # Weight toward the primary device; occasionally a brand-new one.
                if rng.random() < 0.04:
                    device = f"dev_{uuid.uuid4().hex[:10]}"
                else:
                    device = rng.choices(
                        available,
                        weights=[3.0 / (i + 1) for i in range(len(available))], k=1)[0]
        tx["device_id"] = device
        tx["is_new_device"] = device not in seen_devices[aid]

        # ---- counterparty familiarity ----
        # Counterparty selection already happened in _assign_counterparties,
        # using the account's wallet with the SAME mechanic for both classes.
        # An earlier version additionally snapped evasive fraud onto the
        # account's most-used counterparty, which handed fraud a higher
        # familiarity score than legit ever got - the leak inverted.
        tx.pop("_prefer_known_counterparty", None)
        counterparty = tx.get("beneficiary_account_id") or tx.get("merchant_id")
        prior_cp = seen_counterparty[aid].get(counterparty, 0) if counterparty else 0
        tx["is_new_beneficiary"] = bool(counterparty) and prior_cp == 0
        tx["beneficiary_is_new"] = tx["is_new_beneficiary"]
        if counterparty:
            fam = min(1.0, prior_cp / 6.0)
            tx["merchant_familiarity_score"] = round(
                _clip(fam + rng.gauss(0, 0.05), 0.0, 1.0), 4)
        else:
            tx["merchant_familiarity_score"] = None

        # ---- rolling counts and averages (prior only) ----
        dq = hist_amt[aid]
        while dq and (ts - dq[0][0]).total_seconds() > 7 * 86400:
            dq.popleft()
        c1h = c24h = 0
        s1d = n1d = 0
        s7d = n7d = 0
        for pts, pamt in dq:
            dt = (ts - pts).total_seconds()
            if dt <= 3600:
                c1h += 1
            if dt <= 86400:
                c24h += 1
                s1d += pamt
                n1d += 1
            s7d += pamt
            n7d += 1

        tx["transaction_count_last_1h"] = c1h
        tx["transaction_count_last_24h"] = c24h
        tx["avg_amount_last_1d"] = round(s1d / n1d, 2) if n1d else 0.0
        tx["avg_amount_last_7d"] = round(s7d / n7d, 2) if n7d else 0.0
        tx["seconds_since_prev_tx"] = (
            int((ts - dq[-1][0]).total_seconds()) if dq else -1)

        avg7 = tx["avg_amount_last_7d"]
        tx["amount_to_avg_7d_ratio"] = round(amount / avg7, 4) if avg7 > 0 else None

        n = acc_count[aid]
        if n >= 3:
            mean = acc_sum[aid] / n
            var = max(acc_sumsq[aid] / n - mean * mean, 0.0)
            sd = math.sqrt(var)
            tx["amount_zscore_account"] = round((amount - mean) / sd, 4) if sd > 1e-9 else 0.0
        else:
            tx["amount_zscore_account"] = None
        tx["account_tx_count_to_date"] = n

        # distinct beneficiaries / devices in trailing windows
        bq = ben_hist[aid]
        while bq and (ts - bq[0][0]).total_seconds() > 86400:
            bq.popleft()
        tx["distinct_beneficiaries_last_24h"] = len({b for _, b in bq})
        dvq = dev_hist[aid]
        while dvq and (ts - dvq[0][0]).total_seconds() > 7 * 86400:
            dvq.popleft()
        tx["distinct_devices_last_7d"] = len({d for _, d in dvq})

        # ---- velocity: EARNED, identical formula for both classes ----
        vel = (0.42 * min(1.0, c1h / 6.0)
               + 0.28 * min(1.0, c24h / 20.0)
               + 0.18 * min(1.0, (amount / (avg7 + 1.0)) / 6.0)
               + 0.12 * min(1.0, tx["distinct_beneficiaries_last_24h"] / 5.0))
        tx["velocity_score"] = round(_clip(vel + rng.gauss(0, 0.05), 0.0, 1.0), 4)

        # ---- ages, consistent with the entity timeline ----
        first_seen = dict(acc.devices).get(device)
        if first_seen is None:
            tx["device_age_days"] = 0
        else:
            window_start = window_end - timedelta(days=cfg["window_days"])
            dev_dt = window_start + timedelta(days=max(first_seen, 0)) \
                if first_seen >= 0 else window_start + timedelta(days=first_seen)
            tx["device_age_days"] = max(0, int((ts - dev_dt).total_seconds() // 86400))
        days_before_end = (window_end - ts).total_seconds() / 86400.0
        tx["account_age_days"] = max(0, int(acc.age_days_at_end - days_before_end))

        # ---- card_present and auth_success: rule-based, same for both ----
        tx["card_present"] = (
            tx["payment_rail"] == "card"
            and tx["transaction_type"] in ("purchase", "refund")
            and rng.random() < 0.55)
        # Legit users fail auth (typos, expired OTPs); fraud usually succeeds,
        # because failed fraud rarely becomes a transaction. Nearly no signal.
        tx["auth_success"] = rng.random() < (0.955 if tx["is_fraud"] == 1 else 0.935)

        # ---- time-of-day features ----
        tx["hour_of_day"] = ts.hour
        tx["day_of_week"] = ts.weekday()
        tx["is_night"] = int(ts.hour < 6)

        # ---- update state AFTER writing features (no lookahead) ----
        dq.append((ts, amount))
        seen_devices[aid][device] = ts
        if counterparty:
            seen_counterparty[aid][counterparty] = prior_cp + 1
            bq.append((ts, counterparty))
        dvq.append((ts, device))
        acc_count[aid] = n + 1
        acc_sum[aid] += amount
        acc_sumsq[aid] += amount * amount


# ============================================================
# STAGE 7: SEQUENCE METADATA
# ============================================================

def _assign_sequences(txs, rng, cfg):
    """Give campaign_id / campaign_step shared support across both classes.

    Originally campaign_id was non-null for 100% of fraud and 0% of legit - a
    perfect label - and campaign_step was constant 0, so it carried nothing.
    Legit multi-step sequences are real: recurring mandates, EMI schedules,
    subscription renewals, onboarding funnels.
    """
    legit_by_account: Dict[str, List] = defaultdict(list)
    for tx in txs:
        if tx["is_fraud"] == 0:
            legit_by_account[tx["account_id"]].append(tx)

    # Legit series are chunked with the SAME size distribution as fraud
    # campaigns. A previous version keyed them on a random int, which almost
    # never collided, so legit series had 1-2 steps while fraud campaigns ran to
    # 25 - making campaign_step > 3 a near-perfect fraud rule (AUC 0.966).
    # Real legit series are long: 12 monthly EMIs, weekly grocery runs.
    for aid, rows in legit_by_account.items():
        rng.shuffle(rows)
        i = 0
        while i < len(rows):
            if rng.random() < 0.30:
                # A one-off purchase belongs to no series.
                rows[i]["campaign_id"] = None
                rows[i]["campaign_step"] = 0
                i += 1
                continue
            size = rng.choices([1, 2, 3, 5, 8, 14, 25],
                               weights=[18, 20, 18, 16, 13, 10, 5], k=1)[0]
            sid = f"seq_{aid[-8:]}_{uuid.uuid4().hex[:6]}"
            for step, tx in enumerate(rows[i:i + size]):
                tx["campaign_id"] = sid
                tx["campaign_step"] = step + 1
            i += size


def _number_sequence_steps(txs):
    """Renumber campaign_step in timestamp order.

    Runs after timestamps exist (and after hard negatives shift some of them),
    so step 1 is genuinely the first transaction in the series.
    """
    by_seq: Dict[str, List] = defaultdict(list)
    for tx in txs:
        if tx.get("campaign_id"):
            by_seq[tx["campaign_id"]].append(tx)
    for rows in by_seq.values():
        rows.sort(key=lambda t: t["_ts"])
        for i, tx in enumerate(rows):
            tx["campaign_step"] = i + 1


# ============================================================
# STAGE 8: LABEL NOISE
# ============================================================

def _apply_label_noise(txs, rng, cfg):
    """Ground truth is never clean.

    Some fraud is never detected and stays labelled legit; some legit is
    charged back and gets labelled fraud. Both directions cap achievable
    performance at a realistic level and are recorded in meta_ columns so the
    effect can be measured rather than guessed at.
    """
    flipped_f = flipped_l = 0
    for tx in txs:
        tx["meta_label_flipped"] = False
        if tx["is_fraud"] == 1 and rng.random() < cfg["fraud_labelled_legit"]:
            tx["is_fraud"] = 0
            tx["meta_label_flipped"] = True
            flipped_f += 1
        elif tx["is_fraud"] == 0 and rng.random() < cfg["legit_labelled_fraud"]:
            tx["is_fraud"] = 1
            tx["meta_label_flipped"] = True
            flipped_l += 1
    return flipped_f, flipped_l


# ============================================================
# ENTRY POINT
# ============================================================

def apply_realism(transactions: List[Dict[str, Any]], config=None) -> List[Dict[str, Any]]:
    cfg = {**DEFAULTS, **(config or {})}
    rng = random.Random(cfg["seed"])

    n = len(transactions)
    print(f"\n{'='*70}")
    print("APPLYING REALISM LAYER")
    print(f"{'='*70}")
    print(f"  Transactions:      {n:,}")

    for tx in transactions:
        tx.setdefault("meta_hard_negative", False)

    merchants = _build_merchants(rng, cfg)
    beneficiaries = [f"ben_{uuid.uuid4().hex[:10]}" for _ in range(cfg["n_beneficiaries"])]
    accounts = _build_accounts(rng, cfg, merchants, beneficiaries)
    print(f"  Entity pools:      {len(accounts):,} accounts "
          f"({sum(a.is_mule for a in accounts):,} mule), "
          f"{len(merchants):,} merchants")

    # Order matters. The surface (transaction_type / rail / amount) must be
    # final before counterparties are attached, and counterparties must be final
    # before history is derived from them.
    print("  [1/9] rebuilding fraud campaigns ...")
    n_camp = _rebuild_campaigns(transactions, rng, cfg)
    print(f"        {n_camp:,} campaigns")

    print("  [2/9] assigning accounts ...")
    _assign_accounts(transactions, accounts, rng, cfg)

    print("  [3/9] resampling legitimate surface (full vocabulary) ...")
    _resample_legit(transactions, rng, cfg)

    print("  [4/9] applying fraud evasion mix ...")
    _apply_evasion(transactions, rng, cfg)

    print("  [5/9] attaching counterparties and geography ...")
    _assign_counterparties(transactions, merchants, beneficiaries, rng, cfg)

    # Legit series must be grouped BEFORE timestamps, because timestamp
    # assignment gives each series a contiguous slice of the window.
    print("  [6/9] grouping legit recurring series ...")
    _assign_sequences(transactions, rng, cfg)

    print("  [7/9] building per-account timelines ...")
    _assign_timestamps(transactions, accounts, rng, cfg)

    print("  [8/9] injecting hard negatives ...")
    high_risk = sorted(merchants, key=lambda m: -m.risk_score)[:max(1, len(merchants) // 5)]
    _apply_hard_negatives(transactions, rng, cfg, high_risk)
    _number_sequence_steps(transactions)

    print("  [9/9] deriving history features (prior-only) ...")
    _derive_history(transactions, rng, cfg)

    print("  [+]   applying label noise ...")
    ff, fl = _apply_label_noise(transactions, rng, cfg)
    print(f"        {ff:,} fraud -> legit, {fl:,} legit -> fraud")

    # Strip internal scratch keys.
    for tx in transactions:
        tx.pop("_acc", None)
        tx.pop("_ts", None)
        tx.pop("_prefer_known_counterparty", None)
        tx.pop("_prefer_known_device", None)
        tx.pop("_force_new_device", None)

    n_fraud = sum(t["is_fraud"] for t in transactions)
    print(f"\n  Final: {n:,} rows, {n_fraud:,} fraud ({n_fraud/n*100:.1f}%)")
    print(f"{'='*70}")
    return transactions
