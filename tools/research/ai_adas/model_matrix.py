"""Aggregate model metadata into normalized JSON/CSV (no weights, no downloads)."""
import csv, json, sys
from pathlib import Path

REQUIRED = ["model","task","source","license","params","input","flops","metric",
            "export_onnx","int8","op_risk","ipu_feas","cpu_feas","android_feas","value"]

def load(rows_path: Path):
    import json as j
    return j.loads(rows_path.read_text(encoding="utf-8"))

def main():
    if len(sys.argv) < 3:
        print("usage: model_matrix.py <models.json> <out_prefix>"); raise SystemExit(2)
    rows = load(Path(sys.argv[1]))
    for r in rows:
        for k in REQUIRED:
            r.setdefault(k, "UNKNOWN")
    out = sys.argv[2]
    Path(out + ".json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    with open(out + ".csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=REQUIRED); w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "UNKNOWN") for k in REQUIRED})
    print(f"wrote {len(rows)} rows -> {out}.json/.csv")

if __name__ == "__main__":
    main()
