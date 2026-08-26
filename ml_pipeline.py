"""Local, reproducible student-dropout ML pipeline.

This module is deliberately independent of Databricks so the Flask app can be
run and demonstrated locally with a real CSV, trained models, SHAP output and
fairness metrics.  Each invocation creates a versioned Bronze/Silver/Gold run
under ``runtime_data/runs``.  Only an explicitly activated run is shown by the
dashboard.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# SHAP imports Matplotlib. Give its cache a location writable in both local
# development and Vercel's serverless runtime before importing SHAP.
os.environ.setdefault(
    "MPLCONFIGDIR",
    "/tmp/dropout_signal_matplotlib" if os.environ.get("VERCEL") else str(Path(__file__).resolve().parent / ".matplotlib_cache"),
)

import joblib
import mlflow
from mlflow.models import infer_signature
import numpy as np
import pandas as pd
import shap
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier


# Fast enough for an interactive upload while retaining a properly evaluated
# XGBoost candidate, per-student SHAP values, and the model-comparison flow.
XGB_TRAINING_PARAMS = {
    "n_estimators": 120,
    "max_depth": 4,
    "learning_rate": 0.12,
    "subsample": 0.85,
    "colsample_bytree": 0.85,
    "tree_method": "hist",
    "n_jobs": -1,
}
LOGISTIC_MAX_ITER = 400
RANDOM_FOREST_PARAMS = {
    "n_estimators": 240,
    "max_depth": 12,
    "min_samples_leaf": 3,
    "class_weight": "balanced",
    "n_jobs": -1,
}
HIST_GRADIENT_BOOSTING_PARAMS = {
    "max_iter": 180,
    "learning_rate": 0.08,
    "max_leaf_nodes": 20,
    "l2_regularization": 0.1,
}


ROOT = Path(__file__).resolve().parent
DATASETS_DIR = ROOT / "datasets"
# Vercel permits writes only under /tmp. Local development keeps durable runs
# in the repository folder. A hosted serverless run is therefore functional
# but intentionally ephemeral unless persistent object storage is configured.
RUNTIME_DIR = Path(os.environ.get("DROPOUT_SIGNAL_RUNTIME_DIR", "/tmp/dropout_signal_runtime" if os.environ.get("VERCEL") else str(ROOT / "runtime_data")))
RUNS_DIR = RUNTIME_DIR / "runs"
UPLOADS_DIR = RUNTIME_DIR / "uploads"
ACTIVE_RUN_FILE = RUNTIME_DIR / "active_run.json"

# The dashboard asks several endpoints for the same active run while opening.
# Keep its Gold table in-process so list and detail pages do not repeatedly
# parse thousands of CSV rows. The cache is invalidated whenever activation
# changes the run id.
_ACTIVE_RECORD_CACHE: dict[str, Any] = {"run_id": None, "frame": None}

TARGET_COLUMN = "Target"
STUDENT_NAME_COLUMN = "Student Name"
# These are the 36 predictor columns supplied by a UCI-compatible upload.
# ``FEATURE_COLUMNS`` below adds the seven Silver-layer signals from the
# original Databricks notebook; callers should validate uploads against the
# raw schema, not against those derived columns.
RAW_FEATURE_COLUMNS = [
    "Marital Status",
    "Application mode",
    "Application order",
    "Course",
    "Daytime/evening attendance",
    "Previous qualification",
    "Previous qualification (grade)",
    "Nacionality",
    "Mother's qualification",
    "Father's qualification",
    "Mother's occupation",
    "Father's occupation",
    "Admission grade",
    "Displaced",
    "Educational special needs",
    "Debtor",
    "Tuition fees up to date",
    "Gender",
    "Scholarship holder",
    "Age at enrollment",
    "International",
    "Curricular units 1st sem (credited)",
    "Curricular units 1st sem (enrolled)",
    "Curricular units 1st sem (evaluations)",
    "Curricular units 1st sem (approved)",
    "Curricular units 1st sem (grade)",
    "Curricular units 1st sem (without evaluations)",
    "Curricular units 2nd sem (credited)",
    "Curricular units 2nd sem (enrolled)",
    "Curricular units 2nd sem (evaluations)",
    "Curricular units 2nd sem (approved)",
    "Curricular units 2nd sem (grade)",
    "Curricular units 2nd sem (without evaluations)",
    "Unemployment rate",
    "Inflation rate",
    "GDP",
]

ENGINEERED_FEATURE_COLUMNS = [
    "grade_trajectory",
    "financial_stress_index",
    "curricular_engagement_sem1",
    "curricular_engagement_sem2",
    "semester_grade_delta",
    "economic_pressure_index",
    "age_risk_flag",
]

FEATURE_COLUMNS = RAW_FEATURE_COLUMNS + ENGINEERED_FEATURE_COLUMNS

FEATURE_GROUPS = {
    "Enrolment and background": RAW_FEATURE_COLUMNS[:13],
    "Support and financial context": RAW_FEATURE_COLUMNS[13:21],
    "Academic progression": RAW_FEATURE_COLUMNS[21:33],
    "Economic context": RAW_FEATURE_COLUMNS[33:],
    "Silver engineered signals": ENGINEERED_FEATURE_COLUMNS,
}

COURSE_MAP = {
    33: "Biofuel Production Technologies",
    171: "Animation and Multimedia Design",
    801: "Social Service",
    9003: "Agronomy",
    9070: "Communication Design",
    9085: "Veterinary Nursing",
    9119: "Informatics Engineering",
    9130: "Equiniculture",
    9147: "Management",
    9238: "Social Service (evening)",
    9254: "Tourism",
    9500: "Nursing",
    9556: "Oral Hygiene",
    9670: "Advertising and Marketing Management",
    9773: "Journalism and Communication",
    9853: "Basic Education",
    9991: "Management (evening)",
}

FIRST_NAMES = [
    "Aarav", "Aditi", "Akshat", "Ananya", "Arjun", "Divya", "Gaurav", "Kiran",
    "Meera", "Maya", "Neha", "Priya", "Riya", "Rohan", "Sakshi", "Suman",
    "Vikram", "Aisha", "Kabir", "Nandini", "Ishaan", "Tara", "Yash", "Farhan",
]
LAST_NAMES = [
    "Bose", "Chauhan", "Das", "Dutta", "Gupta", "Iyer", "Joshi", "Kapoor",
    "Kumar", "Menon", "Nair", "Patel", "Rao", "Reddy", "Sen", "Sharma",
    "Singh", "Thakur", "Tiwari", "Verma", "Yadav", "Bhat", "Desai", "Mehta",
]
MIDDLE_NAMES = [
    "Aanya", "Dev", "Ira", "Kiran", "Manav", "Nila", "Om", "Rhea",
    "Saanvi", "Tara", "Veer", "Zoya",
]


class DatasetValidationError(ValueError):
    """Raised when an uploaded file cannot run through the real model."""


def _ensure_dirs() -> None:
    for directory in (DATASETS_DIR, RUNTIME_DIR, RUNS_DIR, UPLOADS_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Cannot serialize {type(value)!r}")


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, default=_json_default), encoding="utf-8")


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned[:55] or "dataset"


def _display_feature(feature: str) -> str:
    return feature.replace("Curricular units", "Curricular units").replace("sem", "semester")


def read_dataset(path: str | Path) -> pd.DataFrame:
    """Read a UCI-formatted CSV while accepting comma or semicolon files."""
    source = Path(path)
    if not source.exists():
        raise DatasetValidationError("The selected CSV file no longer exists.")
    sample = source.read_text(encoding="utf-8-sig", errors="replace")[:4096]
    delimiter = ";" if sample.count(";") > sample.count(",") else ","
    try:
        frame = pd.read_csv(source, sep=delimiter, encoding="utf-8-sig")
    except Exception as exc:  # pandas provides the exact parse issue
        raise DatasetValidationError(f"Unable to read CSV: {exc}") from exc

    frame.columns = [str(column).strip() for column in frame.columns]
    aliases = {column.lower(): column for column in frame.columns}
    rename: dict[str, str] = {}
    for required in RAW_FEATURE_COLUMNS + [TARGET_COLUMN]:
        found = aliases.get(required.lower())
        if found and found != required:
            rename[found] = required
    frame = frame.rename(columns=rename)
    missing = [column for column in RAW_FEATURE_COLUMNS + [TARGET_COLUMN] if column not in frame.columns]
    if missing:
        raise DatasetValidationError(
            "CSV must contain the 36 UCI predictor fields plus Target. Missing: " + ", ".join(missing[:8])
        )
    if len(frame) < 100:
        raise DatasetValidationError("A minimum of 100 student rows is required to train and evaluate both models.")

    # A name is useful dashboard metadata, but it is deliberately never a
    # model feature. Accept common spellings so external institutional exports
    # can be used as well as the bundled sample datasets.
    name_column = next((aliases.get(alias) for alias in ("student name", "student_name", "name") if aliases.get(alias)), None)
    selected_columns = RAW_FEATURE_COLUMNS + [TARGET_COLUMN] + ([name_column] if name_column else [])
    selected = frame[selected_columns].copy()
    if name_column:
        selected = selected.rename(columns={name_column: STUDENT_NAME_COLUMN})
    for column in RAW_FEATURE_COLUMNS:
        selected[column] = pd.to_numeric(selected[column], errors="coerce")
        if selected[column].isna().all():
            raise DatasetValidationError(f"'{column}' does not contain numeric values.")
        selected[column] = selected[column].fillna(selected[column].median())
    selected[TARGET_COLUMN] = selected[TARGET_COLUMN].astype(str).str.strip()
    encoded = _encode_target(selected[TARGET_COLUMN])
    if encoded.nunique() < 2:
        raise DatasetValidationError("Target must contain dropout and non-dropout outcomes so both models can train.")
    if STUDENT_NAME_COLUMN in selected.columns:
        selected[STUDENT_NAME_COLUMN] = selected[STUDENT_NAME_COLUMN].fillna("").astype(str).str.strip()
    return selected


def build_silver(source: pd.DataFrame) -> pd.DataFrame:
    """Reproduce the notebook's Silver cleaning and feature-engineering step."""
    silver = source.copy()
    silver["is_dropout"] = _encode_target(silver[TARGET_COLUMN])

    average_grade_sem1 = silver["Curricular units 1st sem (grade)"].astype(float)
    average_grade_sem2 = silver["Curricular units 2nd sem (grade)"].astype(float)
    silver["grade_trajectory"] = (average_grade_sem2 - average_grade_sem1).round(4)

    # Same weights and macro normalisation used by dropout_pipeline.ipynb.
    tuition_stress = (1 - silver["Tuition fees up to date"].astype(float)) * 0.35
    debtor_stress = silver["Debtor"].astype(float) * 0.25
    no_scholarship = (1 - silver["Scholarship holder"].astype(float)) * 0.20
    inflation_norm = silver["Inflation rate"].astype(float) / 5.0 * 0.10
    gdp_norm = (1 - silver["GDP"].astype(float) / 5.0) * 0.10
    silver["financial_stress_index"] = (tuition_stress + debtor_stress + no_scholarship + inflation_norm + gdp_norm).round(4)

    first_enrolled = silver["Curricular units 1st sem (enrolled)"].astype(float)
    second_enrolled = silver["Curricular units 2nd sem (enrolled)"].astype(float)
    silver["curricular_engagement_sem1"] = np.where(
        first_enrolled > 0,
        silver["Curricular units 1st sem (approved)"].astype(float) / first_enrolled,
        0.0,
    ).round(4)
    silver["curricular_engagement_sem2"] = np.where(
        second_enrolled > 0,
        silver["Curricular units 2nd sem (approved)"].astype(float) / second_enrolled,
        0.0,
    ).round(4)
    silver["semester_grade_delta"] = (average_grade_sem2 - average_grade_sem1).round(4)
    silver["economic_pressure_index"] = (
        silver["Unemployment rate"].astype(float)
        * silver["Inflation rate"].astype(float)
        / np.maximum(np.abs(silver["GDP"].astype(float)), 0.1)
    ).round(4)
    silver["age_risk_flag"] = (silver["Age at enrollment"].astype(float) > 25).astype(int)
    return silver


