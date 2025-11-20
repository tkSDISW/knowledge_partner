# se_agent/tools/write_leveled_csv.py
from __future__ import annotations
import csv
from typing import Any, Dict, Optional

from se_agent.core.tool_patterns import register_tool, TransformTool
from se_agent.mcp.artifact_registry import ArtifactRegistry, Artifact  # type: ignore
from se_agent.core.governance import json_serializable, sanitize_ok, check_token_budget

@register_tool
class WriteLeveledCSVTool(TransformTool):
    """
    Write a hierarchical breakdown into a CSV (Level, Name, Description).
    - Accepts hierarchy rows directly or resolves a 'hierarchy' artifact from the active package.
    - Optionally adds a constant column to all rows via `new_column={name, value}`.
    - Persists the hierarchy back into the artifact registry and writes a CSV file.
    """

    name = "write_leveled_csv"
    description = "Write a hierarchical breakdown to CSV. Optionally add a column and persist updated hierarchy to artifacts."
    CATEGORY = "transform"

    IO_SCHEMA: Dict[str, Any] = {
        "inputs": {
            "filename": {
                "type": "path",
                "required": True,
                "description": "Target CSV filename to write."
            },
            "hierarchy": {
                "type": "array",
                "required": False,
                "description": "List[dict] rows. If omitted, tries to resolve a 'hierarchy' artifact from the active package."
            },
            "new_column": {
                "type": "object",
                "required": False,
                "description": "Optional constant column for all rows: {name: str, value: any}."
            },
            "max_tokens": {
                "type": "integer",
                "required": False,
                "description": "Override token budget for governance."
            },
        },
        "outputs": {
            "message": {"type": "string", "remember": False},
            "filename": {"type": "string", "remember": False},
            "rows": {"type": "integer", "remember": False},
            "columns": {"type": "array", "remember": False},
            "artifact_saved": {"type": "boolean", "remember": False},
        },
    }

    def run(self, input_data: Dict[str, Any], artifacts: ArtifactRegistry, package_name: Optional[str] = None, **_) -> Dict[str, Any]:
        filename = input_data.get("filename")
        hierarchy = input_data.get("hierarchy")
        new_column = input_data.get("new_column")
        max_tokens = input_data.get("max_tokens")

        if not filename:
            return {"message": "❌ No filename provided.", "artifact_saved": False}

        # Resolve hierarchy from artifacts if not supplied
        if not hierarchy and artifacts:
            pkg = artifacts.get_package(package_name) if package_name else artifacts.get_active_package()
            if pkg:
                for a in pkg.artifacts.values():
                    if getattr(a, "type", None) == "hierarchy":
                        hierarchy = getattr(a, "content", None)
                        if hierarchy:
                            break

        if not hierarchy:
            return {"message": "❌ No hierarchy found. Load or supply 'hierarchy' first.", "artifact_saved": False}

        # Optional constant column
        if isinstance(new_column, dict) and "name" in new_column:
            col_name = new_column.get("name")
            col_value = new_column.get("value")
            for row in hierarchy:
                row[col_name] = col_value

        # Governance
        ser = json_serializable(hierarchy)
        if not ser["ok"]:
            return {"message": ser["message"], "artifact_saved": False}
        safe = sanitize_ok(hierarchy)
        if not safe["ok"]:
            return {"message": safe["message"], "artifact_saved": False}
        budget = check_token_budget(filename, hierarchy, max_tokens)
        if not budget["ok"]:
            return {"message": budget["message"], "artifact_saved": False}

        # Persist hierarchy artifact
        saved = False
        if artifacts:
            pkg = artifacts.get_package(package_name) if package_name else artifacts.get_active_package()
            if pkg:
                pkg.add_artifact(Artifact(
                    type_="hierarchy",
                    content=hierarchy,
                    metadata={"source_file": filename, "updated": True},
                ))
                saved = True

        # Write CSV
        fieldnames = list(hierarchy[0].keys())
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(hierarchy)

        return {
            "message": f"⚙️📋 Wrote leveled CSV to {filename} and {'saved' if saved else 'did not save'} hierarchy artifact.",
            "filename": filename,
            "rows": len(hierarchy),
            "columns": fieldnames,
            "artifact_saved": saved,
        }
