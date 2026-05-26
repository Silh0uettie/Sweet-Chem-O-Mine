from __future__ import annotations

import io
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd

from . import __version__
from .analysis import AnalysisResult, AnalysisSettings, ColumnMapping


PROJECT_SUFFIX = ".scom"


@dataclass(slots=True)
class LoadedProject:
    data: pd.DataFrame
    mapping: ColumnMapping
    settings: AnalysisSettings
    embedding: pd.DataFrame | None
    excluded: pd.DataFrame | None
    warnings: pd.DataFrame | None
    selected_rows: list[int]
    source_filename: str | None
    source_bytes: bytes | None
    plot_styles: dict[str, dict[str, Any]]
    areas_of_interest: dict[str, list[int]]


def save_project(
    path: str | Path | BinaryIO,
    data: pd.DataFrame,
    mapping: ColumnMapping,
    settings: AnalysisSettings,
    result: AnalysisResult | None = None,
    selected_rows: list[int] | None = None,
    source_filename: str | None = None,
    source_bytes: bytes | None = None,
    plot_styles: dict[str, dict[str, Any]] | None = None,
    areas_of_interest: dict[str, list[int]] | None = None,
) -> None:
    """Store reproducible input and analysis outputs in a portable zip container."""
    metadata = {
        "format": "sweet-chem-o-mine-project",
        "format_version": 1,
        "application_version": __version__,
        "saved_utc": datetime.now(timezone.utc).isoformat(),
        "source_filename": source_filename,
    }
    settings_payload = {
        "mapping": mapping.to_dict(),
        "analysis": settings.to_dict(),
        "selected_rows": selected_rows or [],
        "plot_styles": plot_styles or {},
        "areas_of_interest": areas_of_interest or {},
    }

    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("project_metadata.json", json.dumps(metadata, indent=2))
        archive.writestr("settings.json", json.dumps(settings_payload, indent=2))
        archive.writestr("raw/imported_table.csv", data.to_csv(index=False))
        if source_filename and source_bytes is not None:
            archive.writestr(f"raw/source/{Path(source_filename).name}", source_bytes)
        if result is not None:
            archive.writestr("processed/embedding.csv", result.embedding.to_csv(index=False))
            archive.writestr("processed/excluded_rows.csv", result.excluded.to_csv(index=False))
            archive.writestr("processed/warnings.csv", result.warnings.to_csv(index=False))


def load_project(path: str | Path | BinaryIO) -> LoadedProject:
    with ZipFile(path) as archive:
        metadata = json.loads(archive.read("project_metadata.json"))
        saved_settings = json.loads(archive.read("settings.json"))
        data = pd.read_csv(io.BytesIO(archive.read("raw/imported_table.csv")))

        names = set(archive.namelist())
        embedding = (
            pd.read_csv(io.BytesIO(archive.read("processed/embedding.csv")))
            if "processed/embedding.csv" in names
            else None
        )

        def load_report(member: str) -> pd.DataFrame | None:
            if member not in names:
                return None
            try:
                return pd.read_csv(io.BytesIO(archive.read(member)))
            except pd.errors.EmptyDataError:
                return pd.DataFrame(columns=["source_row", "display_name", "smiles", "reason"])

        excluded = load_report("processed/excluded_rows.csv")
        warnings = load_report("processed/warnings.csv")

        source_filename = metadata.get("source_filename")
        source_bytes = None
        if source_filename:
            member = f"raw/source/{Path(source_filename).name}"
            if member in names:
                source_bytes = archive.read(member)

    return LoadedProject(
        data=data,
        mapping=ColumnMapping.from_dict(saved_settings["mapping"]),
        settings=AnalysisSettings.from_dict(saved_settings["analysis"]),
        embedding=embedding,
        excluded=excluded,
        warnings=warnings,
        selected_rows=saved_settings.get("selected_rows", []),
        source_filename=source_filename,
        source_bytes=source_bytes,
        plot_styles=saved_settings.get("plot_styles", {}),
        areas_of_interest=saved_settings.get("areas_of_interest", {}),
    )
