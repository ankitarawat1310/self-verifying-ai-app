import csv
import io
from typing import Any, Dict, List


def parse_and_validate_csv(csv_content: str, required_headers: List[str]) -> List[Dict[str, Any]]:
    if not csv_content.strip():
        raise ValueError("empty csv")
    stream = io.StringIO(csv_content.strip())
    reader = csv.DictReader(stream)
    if not reader.fieldnames:
        raise ValueError("no headers")
    missing = [h for h in required_headers if h not in reader.fieldnames]
    if missing:
        raise ValueError(f"missing headers: {missing}")
    return [dict(row) for row in reader if all(v and str(v).strip() for v in row.values())]
