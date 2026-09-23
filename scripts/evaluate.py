"""Evaluate frozen paired outcomes without making paid API calls."""

import argparse
import json
from pathlib import Path

from model_router.evaluation import OutcomeRow, evaluate

parser = argparse.ArgumentParser()
parser.add_argument("data", type=Path)
parser.add_argument("--threshold", type=float, default=0.9)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
rows = [
    OutcomeRow.model_validate_json(line)
    for line in args.data.read_text(encoding="utf-8").splitlines()
    if line.strip()
]
result = evaluate(rows, threshold=args.threshold)
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result["laya"], indent=2))
