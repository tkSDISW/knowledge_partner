
# se_agent/mcp/artifact_registry.py

import json
import uuid
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

# ============================================================
# ARTIFACT CLASSES (unchanged)
# ============================================================


class Artifact:
    """Lightweight container for model/file content."""
    def __init__(
        self,
        type_: str,
        content: Any,
        metadata: Optional[Dict[str, Any]] = None,
        name: Optional[str] = None,               # ← NEW (optional)
    ):
        self.id = str(uuid.uuid4())
        self.type = type_
        self.content = content
        self.metadata: Dict[str, Any] = metadata or {}
        if name is not None:                      # store name in metadata (compat)
            self.metadata["name"] = str(name)

    @property
    def name(self) -> Optional[str]:
        return self.metadata.get("name")

    @name.setter
    def name(self, value: Optional[str]) -> None:
        if value is None:
            self.metadata.pop("name", None)
        else:
            self.metadata["name"] = str(value)

class ArtifactPackage:
    """A named collection of artifacts and optional pipelines."""
    def __init__(self, name: str):
        self.name = name
        self.artifacts: Dict[str, Artifact] = {}
        self.pipelines: List[Dict] = []
    def _unique_name(self, desired: str) -> str:
        """Return a unique name within this package by appending (n) as needed."""
        if not desired:
            return desired
        existing = {getattr(a, "name", None) for a in self.artifacts.values()}
        if desired not in existing:
            return desired
        n = 2
        while True:
            candidate = f"{desired} ({n})"
            if candidate not in existing:
                return candidate
            n += 1

    def add_artifact(self, artifact: "Artifact", *, ensure_unique_name: bool = True) -> "Artifact":
        # ensure metadata and timestamps
        if not hasattr(artifact, "metadata") or artifact.metadata is None:
            artifact.metadata = {}
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        artifact.metadata.setdefault("created_at", now)
        artifact.metadata["updated_at"] = now
    
        # enforce unique name (auto-disambiguate)
        if ensure_unique_name and artifact.name:
            artifact.name = self._unique_name(artifact.name)
    
        # register
        self.artifacts[artifact.id] = artifact
    
        # announce
        if artifact.name:
            artifact._announce = (
                f"✅ Artifact created: name='{artifact.name}' "
                f"id='{artifact.id[:8]}' "
                f"type='{artifact.type}' in package '{self.name}'"
            )
        else:
            artifact._announce = (
                f"✅ Artifact created: id='{artifact.id[:8]}' "
                f"type='{artifact.type}' in package '{self.name}'"
            )
    
        artifact._created_at = now  # keep internal timestamp if you use it elsewhere
        print(artifact._announce)
        return artifact

    def add_pipeline(self, pipeline: List[Dict]):
        self.pipelines.append(pipeline)

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "artifacts": [a.to_dict() for a in self.artifacts.values()],
            "pipelines": self.pipelines,
        }

    @staticmethod
    def from_dict(data: Dict) -> "ArtifactPackage":
        pkg = ArtifactPackage(data["name"])
        for art in data.get("artifacts", []):
            pkg.add_artifact(Artifact.from_dict(art))
        for pl in data.get("pipelines", []):
            pkg.add_pipeline(pl)
        return pkg

    def get_by_id(self, artifact_id: str):
        return self.artifacts.get(artifact_id)

    def get_by_name(self, name: str):
        matches = [a for a in self.artifacts.values() if a.name == name]
        return matches[-1] if matches else None

    def list_artifacts(self, type_filter: str = None):
        if type_filter:
            return [a for a in self.artifacts.values() if a.type == type_filter]
        return list(self.artifacts.values())


# ============================================================
# ARTIFACT & TOOL REGISTRY
# ============================================================

