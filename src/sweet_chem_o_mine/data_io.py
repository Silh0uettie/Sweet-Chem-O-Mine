from __future__ import annotations

from pathlib import Path

import pandas as pd


TABULAR_SUFFIXES = {".csv", ".xls", ".xlsx"}


def excel_sheet_names(path: str | Path) -> list[str]:
    """Return sheet names for an Excel workbook without loading a data sheet."""
    with pd.ExcelFile(path) as workbook:
        return workbook.sheet_names


def load_table(path: str | Path, sheet_name: str | None = None) -> pd.DataFrame:
    """Load a supported table, preserving source column names for user mapping."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".xls", ".xlsx"}:
        return pd.read_excel(path, sheet_name=sheet_name)
    raise ValueError(f"Unsupported data file type: {suffix}")
