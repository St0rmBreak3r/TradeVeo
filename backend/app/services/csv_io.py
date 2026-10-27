from __future__ import annotations

import csv
import io
import json
import re
from typing import Any

from pydantic import ValidationError

CSV_COLUMNS = ["instrument", "market", "direction", "opened_at", "closed_at", "entry_price", "exit_price", "size", "multiplier", "fees", "currency", "realized_pnl_override", "strategy", "tags", "notes"]
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_ROWS = 20_000
_TEXT_FIELDS = {"instrument", "market", "direction", "opened_at", "closed_at", "currency", "strategy", "tags", "notes"}


def _safe_cell(value: Any, field: str) -> str:
    text = "" if value is None else str(value)
    if field in _TEXT_FIELDS and re.match(r"^[ \t\r\n]*[=+\-@]", text):
        return "'" + text
    return text


def export_trades(rows: list[dict[str, Any]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        values = {column: row.get(column) for column in CSV_COLUMNS}
        values["tags"] = json.dumps(values["tags"] or [], ensure_ascii=False)
        writer.writerow({column: _safe_cell(values[column], column) for column in CSV_COLUMNS})
    return output.getvalue().encode("utf-8-sig")


def parse_csv(contents: bytes, mapping: dict[str, str] | None = None) -> dict[str, Any]:
    if len(contents) > MAX_FILE_BYTES:
        raise ValueError("CSV file must be no larger than 10 MiB.")
    try:
        text = contents.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV file must use UTF-8 encoding.") from exc
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        headers = reader.fieldnames or []
        if not headers:
            raise ValueError("CSV must have a header row.")
        headers = [header.strip() for header in headers]
        reader.fieldnames = headers
        if len(headers) != len(set(headers)):
            raise ValueError("CSV headers must be unique.")
        resolved = mapping or {field: field for field in CSV_COLUMNS if field in headers}
        missing = [field for field in CSV_COLUMNS if field not in resolved or resolved[field] not in headers]
        if missing:
            raise ValueError("Map every canonical field to a source column; missing: " + ", ".join(missing))
        from backend.app.main import TradeCreate
        rows = []
        errors = []
        count = 0
        for index, raw in enumerate(reader, start=2):
            count += 1
            if count > MAX_ROWS:
                raise ValueError("CSV cannot contain more than 20,000 data rows.")
            if None in raw:
                errors.append({"row": index, "error": "Row has more fields than the header."})
                continue
            try:
                tags = json.loads(raw.get("tags") or "[]")
                if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
                    raise ValueError("Tags must be encoded as a JSON array of strings.")
                item: dict[str, Any] = {field: (raw[resolved[field]] or None) for field in CSV_COLUMNS}
                item["tags"] = tags
                item["market"] = item["market"] or None
                item["strategy"] = item["strategy"] or None
                item["notes"] = item["notes"] or None
                item["closed_at"] = item["closed_at"] or None
                item["exit_price"] = item["exit_price"] or None
                item["realized_pnl_override"] = item["realized_pnl_override"] or None
                TradeCreate.model_validate(item)
                rows.append(item)
            except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                detail = str(exc)
                errors.append({"row": index, "error": detail[:500]})
        return {"headers": headers, "row_count": count, "valid_rows": rows, "errors": errors}
    except csv.Error as exc:
        raise ValueError(f"Malformed CSV: {exc}") from exc