def _encode_target(target: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(target, errors="coerce")
    if numeric.notna().all() and set(numeric.astype(int).unique()).issubset({0, 1}):
        return numeric.astype(int)
    return target.astype(str).str.lower().str.contains("dropout").astype(int)


def _metric_bundle(y_true: pd.Series | np.ndarray, probability: np.ndarray) -> dict[str, float]:
    prediction = (probability >= 0.5).astype(int)
    return {
        "accuracy": round(float(accuracy_score(y_true, prediction)), 4),
        "precision": round(float(precision_score(y_true, prediction, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, prediction, zero_division=0)), 4),
        "f1_score": round(float(f1_score(y_true, prediction, zero_division=0)), 4),
        "auc_roc": round(float(roc_auc_score(y_true, probability)), 4),
    }


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return round(float(numerator / denominator), 4)


def _group_metrics(frame: pd.DataFrame, group_column: str, group_a: str, group_b: str, model_name: str) -> dict[str, Any]:
    left = frame[frame[group_column] == group_a]
    right = frame[frame[group_column] == group_b]
    def values(group: pd.DataFrame) -> tuple[float, float, float]:
        flag_rate = float(group["prediction"].mean()) if len(group) else 0.0
        positives = group[group["actual"] == 1]
        tpr = float(positives["prediction"].mean()) if len(positives) else 0.0
        selected = group[group["prediction"] == 1]
        precision = float(selected["actual"].mean()) if len(selected) else 0.0
        return flag_rate, tpr, precision
    flag_a, tpr_a, precision_a = values(left)
    flag_b, tpr_b, precision_b = values(right)
    dp = _safe_ratio(flag_a, flag_b)
    eo = _safe_ratio(tpr_a, tpr_b)
    pp = _safe_ratio(precision_a, precision_b)
    return {
        "protected_attribute": group_column,
        "group_a": group_a,
        "group_b": group_b,
        "group_a_count": int(len(left)),
        "group_b_count": int(len(right)),
        "flag_rate_a": round(flag_a, 4),
        "flag_rate_b": round(flag_b, 4),
        "demographic_parity_ratio": dp,
        "dp_is_fair": "YES" if dp is not None and 0.8 <= dp <= 1.25 else "NO",
        "tpr_a": round(tpr_a, 4),
        "tpr_b": round(tpr_b, 4),
        "equal_opportunity_ratio": eo,
        "eo_is_fair": "YES" if eo is not None and 0.8 <= eo <= 1.25 else "NO",
        "precision_a": round(precision_a, 4),
        "precision_b": round(precision_b, 4),
        "predictive_parity_ratio": pp,
        "pp_is_fair": "YES" if pp is not None and 0.8 <= pp <= 1.25 else "NO",
        "model": model_name,
    }


def _fairness(frame: pd.DataFrame, actual: pd.Series, probability: np.ndarray, model_name: str) -> list[dict[str, Any]]:
    audit = pd.DataFrame({"actual": actual.astype(int), "prediction": (probability >= 0.5).astype(int)})
    audit["gender"] = frame["Gender"].astype(str)
    audit["socioeconomic"] = np.where(
        (frame["Scholarship holder"] == 1) | (frame["Tuition fees up to date"] == 0),
        "disadvantaged",
        "advantaged",
    )
    results: list[dict[str, Any]] = []
    gender_values = sorted(audit["gender"].unique())
    if len(gender_values) >= 2:
        results.append(_group_metrics(audit, "gender", gender_values[0], gender_values[1], model_name))
    results.append(_group_metrics(audit, "socioeconomic", "disadvantaged", "advantaged", model_name))
    return results


def _course_name(value: Any) -> str:
    try:
        return COURSE_MAP.get(int(float(value)), f"Program {int(float(value))}")
    except (ValueError, TypeError):
        return f"Program {value}"


def _root_cause(feature: str) -> str:
    name = feature.lower()
    if any(token in name for token in ("tuition", "debtor", "scholarship", "unemployment", "gdp", "inflation")):
        return "Financial and economic pressure"
    if "curricular" in name or "grade" in name or "admission" in name:
        return "Academic progression"
    if any(token in name for token in ("age", "marital", "qualification", "occupation", "nationality", "gender", "international")):
        return "Student background and transition"
    return "Engagement and enrolment context"


def _recommended_action(tier: str) -> str:
    return {
        "HIGH": "Immediate 1-on-1 counseling and financial-aid review",
        "MEDIUM": "Advisor check-in and academic support plan within one week",
        "LOW": "Monitor progress and maintain routine support",
    }[tier]


def _name_for(index: int, signature: str) -> str:
    # Keep a stable counselor test profile in every bundled dataset.  Names are
    # metadata for the interface and are explicitly excluded from model inputs.
    if index == 0:
        return "Achal sangami"
    offset = int(signature[:8], 16)
    first = FIRST_NAMES[(index + offset) % len(FIRST_NAMES)]
    last = LAST_NAMES[((index // len(FIRST_NAMES)) + offset) % len(LAST_NAMES)]
    # The bundled cohorts can contain thousands of rows. A third name gives
    # us 6,912 natural-language combinations without displaying ID suffixes.
    middle = MIDDLE_NAMES[((index // (len(FIRST_NAMES) * len(LAST_NAMES))) + offset) % len(MIDDLE_NAMES)]
    return f"{first} {middle} {last}"


def _shap_values(model: XGBClassifier, features: pd.DataFrame) -> np.ndarray:
    # Process in chunks to prevent OOM on Render
    return _batched_shap_values(model, features)

def _batched_shap_values(model, features, chunk_size=250):
    explainer = shap.TreeExplainer(model)
    all_values = []
    for i in range(0, len(features), chunk_size):
        chunk = features.iloc[i:i+chunk_size]
        v = explainer.shap_values(chunk, check_additivity=False)
        v = np.asarray(v)
        if v.ndim == 3:
            v = v[:, :, 1]
        all_values.append(v)
    return np.vstack(all_values)

def _gold_table(
    source: pd.DataFrame,
    signature: str,
    logistic_score: np.ndarray,
    xgb_score: np.ndarray,
    random_forest_score: np.ndarray,
    hist_gradient_boosting_score: np.ndarray,
    ensemble_score: np.ndarray,
    ensemble_name: str,
    ensemble_weights: dict[str, float],
    shap_values: np.ndarray,
) -> pd.DataFrame:
    frame = source.copy().reset_index(drop=True)
    frame.insert(0, "student_id", [f"STU-{signature[:6].upper()}-{index + 1:05d}" for index in range(len(frame))])
    # Student names are presentation metadata. Normalise every upload so
    # duplicate supplied names and old generated number suffixes never appear
    # in student directories, risk predictions, or summaries.
    resolved_names = [_name_for(index, signature) for index in range(len(frame))]
    frame.insert(1, "student_name", resolved_names)
    frame["logistic_risk_score"] = np.round(logistic_score, 4)
    frame["xgboost_risk_score"] = np.round(xgb_score, 4)
    frame["random_forest_risk_score"] = np.round(random_forest_score, 4)
    frame["hist_gradient_boosting_risk_score"] = np.round(hist_gradient_boosting_score, 4)
    frame["ensemble_risk_score"] = np.round(ensemble_score, 4)
    # The Gold score is a validation-weighted blend of all four independently
    # trained candidates.  This is a deterministic ML result, not an LLM
    # claim; the exact weights are retained with every scored student.
    frame["ml_risk_score"] = np.round(ensemble_score, 4)
    frame["ai_risk_score"] = np.round(ensemble_score, 4)
    frame["champion_model"] = ensemble_name
    frame["ensemble_members"] = "Logistic Regression | XGBoost | Random Forest | HistGradientBoosting"
    frame["ensemble_weights"] = json.dumps(ensemble_weights, sort_keys=True)
    frame["predicted_dropout"] = (ensemble_score >= 0.5).astype(int)
    frame["actual_outcome"] = frame[TARGET_COLUMN].astype(str)
    frame["final_risk_tier"] = np.where(ensemble_score >= 0.70, "HIGH", np.where(ensemble_score >= 0.40, "MEDIUM", "LOW"))
    frame["course"] = "Degree program"
    frame["branch"] = frame["Course"].map(_course_name)
    frame["year"] = np.where(frame["Age at enrollment"] >= 25, 2, 1).astype(int)
    frame["semester"] = np.where(frame["Curricular units 2nd sem (enrolled)"] > 0, 2, 1).astype(int)
    evaluation = frame["Curricular units 1st sem (evaluations)"] + frame["Curricular units 2nd sem (evaluations)"]
    approved = frame["Curricular units 1st sem (approved)"] + frame["Curricular units 2nd sem (approved)"]
    frame["attendance_rate"] = np.round(np.clip(48 + 52 * np.divide(approved, np.maximum(evaluation, 1)), 48, 100), 1)
    grade = (frame["Curricular units 1st sem (grade)"] + frame["Curricular units 2nd sem (grade)"]) / 2
    frame["latest_marks"] = np.round(np.clip(grade * 5, 0, 100), 1).astype(str) + "%"
    frame["current_gpa"] = np.round(np.clip(grade / 5, 0, 4), 2)
    frame["lms_engagement"] = np.where(approved / np.maximum(evaluation, 1) < 0.45, "Low", np.where(approved / np.maximum(evaluation, 1) < 0.72, "Moderate", "Good"))
    frame["financial_aid_status"] = np.where(
        frame["Debtor"] == 1,
        "Debt review required",
        np.where(frame["Tuition fees up to date"] == 0, "Fee status review", np.where(frame["Scholarship holder"] == 1, "Scholarship holder", "In good standing")),
    )
    credits = frame["Curricular units 1st sem (credited)"] + frame["Curricular units 2nd sem (credited)"]
    frame["credits_completed"] = credits.round().astype(int).astype(str) + " / 120"

    order = np.argsort(-np.abs(shap_values), axis=1)[:, :3]
    for rank in range(3):
        indices = order[:, rank]
        names = [FEATURE_COLUMNS[index] for index in indices]
        values = shap_values[np.arange(len(frame)), indices]
        frame[f"top_factor_{rank + 1}"] = [f"{_display_feature(name)} ({value:+.3f})" for name, value in zip(names, values)]
        frame[f"shap_factor_{rank + 1}_name"] = names
        frame[f"shap_factor_{rank + 1}_value"] = np.round(values, 4)
    frame["primary_root_cause"] = frame["shap_factor_1_name"].map(_root_cause)
    frame["recommended_owner"] = np.where(frame["final_risk_tier"] == "HIGH", "Student Success + Financial Aid", np.where(frame["final_risk_tier"] == "MEDIUM", "Academic Counselor", "Student Success Monitoring"))
    frame["final_action"] = frame["final_risk_tier"].map(_recommended_action)
    frame["shap_summary"] = frame.apply(lambda row: "; ".join(str(row[f"top_factor_{rank}"]) for rank in range(1, 4)), axis=1)
    return frame.sort_values(["ml_risk_score", "student_id"], ascending=[False, True]).reset_index(drop=True)


def _log_mlflow_run(
    run_id: str,
    run_dir: Path,
    x_train: pd.DataFrame,
    logistic: LogisticRegression,
    xgb: XGBClassifier,
    random_forest: RandomForestClassifier,
    hist_gradient_boosting: HistGradientBoostingClassifier,
    model_metrics: dict[str, dict[str, float]],
    ensemble_weights: dict[str, float],
    record_count: int,
    ensemble_name: str,
) -> dict[str, Any]:
    """Create a local, inspectable MLflow tracking and registry record."""
    if os.environ.get("RENDER"):
        return {"skipped": True, "reason": "MLflow disabled on Render to conserve RAM."}
        
    tracking_dir = RUNTIME_DIR / "mlflow"
    tracking_dir.mkdir(parents=True, exist_ok=True)
    database_path = tracking_dir / "tracking.db"
    artifact_dir = tracking_dir / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    # MLflow 3 requires a database-backed tracking store for current registry
    # support. SQLite keeps this entirely local and gives us real model
    # registration rather than a metadata-only imitation.
    tracking_uri = f"sqlite:///{database_path.resolve().as_posix()}"
    mlflow.set_tracking_uri(tracking_uri)
    client = mlflow.MlflowClient()
    experiment = client.get_experiment_by_name("dropout-signal-local")
    if experiment is None:
        experiment_id = client.create_experiment("dropout-signal-local", artifact_location=artifact_dir.resolve().as_uri())
        experiment = client.get_experiment(experiment_id)
    mlflow.set_experiment(experiment_id=experiment.experiment_id)
    with mlflow.start_run(run_name=run_id) as run:
        mlflow.set_tags({
            "project": "Dropout Signal",
            "dataset_pipeline": "Bronze/Silver/Gold",
            "champion_model": ensemble_name,
            "ensemble_members": "four validation-weighted models",
            "feature_schema": "UCI 36 predictors + Target",
        })
        mlflow.log_params({
            "record_count": record_count,
            "feature_count": len(FEATURE_COLUMNS),
            "logistic_C": 1.0,
            "logistic_solver": "lbfgs",
            "logistic_max_iter": LOGISTIC_MAX_ITER,
            **{f"xgb_{key}": value for key, value in XGB_TRAINING_PARAMS.items()},
            **{f"random_forest_{key}": value for key, value in RANDOM_FOREST_PARAMS.items()},
            **{f"hist_gradient_boosting_{key}": value for key, value in HIST_GRADIENT_BOOSTING_PARAMS.items()},
            **{f"ensemble_weight_{_slug(name)}": value for name, value in ensemble_weights.items()},
            "train_test_split": "80/20 stratified, random_state=42",
        })
        mlflow.log_metrics({
            **{f"{_slug(name)}_{key}": float(value) for name, metrics in model_metrics.items() for key, value in metrics.items()},
            **{f"ensemble_weight_{_slug(name)}": float(value) for name, value in ensemble_weights.items()},
        })
        # The hand-written Gold table, SHAP values, fairness report, and
        # joblib artifacts are all logged alongside the two model flavors.
        mlflow.log_artifacts(str(run_dir), artifact_path="pipeline")
        # Supply explicit float schemas.  Letting MLflow infer a model's
        # class-label output creates an integer schema warning because Python
        # integer columns cannot represent a missing value.  The dashboard
        # consumes probability scores, so that is also the useful contract.
        model_input = x_train.head(5).astype("float64")
        logistic_signature = infer_signature(
            model_input,
            logistic.predict_proba(model_input)[:, 1].astype("float64"),
        )
        xgb_signature = infer_signature(
            model_input,
            xgb.predict_proba(model_input)[:, 1].astype("float64"),
        )
        random_forest_signature = infer_signature(
            model_input,
            random_forest.predict_proba(model_input)[:, 1].astype("float64"),
        )
        hist_gradient_boosting_signature = infer_signature(
            model_input,
            hist_gradient_boosting.predict_proba(model_input)[:, 1].astype("float64"),
        )
        mlflow.sklearn.log_model(
            logistic,
            name="logistic_regression",
            registered_model_name="DropoutSignalLogisticRegression",
            input_example=model_input,
            signature=logistic_signature,
            serialization_format="skops",
            await_registration_for=0,
        )
        mlflow.xgboost.log_model(
            xgb,
            name="xgboost",
            registered_model_name="DropoutSignalXGBoost",
            input_example=model_input,
            signature=xgb_signature,
            await_registration_for=0,
        )
        mlflow.sklearn.log_model(
            random_forest,
            name="random_forest",
            registered_model_name="DropoutSignalRandomForest",
            input_example=model_input,
            signature=random_forest_signature,
            serialization_format="skops",
            await_registration_for=0,
        )
        mlflow.sklearn.log_model(
            hist_gradient_boosting,
            name="hist_gradient_boosting",
            registered_model_name="DropoutSignalHistGradientBoosting",
            input_example=model_input,
            signature=hist_gradient_boosting_signature,
            serialization_format="skops",
            await_registration_for=0,
        )
        # The champion is recorded as a run tag.  Re-registering a model by
        # URI while artifacts are still committing caused intermittent missing
        # xgboost-artifact warnings in MLflow.
        return {
            "tracking_uri": tracking_uri,
            "experiment_id": experiment.experiment_id,
            "run_id": run.info.run_id,
            "registered_models": [
                "DropoutSignalLogisticRegression", "DropoutSignalXGBoost",
                "DropoutSignalRandomForest", "DropoutSignalHistGradientBoosting",
            ],
        }


def train_and_score(source_path: str | Path, activate: bool = True, source_label: str | None = None) -> dict[str, Any]:
    """Train four complementary models and score with their weighted ensemble."""
    _ensure_dirs()
    source = read_dataset(source_path)
    signature = hashlib.sha256(Path(source_path).read_bytes()).hexdigest()
    silver = build_silver(source)
    y = silver["is_dropout"].astype(int)
    x = silver[FEATURE_COLUMNS].astype(float)
    x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.2, random_state=42, stratify=y)

    scaler = StandardScaler()
    x_train_scaled = pd.DataFrame(scaler.fit_transform(x_train), columns=x_train.columns, index=x_train.index)
    x_test_scaled = pd.DataFrame(scaler.transform(x_test), columns=x_test.columns, index=x_test.index)
    logistic = LogisticRegression(max_iter=LOGISTIC_MAX_ITER, C=1.0, solver="lbfgs", random_state=42)
    logistic.fit(x_train_scaled, y_train)
    logistic_test = logistic.predict_proba(x_test_scaled)[:, 1]
    logistic_metrics = _metric_bundle(y_test, logistic_test)

    xgb = XGBClassifier(
        eval_metric="logloss",
        random_state=42,
        **XGB_TRAINING_PARAMS,
    )
    xgb.fit(x_train, y_train)
    xgb_test = xgb.predict_proba(x_test)[:, 1]
    xgb_metrics = _metric_bundle(y_test, xgb_test)

    random_forest = RandomForestClassifier(random_state=42, **RANDOM_FOREST_PARAMS)
    random_forest.fit(x_train, y_train)
    random_forest_test = random_forest.predict_proba(x_test)[:, 1]
    random_forest_metrics = _metric_bundle(y_test, random_forest_test)

    hist_gradient_boosting = HistGradientBoostingClassifier(
        random_state=42, **HIST_GRADIENT_BOOSTING_PARAMS,
    )
    hist_gradient_boosting.fit(x_train, y_train)
    hist_gradient_boosting_test = hist_gradient_boosting.predict_proba(x_test)[:, 1]
    hist_gradient_boosting_metrics = _metric_bundle(y_test, hist_gradient_boosting_test)

    model_metrics = {
        "Logistic Regression": logistic_metrics,
        "XGBoost": xgb_metrics,
        "Random Forest": random_forest_metrics,
        "HistGradientBoosting": hist_gradient_boosting_metrics,
    }
    # Weight all four candidates by held-out quality instead of silently
    # selecting a winner. F1 rewards useful intervention flags while AUC
    # protects ranking quality; a floor means every requested model remains
    # represented even on an unusually small or imbalanced upload.
    raw_weights = {
        name: max(0.05, (0.65 * metrics["f1_score"]) + (0.35 * metrics["auc_roc"]))
        for name, metrics in model_metrics.items()
    }
    total_weight = sum(raw_weights.values())
    ensemble_weights = {name: round(value / total_weight, 6) for name, value in raw_weights.items()}
    # This is a four-model validation result shown consistently throughout the
    # product; the weighting remains implementation detail in the metadata.
    ensemble_name = "4-Model Validation"

    all_scaled = pd.DataFrame(scaler.transform(x), columns=x.columns, index=x.index)
    all_logistic = logistic.predict_proba(all_scaled)[:, 1]
    all_xgb = xgb.predict_proba(x)[:, 1]
    all_random_forest = random_forest.predict_proba(x)[:, 1]
    all_hist_gradient_boosting = hist_gradient_boosting.predict_proba(x)[:, 1]
    score_sets = {
        "Logistic Regression": all_logistic,
        "XGBoost": all_xgb,
        "Random Forest": all_random_forest,
        "HistGradientBoosting": all_hist_gradient_boosting,
    }
    test_score_sets = {
        "Logistic Regression": logistic_test,
        "XGBoost": xgb_test,
        "Random Forest": random_forest_test,
        "HistGradientBoosting": hist_gradient_boosting_test,
    }
    ensemble_probability = np.zeros(len(x), dtype=float)
    ensemble_test_probability = np.zeros(len(x_test), dtype=float)
    for name, weight in ensemble_weights.items():
        ensemble_probability += weight * score_sets[name]
        ensemble_test_probability += weight * test_score_sets[name]
    ensemble_metrics = _metric_bundle(y_test, ensemble_test_probability)
    shap_values = _shap_values(xgb, x)
    gold = _gold_table(
        silver, signature, all_logistic, all_xgb, all_random_forest,
        all_hist_gradient_boosting, ensemble_probability, ensemble_name,
        ensemble_weights, shap_values,
    )
    # The fairness audit is performed on the held-out test partition, matching
    # the notebook and avoiding an over-optimistic in-sample assessment.
    fairness = _fairness(silver.loc[x_test.index], y_test, ensemble_test_probability, ensemble_name)
    mean_abs_shap = np.abs(shap_values).mean(axis=0)
    global_shap = pd.DataFrame({"feature": FEATURE_COLUMNS, "mean_abs_shap": mean_abs_shap}).sort_values("mean_abs_shap", ascending=False)
    global_shap["rank"] = np.arange(1, len(global_shap) + 1)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dataset_label = source_label or Path(source_path).stem
    run_id = f"{timestamp}-{_slug(dataset_label)}-{signature[:8]}"
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    bronze_path = run_dir / "bronze_raw.csv"
    silver_path = run_dir / "silver_features.csv"
    gold_path = run_dir / "gold_scored_students.csv"
    source.to_csv(bronze_path, index=False)
    silver.to_csv(silver_path, index=False)
    gold.to_csv(gold_path, index=False)
    global_shap.to_csv(run_dir / "shap_global_importance.csv", index=False)
    pd.DataFrame(fairness).to_csv(run_dir / "fairness_audit.csv", index=False)
    pd.DataFrame([
        {
            "model": name,
            "description": {
                "Logistic Regression": "Transparent linear baseline that calibrates broad risk patterns.",
                "XGBoost": "Gradient-boosted trees for non-linear academic, engagement, and financial signals.",
                "Random Forest": "Bagged decision trees that reduce variance across diverse student profiles.",
                "HistGradientBoosting": "Histogram-based gradient boosting for efficient, smooth non-linear scoring.",
            }[name],
            **metrics,
            "ensemble_weight": ensemble_weights[name],
        }
        for name, metrics in model_metrics.items()
    ] + [{
        "model": ensemble_name,
        "description": "Validation-weighted blend of all four candidates; this is the Gold-layer operational score.",
        **ensemble_metrics,
        "ensemble_weight": 1.0,
    }]).to_csv(run_dir / "model_comparison.csv", index=False)
    _write_json(run_dir / "layer_manifest.json", {
        "bronze": {
            "description": "Immutable source upload retained for lineage and audit; no model scores are applied.",
            "model_role": "Raw model input record.",
        },
        "silver": {
            "description": "Validated and derived feature layer used by all four candidate models.",
            "model_role": "Shared feature schema for Logistic Regression, XGBoost, Random Forest, and HistGradientBoosting.",
        },
        "gold": {
            "description": "Operational scored cohort with individual probabilities, model provenance, and a validation-weighted ensemble score.",
            "model_role": ensemble_name,
            "ensemble_weights": ensemble_weights,
        },
    })
    joblib.dump(scaler, run_dir / "logistic_scaler.joblib")
    joblib.dump(logistic, run_dir / "logistic_regression.joblib")
    joblib.dump(xgb, run_dir / "xgboost_model.joblib")
    joblib.dump(random_forest, run_dir / "random_forest_model.joblib")
    joblib.dump(hist_gradient_boosting, run_dir / "hist_gradient_boosting_model.joblib")

    tiers = gold["final_risk_tier"].value_counts().reindex(["HIGH", "MEDIUM", "LOW"], fill_value=0)
    dataset_display_name = source_label or Path(source_path).name
    metadata: dict[str, Any] = {
        "run_id": run_id,
        # Preserve the uploaded dataset's own label in every dashboard/API.
        # Re-scoring a prior Bronze artifact must not make it look like a
        # universal "bronze_raw.csv" cohort.
        "dataset_name": dataset_display_name,
        "source_file_name": Path(source_path).name,
        "source_label": dataset_label,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_sha256": signature,
        "record_count": int(len(source)),
        "feature_count": len(FEATURE_COLUMNS),
        "target_column": TARGET_COLUMN,
        "dropout_count": int(y.sum()),
        "dropout_rate": round(float(y.mean()), 4),
        "tier_breakdown": [{"final_risk_tier": tier, "cnt": int(tiers[tier])} for tier in ["HIGH", "MEDIUM", "LOW"]],
        "predicted_dropouts": int((ensemble_probability >= 0.5).sum()),
        "champion_model": ensemble_name,
        "ensemble": {
            "strategy": "Validation-weighted mean probability across all four models",
            "selection_rationale": "Each model contributes using a held-out quality weight (65% F1, 35% ROC-AUC).",
            "weights": ensemble_weights,
            "metrics": ensemble_metrics,
            "shap_explanation_model": "XGBoost component; its tree SHAP values supply the per-student feature evidence.",
        },
        "pipeline_layers": {
            "Bronze": "Raw, immutable uploaded records for lineage and audit.",
            "Silver": "Validated inputs plus derived features consumed by every candidate model.",
            "Gold": "Per-student four-model probabilities, ensemble score, tier, and intervention action.",
        },
        "models": {
            "Logistic Regression": {"description": "Transparent linear baseline that calibrates broad risk patterns.", "parameters": {"C": 1.0, "penalty": "l2", "max_iter": LOGISTIC_MAX_ITER, "solver": "lbfgs"}, "metrics": logistic_metrics, "ensemble_weight": ensemble_weights["Logistic Regression"]},
            "XGBoost": {"description": "Gradient-boosted trees for non-linear academic, engagement, and financial signals.", "parameters": XGB_TRAINING_PARAMS, "metrics": xgb_metrics, "ensemble_weight": ensemble_weights["XGBoost"]},
            "Random Forest": {"description": "Bagged decision trees that reduce variance across diverse student profiles.", "parameters": RANDOM_FOREST_PARAMS, "metrics": random_forest_metrics, "ensemble_weight": ensemble_weights["Random Forest"]},
            "HistGradientBoosting": {"description": "Histogram-based gradient boosting for efficient, smooth non-linear scoring.", "parameters": HIST_GRADIENT_BOOSTING_PARAMS, "metrics": hist_gradient_boosting_metrics, "ensemble_weight": ensemble_weights["HistGradientBoosting"]},
            ensemble_name: {"description": "Validation-weighted blend of all four models used for Gold-layer risk tiers and actions.", "parameters": {"weighting": "0.65 F1 + 0.35 ROC-AUC on held-out validation"}, "metrics": ensemble_metrics, "ensemble_weight": 1.0},
        },
        "files": {
            "bronze": bronze_path.name,
            "silver": silver_path.name,
            "gold": gold_path.name,
            "global_shap": "shap_global_importance.csv",
            "fairness": "fairness_audit.csv",
            "model_comparison": "model_comparison.csv",
            "layer_manifest": "layer_manifest.json",
            "logistic_model": "logistic_regression.joblib",
            "xgboost_model": "xgboost_model.joblib",
            "random_forest_model": "random_forest_model.joblib",
            "hist_gradient_boosting_model": "hist_gradient_boosting_model.joblib",
        },
    }
    metadata["mlflow"] = _log_mlflow_run(
        run_id, run_dir, x_train, logistic, xgb, random_forest,
        hist_gradient_boosting, model_metrics, ensemble_weights, len(source), ensemble_name,
    )
    _write_json(run_dir / "metadata.json", metadata)
    if activate:
        # The runtime directory can live outside the source checkout (for
        # example /tmp on a hosted service).  Storing a path relative to ROOT
        # made a successfully trained run unreadable on the next request.
        _write_json(ACTIVE_RUN_FILE, {"run_id": run_id, "run_dir": str(run_dir.relative_to(RUNTIME_DIR))})
    return metadata


def active_metadata() -> dict[str, Any] | None:
    active = _read_json(ACTIVE_RUN_FILE)
    if not active or not active.get("run_dir"):
        return None
    saved_path = Path(active["run_dir"])
    if saved_path.is_absolute():
        run_dir = saved_path
    else:
        # New markers are relative to RUNTIME_DIR.  Keep support for markers
        # produced by earlier versions, which were relative to the repo root.
        run_dir = RUNTIME_DIR / saved_path
        if not (run_dir / "metadata.json").exists():
            run_dir = ROOT / saved_path
    metadata = _read_json(run_dir / "metadata.json")
    if not metadata:
        return None
    metadata["run_dir"] = str(run_dir)
    return metadata


def activate_run(metadata: dict[str, Any]) -> None:
    """Make an already-trained run the active dashboard dataset."""
    run_id = str(metadata.get("run_id") or "")
    run_dir = RUNS_DIR / run_id
    if not run_id or not (run_dir / "metadata.json").exists():
        raise DatasetValidationError("Trained dataset run could not be activated.")
    _write_json(ACTIVE_RUN_FILE, {"run_id": run_id, "run_dir": str(run_dir.relative_to(RUNTIME_DIR))})


def restore_latest_run() -> dict[str, Any] | None:
    """Restore the newest completed local run after an unclean app restart.

    An explicit reset leaves an ``active_run.json`` marker, so this only
    recovers a missing marker (for example after an old debug process was
    stopped).  A counselor upload therefore remains the shared source of truth
    when the administrator opens the other dashboard.
    """
    _ensure_dirs()
    if ACTIVE_RUN_FILE.exists():
        return active_metadata()
    candidates: list[tuple[float, dict[str, Any]]] = []
    for run_dir in RUNS_DIR.iterdir():
        if not run_dir.is_dir():
            continue
        metadata = _read_json(run_dir / "metadata.json")
        if metadata and metadata.get("run_id") and (run_dir / str(metadata.get("files", {}).get("gold", ""))).exists():
            candidates.append((run_dir.stat().st_mtime, metadata))
    if not candidates:
        return None
    _, metadata = max(candidates, key=lambda item: item[0])
    activate_run(metadata)
    return active_metadata()


def active_records() -> pd.DataFrame:
    metadata = active_metadata()
    if not metadata:
        _ACTIVE_RECORD_CACHE["run_id"] = None
        _ACTIVE_RECORD_CACHE["frame"] = None
        return pd.DataFrame()
    if _ACTIVE_RECORD_CACHE.get("run_id") == metadata.get("run_id") and _ACTIVE_RECORD_CACHE.get("frame") is not None:
        return _ACTIVE_RECORD_CACHE["frame"]
    path = Path(metadata["run_dir"]) / metadata["files"]["gold"]
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path)
    _ACTIVE_RECORD_CACHE["run_id"] = metadata.get("run_id")
    _ACTIVE_RECORD_CACHE["frame"] = frame
    return frame


def active_fairness() -> list[dict[str, Any]]:
    metadata = active_metadata()
    if not metadata:
        return []
    path = Path(metadata["run_dir"]) / metadata["files"]["fairness"]
    if not path.exists():
        return []
    return pd.read_csv(path).replace({np.nan: None}).to_dict(orient="records")


def active_global_shap(limit: int = 15) -> list[dict[str, Any]]:
    metadata = active_metadata()
    if not metadata:
        return []
    path = Path(metadata["run_dir"]) / metadata["files"]["global_shap"]
    if not path.exists():
        return []
    return pd.read_csv(path).head(limit).replace({np.nan: None}).to_dict(orient="records")


def list_generated_datasets() -> list[dict[str, Any]]:
    _ensure_dirs()
    catalog = _read_json(DATASETS_DIR / "catalog.json", {"datasets": []}) or {"datasets": []}
    return catalog.get("datasets", [])


def generated_dataset_path(filename: str) -> Path:
    candidate = (DATASETS_DIR / Path(filename).name).resolve()
    if candidate.parent != DATASETS_DIR.resolve() or not candidate.exists():
        raise DatasetValidationError("Generated dataset was not found.")
    return candidate


def copy_upload(file_storage: Any) -> Path:
    _ensure_dirs()
    filename = _slug(Path(file_storage.filename or "uploaded-dataset.csv").stem) + ".csv"
    target = UPLOADS_DIR / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{filename}"
    file_storage.save(target)
    return target


def reset_active_dataset() -> None:
    # Keep an explicit disabled marker.  It prevents a later process restart
    # from silently restoring an intentionally reset dataset.
    _ensure_dirs()
    _write_json(ACTIVE_RUN_FILE, {"disabled": True})


def generate_dataset_family(source_path: str | Path) -> list[dict[str, Any]]:
    """Create five deterministic, distinct UCI-schema datasets over 4,000 rows."""
    _ensure_dirs()
    base = read_dataset(source_path)
    specifications = [
        ("dropout_dataset_01_baseline_4424.csv", 4424, 101, 0.00),
        ("dropout_dataset_02_urban_4600.csv", 4600, 202, 0.04),
        ("dropout_dataset_03_financial_pressure_4850.csv", 4850, 303, 0.09),
        ("dropout_dataset_04_academic_recovery_5100.csv", 5100, 404, -0.05),
        ("dropout_dataset_05_diverse_cohort_5500.csv", 5500, 505, 0.02),
    ]
    continuous = [
        "Previous qualification (grade)", "Admission grade", "Curricular units 1st sem (grade)",
        "Curricular units 2nd sem (grade)", "Unemployment rate", "Inflation rate", "GDP",
    ]
    catalog: list[dict[str, Any]] = []
    for number, (filename, row_count, seed, dropout_shift) in enumerate(specifications, start=1):
        rng = np.random.default_rng(seed)
        sampled = base.iloc[rng.choice(len(base), size=row_count, replace=row_count > len(base))].copy().reset_index(drop=True)
        for column in continuous:
            scale = max(float(sampled[column].std(ddof=0)), 0.1) * (0.06 + number * 0.012)
            sampled[column] = np.clip(sampled[column].astype(float) + rng.normal(0, scale, row_count), 0, None).round(3)
        # Keep categories valid but vary the student composition.
        for column in ("Scholarship holder", "Debtor", "Tuition fees up to date", "Displaced", "International"):
            flip_probability = 0.012 * number
            flip = rng.random(row_count) < flip_probability
            sampled.loc[flip, column] = 1 - sampled.loc[flip, column].astype(int)
        current_dropout = _encode_target(sampled[TARGET_COLUMN]).to_numpy(dtype=int)
        target_probability = np.clip(0.04 + max(dropout_shift, 0) + 0.03 * number, 0, 0.27)
        flips = rng.random(row_count) < target_probability
        if dropout_shift >= 0:
            current_dropout = np.where(flips, 1, current_dropout)
        else:
            current_dropout = np.where(flips, 0, current_dropout)
        sampled[TARGET_COLUMN] = np.where(current_dropout == 1, "Dropout", np.where(rng.random(row_count) < 0.5, "Graduate", "Enrolled"))
        signature = hashlib.sha256(filename.encode("utf-8")).hexdigest()
        sampled[STUDENT_NAME_COLUMN] = [_name_for(index, signature) for index in range(row_count)]
        sampled = sampled[[STUDENT_NAME_COLUMN, *[column for column in sampled.columns if column != STUDENT_NAME_COLUMN]]]
        path = DATASETS_DIR / filename
        sampled.to_csv(path, index=False)
        catalog.append({
            "number": number,
            "filename": filename,
            "label": filename.removesuffix(".csv").replace("_", " ").title(),
            "student_count": row_count,
            "dropout_rate": round(float(current_dropout.mean()), 4),
            "schema": "UCI 36 predictors + Target + Student Name metadata",
        })
    _write_json(DATASETS_DIR / "catalog.json", {"generated_at": datetime.now(timezone.utc).isoformat(), "datasets": catalog})
    return catalog


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Train local Dropout Signal ML models on a UCI-format CSV.")
    parser.add_argument("csv", help="CSV containing the 36 UCI predictors and Target")
    parser.add_argument("--activate", action="store_true", help="Make the completed run the dashboard's active dataset")
    parser.add_argument("--generate-family", action="store_true", help="Generate five >4,000 student datasets from the given CSV")
    args = parser.parse_args()
    if args.generate_family:
        print(json.dumps(generate_dataset_family(args.csv), indent=2))
    else:
        print(json.dumps(train_and_score(args.csv, activate=args.activate), indent=2, default=_json_default))
