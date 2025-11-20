from abc import ABC, abstractmethod
from se_agent.core.tool_registry import BaseTool
from se_agent.mcp.artifact_registry import Artifact, ArtifactRegistry, ArtifactPackage
from se_agent.mcp.artifact_registry import artifact_registry

"""
tool_patterns.py
Unified base classes for import, export, display, transform, and generative tools.
All derive from BaseTool (from se_agent/core/tool_registry.py)
and integrate with ArtifactRegistry.
"""


def register_tool(cls: type) -> type:
    """
    Decorator that registers a tool class into the global tool registry.
    Uses a lazy import to avoid circular dependencies.
    """
    # Lazy import to avoid cycles
    from se_agent.core.tool_registry import tool_registry
    tool_registry.register_tool(cls)
    return cls



# ===============================================================
# 🟢 ImportTool
# ===============================================================

class ImportTool(BaseTool):
    """Base class for tools that import data and create artifacts."""
    category = "import"

    def __init__(self):
        super().__init__()

    def run(self, input_data, artifacts, package_name=None, **kwargs):
        # Resolve package name
        pkg_name = package_name or getattr(artifacts, "active_package", None)
        if not artifacts or not pkg_name:
            # No registry context — still return content/metadata for debugging
            content, metadata = self.load(input_data)
            preview = content[:10] if isinstance(content, list) else None
            return {
                "message": f"📑 Loaded data via '{self.name}', but no artifact registry active.",
                "content": content,
                "metadata": metadata,
                "preview": preview,
            }

        # Import & register as artifact via REGISTRY method (expects type_ + content)
        content, metadata = self.load(input_data)
        artifact_type = getattr(self, "artifact_type", self.name)  # e.g., 'hierarchy'
        art = artifacts.add_artifact(pkg_name, type_=artifact_type, content=content, metadata=metadata or {})

        preview = content[:10] if isinstance(content, list) else None
        return {
            "message": f"📑 Loaded data via '{self.name}' into artifact.",
            "artifact_message": getattr(art, "_announce", None),
            "artifact_id": art.id,
            "artifact_type": art.type,
            "package_name": pkg_name,
            "preview": preview,
        }

    def load(self, input_data):
        """Subclasses must implement this to return (content, metadata)."""
        raise NotImplementedError("ImportTool.load() must be implemented by subclasses.")


# ===============================================================
# 🟣 TransformTool
# ===============================================================

class TransformTool(BaseTool):
    """Base class for tools that transform existing artifacts and create new ones."""
    category = "transform"

    def __init__(self):
        super().__init__()

    def run(self, input_data, artifacts, package_name=None, **kwargs):
        pkg_name = package_name or getattr(artifacts, "active_package", None)
        new_content, metadata = self.transform(input_data, artifacts, package_name)
        
        ui_summary = (metadata or {}).get("ui_summary")
        default_msg = f"🔄 Transformed artifact via '{self.name}'."
        msg = ui_summary or default_msg
        
        if artifacts and pkg_name:
            artifact_type = getattr(self, "artifact_type", self.name)
            art = artifacts.add_artifact(
                pkg_name,
                type_=artifact_type,
                content=new_content,
                metadata=metadata or {}
            )
        
            # ✅ Always provide a banner, even if the registry didn't set _announce
            artifact_msg = getattr(art, "_announce", None)
            if not artifact_msg:
                short_id = (getattr(art, "id", "") or "")[:8]
                artifact_msg = (
                    f"📑 Artifact created: id='{short_id}' type='{art.type}' in package '{pkg_name}'"
                )
        
            # Optional name support (if you already added this pattern)
            name = (metadata or {}).get("name") or (input_data or {}).get("name")
            if name:
                try:
                    named = artifacts.name_artifact(pkg_name, artifact_type, name)
                    # prefer name announcement if available
                    name_banner = getattr(named, "_announce", None)
                    if name_banner:
                        artifact_msg = name_banner
                except Exception as e:
                    # keep going; banner still shows creation message
                    pass
        
            return {
                "message": msg,                   # shows your ui_summary when present
                "artifact_message": artifact_msg, # banner guaranteed
                "artifact_id": art.id,
                "artifact_type": art.type,
                "package_name": pkg_name,
                "artifact_created": True,
            }
        
        # No registry / no active package → still surface summary
        return {
            "message": msg,
            "content": new_content,
            "metadata": metadata,
            "package_name": pkg_name,
            "artifact_created": False,
        }





    def transform(self, input_data, artifacts, package_name=None):
        raise NotImplementedError("TransformTool.transform() must be implemented by subclasses.")


# ===============================================================
# 🔵 GenerativeTool
# ===============================================================

class GenerativeTool(BaseTool):
    """Base class for AI-driven or procedural content generation tools."""
    category = "generative"

    def __init__(self):
        super().__init__()

    def run(self, input_data, artifacts, package_name=None, **kwargs):
        content, metadata = self.generate(input_data, artifacts, package_name)
        create_artifact = getattr(self, "create_artifact", True)

        if create_artifact and artifacts:
            pkg_name = package_name or getattr(artifacts, "active_package", None)
            if pkg_name:
                artifact_type = getattr(self, "artifact_type", self.name)
                art = artifacts.add_artifact(pkg_name, type_=artifact_type, content=content, metadata=metadata or {})
                return {
                    "message": f"✨ Generated artifact via '{self.name}'.",
                    "artifact_message": getattr(art, "_announce", None),
                    "artifact_id": art.id,
                    "artifact_type": art.type,
                    "package_name": pkg_name,
                }

        # Display-only path (no artifact)
        return {
            "message": f"✨ Generated content via '{self.name}' (no artifact created).",
            "html": self._maybe_html(content),
            "displayed": True,
        }


    def generate(self, input_data, artifacts, package_name=None):
        raise NotImplementedError("GenerativeTool.generate() must be implemented by subclasses.")

    def _maybe_html(self, content):
        if isinstance(content, str):
            return f"<pre style='white-space: pre-wrap'>{content}</pre>"
        elif isinstance(content, (list, dict)):
            import json
            return f"<pre>{json.dumps(content, indent=2)}</pre>"
        else:
            return f"<pre>{str(content)}</pre>"


# ===============================================================
# 🟡 ExportTool
# ===============================================================

class ExportTool(BaseTool):
    """Base class for exporting artifacts to external formats."""
    category = "export"

    def __init__(self):
        super().__init__()

    def run(self, input_data, artifacts, package_name=None, **kwargs):
        result = self.export(input_data, artifacts, package_name)
        return {
            "message": f"💾 Export completed via '{self.name}'.",
            "export_result": result,
        } 

    def export(self, input_data, artifacts, package_name=None):
        raise NotImplementedError("ExportTool.export() must be implemented by subclasses.")


# ===============================================================
# 🖥️ DisplayTool
# ===============================================================

class DisplayTool(BaseTool):
    """Base class for tools that produce HTML/text displays (no artifact)."""
    category = "display"

    def __init__(self):
        super().__init__()

    def run(self, input_data, artifacts, package_name=None, **kwargs):
        result = self.render(input_data, artifacts, package_name)

        # If the tool returned a structured dict (e.g., with 'html', 'displayed', etc.),
        # pass it straight through so the agent can respect those flags.
        if isinstance(result, dict):
            return result

        # Otherwise treat it as a raw HTML string and wrap it
        return {
            "message": f"🖥️ Display generated by '{self.name}'.",
            "html": result,     # result is expected to be a string
            # no "displayed": True here — we want the agent to render it
        }


