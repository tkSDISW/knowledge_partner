# se_agent/tools/write_csv.py
from __future__ import annotations
from typing import Any, Dict, Optional

import pandas as pd
from se_agent.core.tool_patterns import register_tool, ExportTool
from se_agent.core.governance import json_serializable, sanitize_ok

@register_tool
class WriteCSVTool(ExportTool):
    """
    Write rows to a CSV file.
    Data can come directly from input_data['data'] (list of dicts),
    or be pulled from an existing 'table' artifact via name/id.
    """

    name = "write_csv"
    description = "Write a list of rows to a CSV file (source: input data or a 'table' artifact)."

    IO_SCHEMA: Dict[str, Any] = {
        "inputs": {
            "filename": {"type": "path", "required": True, "description": "Target CSV file path."},
            "data": {"type": "array", "required": False, "description": "List[dict] rows to write."},
            "name": {"type": "string", "required": False, "description": "Name of a 'table' artifact to use if data not provided."},
            "id": {"type": "string", "required": False, "description": "ID of a 'table' artifact to use if data not provided."},
        },
        "outputs": {
            "filename": {"type": "string", "remember": False},
            "rows": {"type": "integer", "remember": False},
            "columns": {"type": "array", "remember": False},
            "message": {"type": "string", "remember": False},
        }
    }

    # ExportTool does not create new artifacts by design.
    def export(self, input_data: Dict[str, Any], artifacts, package_name: Optional[str] = None) -> Dict[str, Any]:
        filename = input_data.get("filename")
        if not filename:
            return {"message": "❌ No filename provided."}

        data = input_data.get("data")

        # Resolve from artifact if needed
        if data is None and artifacts:
            name = input_data.get("name")
            art_id = input_data.get("id")
            pkg_name = package_name or getattr(artifacts, "active_package", None)
            art = None

            if name and hasattr(artifacts, "get_artifact"):
                try:
                    art = artifacts.get_artifact(name=name, package_name=pkg_name)
                except Exception:
                    art = None
            if art_id and not art and hasattr(artifacts, "get_artifact"):
                try:
                    art = artifacts.get_artifact(id=art_id, package_name=pkg_name)
                except Exception:
                    art = None

            if art and getattr(art, "type", None) == "table":
                data = getattr(art, "content", None)

        if data is None:
            return {"message": "❌ No data provided and no source artifact (name/id) resolved."}

        # Governance
        ser = json_serializable(data)
        if not ser["ok"]:
            return {"message": ser["message"]}
        safe = sanitize_ok(data)
        if not safe["ok"]:
            return {"message": safe["message"]}

        df = pd.DataFrame(data)
        df.to_csv(filename, index=False)

        return {
            "message": f"📋 Wrote CSV to {filename}",
            "filename": filename,
            "rows": int(len(df)),
            "columns": [str(c) for c in df.columns],
        }