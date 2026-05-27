from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable

import numpy as np
import pandas as pd
from rdkit import Chem, rdBase
from rdkit.Chem import rdFingerprintGenerator


def parse_smiles_quietly(smiles: str):  # type: ignore[no-untyped-def]
    """Parse a SMILES string without forwarding RDKit diagnostics to the console."""
    with rdBase.BlockLogs():
        return Chem.MolFromSmiles(smiles)


@dataclass(slots=True)
class ColumnMapping:
    display_name: str
    smiles: str
    value: str
    stdev: str | None = None
    value_label: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, str | None]) -> "ColumnMapping":
        return cls(
            display_name=str(value["display_name"]),
            smiles=str(value["smiles"]),
            value=str(value["value"]),
            stdev=value.get("stdev") or None,
            value_label=value.get("value_label") or None,
        )

    def display_value_label(self) -> str:
        return (self.value_label or "").strip() or self.value


@dataclass(slots=True)
class AnalysisSettings:
    fingerprint_radius: int = 2
    fingerprint_bits: int = 2048
    include_chirality: bool = False
    n_neighbors: int = 10
    min_dist: float = 0.01
    metric: str = "jaccard"
    random_seed: int = 10

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "AnalysisSettings":
        return cls(**value)


@dataclass(slots=True)
class AnalysisResult:
    embedding: pd.DataFrame
    excluded: pd.DataFrame
    settings: AnalysisSettings
    mapping: ColumnMapping
    warnings: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(columns=["source_row", "display_name", "smiles", "reason"])
    )


def _validate_mapping(data: pd.DataFrame, mapping: ColumnMapping) -> None:
    required_columns = [mapping.display_name, mapping.smiles, mapping.value]
    if mapping.stdev:
        required_columns.append(mapping.stdev)
    missing = [column for column in required_columns if column not in data.columns]
    if missing:
        raise ValueError(f"Mapped columns are missing from the table: {', '.join(missing)}")


def run_analysis(
    data: pd.DataFrame,
    mapping: ColumnMapping,
    settings: AnalysisSettings | None = None,
    progress: Callable[[int, str], None] | None = None,
) -> AnalysisResult:
    """Validate compounds, compute Morgan fingerprints, and calculate UMAP coordinates."""
    def report(value: int, message: str) -> None:
        if progress is not None:
            progress(value, message)

    settings = settings or AnalysisSettings()
    report(2, "Validating column mapping...")
    _validate_mapping(data, mapping)

    fp_generator = rdFingerprintGenerator.GetMorganGenerator(
        radius=settings.fingerprint_radius,
        fpSize=settings.fingerprint_bits,
        includeChirality=settings.include_chirality,
    )

    fingerprints: list[np.ndarray] = []
    valid_rows: list[dict[str, Any]] = []
    invalid_rows: list[dict[str, Any]] = []
    warning_rows: list[dict[str, Any]] = []
    duplicated_names = set(
        data.index[data[mapping.display_name].astype(str).duplicated(keep=False)].tolist()
    )

    total_rows = max(1, len(data))
    for row_number, (source_index, row) in enumerate(data.iterrows(), start=1):
        reasons: list[str] = []
        smiles = row[mapping.smiles]
        value = pd.to_numeric(row[mapping.value], errors="coerce")
        stdev = pd.to_numeric(row[mapping.stdev], errors="coerce") if mapping.stdev else np.nan

        if pd.isna(smiles) or not str(smiles).strip():
            reasons.append("Missing SMILES")
            mol = None
        else:
            mol = parse_smiles_quietly(str(smiles).strip())
            if mol is None:
                reasons.append("Invalid SMILES")
        if pd.isna(value):
            reasons.append("Non-numeric value")

        if reasons:
            invalid_rows.append(
                {
                    "source_row": source_index,
                    "display_name": row[mapping.display_name],
                    "smiles": smiles,
                    "reason": "; ".join(reasons),
                }
            )
            report(5 + int(55 * row_number / total_rows), f"Processing molecular structures: {row_number}/{total_rows}")
            continue

        fingerprints.append(fp_generator.GetFingerprintAsNumPy(mol))
        valid_rows.append(
            {
                "source_row": source_index,
                "display_name": str(row[mapping.display_name]),
                "smiles": str(smiles).strip(),
                "value": float(value),
                "stdev": float(stdev) if not pd.isna(stdev) else np.nan,
            }
        )
        warning_reasons: list[str] = []
        if source_index in duplicated_names:
            warning_reasons.append("Duplicate display name")
        if mapping.stdev and pd.isna(stdev):
            warning_reasons.append("Missing or non-numeric error bar")
        if warning_reasons:
            warning_rows.append(
                {
                    "source_row": source_index,
                    "display_name": row[mapping.display_name],
                    "smiles": smiles,
                    "reason": "; ".join(warning_reasons),
                }
            )
        report(5 + int(55 * row_number / total_rows), f"Processing molecular structures: {row_number}/{total_rows}")

    if len(valid_rows) < 3:
        raise ValueError("At least three rows with valid SMILES and numeric values are needed.")

    effective_neighbors = min(settings.n_neighbors, len(valid_rows) - 1)
    if effective_neighbors < 2:
        raise ValueError("UMAP requires at least two neighbours after input validation.")

    report(65, "Loading UMAP reducer...")
    import umap

    report(70, "Calculating UMAP embedding...")
    reducer = umap.UMAP(
        n_neighbors=effective_neighbors,
        min_dist=settings.min_dist,
        metric=settings.metric,
        random_state=settings.random_seed,
    )
    coordinates = reducer.fit_transform(np.asarray(fingerprints))
    report(95, "Preparing analysis results...")
    embedding = pd.DataFrame(valid_rows)
    embedding["UMAP 1"] = coordinates[:, 0]
    embedding["UMAP 2"] = coordinates[:, 1]

    excluded = pd.DataFrame(
        invalid_rows,
        columns=["source_row", "display_name", "smiles", "reason"],
    )
    warnings = pd.DataFrame(
        warning_rows,
        columns=["source_row", "display_name", "smiles", "reason"],
    )
    return AnalysisResult(embedding, excluded, settings, mapping, warnings)
