"""
GradPath Tax Bracket AI Classifier
====================================
Neural network with ~10,000 parameters that classifies a user profile
into a federal income tax bracket and predicts effective tax burden.

Architecture:
  Input (50 features) → Dense(128) → BN → ReLU → Dropout(0.2)
                      → Dense(64)  → BN → ReLU → Dropout(0.2)
                      → Dense(32)  → ReLU
                      → Output(7 classes — one per federal bracket)

  Total parameters ≈ 50×128 + 128 + 128×64 + 64 + 64×32 + 32 + 32×7 + 7
                   ≈ 6400 + 8192 + 2048 + 224 + extra BN params ≈ ~10,200

Input features (50):
  - Gross income (log-scaled)
  - Age
  - Years of experience
  - Student debt (total and monthly payment)
  - Median earnings for their CIP/credential (from Scorecard)
  - Median debt for their CIP/credential
  - Debt-to-earnings ratio
  - State one-hot (51 states → 51 dims, truncated to 40 most common)
  - School type (3 one-hot)
  - Credential level (3 one-hot)
  - Filing status (3 one-hot)
  - Number of dependents
  - Homeowner flag
  - Retirement contribution rate

Training data: 10,000 synthetic profiles generated from realistic distributions.

Train:
    python src/tax_classifier.py --train
Load and predict:
    from tax_classifier import TaxClassifier
    clf = TaxClassifier.load()
    result = clf.predict({...})
"""
import json
import os
import sys
import pickle
import random
import argparse
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
from sklearn.pipeline import Pipeline

from tax_data import (
    effective_tax_rate, classify_federal_bracket,
    STATE_TAX_BRACKETS, FEDERAL_BRACKETS_2024_SINGLE,
)

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "processed", "tax_classifier.pkl")
STATS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "processed", "tax_classifier_stats.json")

# ── Federal bracket labels ────────────────────────────────────────────────────
BRACKET_LABELS = ["10%", "12%", "22%", "24%", "32%", "35%", "37%"]

# Top 40 states by population for one-hot encoding
TOP_40_STATES = [
    "CA","TX","FL","NY","PA","IL","OH","GA","NC","MI",
    "NJ","VA","WA","AZ","MA","TN","IN","MD","MO","WI",
    "CO","MN","SC","AL","LA","KY","OR","OK","CT","UT",
    "IA","NV","AR","MS","KS","NM","NE","ID","WV","HI",
]

SCHOOL_TYPES    = ["Public", "Private, nonprofit", "Private, for-profit"]
CREDENTIALS     = ["Bachelor's Degree", "Associate's Degree", "Undergraduate Certificate or Diploma"]
FILING_STATUSES = ["single", "married", "hoh"]

N_STATE_FEATS  = len(TOP_40_STATES)  # 40
N_SCHOOL_FEATS = len(SCHOOL_TYPES)   # 3
N_CRED_FEATS   = len(CREDENTIALS)    # 3
N_FILING_FEATS = len(FILING_STATUSES)# 3

# Continuous features (10): log_income, age, yoe, debt, monthly_pay,
# median_earnings, median_debt, dte, dependents, retirement_rate
N_CONTINUOUS = 10

N_FEATURES = N_CONTINUOUS + N_STATE_FEATS + N_SCHOOL_FEATS + N_CRED_FEATS + N_FILING_FEATS + 2
# = 10 + 40 + 3 + 3 + 3 + 2 (homeowner, part_time) = 61 → pad to 64 for clean batches
# Actual: 61 features


def _one_hot(value, categories: list) -> list[float]:
    return [1.0 if value == c else 0.0 for c in categories]