class ArtifactRegistry:
    """Registry to manage artifact packages and tool metadata, including planning."""

    def __init__(self):
        self.packages: Dict[str, ArtifactPackage] = {}
        self.active_package: Optional[str] = None
        self.tools: Dict[str, Dict[str, Any]] = {}
        self.artifact_flows: Dict[str, Dict[str, List[str]]] = {
            "produces": {},  # artifact_type → [tool_names]
            "consumes": {},  # artifact_type → [tool_names]
        }

    # ---------- PACKAGE MANAGEMENT ----------
    def create_package(self, name: str) -> ArtifactPackage:
        pkg = ArtifactPackage(name)
        self.packages[name] = pkg
        return pkg

    def use_package(self, name: str):
        if name not in self.packages:
            raise ValueError(f"Package '{name}' does not exist.")
        self.active_package = name

    def get_active_package(self) -> Optional[ArtifactPackage]:
        if not self.active_package:
            return None
        return self.packages[self.active_package]
    # --- Import / Export ---
    def export_package(self, package_name: str, out_path: Path):
        if package_name not in self.packages:
            raise ValueError(f"Package '{package_name}' does not exist.")

        pkg = self.packages[package_name]
        data = pkg.to_dict()

        out_path = Path(out_path)
        if out_path.suffix != ".zip":
            out_path = out_path.with_suffix(".zip")

        with zipfile.ZipFile(out_path, "w") as zf:
            zf.writestr(f"{package_name}.json", json.dumps(data, indent=2))

    def import_package(self, zip_path: Path) -> ArtifactPackage:
        zip_path = Path(zip_path)
        with zipfile.ZipFile(zip_path, "r") as zf:
            # Expect JSON inside
            names = [n for n in zf.namelist() if n.endswith(".json")]
            if not names:
                raise ValueError("No JSON file found in package ZIP.")

            data = json.loads(zf.read(names[0]).decode("utf-8"))
            pkg = ArtifactPackage.from_dict(data)
            self.packages[pkg.name] = pkg
            return pkg

    def get_package(self, name: str):
        """Return ArtifactPackage by name or None."""
        return self.packages.get(name)

    # ---------- ARTIFACT MANAGEMENT ----------
    def add_artifact(self, package_name: str, type_: str, content: Any, metadata: Optional[Dict] = None) -> Artifact:
        if package_name not in self.packages:
            raise ValueError(f"Package '{package_name}' does not exist.")
        artifact = Artifact(type_, content, metadata)
        self.packages[package_name].add_artifact(artifact)
        return artifact

    def list_artifacts(self, package_name: str, type_filter: str = None):
        pkg = self.get_package(package_name)
        if not pkg:
            return []
        # compact surface for LLM/UX
        out = []
        for a in pkg.artifacts.values():
            if type_filter and getattr(a, "type", None) != type_filter:
                continue
            out.append({
                "id": getattr(a, "id", None),
                "type": getattr(a, "type", None),
                "name": a.name,
                "created_at": getattr(a, "_created_at", None),
                "metadata": getattr(a, "metadata", None),
            })
        # newest first if timestamp exists
        out.sort(key=lambda x: (x.get("created_at") or ""), reverse=True)
        return out

  
    
    # ---------- TOOL REGISTRATION ----------
    def register_tool(self, tool_cls):
        """Register tool metadata and map artifact flow relationships."""
        name = getattr(tool_cls, "TOOL_NAME", tool_cls.__name__)
        description = getattr(tool_cls, "DESCRIPTION", "(no description)")
        category = getattr(tool_cls, "CATEGORY", "general")
        io_schema = getattr(tool_cls, "IO_SCHEMA", {})

        self.tools[name] = {
            "description": description,
            "category": category,
            "class": tool_cls,
            "artifacts": getattr(tool_cls, "ARTIFACTS", {}),
            "io_schema": io_schema,
        }

        # 🔹 NEW: Track artifact type flow relationships
        for inp in io_schema.get("inputs", {}).values():
            art_type = inp.get("type")
            if art_type:
                self.artifact_flows["consumes"].setdefault(art_type, []).append(name)

        for out in io_schema.get("outputs", {}).values():
            art_type = out.get("type")
            if art_type:
                self.artifact_flows["produces"].setdefault(art_type, []).append(name)

        print(f"🧩 Registered tool: {name} – {description}")

    def list_tools(self, category: Optional[str] = None):
        if not category:
            return self.tools
        return {k: v for k, v in self.tools.items() if v.get("category") == category}

    def describe_tool(self, name: str):
        info = self.tools.get(name)
        if not info:
            return f"❌ Tool '{name}' not found."
        desc = info["description"]
        cat = info["category"]
        inputs = ", ".join([v["type"] for v in info["io_schema"].get("inputs", {}).values()])
        outputs = ", ".join([v["type"] for v in info["io_schema"].get("outputs", {}).values()])
        return f"{name} ({cat}) – {desc}\nConsumes: {inputs or 'none'}\nProduces: {outputs or 'none'}"

    # ---------- PLANNING / FLOW QUERIES ----------
    def suggest_next(self, artifact_type: str) -> List[str]:
        """Return tools that can consume the given artifact type."""
        return self.artifact_flows["consumes"].get(artifact_type, [])

    def get_producers(self, artifact_type: str) -> List[str]:
        """Return tools that produce the given artifact type."""
        return self.artifact_flows["produces"].get(artifact_type, [])

    def plan_path(self, start_type: str, goal_type: str) -> List[str]:
        """
        Simple heuristic planner: find a tool chain from start_type to goal_type.
        """
        visited = set()
        frontier = [(start_type, [])]
        while frontier:
            current_type, path = frontier.pop(0)
            if current_type == goal_type:
                return path
            visited.add(current_type)
            for tool_name in self.suggest_next(current_type):
                tool_info = self.tools[tool_name]
                out_types = [v["type"] for v in tool_info["io_schema"].get("outputs", {}).values()]
                for ot in out_types:
                    if ot not in visited:
                        frontier.append((ot, path + [tool_name]))
        return []

    # ---------- PIPELINE MANAGEMENT ----------
    def add_pipeline(self, package_name: str, pipeline: List[Dict]):
        if package_name not in self.packages:
            raise ValueError(f"Package '{package_name}' does not exist.")
        self.packages[package_name].add_pipeline(pipeline)

  # ---------- NEW / UPDATED LOOKUP API (backward compatible) ----------

    def get_artifact(self, package_name: str, artifact_id: Optional[str] = None, **kwargs):
        """
        Backward-compatible getter:
          - Old style: get_artifact(package_name, artifact_id)
          - New style: get_artifact(package_name, name='foo')
          - New style: get_artifact(package_name, type_='bar', latest=True)

        Returns a single Artifact or None.
        """
        pkg = self.get_package(package_name)
        if not pkg:
            return None

        # Old behavior: by id
        if artifact_id:
            return pkg.get_by_id(artifact_id)

        # New behavior: by name
        name = kwargs.get("name")
        if name:
            return pkg.get_by_name(name)

        # New behavior: by type (latest by default)
        type_ = kwargs.get("type_")
        if type_:
            arts = pkg.list_artifacts(type_filter=type_)
            if not arts:
                return None
            # 'arts' here is a list[Artifact], not the dict we produce in list_artifacts()
            # If you kept list_artifacts returning dicts, switch to:
            # arts = [a for a in pkg.artifacts.values() if a.type == type_]
            arts = [a for a in pkg.artifacts.values() if getattr(a, "type", None) == type_]
            if not arts:
                return None
            arts.sort(key=lambda a: getattr(a, "_created_at", ""), reverse=True)
            latest = kwargs.get("latest", True)
            return arts[0] if latest else arts

        return None

    def get_artifact_by_name(self, package_name: str, name: str) -> Optional[Artifact]:
        """Explicit name helper (returns most-recent match)."""
        pkg = self.get_package(package_name)
        if not pkg:
            return None
        return pkg.get_by_name(name)

    def get_latest_by_type(self, package_name: str, type_: str) -> Optional[Artifact]:
        """Explicit helper to fetch the latest artifact of a given type."""
        pkg = self.get_package(package_name)
        if not pkg:
            return None
        arts = [a for a in pkg.artifacts.values() if getattr(a, "type", None) == type_]
        if not arts:
            return None
        arts.sort(key=lambda a: getattr(a, "_created_at", ""), reverse=True)
        return arts[0]    

    def name_artifact(self, package_name: str, artifact_type: str, name: str) -> Optional[Artifact]:
        """Assign an name to the most recent artifact of a given type in a package."""
        pkg = self.get_package(package_name)
        if not pkg:
            raise ValueError(f"Package '{package_name}' not found.")
    
        # filter artifacts by type
        arts = [a for a in pkg.artifacts.values() if a.type == artifact_type]
        if not arts:
            return None
    
        # pick latest
        arts.sort(key=lambda a: getattr(a, "_created_at", ""), reverse=True)
        target = arts[0]
        target.metadata["name"] = name
        target._announce = (
            f"✅ name '{name}' assigned to artifact id='{target.id[:8]}' "
            f"type='{target.type}' in package '{pkg.name}'"
        )
        print(target._announce)
        return target
# ============================================================
# SHARED GLOBAL REGISTRY INSTANCE
# ============================================================

# This instance is imported by tools and core modules
artifact_registry = ArtifactRegistry()