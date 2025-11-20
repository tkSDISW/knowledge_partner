# se_agent/tools/read_leveled_csv.py

import csv
from se_agent.core.tool_patterns import ImportTool
from se_agent.core.tool_patterns import register_tool

@register_tool
class ReadLeveledCSVTool(ImportTool):
    TOOL_NAME   = "read_leveled_csv"
    DESCRIPTION = "IMPORTS A LEVELED CSV FILE AND CREATES A HIERARCHY ARTIFACT."
    CATEGORY    = "import"

    ARTIFACTS = {
        "hierarchy": {
            "fields": {
                "levels": {"type": "list"},
                "records": {"type": "list"},
                "source_file": {"type": "path"},
            },
            "schema_version": "1.0",
            "description": "Hierarchy data derived from a leveled CSV file.",
        }
    }

    IO_SCHEMA = {
        "inputs": {
            "filename": {
                "type": "path",
                "required": True,
                "description": "CSV file containing leveled hierarchy data",
            },
            "package": {
                "type": "string",
                "required": False,
                "description": "Optional package override; defaults to agent package_name",
            },
        },
        "outputs": {
            "hierarchy_artifact_id": {
                "type": "hierarchy",
                "remember": True,
                "description": "Hierarchy artifact created from the CSV import",
            }
        },
    }

    # ✅ New contract-compliant signature
    def run(self, input_data, artifacts, package_name=None, **kwargs):
        """
        input_data: {"filename": "...", "package": "...?"}
        artifacts:  ArtifactRegistry singleton (passed by AgentCore)
        package_name: current package from AgentCore.run(...)
        """
        if not input_data or "filename" not in input_data:
            return {"error": "No filename provided."}

        # inside run(...)
        raw = input_data or {}
        filename = (
            raw.get("filename")
            or raw.get("path")
            or raw.get("file")
            or raw.get("source")
        )
        if not filename:
            return {"error": "No filename provided. Use 'filename' (or 'path', 'file')."}
        pkg_name = input_data.get("package") or package_name or "default"

        # Read CSV
        try:
            with open(filename, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                fieldnames = list(reader.fieldnames or [])
                records = []
                for row in reader:
                    # keep the whole row; callers can interpret levels as needed
                    records.append(dict(row))
        except FileNotFoundError:
            return {"error": f"File not found: {filename}"}
        except Exception as e:
            return {"error": f"Failed to read '{filename}': {e}"}

        # Build artifact content
        content = {
            "levels": fieldnames,
            "records": records,
            "source_file": filename,
        }

        # Create artifact in the requested package
        art = artifacts.add_artifact(
            package_name=pkg_name,
            type_="hierarchy",
            content=content,
            metadata={"rows": len(records), "source": filename},
        )

        return {
            "message": f"✅ Imported '{filename}' into hierarchy artifact 📋.",
            "artifact_ids": {"hierarchy_artifact_id": art.id},
            "record_count": len(records),
        }