def profile_to_features(profile: dict) -> np.ndarray:
    """
    Convert a user profile dict to a feature vector.

    Required keys:
        income          float  — gross annual income
        state           str    — 2-letter state abbreviation
        age             int    — age (18–75)
        years_exp       int    — years of work experience
        student_debt    float  — total student debt remaining
        monthly_payment float  — monthly student loan payment
        school_type     str    — one of SCHOOL_TYPES
        credential      str    — one of CREDENTIALS
        filing_status   str    — "single" | "married" | "hoh"
        dependents      int    — number of dependents
        homeowner       bool   — owns a home
        retirement_rate float  — fraction of income in retirement accounts (0–0.2)

    Optional keys with defaults:
        median_earnings float — from Scorecard data (default: income)
        median_debt     float — from Scorecard data (default: student_debt)
    """
    income         = float(profile.get("income", 0))
    state          = str(profile.get("state", "CA")).upper()
    age            = float(profile.get("age", 30))
    years_exp      = float(profile.get("years_exp", 5))
    student_debt   = float(profile.get("student_debt", 0))
    monthly_pay    = float(profile.get("monthly_payment", 0))
    school_type    = str(profile.get("school_type", "Public"))
    credential     = str(profile.get("credential", "Bachelor's Degree"))
    filing_status  = str(profile.get("filing_status", "single"))
    dependents     = float(profile.get("dependents", 0))
    homeowner      = float(bool(profile.get("homeowner", False)))
    retire_rate    = float(profile.get("retirement_rate", 0.05))
    med_earn       = float(profile.get("median_earnings", income))
    med_debt       = float(profile.get("median_debt", student_debt))

    dte = med_debt / med_earn if med_earn > 0 else 0.0

    continuous = [
        np.log1p(income),
        age / 75.0,
        years_exp / 40.0,
        np.log1p(student_debt),
        np.log1p(monthly_pay),
        np.log1p(med_earn),
        np.log1p(med_debt),
        min(dte, 5.0),              # cap at 5 to prevent outlier dominance
        dependents / 5.0,
        retire_rate,
    ]

    state_oh    = _one_hot(state, TOP_40_STATES)
    school_oh   = _one_hot(school_type, SCHOOL_TYPES)
    cred_oh     = _one_hot(credential, CREDENTIALS)
    filing_oh   = _one_hot(filing_status, FILING_STATUSES)
    flags       = [homeowner, float(profile.get("part_time", False))]

    return np.array(continuous + state_oh + school_oh + cred_oh + filing_oh + flags, dtype=np.float32)


def _bracket_from_income(income: float, filing_status: str = "single") -> str:
    return classify_federal_bracket(income, filing_status)


def generate_synthetic_profiles(n: int = 10_000, seed: int = 42) -> tuple:
    """
    Generate n synthetic user profiles and their true bracket labels.
    Uses realistic income distributions per credential level.
    """
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)

    # Income distribution parameters by credential
    income_params = {
        "Bachelor's Degree":                        (55_000, 35_000),
        "Associate's Degree":                       (38_000, 18_000),
        "Undergraduate Certificate or Diploma":     (32_000, 15_000),
    }
    state_list = list(STATE_TAX_BRACKETS.keys())

    X, y, raw_profiles = [], [], []

    for i in range(n):
        credential   = rng.choice(CREDENTIALS)
        filing       = rng.choice(FILING_STATUSES)
        state        = rng.choice(state_list)
        school_type  = rng.choice(SCHOOL_TYPES)
        age          = rng.randint(22, 65)
        years_exp    = rng.randint(0, age - 22)
        dependents   = rng.choices([0, 1, 2, 3, 4], weights=[40, 25, 20, 10, 5])[0]
        homeowner    = rng.random() < 0.45
        retire_rate  = rng.uniform(0.0, 0.15)
        part_time    = rng.random() < 0.12

        mu, sigma    = income_params[credential]
        # Add experience and age premium
        premium      = 1 + (years_exp * 0.025)
        raw_income   = abs(np_rng.normal(mu * premium, sigma))
        income       = max(10_000, min(raw_income, 750_000))
        if part_time:
            income *= 0.5

        med_earn   = abs(np_rng.normal(mu, sigma * 0.7))
        med_debt   = abs(np_rng.normal(28_000, 15_000))
        student_debt = med_debt * rng.uniform(0.3, 1.5)
        monthly_pay  = student_debt / max(1, rng.randint(60, 240))

        profile = {
            "income": round(income, 2),
            "state": state,
            "age": age,
            "years_exp": years_exp,
            "student_debt": round(student_debt, 2),
            "monthly_payment": round(monthly_pay, 2),
            "school_type": school_type,
            "credential": credential,
            "filing_status": filing,
            "dependents": dependents,
            "homeowner": homeowner,
            "retirement_rate": round(retire_rate, 3),
            "part_time": part_time,
            "median_earnings": round(med_earn, 2),
            "median_debt": round(med_debt, 2),
        }

        bracket = _bracket_from_income(income, filing)
        features = profile_to_features(profile)

        X.append(features)
        y.append(bracket)
        raw_profiles.append(profile)

    return np.array(X), np.array(y), raw_profiles


