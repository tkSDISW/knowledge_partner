# se_agent/tools/read_csv.py
from __future__ import annotations
from typing import Any, Dict, List
import pandas as pd


from se_agent.core.tool_patterns import register_tool,  ImportTool
from se_agent.mcp.artifact_registry import ArtifactRegistry


@register_tool
class ReadCSVTool(ImportTool):
    """
    Import a CSV file into a 'table' artifact.
    Content structure:
      {
        "columns": [col1, col2, ...],
        "records": [ {col1:val,...}, ... ],
        "source_file": "<path>"
      }
    """

    TOOL_NAME   = "read_csv"
    DESCRIPTION = "IMPORT A CSV AND CREATE A 'TABLE' ARTIFACT (COLUMNS + RECORDS)."
    CATEGORY    = "import"

    ARTIFACTS: Dict[str, Any] = {
        "table": {
            "fields": {
                "columns": {"type": "list", "description": "Column names from the CSV."},
                "records": {"type": "list", "description": "List of row dicts."},
                "source_file": {"type": "path"},
            },
            "schema_version": "1.0",
            "description": "Generic table parsed from CSV.",
        }
    }

    IO_SCHEMA = {
        "inputs": {
            "filename": {
                "type": "path",
                "required": True,
                "description": "Path to the CSV file to import.",
            },
            "package": {
                "type": "string",
                "required": False,
                "description": "Artifact package (defaults to agent package).",
            },
        },
        "outputs": {
            "table_artifact_id": {
                "type": "table",
                "remember": True,  # set True if you want to keep tables in convo memory by default
                "description": "Created 'table' artifact id.",
            }
        },
    }

    def run(self, input_data, artifacts: ArtifactRegistry, package_name=None, **kwargs):
        raw = input_data or {}
        filename = raw.get("filename") or raw.get("path") or raw.get("file")
        pkg_name = raw.get("package") or package_name

        if not filename:
            return {"error": "❌ No filename provided. Use 'filename' (or 'path', 'file')."}
        if not pkg_name:
            return {"error": "❌ No package selected. Pass `package` or use agent.use_package(...)."}

        try:
            df = pd.read_csv(filename)
        except FileNotFoundError:
            return {"error": f"File not found: {filename}"}
        except Exception as e:
            return {"error": f"Failed to read '{filename}': {e}"}

        columns: List[str] = [str(c) for c in df.columns]
        records: List[Dict[str, Any]] = df.to_dict(orient="records")

        content = {
            "columns": columns,
            "records": records,
            "source_file": filename,
        }

        art = artifacts.add_artifact(
            package_name=pkg_name,
            type_="table",
            content=content,
            metadata={"rows": len(records), "columns": columns, "source": filename},
        )

        return {
            "message": f"✅ Imported '{filename}' into table artifact 📋.",
            "artifact_ids": {"table_artifact_id": art.id},
            "row_count": len(records),
            "columns": columns,
        }

