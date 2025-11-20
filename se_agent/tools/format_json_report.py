# se_agent/tools/format_json_report.py
from __future__ import annotations
from typing import Any, Dict, Optional
import json

from se_agent.core.tool_patterns import register_tool, DisplayTool
from se_agent.core.governance import json_serializable, sanitize_ok
from capella_tools import Open_AI_RAG_manager  # type: ignore

@register_tool
class FormatJsonReportTool(DisplayTool):
    """
    Generate an engineer-friendly HTML report for a JSON-based artifact or payload.
    - Input may be an artifact by name/id from the active package OR direct 'json' content.
    - Returns 'ui'/'html' for rendering in chat UI.
    """
    # TOOL_NAME ="format_json_report"
    description = "Format a JSON artifact or raw JSON as concise, engineer-friendly HTML using the RAG Manager."

    IO_SCHEMA: Dict[str, Any] = {
        "inputs": {
            "name": {"type": "string", "required": False, "description": "Artifact name to render (JSON-like)."},
            "id": {"type": "string", "required": False, "description": "Artifact id to render (JSON-like)."},
            "json": {"type": "any", "required": False, "description": "Direct JSON value to render if no artifact is provided."},
            "title": {"type": "string", "required": False, "description": "Optional title to hint formatter."},
        },
        "outputs": {
            "message": {"type": "string", "remember": False},
            "ui": {"type": "string", "remember": False},
            "html": {"type": "string", "remember": False},
            "displayed": {"type": "boolean", "remember": False},
            "source": {"type": "string", "remember": False},
        }
    }

    def display(self, input_data: Dict[str, Any], artifacts, package_name: Optional[str] = None) -> Dict[str, Any]:
        name = input_data.get("name")
        artifact_id = input_data.get("id")
        raw_json = input_data.get("json")
        title = input_data.get("title", "JSON View")

        # Resolve package
        pkg = artifacts.get_package(package_name) if package_name else artifacts.get_active_package()
        if not pkg:
            return {"message": f"❌ No package found (package_name={package_name})", "displayed": False}

        # Resolve artifact or raw JSON
        payload = None
        source = "raw"
        if raw_json is not None:
            payload = raw_json
        else:
            artifact = None
            if name and hasattr(pkg, "get_by_name"):
                try:
                    artifact = pkg.get_by_name(name)
                except Exception:
                    artifact = None
            if artifact_id and not artifact and hasattr(pkg, "get_by_id"):
                try:
                    artifact = pkg.get_by_id(artifact_id)
                except Exception:
                    artifact = None

            if not artifact:
                return {"message": f"❌ Artifact not found (name={name}, id={artifact_id})", "displayed": False}
            payload = artifact["content"] if isinstance(artifact, dict) else getattr(artifact, "content", artifact)
            source = str(name or artifact_id or "artifact")

        # Make a formatter-friendly string
        ser = json_serializable(payload)
        if not ser["ok"]:
            try:
                payload_str = str(payload)
            except Exception:
                return {"message": ser["message"], "displayed": False}
        else:
            try:
                payload_str = json.dumps(payload, indent=2, ensure_ascii=False)
            except Exception:
                payload_str = str(payload)

        # Safety scan (lightweight)
        safe = sanitize_ok(payload_str)
        if not safe["ok"]:
            return {"message": safe["message"], "displayed": False}

        # Format via RAG manager
        try:
            fmt = Open_AI_RAG_manager.ChatGPTAnalyzer(yaml_content=payload_str)
            baseline_prompt = (
                "You are a formatting assistant. Convert the following JSON into a concise,"
                " engineer-friendly HTML snippet. Use headings, short bullet lists, and compact tables."
            )
            fmt.initial_prompt(baseline_prompt)
            html = fmt.get_response()

            return {
                "message": f"🖨️ Formatted {source} into engineer-friendly HTML.",
                "ui": html,
                "html": html,
                "displayed": True,
                "source": source,
            }
        except Exception as e:
            return {
                "message": f"❌ JSON formatting failed: {e}",
                "displayed": False,
                "source": source,
            }

