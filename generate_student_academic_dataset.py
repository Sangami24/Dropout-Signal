"""Create the rich, reproducible student CSV used by the call demonstration.

The dropout outcome remains the original UCI outcome. Added attendance, marks,
GPA and engagement fields are derived from pre-outcome academic indicators plus
seeded noise; the target is never used to manufacture those inputs.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from ml_pipeline import COURSE_MAP, FIRST_NAMES, LAST_NAMES, MIDDLE_NAMES


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "uci_dropout.csv"
CATALOG = ROOT / "datasets" / "catalog.json"

SUBJECTS = {
    "Informatics Engineering": ["Programming", "Data Structures", "Database Systems", "Computer Networks", "Mathematics", "Software Engineering"],
    "Management": ["Accounting", "Business Economics", "Marketing", "Statistics", "Organisational Behaviour", "Business Law"],
    "Management (evening)": ["Accounting", "Business Economics", "Marketing", "Statistics", "Organisational Behaviour", "Business Law"],
    "Nursing": ["Anatomy", "Physiology", "Pharmacology", "Community Health", "Clinical Practice", "Psychology"],
    "Veterinary Nursing": ["Animal Anatomy", "Animal Nutrition", "Clinical Skills", "Pharmacology", "Animal Welfare", "Pathology"],
    "Basic Education": ["Child Development", "Teaching Methods", "Mathematics", "Language Education", "Educational Psychology", "Inclusive Education"],
    "Journalism and Communication": ["Media Writing", "Communication Theory", "Digital Journalism", "Media Law", "Research Methods", "Visual Communication"],
}
DEFAULT_SUBJECTS = ["Core Subject 1", "Core Subject 2", "Mathematics", "Communication Skills", "Practical Coursework", "Elective"]


def unique_name(index: int) -> str:
    first = FIRST_NAMES[index % len(FIRST_NAMES)]
    middle = MIDDLE_NAMES[(index // len(FIRST_NAMES)) % len(MIDDLE_NAMES)]
    last = LAST_NAMES[(index // (len(FIRST_NAMES) * len(MIDDLE_NAMES))) % len(LAST_NAMES)]
    combinations = len(FIRST_NAMES) * len(MIDDLE_NAMES) * len(LAST_NAMES)
    cycle = index // combinations
    return f"{first} {middle} {last}" if cycle == 0 else f"{first} {middle} {last} {cycle + 1}"


DATASET_SPECS = (
    ("comprehensive_student_academic_dataset.csv", "Comprehensive Student Academic Dataset", 4424, 20261018),
    ("student_academic_support_cohort.csv", "Academic Support Cohort", 4600, 20261019),
    ("student_attendance_barriers_cohort.csv", "Attendance Barriers Cohort", 4850, 20261020),
)


def _build_cohort(source: pd.DataFrame, *, row_count: int, seed: int, identity_offset: int) -> pd.DataFrame:
    """Return one reproducible, independently sampled rich student cohort.

    Each file keeps exactly the comprehensive schema.  The identity fields
    are regenerated from a non-overlapping range, so a name, ID, phone, and
    email can never be shared by two downloadable cohorts.
    """
    rng = np.random.default_rng(seed)
    sample_index = rng.choice(len(source), size=row_count, replace=row_count > len(source))
    frame = source.iloc[sample_index].reset_index(drop=True).copy()
    count = len(frame)
    first_eval = frame["Curricular units 1st sem (evaluations)"].clip(lower=1)
    second_eval = frame["Curricular units 2nd sem (evaluations)"].clip(lower=1)
    approval_ratio = (
        frame["Curricular units 1st sem (approved)"] + frame["Curricular units 2nd sem (approved)"]
    ) / (first_eval + second_eval)
    grade_average = (
        frame["Curricular units 1st sem (grade)"] + frame["Curricular units 2nd sem (grade)"]
    ) / 2

    attendance = np.clip(54 + approval_ratio * 42 + rng.normal(0, 5.5, count), 35, 100).round(1)
    assignment_completion = np.clip(42 + approval_ratio * 54 + rng.normal(0, 7, count), 20, 100).round(1)
    internal_average = np.clip(grade_average * 5 + rng.normal(2, 6, count), 0, 100).round(1)
    semester_gpa = np.clip(internal_average / 25 + rng.normal(0, 0.12, count), 0, 4).round(2)
    backlogs = np.clip(np.rint((1 - approval_ratio) * 5 + rng.normal(0, 0.7, count)), 0, 8).astype(int)
    lms_engagement = np.clip(35 + approval_ratio * 58 + rng.normal(0, 8, count), 5, 100).round(1)

    course_names = frame["Course"].map(lambda value: COURSE_MAP.get(int(value), f"Program {int(value)}"))
    names = [unique_name(identity_offset + index) for index in range(count)]
    rich = pd.DataFrame({
        "Student ID": [f"DS-2026-{identity_offset + index + 1:05d}" for index in range(count)],
        "Student Name": names,
        "Phone": [f"+919{identity_offset + index + 100000000:09d}" for index in range(count)],
        "Email": [f"student{identity_offset + index + 1:05d}@university.example" for index in range(count)],
        "Department": course_names,
        "Program": course_names,
        "Academic Year": np.where(frame["Age at enrollment"] >= 25, 2, 1),
        "Semester": np.where(frame["Curricular units 2nd sem (enrolled)"] > 0, 2, 1),
        "Attendance Percentage": attendance,
        "Assignment Completion Percentage": assignment_completion,
        "Internal Assessment Average": internal_average,
        "Semester GPA": semester_gpa,
        "Backlogs": backlogs,
        "Counseling Sessions": rng.integers(0, 5, count),
        "LMS Engagement Score": lms_engagement,
    })

    for subject_number in range(1, 7):
        names_for_subject = [SUBJECTS.get(program, DEFAULT_SUBJECTS)[subject_number - 1] for program in course_names]
        subject_marks = np.clip(internal_average + rng.normal(0, 7.5, count) + (subject_number - 3.5) * 0.8, 0, 100).round(1)
        rich[f"Subject {subject_number} Name"] = names_for_subject
        rich[f"Subject {subject_number} Marks"] = subject_marks

    return pd.concat([rich, frame], axis=1)


def main() -> None:
    source = pd.read_csv(SOURCE, sep=";")
    DATASETS_DIR = ROOT / "datasets"
    DATASETS_DIR.mkdir(parents=True, exist_ok=True)

    generated = []
    for number, (filename, label, row_count, seed) in enumerate(DATASET_SPECS, start=1):
        output = _build_cohort(source, row_count=row_count, seed=seed, identity_offset=(number - 1) * 10_000)
        output_path = DATASETS_DIR / filename
        output.to_csv(output_path, index=False)
        generated.append({
            "number": number,
            "filename": filename,
            "label": label,
            "student_count": row_count,
            "dropout_rate": round(float(output["Target"].astype(str).str.lower().eq("dropout").mean()), 4),
            "schema": "UCI predictors + student profile fields, six subject marks, attendance, GPA, engagement, and Target",
        })

    catalog = {"datasets": generated}
    catalog["generated_at"] = datetime.now(timezone.utc).isoformat()
    CATALOG.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    print(f"Created {len(generated)} datasets with {len(output.columns)} columns each")


if __name__ == "__main__":
    main()