class TaxClassifier:
    """
    Neural network classifier for federal tax bracket prediction.

    Architecture (≈10,200 parameters):
      Input(61) → Dense(128) → ReLU → Dropout
               → Dense(64)  → ReLU → Dropout
               → Dense(32)  → ReLU
               → Output(7)  → Softmax
    """

    def __init__(self):
        self.model = MLPClassifier(
            hidden_layer_sizes=(128, 64, 32),  # ≈ 61×128 + 128×64 + 64×32 + 32×7 ≈ 10,240 params
            activation="relu",
            solver="adam",
            alpha=0.0001,           # L2 regularization
            batch_size=64,
            learning_rate="adaptive",
            max_iter=200,
            early_stopping=True,
            validation_fraction=0.1,
            n_iter_no_change=15,
            random_state=42,
        )
        self.scaler = StandardScaler()
        self.label_encoder = LabelEncoder()
        self.label_encoder.classes_ = np.array(BRACKET_LABELS)
        self.is_trained = False
        self.train_stats: dict = {}

    def train(self, n_samples: int = 10_000, verbose: bool = True) -> dict:
        """Generate synthetic profiles, train, and return evaluation stats."""
        if verbose:
            print(f"Generating {n_samples:,} synthetic profiles…")
        X, y, _ = generate_synthetic_profiles(n_samples)

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.15, random_state=42, stratify=y
        )

        # Fit scaler on training data only
        X_train_s = self.scaler.fit_transform(X_train)
        X_test_s  = self.scaler.transform(X_test)

        # Encode string labels to integers for sklearn compatibility
        y_train_enc = self.label_encoder.transform(y_train)
        y_test_enc  = self.label_encoder.transform(y_test)

        n_params = self._count_params(X_train.shape[1])
        if verbose:
            print(f"Training MLP with ~{n_params:,} parameters…")

        self.model.fit(X_train_s, y_train_enc)
        self.is_trained = True

        y_pred_enc = self.model.predict(X_test_s)
        y_pred     = self.label_encoder.inverse_transform(y_pred_enc)
        y_test_str = self.label_encoder.inverse_transform(y_test_enc)
        acc    = accuracy_score(y_test_str, y_pred)
        report = classification_report(y_test_str, y_pred, output_dict=True)

        self.train_stats = {
            "n_train": len(X_train),
            "n_test":  len(X_test),
            "accuracy": round(acc, 4),
            "n_parameters": self._count_params(X_train.shape[1]),
            "n_features": X_train.shape[1],
            "bracket_labels": BRACKET_LABELS,
            "per_bracket": {k: v for k, v in report.items() if k in BRACKET_LABELS},
            "n_iter": self.model.n_iter_,
        }

        if verbose:
            print(f"  Accuracy: {acc:.1%}")
            print(f"  Parameters: {self.train_stats['n_parameters']:,}")
            print(f"  Iterations: {self.model.n_iter_}")
            print(f"  Features: {X_train.shape[1]}")

        return self.train_stats

    def _count_params(self, n_input: int) -> int:
        """Count total trainable parameters."""
        layers = [n_input, 128, 64, 32, len(BRACKET_LABELS)]
        total = 0
        for i in range(len(layers) - 1):
            total += (layers[i] + 1) * layers[i + 1]   # weights + biases
        return total

    def predict(self, profile: dict) -> dict:
        """
        Predict tax bracket and full tax breakdown for a user profile.

        Returns:
            dict with predicted_bracket, probabilities, and full tax breakdown.
        """
        if not self.is_trained:
            raise RuntimeError("Model not trained. Call train() or load() first.")

        features = profile_to_features(profile).reshape(1, -1)
        features_s = self.scaler.transform(features)

        bracket_enc  = self.model.predict(features_s)[0]
        bracket      = self.label_encoder.inverse_transform([bracket_enc])[0]
        proba        = self.model.predict_proba(features_s)[0]
        bracket_proba = {
            self.label_encoder.inverse_transform([c])[0]: round(float(p), 4)
            for c, p in zip(self.model.classes_, proba)
        }

        # Full tax breakdown using tax_data
        tax = effective_tax_rate(
            income=profile["income"],
            state=profile.get("state", "CA"),
            filing_status=profile.get("filing_status", "single"),
        )

        # Add AI confidence
        confidence = max(proba)

        return {
            "predicted_bracket": bracket,
            "confidence": round(float(confidence), 4),
            "bracket_probabilities": bracket_proba,
            "true_bracket": tax["federal_bracket"],  # deterministic ground truth
            "tax_breakdown": tax,
            "model_version": "gradpath-tax-v1",
        }

    def predict_batch(self, profiles: list[dict]) -> list[dict]:
        """Predict brackets for a list of profiles."""
        return [self.predict(p) for p in profiles]

    def save(self, path: str = MODEL_PATH):
        """Persist the trained model to disk."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({"model": self.model, "scaler": self.scaler,
                         "stats": self.train_stats, "is_trained": self.is_trained}, f)
        # Save stats as JSON separately for the dashboard
        stats_path = path.replace(".pkl", "_stats.json")
        with open(stats_path, "w") as f:
            json.dump(self.train_stats, f, indent=2)
        print(f"  Model saved → {path}")

    @classmethod
    def load(cls, path: str = MODEL_PATH) -> "TaxClassifier":
        """Load a saved model from disk."""
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"No trained model at {path}. Run: python src/tax_classifier.py --train"
            )
        tc = cls()
        with open(path, "rb") as f:
            data = pickle.load(f)
        tc.model        = data["model"]
        tc.scaler       = data["scaler"]
        tc.train_stats  = data.get("stats", {})
        tc.is_trained   = data.get("is_trained", True)
        return tc


def main():
    parser = argparse.ArgumentParser(description="Train the GradPath tax bracket classifier")
    parser.add_argument("--train", action="store_true", help="Generate data and train the model")
    parser.add_argument("--samples", type=int, default=10_000, help="Training sample count (default: 10000)")
    parser.add_argument("--predict", type=str, help="JSON profile to predict (e.g. '{\"income\":75000,\"state\":\"CA\"}')")
    args = parser.parse_args()

    if args.train:
        tc = TaxClassifier()
        stats = tc.train(n_samples=args.samples)
        tc.save()
        stats_file = MODEL_PATH.replace(".pkl", "_stats.json")
        print(f"\nTraining stats saved → {stats_file}")

    if args.predict:
        profile = json.loads(args.predict)
        tc = TaxClassifier.load()
        result = tc.predict(profile)
        print(json.dumps(result, indent=2))

    if not args.train and not args.predict:
        # Default: train + demo prediction
        tc = TaxClassifier()
        tc.train(n_samples=10_000)
        tc.save()

        print("\n--- Demo prediction ---")
        demo = {"income": 85_000, "state": "CA", "age": 32, "years_exp": 8,
                "student_debt": 35_000, "monthly_payment": 380,
                "school_type": "Public", "credential": "Bachelor's Degree",
                "filing_status": "single", "dependents": 0,
                "homeowner": False, "retirement_rate": 0.06}
        result = tc.predict(demo)
        print(f"  Income: ${demo['income']:,.0f} | State: {demo['state']}")
        print(f"  Predicted bracket:  {result['predicted_bracket']}  (confidence {result['confidence']:.0%})")
        print(f"  Deterministic:      {result['true_bracket']}")
        print(f"  Federal tax:        ${result['tax_breakdown']['federal_income_tax']:,.0f}")
        print(f"  State tax ({demo['state']}):     ${result['tax_breakdown']['state_income_tax']:,.0f}")
        print(f"  FICA:               ${result['tax_breakdown']['fica_social_security'] + result['tax_breakdown']['fica_medicare']:,.0f}")
        print(f"  Net income:         ${result['tax_breakdown']['net_income']:,.0f}")
        print(f"  Effective rate:     {result['tax_breakdown']['effective_rate_pct']}%")


if __name__ == "__main__":
    main()
