"""Schema checks and access-list parsing; no silent data repairs."""
from __future__ import annotations
from pathlib import Path
import pandas as pd
from .security import Principal

REQUIRED = {
    "households": {"household_id"},
    "holdings": {"household_id", "isin"},
    "meetings": {"household_id", "advisor_id"},
    "advisors": {"advisor_id", "behorighet_hushall"},
}

class SchemaError(ValueError):
    pass

def read_tables(folder: Path) -> dict[str, pd.DataFrame]:
    tables = {}
    for name, columns in REQUIRED.items():
        frame = pd.read_csv(folder / f"{name}.csv", dtype=str, keep_default_na=False)
        missing = columns - set(frame.columns)
        if missing:
            raise SchemaError(f"{name}: missing columns {sorted(missing)}")
        tables[name] = frame
    ids = set(tables["households"]["household_id"])
    if tables["households"]["household_id"].duplicated().any():
        raise SchemaError("Duplicate household_id")
    for name in ("holdings", "meetings"):
        invalid = set(tables[name]["household_id"]) - ids
        if invalid:
            raise SchemaError(f"{name}: orphan household IDs {sorted(invalid)}")
    return tables

def principal_for(advisor_id: str, advisors: pd.DataFrame) -> Principal:
    matches = advisors.loc[advisors["advisor_id"] == advisor_id]
    if len(matches) != 1:
        raise SchemaError("Advisor must resolve to exactly one record")
    raw = matches.iloc[0]["behorighet_hushall"]
    allowed = frozenset(x.strip() for x in raw.split(";") if x.strip())
    return Principal(advisor_id, allowed)
