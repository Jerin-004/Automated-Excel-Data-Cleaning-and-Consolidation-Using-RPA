"""
sample_generator.py
===================
Generates realistic, intentionally dirty sample Excel files for demonstration.

Three workbooks are produced:
  employees_north_region.xlsx   — HR data, North region
  employees_south_region.xlsx   — HR data, South region (different col names)
  employees_legacy_export.xlsx  — Legacy system export (mixed issues)

Issues intentionally introduced
---------------------------------
* Duplicate rows (exact)
* Duplicate record IDs with conflicting data
* Missing email addresses
* Missing mandatory values (salary, name)
* Leading/trailing whitespace
* Inconsistent capitalisation
* Different date formats across files
* Invalid email addresses
* Non-numeric salary values
* Negative salary values
* Inconsistent department names
* Slightly different column names across workbooks (tested via alias mapping)
* Completely empty rows

Uses a fixed random seed for reproducibility.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import pandas as pd


# ---------------------------------------------------------------------------
# Seed for reproducibility
# ---------------------------------------------------------------------------
SEED = 42
RNG  = random.Random(SEED)


# ---------------------------------------------------------------------------
# Base valid data pool
# ---------------------------------------------------------------------------

FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael",
    "Linda", "William", "Barbara", "David", "Elizabeth", "Richard", "Susan",
    "Joseph", "Jessica", "Thomas", "Sarah", "Charles", "Karen",
]
LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
    "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
]
DEPARTMENTS_CLEAN = [
    "Human Resources", "Information Technology", "Finance",
    "Marketing", "Operations", "Sales",
]
CITIES = ["New York", "Los Angeles", "Chicago", "Houston", "Phoenix",
          "Philadelphia", "San Antonio", "San Diego", "Dallas", "San Jose"]
EMAIL_DOMAINS = ["gmail.com", "yahoo.com", "outlook.com", "company.org", "work.net"]


def _name() -> str:
    return f"{RNG.choice(FIRST_NAMES)} {RNG.choice(LAST_NAMES)}"


def _email(name: str) -> str:
    local = name.lower().replace(" ", ".")
    return f"{local}@{RNG.choice(EMAIL_DOMAINS)}"


def _date_iso() -> str:
    y = RNG.randint(2015, 2023)
    m = RNG.randint(1, 12)
    d = RNG.randint(1, 28)
    return f"{y}-{m:02d}-{d:02d}"


def _salary() -> float:
    return round(RNG.uniform(30_000, 120_000), 2)


def _make_record(rid: int) -> dict:
    name = _name()
    return {
        "record_id":    f"EMP{rid:04d}",
        "name":         name,
        "email":        _email(name),
        "phone":        f"+1 ({RNG.randint(200,999)}) {RNG.randint(100,999)}-{RNG.randint(1000,9999)}",
        "department":   RNG.choice(DEPARTMENTS_CLEAN),
        "joining_date": _date_iso(),
        "salary":       _salary(),
        "city":         RNG.choice(CITIES),
    }


# ---------------------------------------------------------------------------
# File 1 — North region (mostly clean, a few issues)
# ---------------------------------------------------------------------------

def _build_north() -> pd.DataFrame:
    rows: list[dict] = []
    for rid in range(1, 31):
        rows.append(_make_record(rid))

    # Issue: leading/trailing whitespace in name
    rows[2]["name"] = "  " + rows[2]["name"] + "  "

    # Issue: inconsistent capitalisation in department
    rows[5]["department"] = "hr"
    rows[8]["department"] = "I.T."
    rows[11]["department"] = "Fin"

    # Issue: different date format
    rows[3]["joining_date"] = "15/03/2019"
    rows[7]["joining_date"] = "March 22, 2020"

    # Issue: missing email
    rows[9]["email"] = ""

    # Issue: exact duplicate (copy row 0)
    rows.append(dict(rows[0]))

    # Issue: missing salary (mandatory)
    rows[14]["salary"] = ""

    # Issue: non-numeric salary
    rows[16]["salary"] = "eighty thousand"

    # Issue: negative salary
    rows[18]["salary"] = -5000

    # Issue: invalid email format
    rows[20]["email"] = "not_an_email"

    # Insert a completely empty row (will be dropped by reader)
    rows.insert(10, {k: "" for k in rows[0].keys()})

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# File 2 — South region (different column names, more issues)
# ---------------------------------------------------------------------------

def _build_south() -> pd.DataFrame:
    rows: list[dict] = []
    for rid in range(20, 51):  # overlapping IDs with north (EMP0020–EMP0030 conflict)
        rows.append(_make_record(rid))

    # Issue: inconsistent capitalisation
    rows[0]["name"] = rows[0]["name"].upper()
    rows[3]["name"] = rows[3]["name"].lower()

    # Issue: inconsistent department names
    rows[1]["department"]  = "mktg"
    rows[5]["department"]  = "Operations"
    rows[9]["department"]  = "operation"
    rows[12]["department"] = "R&D"     # unmapped — will flag

    # Issue: date in American format
    rows[4]["joining_date"]  = "12/31/2018"
    rows[10]["joining_date"] = "2022/07/15"

    # Issue: email with extra spaces
    rows[6]["email"] = "  " + rows[6]["email"] + "  "

    # Issue: missing mandatory field (name)
    rows[15]["name"] = ""

    # Issue: conflicting duplicate — same record_id as EMP0025 in north
    conflict_row = dict(rows[5])
    conflict_row["record_id"] = "EMP0025"
    conflict_row["name"]      = "Conflict Name"
    conflict_row["salary"]    = 99999
    rows.append(conflict_row)

    # Rename columns to simulate a different source system
    df = pd.DataFrame(rows)
    df = df.rename(columns={
        "record_id":    "emp_id",
        "name":         "employee_name",
        "phone":        "mobile_number",
        "joining_date": "date_of_joining",
    })

    return df


# ---------------------------------------------------------------------------
# File 3 — Legacy export (many issues)
# ---------------------------------------------------------------------------

def _build_legacy() -> pd.DataFrame:
    rows: list[dict] = []
    for rid in range(45, 66):
        rows.append(_make_record(rid))

    # Issue: several missing emails
    for idx in [2, 5, 8]:
        rows[idx]["email"] = None

    # Issue: salary with currency symbol and commas
    rows[0]["salary"] = "$45,000.00"
    rows[3]["salary"] = "£78,500"

    # Issue: inconsistent phone formatting
    rows[1]["phone"]  = "555.123.4567"
    rows[4]["phone"]  = "1-800-CALL-NOW"

    # Issue: department inconsistency
    rows[6]["department"]  = "Human Resource"
    rows[9]["department"]  = "admin"
    rows[13]["department"] = "Accounts"

    # Issue: duplicate record from file 2
    dup_row = _make_record(48)
    dup_row["record_id"] = "EMP0048"
    rows.append(dup_row)
    rows.append(dict(dup_row))   # exact duplicate

    # Issue: missing city and salary on same row
    rows[11]["city"]   = ""
    rows[11]["salary"] = ""

    # Rename some columns (legacy format)
    df = pd.DataFrame(rows)
    df = df.rename(columns={
        "record_id":    "id",
        "joining_date": "hire_date",
        "salary":       "annual_salary",
    })

    return df


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_sample_files(
    output_dir: str | Path = "data/input",
    overwrite: bool = False,
) -> list[Path]:
    """
    Create the three sample Excel files in *output_dir*.

    Parameters
    ----------
    output_dir : Target directory.
    overwrite  : If False and files already exist, skip them.

    Returns
    -------
    List of created file paths.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    files = {
        "employees_north_region.xlsx": _build_north(),
        "employees_south_region.xlsx": _build_south(),
        "employees_legacy_export.xlsx": _build_legacy(),
    }

    created: list[Path] = []
    for filename, df in files.items():
        path = output_dir / filename
        if path.exists() and not overwrite:
            print(f"  [SKIP] {filename} already exists. Use overwrite=True to replace.")
            created.append(path)
            continue
        df.to_excel(path, index=False, engine="openpyxl")
        print(f"  [OK]   Created {path}")
        created.append(path)

    return created


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    overwrite = "--overwrite" in sys.argv
    paths = generate_sample_files(overwrite=overwrite)
    print(f"\nGenerated {len(paths)} file(s).")
