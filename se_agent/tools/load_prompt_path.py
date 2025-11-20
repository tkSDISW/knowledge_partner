# se_agent/tools/load_prompt_path.py
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from se_agent.core.tool_patterns import register_tool, TransformTool
from se_agent.mcp.artifact_registry import ArtifactRegistry, ArtifactPackage

__all__ = ["LoadPromptPathTool"]


@dataclass
class _DirInfo:
    root: str
    notebooks: List[str]
    count: int

@register_tool
class LoadPromptPathTool(TransformTool):
    """
    Transform: Register a directory containing Notebook-based prompt definitions
    as an artifact so other tools/agents can reference it.

    Inputs (contract):
      • prompt_dir_path : str – absolute or relative path to a directory of Notebook files (.ipynb)
      • name            : optional nice name for the created artifact

    Behavior:
      1) Validate the directory exists and is readable.
      2) Enumerate *.ipynb files (non-recursive by default).
      3) Create a `prompt_path` artifact with the directory path and a file listing.

    Returns:
      {
        "message": "📋 Prompt path loaded: id='xxxx' (N notebooks)",
        "artifact_ids": {"prompt_path_artifact_id": "..."}
      }
    """

    # ===============================
    # Contract v1 static metadata
    # ===============================
    TOOL_NAME = "load_prompt_path"
    DESCRIPTION = (
        "LOADS A DIRECTORY OF NOTEBOOK-DEFINED PROMPTS AND SAVES A POINTER ARTIFACT FOR OTHER TOOLS TO USE."
    )
    CATEGORY = "transform"
    USAGE = (
        "Use when you have a folder of .ipynb notebooks that define prompts and you want the agent to remember that folder."
    )

    # Artifact type produced by this tool
    ARTIFACTS: Dict[str, Any] = {
        "prompt_path": {
            "fields": {
                "directory_path": {"type": "path"},
                "notebooks": {"type": "list"},  # list[str] of notebook filenames
                "count": {"type": "integer"},
                "scanned_at": {"type": "string"},  # ISO timestamp
            },
            "schema_version": "1.0",
            "description": "Pointer to a directory that contains .ipynb notebooks which define prompts.",
        }
    }

    # IO schema per contract
    IO_SCHEMA: Dict[str, Any] = {
        "inputs": {
            "prompt_dir_path": {
                "type": "path",
                "required": True,
                "description": "Path to a directory containing .ipynb prompt notebooks.",
            },
            "name": {
                "type": "string",
                "required": False,
                "description": "Optional name to assign to the created prompt_path artifact.",
            },
        },
        "outputs": {
            "prompt_path_artifact_id": {
                "type": "prompt_path",
                "remember": True,
                "description": "Created prompt_path artifact id.",
            }
        },
    }

    # Back-compat fields used by some listers
    name = TOOL_NAME
    description = (
        "Register a directory containing Notebook-based prompt definitions and expose it as a prompt_path artifact."
    )
    artifact_type = "prompt_path"

    # Optional examples
    EXAMPLES: List[Dict[str, Any]] = [
        {
            "input": {
                "prompt_dir_path": "./prompts/icd_reports/",
                "name": "ICD_Prompts",
            },
            "why": "Make a folder of prompt notebooks discoverable to other tools.",
        }
    ]

    # ---------- Helpers ----------
    def _pkg_name(self, artifacts: ArtifactRegistry, package_name: Optional[str]) -> str:
        return package_name or getattr(artifacts, "active_package", None)

    def _scan_dir(self, root: str) -> _DirInfo:
        if not os.path.exists(root):
            raise ValueError(f"Directory not found: {root}")
        if not os.path.isdir(root):
            raise ValueError(f"Path is not a directory: {root}")

        try:
            entries = sorted(os.listdir(root))
        except Exception as e:
            raise RuntimeError(f"Unable to list directory '{root}': {e}")

        notebooks = [e for e in entries if e.lower().endswith(".ipynb")]
        return _DirInfo(root=root, notebooks=notebooks, count=len(notebooks))

    # ---------- Core transform ----------
    def transform(
        self,
        input_data: Dict[str, Any],
        artifacts: ArtifactRegistry,
        package_name: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        pkg_name = self._pkg_name(artifacts, package_name)
        if not artifacts or not pkg_name:
            raise ValueError("No artifact registry or active package.")

        prompt_dir_path = input_data.get("prompt_dir_path")
        if not isinstance(prompt_dir_path, str) or not prompt_dir_path.strip():
            raise ValueError("prompt_dir_path must be a non-empty string path.")

        # Normalize to absolute path for stability
        root = os.path.abspath(os.path.expanduser(prompt_dir_path))
        info = self._scan_dir(root)

        scanned_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        content_record = {
            "directory_path": info.root,
            "notebooks": info.notebooks,
            "count": info.count,
            "scanned_at": scanned_at,
        }

        # Metadata to help UIs
        metadata = {
            "ui_summary": f"Prompt dir: {os.path.basename(info.root)} • {info.count} notebook(s)",
            "directory_path": info.root,
            "count": info.count,
            "scanned_at": scanned_at,
        }

        # Choose a friendly default name if not supplied
        name = input_data.get("name")
        if not name:
            base = os.path.basename(os.path.normpath(info.root)) or "prompts"
            name = f"{base}_prompt_path"
        metadata["name"] = name

        return content_record, metadata

    # ---------- Contract v1 entrypoint ----------
    def run(
        self,
        input_data: Dict[str, Any],
        artifacts: ArtifactRegistry,
        package_name: Optional[str] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        """Contract v1: validate → do work → persist artifact → return dict."""
        content_record, metadata = self.transform(input_data, artifacts, package_name)

        pkg_name = self._pkg_name(artifacts, package_name)
        art = artifacts.add_artifact(
            pkg_name,
            "prompt_path",
            content_record,
            metadata,
        )
        if metadata.get("name"):
            art.name = metadata["name"]

        banner = f"✅ Prompt path loaded as artifact📋: id='{getattr(art, 'id', '')[:8]}' ({metadata.get('count', 0)} notebooks)"
        return {
            "message": banner,
            "artifact_ids": {"prompt_path_artifact_id": getattr(art, "id", None)},
        }
