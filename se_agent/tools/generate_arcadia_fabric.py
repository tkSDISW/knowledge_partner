# se_agent/tools/generate_arcadia_fabric.py
from se_agent.core.tool_patterns import register_tool, TransformTool
from se_agent.mcp.artifact_registry import ArtifactRegistry, ArtifactPackage
from typing import Any, Dict, List, Optional

@register_tool
class GenerateARCADIAFabricTool(TransformTool):
    """
    Transform: Generate YAML-based knowledge fabric from a Capella model selection
    and store it as an artifact.

    Preferred inputs (saved artifacts):
      • selection_name    : name of a 'capella_selection' artifact (list of {uuid, name, ...})
      • capella_model_name: name of a 'capella_model' artifact
      • capella_model_id  : id of a 'capella_model' artifact

    Optional:
      • name              : name to assign to the created YAML artifact (e.g., "MB_fabric")

      • name              : name to assign to the created YAML artifact (e.g., "MB_fabric")

    Behavior:
      1) Resolve selection (prefer selection_name, else uuids/uuid).
      2) Resolve model path/resources via a single capella_model artifact.
      3) Build capellambse.MelodyModel.
      4) Use capella_tools.capellambse_yaml_manager.CapellaYAMLHandler to generate YAML for targets + references.
      5) Write output file (per your handler), collect YAML string, and return (content, metadata).

    Returns:
      content: str (YAML)
      metadata: dict including 'ui_summary', 'model_path', 'count', 'name', etc.
    """

    # ===============================
    # Contract v1 static metadata
    # ===============================
    TOOL_NAME = "generate_arcadia_fabric"
    DESCRIPTION = (
        "GENERATES A YAML-BASED KNOWLEDGE FABRIC FOR SELECTED CAPELLA OBJECTS AND SAVES IT AS AN ARTIFACT."
    )
    CATEGORY = "transform"
    USAGE = (
        "Use after you have a selection of Capella elements and a capella_model artifact available."
    )

    ARTIFACTS: Dict[str, Any] = {
        "arcadia_fabric": {
            "fields": {
                "yaml": {"type": "string"},
                "targets": {"type": "list"},
                "model_path": {"type": "path"}
            },
            "schema_version": "1.0",
            "description": "YAML knowledge fabric extracted from Capella elements."
        }
    }


    IO_SCHEMA = {
        "inputs": {
            # selection resolution
            "selection_name": {"type": "string", "required": False, "description": "Name of saved capella_selection artifact."},
            "uuids": {"type": "list", "required": False, "description": "List of UUIDs to export."},
            "uuid": {"type": "string", "required": False, "description": "Single UUID to export."},
            # model/resources resolution via a single model artifact (required)
            "capella_model_name": {"type": "string", "required": False, "description": "Name of a capella_model artifact."},
            "capella_model_id":   {"type": "string", "required": False, "description": "ID of a capella_model artifact."},
            # optional naming
            "name": {"type": "string", "required": False, "description": "Name to give to the created fabric artifact."}
        },
        "outputs": {
            "fabric_artifact_id": {"type": "arcadia_fabric",
            "remember": False,
            "description": "Created fabric artifact id."}
        }
    }




    # ---------- Registry helpers ----------
    def _pkg_name(self, artifacts, package_name):
        return package_name or getattr(artifacts, "active_package", None)

    def _get_by_name(self, artifacts, pkg_name, name):
        try:
            pkg = artifacts.get_package(pkg_name)
            if not pkg or not hasattr(pkg, "artifacts"):
                return None
            arts = list(pkg.artifacts.values())
            matches = [a for a in arts if getattr(a, "name", None) == name]
            if not matches:
                return None
            matches.sort(key=lambda a: getattr(a, "_created_at", 0), reverse=True)
            return matches[0]
        except Exception:
            return None

    def _get_by_id(self, artifacts, pkg_name, art_id):
        try:
            return artifacts.get_artifact(pkg_name, art_id)
        except Exception:
            return None

    # ---------- Resolution helpers ----------
    def _resolve_selection(self, input_data, artifacts, pkg_name):
        selection_name = input_data.get("selection_name")
        uuids = input_data.get("uuids")
        single_uuid = input_data.get("uuid")
    
        def _normalize_entries(entries):
            targets = []
            for it in entries or []:
                if not isinstance(it, dict):
                    continue
                # prefer explicit 'uuid'
                u = it.get("uuid")
                n = it.get("name") or it.get("label") or it.get("title") or ""
                # fallback: some tools put UUID under 'id' (if looks like a UUID) or 'eid'
                if not u:
                    u = it.get("id") or it.get("eid")
                if u:
                    targets.append({"uuid": str(u), "name": str(n)})
            return targets
    
        targets = []
    
        if selection_name and artifacts:
            sel_art = self._get_by_name(artifacts, pkg_name, selection_name)
            if not sel_art:
                raise ValueError(f"Selection name '{selection_name}' not found in package '{pkg_name}'.")
            c = getattr(sel_art, "content", None)
    
            # Case A: artifact content is already a list of entries
            if isinstance(c, list):
                targets = _normalize_entries(c)
    
            # Case B: artifact content is a dict (your schema): look for common keys
            elif isinstance(c, dict):
                # Your declared schema: matches=[{uuid,id,name,type,...}]
                if isinstance(c.get("matches"), list):
                    targets = _normalize_entries(c["matches"])
                # other common shapes
                elif isinstance(c.get("selection"), list):
                    targets = _normalize_entries(c["selection"])
                elif isinstance(c.get("items"), list):
                    targets = _normalize_entries(c["items"])
                elif isinstance(c.get("uuids"), list):
                    targets = [{"uuid": str(u), "name": ""} for u in c["uuids"]]
    
            if not targets:
                raise ValueError(
                    f"Selection '{selection_name}' content not recognized. "
                    f"Expected a list of entries or dict with one of keys: matches/selection/items/uuids."
                )
    
        elif isinstance(uuids, list) and uuids:
            targets = [{"uuid": str(u), "name": ""} for u in uuids]
    
        elif isinstance(single_uuid, str) and single_uuid:
            targets = [{"uuid": single_uuid, "name": ""}]
    
        else:
            raise ValueError("Provide selection_name, uuids (list), or uuid (string).")
    
        return targets, selection_name

    def _resolve_model_bundle(self, input_data, artifacts, pkg_name):
        """Resolve MelodyModel inputs from a required capella_model artifact.
        Accepts content variants for resilience:
          • dict with keys {"model_path"|"path"|"aird", "resources"}
          • string path to the .aird (resources default to {})
        """
        # Require capella_model artifact by name or id
        name = input_data.get("capella_model_name")
        art_id = input_data.get("capella_model_id")
        if not (name or art_id):
            raise ValueError("Provide capella_model_name or capella_model_id.")

        art = None
        if name:
            art = self._get_by_name(artifacts, pkg_name, name)
        if not art and art_id:
            art = self._get_by_id(artifacts, pkg_name, art_id)
        if not art:
            raise ValueError("capella_model artifact not found.")

        c = getattr(art, "content", None)
        if isinstance(c, dict):
            path = c.get("model_path") or c.get("path") or c.get("aird")
            resources = c.get("resources") or {}
            if not isinstance(path, str) or not path.strip():
                raise ValueError(
                    f"capella_model '{getattr(art,'name',name) or art_id}' missing a valid model path."
                )
            if resources and not isinstance(resources, dict):
                raise ValueError("capella_model 'resources' must be a dict if present.")
            return path, resources, getattr(art, "name", name)
        if isinstance(c, str) and c.strip():
            return c, {}, getattr(art, "name", name)
        raise ValueError(
            f"capella_model '{getattr(art,'name',name) or art_id}' has unsupported content type."
        )

        # Prefer capella_model artifact by name/id
        name = input_data.get("capella_model_name")
        art_id = input_data.get("capella_model_id")

        art = None
        if name and artifacts:
            art = self._get_by_name(artifacts, pkg_name, name)
        if not art and art_id and artifacts:
            art = self._get_by_id(artifacts, pkg_name, art_id)

        if art is not None:
            c = getattr(art, "content", None)
            # Case 1/2: dict
            if isinstance(c, dict):
                path = c.get("model_path") or c.get("path") or c.get("aird")
                resources = c.get("resources") or {}
                if not isinstance(path, str) or not path.strip():
                    raise ValueError(
                        f"capella_model '{getattr(art,'name',name) or art_id}' missing a valid model path."
                    )
                if resources and not isinstance(resources, dict):
                    raise ValueError("capella_model 'resources' must be a dict if present.")
                return path, resources, getattr(art, "name", name)
            # Case 3: string path
            if isinstance(c, str) and c.strip():
                return c, {}, getattr(art, "name", name)
            raise ValueError(
                f"capella_model '{getattr(art,'name',name) or art_id}' has unsupported content type."
            )

        # ------- Back-compat fallbacks (deprecated) -------
        # Allow direct fields until callers migrate fully.
        # model path
        direct_path = input_data.get("model_path")
        # resources
        direct_resources = input_data.get("resources")
        # Try auto-resolve if direct_path is actually an artifact name
        if isinstance(direct_path, str) and artifacts:
            maybe = self._get_by_name(artifacts, pkg_name, direct_path)
            if maybe and isinstance(maybe.content, str):
                direct_path = maybe.content
        if isinstance(direct_resources, str) and artifacts:
            maybe = self._get_by_name(artifacts, pkg_name, direct_resources)
            if maybe and isinstance(maybe.content, dict):
                direct_resources = maybe.content

        if isinstance(direct_path, str) and direct_path.strip():
            if direct_resources is None:
                direct_resources = {}
            if not isinstance(direct_resources, dict):
                raise ValueError("resources must be a dict when provided.")
            return direct_path, direct_resources, None

        raise ValueError(
            "Provide capella_model_name/capella_model_id (preferred). Deprecated direct model_path/resources also accepted for now."
        )

    # ---------- Core transform ----------
    def transform(self, input_data, artifacts, package_name=None):
        pkg_name = self._pkg_name(artifacts, package_name)
        if not artifacts or not pkg_name:
            raise ValueError("No artifact registry or active package.")

        # 1) Resolve selection
        targets, selection_name = self._resolve_selection(input_data, artifacts, pkg_name)

        # 2) Resolve model path/resources via capella_model artifact
        path_to_model, resources, model_src_name = self._resolve_model_bundle(input_data, artifacts, pkg_name)

        # 3) Imports
        try:
            import capellambse
        except Exception as e:
            raise RuntimeError(f"Missing capellambse: {e}")

        try:
            from capella_tools import capellambse_yaml_manager
        except Exception as e:
            raise RuntimeError(f"Missing capella_tools.capellambse_yaml_manager: {e}")

        # 4) Build model
        try:
            model = capellambse.MelodyModel(path_to_model, resources=resources)
        except Exception as e:
            raise RuntimeError(f"Failed to construct MelodyModel: {e}")

        # 5) Generate YAML
        try:
            yaml_handler = capellambse_yaml_manager.CapellaYAMLHandler()
            for t in targets:
                uuid = t["uuid"]
                obj = model.by_uuid(uuid)
                yaml_handler.generate_yaml(obj)
            yaml_handler.generate_yaml_referenced_objects()
            yaml_handler.write_output_file()  # your workflow writes to disk
            arcadia_fabric = yaml_handler.get_yaml_content()
        except Exception as e:
            raise RuntimeError(f"YAML generation error: {e}")

        # 6) Metadata and concise UI summary
        names = [t.get("name") for t in targets if t.get("name")]
        if names:
            shown = ", ".join(names[:5]) + ("…" if len(names) > 5 else "")
        else:
            uuids_shown = ", ".join([t["uuid"] for t in targets[:5]]) + ("…" if len(targets) > 5 else "")
            shown = uuids_shown or "(none)"

        count = len(targets)
        metadata = {
            "ui_summary": f"Generated YAML for {count} object(s): {shown}",
            "model_path": path_to_model,
            "model_path_source": model_src_name or "capella_model",
            "resources_source": "capella_model",
            "selection_name": selection_name,
            "targets": targets,
            "count": count,
            "source": "capellambse_yaml_manager",
        }

        # Default output name if not provided
        name = input_data.get("name")
        if not name:
            base = (selection_name or "capella").strip().replace(" ", "_")
            name = f"{base}_fabric"
        metadata["name"] = name

        # (content, metadata) for caller
        return arcadia_fabric, metadata

    # ---------- Contract v1 entrypoint ----------
    def run(self, input_data, artifacts, package_name=None, **_):

        # Defer validation to transform() which raises clear errors on missing inputs
        arcadia_fabric, metadata = self.transform(input_data, artifacts, package_name)

        # Persist artifact explicitly per contract examples
        pkg_name = self._pkg_name(artifacts, package_name)
        content_record = {
            "yaml": arcadia_fabric,
            "targets": metadata.get("targets", []),
            "model_path": metadata.get("model_path"),
        }
        art = artifacts.add_artifact(
            pkg_name,
            "arcadia_fabric",
            content_record,
            metadata,
        )
        # Optional friendly name
        if metadata.get("name"):
            art.name = metadata["name"]

        # One-shot banner (agents may show once)
        banner = f"✅ Fabric created: id='{getattr(art, 'id', '')[:8]}' ({metadata.get('count', 0)} item(s))"

        return {
            "message": banner,
            "artifact_ids": {"fabric_artifact_id": getattr(art, "id", None)},
        }



