from __future__ import annotations

import sys


def analysis_smoke() -> int:
    import pandas as pd

    from sweet_chem_o_mine.analysis import AnalysisSettings, ColumnMapping, run_analysis

    data = pd.DataFrame(
        {
            "name": ["ethanol", "ethylamine", "propane"],
            "smiles": ["CCO", "CCN", "CCC"],
        }
    )
    run_analysis(data, ColumnMapping("name", "smiles", None), AnalysisSettings(n_neighbors=2))
    return 0


from sweet_chem_o_mine.app import main


if __name__ == "__main__":
    if "--analysis-smoke" in sys.argv:
        raise SystemExit(analysis_smoke())
    raise SystemExit(main())
