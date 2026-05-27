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
REPORT_COLUMNS = ["source_row", "display_name", "smiles", "reason"]
FRAME_MEMBERS = {
    "data": ("raw/imported_table.json", "raw/imported_table.csv"),
    "embedding": ("processed/embedding.json", "processed/embedding.csv"),
    "excluded": ("processed/excluded_rows.json", "processed/excluded_rows.csv"),
    "warnings": ("processed/warnings.json", "processed/warnings.csv"),
}


@dataclass(slots=True)
class LoadedProject:
    data: pd.DataFrame
    mapping: ColumnMapping
    settings: AnalysisSettings
    embedding: pd.DataFrame | None
    excluded: pd.DataFrame | None
    warnings: pd.DataFrame | None
    selected_rows: list[Any]
    source_filename: str | None
    source_bytes: bytes | None
    plot_styles: dict[str, dict[str, Any]]
    areas_of_interest: dict[str, list[Any]]


def save_project(
    path: str | Path | BinaryIO,
    data: pd.DataFrame,
    mapping: ColumnMapping,
    settings: AnalysisSettings,
    result: AnalysisResult | None = None,
    selected_rows: list[Any] | None = None,
    source_filename: str | None = None,
    source_bytes: bytes | None = None,
    plot_styles: dict[str, dict[str, Any]] | None = None,
    areas_of_interest: dict[str, list[Any]] | None = None,
) -> None:
    """Store reproducible input and analysis outputs in a portable zip container."""
    metadata = {
        "format": "sweet-chem-o-mine-project",
        "format_version": 2,
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
        archive.writestr(FRAME_MEMBERS["data"][0], data.to_json(orient="table", index=True))
        archive.writestr(FRAME_MEMBERS["data"][1], data.to_csv(index=False))
        if source_filename and source_bytes is not None:
            archive.writestr(f"raw/source/{Path(source_filename).name}", source_bytes)
        if result is not None:
            for name, frame in (
                ("embedding", result.embedding),
                ("excluded", result.excluded),
                ("warnings", result.warnings),
            ):
                json_member, csv_member = FRAME_MEMBERS[name]
                archive.writestr(json_member, frame.to_json(orient="table", index=True))
                archive.writestr(csv_member, frame.to_csv(index=False))


def load_project(path: str | Path | BinaryIO) -> LoadedProject:
    with ZipFile(path) as archive:
        metadata = json.loads(archive.read("project_metadata.json"))
        saved_settings = json.loads(archive.read("settings.json"))
        names = set(archive.namelist())

        def load_frame(name: str) -> pd.DataFrame | None:
            json_member, csv_member = FRAME_MEMBERS[name]
            if json_member in names:
                frame = pd.read_json(io.StringIO(archive.read(json_member).decode("utf-8")), orient="table")
                if name in {"excluded", "warnings"} and frame.empty and not len(frame.columns):
                    return pd.DataFrame(columns=REPORT_COLUMNS)
                return frame
            if csv_member not in names:
                return None
            try:
                if name == "data":
                    return pd.read_csv(io.BytesIO(archive.read(csv_member)), dtype=object)
                return pd.read_csv(io.BytesIO(archive.read(csv_member)))
            except pd.errors.EmptyDataError:
                return pd.DataFrame(columns=REPORT_COLUMNS)

        data = load_frame("data")
        if data is None:
            raise ValueError("Project archive is missing the imported data table.")
        embedding = load_frame("embedding")
        excluded = load_frame("excluded")
        warnings = load_frame("warnings")

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
