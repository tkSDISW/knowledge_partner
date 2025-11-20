# se_agent/tools/search_prompts.py
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from se_agent.core.tool_patterns import register_tool,  TransformTool
from se_agent.mcp.artifact_registry import ArtifactRegistry

__all__ = ["SearchPromptsTool"]

@register_tool
class SearchPromptsTool(TransformTool):
    """
    Query: List notebooks inside a prompt_path artifact, optionally filtering by a search term.

    Inputs:
      • prompt_path_name | prompt_path_id : the prompt_path artifact to inspect
      • query                            : optional substring (case-insensitive) to filter filenames
      • recursive                        : optional, include notebooks in subdirectories (default False)

    Returns:
      { "message": "N notebooks found", "results": [ {"name": "...", "path": "..."}, ... ] }
    """

    TOOL_NAME = "search_prompts"
    DESCRIPTION = "LISTS PROMPT NOTEBOOKS WITHIN A PROMPT_PATH ARTIFACT, WITH OPTIONAL FILTERING."
    CATEGORY = "query"
    USAGE = "Use after load_prompt_path to discover available prompt notebooks."

    ARTIFACTS: Dict[str, Any] = {}

    IO_SCHEMA: Dict[str, Any] = {
        "inputs": {
            "prompt_path_name": {"type": "string", "required": False},
            "prompt_path_id": {"type": "string", "required": False},
            "query": {"type": "string", "required": False},
            "recursive": {"type": "boolean", "required": False},
        },
        "outputs": {}
    }

    name = TOOL_NAME
    description = "List notebooks from a prompt_path (filter by substring)."

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

    def _walk(self, root: str):
        for r, _, files in os.walk(root):
            for f in files:
                if f.lower().endswith(".ipynb"):
                    yield os.path.join(r, f)

    def run(self, input_data: Dict[str, Any], artifacts: ArtifactRegistry, package_name: Optional[str] = None, **_: Any) -> Dict[str, Any]:
        pkg = self._pkg(artifacts, package_name)
        if not pkg:
            raise ValueError("No artifact registry or active package.")
        path_name = input_data.get("prompt_path_name")
        path_id = input_data.get("prompt_path_id")
        recursive = bool(input_data.get("recursive"))
        q = (input_data.get("query") or "").lower()

        art = None
        if path_name:
            art = self._get_by_name(artifacts, pkg, path_name)
        if not art and path_id:
            art = self._get_by_id(artifacts, pkg, path_id)
        if not art:
            raise ValueError("prompt_path artifact not found.")

        root = (getattr(art, "content", {}) or {}).get("directory_path")
        if not isinstance(root, str) or not root:
            raise ValueError("prompt_path artifact missing 'directory_path'.")

        results: List[Dict[str, str]] = []
        if recursive:
            for p in self._walk(root):
                base = os.path.relpath(p, root)
                if q and q not in base.lower():
                    continue
                results.append({"name": base, "path": p})
        else:
            for base in sorted(os.listdir(root)):
                if not base.lower().endswith(".ipynb"):
                    continue
                if q and q not in base.lower():
                    continue
                results.append({"name": base, "path": os.path.join(root, base)})

        return {
            "message": f"{len(results)} notebook(s) found.",
            "results": results,
        }
