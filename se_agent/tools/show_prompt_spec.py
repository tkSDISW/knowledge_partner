# se_agent/tools/show_prompt_spec.py
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from se_agent.core.tool_patterns import register_tool, DisplayTool
from se_agent.mcp.artifact_registry import ArtifactRegistry

__all__ = ["ShowPromptSpecTool"]

@register_tool
class ShowPromptSpecTool(DisplayTool):
    """
    Display: Show a prompt_spec artifact with a compact preview.

    Inputs:
      • prompt_spec_name | prompt_spec_id

    Returns:
      {
        "message": "Prompt: <title> (key) • v<version>",
        "prompt": { ... },  # full JSON
        "content_preview": "<pretty JSON up to 2k chars>"
      }
    """

    TOOL_NAME = "show_prompt_spec"
    DESCRIPTION = "DISPLAYS A PROMPT_SPEC ARTIFACT WITH TITLE, VERSION, AND JSON PREVIEW."
    CATEGORY = "display"
    USAGE = "Use after building a prompt_spec from a notebook."

    ARTIFACTS: Dict[str, Any] = {}

    IO_SCHEMA: Dict[str, Any] = {
        "inputs": {
            "prompt_spec_name": {"type": "string", "required": False},
            "prompt_spec_id": {"type": "string", "required": False},
        },
        "outputs": {}
    }

    name = TOOL_NAME
    description = "Show a prompt_spec artifact (pretty JSON preview)."

    def _pkg(self, artifacts: ArtifactRegistry, package_name: Optional[str]) -> str:
        return package_name or getattr(artifacts, "active_package", None)

    def _get_by_name(self, artifacts: ArtifactRegistry, pkg_name: str, name: str):
        try:
            pkg = artifacts.get_package(pkg_name)
            arts = list(pkg.artifacts.values())
            matches = [a for a in arts if getattr(a, "name", None) == name]
            if not matches:
                return None
            matches.sort(key=lambda a: getattr(a, "_created_at", 0), reverse=True)
            return matches[0]
        except Exception:
            return None

    def _get_by_id(self, artifacts: ArtifactRegistry, pkg_name: str, art_id: str):
        try:
            return artifacts.get_artifact(pkg_name, art_id)
        except Exception:
            return None

    def run(self, input_data: Dict[str, Any], artifacts: ArtifactRegistry, package_name: Optional[str] = None, **_: Any) -> Dict[str, Any]:
        pkg = self._pkg(artifacts, package_name)
        if not pkg:
            raise ValueError("No artifact registry or active package.")
        name = input_data.get("prompt_spec_name")
        pid = input_data.get("prompt_spec_id")
        art = None
        if name:
            art = self._get_by_name(artifacts, pkg, name)
        if not art and pid:
            art = self._get_by_id(artifacts, pkg, pid)
        if not art:
            raise ValueError("prompt_spec artifact not found.")

        content = getattr(art, "content", {}) or {}
        title = content.get("title") or content.get("key") or getattr(art, "name", "prompt")
        version = content.get("version", "")
        key = content.get("key", "")

        try:
            pretty = json.dumps(content, ensure_ascii=False, indent=2)
        except Exception:
            pretty = str(content)
        preview = pretty if len(pretty) <= 2000 else pretty[:2000] + "…"

        return {
            "message": f"Prompt: {title} ({key}) • v{version}",
            "prompt": content,
            "content_preview": preview,
        }

