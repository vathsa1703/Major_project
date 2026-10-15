"""Combine the split CSVs in ./data into ONE Excel file with a 'split' column.
Sheets: scenarios, users, trajectory, obstacles, sweep.
Run after make_dataset.py:   python export_excel.py"""
from pathlib import Path

import pandas as pd

OUT = Path(__file__).parent / "data"
LIMIT = 1_048_575  # Excel rows per sheet, minus the header


def combine(prefix):
    parts = []
    for split in ["train", "val", "test"]:
        df = pd.read_csv(OUT / f"{prefix}_{split}.csv")
        df.insert(0, "split", split)
        parts.append(df)
    df = pd.concat(parts, ignore_index=True)
    assert len(df) <= LIMIT, f"{prefix} has {len(df)} rows, over Excel's limit"
    return df


if __name__ == "__main__":
    names = ["scenarios", "users", "trajectory", "obstacles", "sweep"]
    scenarios, users, trajectory, obstacles, sweep = (combine(n) for n in names)
    path = OUT / "uav_noma_dataset.xlsx"
    with pd.ExcelWriter(path, engine="xlsxwriter") as xw:
        scenarios.to_excel(xw, sheet_name="scenarios", index=False)
        obstacles.to_excel(xw, sheet_name="obstacles", index=False)
        users.to_excel(xw, sheet_name="users", index=False)
        trajectory.to_excel(xw, sheet_name="trajectory", index=False)
        sweep.to_excel(xw, sheet_name="sweep", index=False)
    frames = (scenarios, users, trajectory, obstacles, sweep)
    sizes = ", ".join(f"{n} {len(d)} rows" for n, d in zip(names, frames, strict=True))
    print(f"saved {path.name}: {sizes}")
