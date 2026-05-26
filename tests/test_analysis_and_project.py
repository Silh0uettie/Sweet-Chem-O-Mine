from __future__ import annotations

import io
import types
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from sweet_chem_o_mine.analysis import AnalysisSettings, ColumnMapping, run_analysis
from sweet_chem_o_mine.project_file import load_project, save_project


class FastReducer:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    def fit_transform(self, fingerprints: np.ndarray) -> np.ndarray:
        length = len(fingerprints)
        return np.column_stack((np.arange(length, dtype=float), np.zeros(length)))


class AnalysisAndProjectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mapping = ColumnMapping("name", "smiles", "value", "stdev")
        self.data = pd.DataFrame(
            {
                "name": ["aspirin", "caffeine", "ethanol", "missing", "invalid"],
                "smiles": [
                    "CC(=O)OC1=CC=CC=C1C(=O)O",
                    "Cn1cnc2c1c(=O)n(C)c(=O)n2C",
                    "CCO",
                    "",
                    "invalid_smiles",
                ],
                "value": [10.0, 25.0, -2.0, 7.0, 3.0],
                "stdev": [1.0, 2.0, 0.5, 0.4, 0.2],
            }
        )

    def run_fast_analysis(self):
        fake_umap = types.SimpleNamespace(UMAP=FastReducer)
        with patch.dict("sys.modules", {"umap": fake_umap}):
            return run_analysis(
                self.data,
                self.mapping,
                AnalysisSettings(n_neighbors=2, random_seed=10),
            )

    def test_analysis_generates_embedding_and_exclusion_report(self) -> None:
        progress: list[tuple[int, str]] = []
        fake_umap = types.SimpleNamespace(UMAP=FastReducer)
        with patch.dict("sys.modules", {"umap": fake_umap}):
            result = run_analysis(
                self.data,
                self.mapping,
                AnalysisSettings(n_neighbors=2, random_seed=10),
                lambda value, message: progress.append((value, message)),
            )
        self.assertEqual(len(result.embedding), 3)
        self.assertEqual(len(result.excluded), 2)
        self.assertIn("UMAP 1", result.embedding.columns)
        self.assertIn("Missing SMILES", result.excluded["reason"].to_list())
        self.assertIn("Invalid SMILES", result.excluded["reason"].to_list())
        self.assertIn(70, [value for value, _ in progress])
        self.assertEqual(progress[-1][0], 95)

    def test_analysis_allows_no_error_bar_column(self) -> None:
        mapping = ColumnMapping("name", "smiles", "value", None, "Inhibition (%)")
        fake_umap = types.SimpleNamespace(UMAP=FastReducer)
        with patch.dict("sys.modules", {"umap": fake_umap}):
            result = run_analysis(
                self.data.drop(columns=["stdev"]),
                mapping,
                AnalysisSettings(n_neighbors=2),
            )
        self.assertTrue(result.embedding["stdev"].isna().all())
        self.assertEqual(mapping.display_value_label(), "Inhibition (%)")

    def test_analysis_reports_non_fatal_data_warnings(self) -> None:
        data = self.data.copy()
        data.loc[1, "name"] = "aspirin"
        data.loc[1, "stdev"] = np.nan
        fake_umap = types.SimpleNamespace(UMAP=FastReducer)
        with patch.dict("sys.modules", {"umap": fake_umap}):
            result = run_analysis(data, self.mapping, AnalysisSettings(n_neighbors=2))
        self.assertEqual(len(result.embedding), 3)
        self.assertEqual(len(result.warnings), 2)
        reasons = "; ".join(result.warnings["reason"].to_list())
        self.assertIn("Duplicate display name", reasons)
        self.assertIn("Missing or non-numeric error bar", reasons)

    def test_project_roundtrip_includes_data_and_embedding(self) -> None:
        data = self.data.copy()
        data.loc[1, "name"] = "aspirin"
        data.loc[1, "stdev"] = np.nan
        fake_umap = types.SimpleNamespace(UMAP=FastReducer)
        with patch.dict("sys.modules", {"umap": fake_umap}):
            result = run_analysis(data, self.mapping, AnalysisSettings(n_neighbors=2))
        package = io.BytesIO()
        save_project(
            package,
            data,
            ColumnMapping("name", "smiles", "value", "stdev", "Average inhibition (%)"),
            result.settings,
            result=result,
            selected_rows=[0],
            source_filename="compounds.csv",
            source_bytes=b"name,smiles\n",
            plot_styles={"umap": {"title": "A UMAP", "color": "viridis", "marker_size": 20}},
            areas_of_interest={"Hit cluster": [0, 2]},
        )
        package.seek(0)
        loaded = load_project(package)

        self.assertEqual(len(loaded.data), len(self.data))
        self.assertEqual(len(loaded.embedding), 3)
        self.assertEqual(loaded.selected_rows, [0])
        self.assertEqual(loaded.source_filename, "compounds.csv")
        self.assertEqual(loaded.source_bytes, b"name,smiles\n")
        self.assertEqual(loaded.plot_styles["umap"]["title"], "A UMAP")
        self.assertEqual(loaded.areas_of_interest["Hit cluster"], [0, 2])
        self.assertEqual(loaded.mapping.value_label, "Average inhibition (%)")
        self.assertEqual(len(loaded.warnings), 2)

    def test_project_loads_blank_saved_warning_report(self) -> None:
        result = self.run_fast_analysis()
        result.warnings = pd.DataFrame()
        package = io.BytesIO()
        save_project(package, self.data, self.mapping, result.settings, result=result)
        package.seek(0)
        loaded = load_project(package)
        self.assertTrue(loaded.warnings.empty)
        self.assertIn("reason", loaded.warnings.columns)


if __name__ == "__main__":
    unittest.main()
