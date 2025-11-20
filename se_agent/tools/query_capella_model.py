# se_agent/tools/query_capella_model.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
from pathlib import Path
import hashlib


from se_agent.core.tool_patterns import register_tool, TransformTool



@register_tool
class QueryCapellaModelTool(TransformTool):
    """
    Query a Capella model using the embeddings manager and return a selection artifact.

    Inputs (one of):
      - capella_model_name (preferred)
      - capella_model_id

    Also requires:
      - query (text)

    Optional:
      - top_n (default 50)
      - embedding_file (if omitted, derived from <aird>.embeddings.<sha8>.json based on manager's model)

    Output:
      - selection_artifact_id (type=capella_selection, remember=True)
    """

    TOOL_NAME   = "query_capella_model"
    DESCRIPTION = "QUERY A CAPELLA MODEL USING EMBEDDINGS AND SAVE A SELECTION ARTIFACT."
    CATEGORY    = "analysis"

    ARTIFACTS: Dict[str, Any] = {
        "capella_selection": {
            "fields": {
                "query": {"type": "string"},
                "model_path": {"type": "path"},
                "count": {"type": "integer"},
                "matches": {"type": "list"},  # [{uuid, id, name, type, attrs?}]
                "embedding_file": {"type": "path"},
                "manager_model": {"type": "string"},
            },
            "schema_version": "1.0",
            "description": "Selection of Capella elements matched by an embeddings-based query.",
        }
    }

    IO_SCHEMA = {
    "inputs": {
        "capella_model_name": {"type": "string", "required": False, "description": "Name of a capella_model artifact."},
        "capella_model_id":   {"type": "string", "required": False, "description": "ID of a capella_model artifact."},
        "query":              {"type": "string", "required": False, "description": "Search text."},
        "prompt_name": {
            "type": "string",
            "required": False,
            "description": "Name of a 'prompt' artifact whose content will be used as the query if 'query' is omitted.",
        },
        "prompt_id": {
            "type": "string",
            "required": False,
            "description": "ID of a 'prompt' artifact whose content will be used as the query if 'query' is omitted.",
        },
        "top_n":              {"type": "integer","required": False, "description": "Max results (default 50)."},
        "embedding_file":     {"type": "path",   "required": False, "description": "Override embeddings file path."},
    },
        "outputs": {
            "selection_artifact_id": {
                "type": "capella_selection",
                "remember": True,
                "description": "Selection artifact id containing the matched elements.",
            }
        },
    }

    # ---------- helpers ----------
    def _pkg(self, artifacts: ArtifactRegistry, pkg_name: Optional[str]) -> Optional[ArtifactPackage]:
        return artifacts.get_package(pkg_name) if pkg_name else None

    def _get_capella_model(self, artifacts: ArtifactRegistry, pkg_name: str, name: Optional[str], art_id: Optional[str]):
        pkg = self._pkg(artifacts, pkg_name)
        if not pkg or not pkg.artifacts:
            raise ValueError(f"Package '{pkg_name}' not found or empty.")
        art = None
        if name:
            cands = [a for a in pkg.artifacts.values() if getattr(a, "name", None) == name and a.type == "capella_model"]
            if not cands:
                raise ValueError(f"capella_model named '{name}' not found.")
            cands.sort(key=lambda a: getattr(a, "_created_at", ""), reverse=True)
            art = cands[0]
        elif art_id:
            art = pkg.artifacts.get(art_id)
            if not art or art.type != "capella_model":
                raise ValueError(f"Artifact id '{art_id}' not found or not type='capella_model'.")
        else:
            raise ValueError("Provide either 'capella_model_name' or 'capella_model_id'.")
        if not isinstance(art.content, dict) or "path" not in art.content or "resources" not in art.content:
            raise ValueError("capella_model content must include {'path', 'resources'}")
        return art
        
    def _get_art_by_name(self, artifacts: ArtifactRegistry, pkg_name: str, name: str):
        pkg = artifacts.get_package(pkg_name) if pkg_name else None
        if not pkg:
            return None
        for art in pkg.artifacts.values():
            if art.name == name:
                return art
        return None
    
    def _get_art_by_id(self, artifacts: ArtifactRegistry, pkg_name: str, art_id: str):
        pkg = artifacts.get_package(pkg_name) if pkg_name else None
        if not pkg:
            return None
        return pkg.artifacts.get(art_id)
    # ---------- main ----------
    def run(self, input_data: Dict[str, Any], artifacts: ArtifactRegistry, package_name: Optional[str] = None, **kwargs):
        raw = input_data or {}
        pkg_name = package_name
        if not pkg_name:
            return {"error": "No package selected. Pass `package` or use agent.use_package(...)."}

        cap_name = raw.get("capella_model_name")
        cap_id   = raw.get("capella_model_id")

        query = (raw.get("query") or "").strip()
    
        pr_name = (raw.get("prompt_name") or "").strip()
        pr_id   = (raw.get("prompt_id") or "").strip()
    
        # If no direct query provided, try to use a prompt artifact
        if not query and (pr_name or pr_id):
            prompt = None
            if pr_name:
                prompt = self._get_art_by_name(artifacts, pkg_name, pr_name)
            if not prompt and pr_id:
                prompt = self._get_art_by_id(artifacts, pkg_name, pr_id)
    
            if prompt:
                if getattr(prompt, "type", None) != "prompt":
                    return {"error": "Provided prompt is not of type 'prompt'."}
    
                pcontent = getattr(prompt, "content", None)
                if isinstance(pcontent, str):
                    query = pcontent.strip()
                elif isinstance(pcontent, dict):
                    query = str(
                        pcontent.get("text")
                        or pcontent.get("prompt")
                        or pcontent.get("value")
                        or ""
                    ).strip()
                else:
                    query = str(pcontent or "").strip()
    
        # Final guard
        if not query:
            return {"error": "Missing 'query' or usable prompt artifact (prompt_name/prompt_id)."}       

        top_n          = int(raw.get("top_n", 50) or 50)
        embedding_file = raw.get("embedding_file")

        # ------------ 3) Build dependencies ------------
        try:
            import capellambse
        except Exception as e:
            raise RuntimeError(f"Missing capellambse: {e}")

        try:
            from capella_tools import capella_embeddings_manager
        except Exception as e:
            raise RuntimeError(f"Missing capella_tools.capella_embeddings_manager: {e}")

        # Resolve capella_model → (path_to_model, resources)
        cm = self._get_capella_model(artifacts, pkg_name, cap_name, cap_id)
        path_to_model = cm.content["path"]
        resources     = cm.content["resources"]

        # ------------ 4) Build model ------------
        try:
            model_obj = capellambse.MelodyModel(path_to_model, resources=resources)
        except Exception as e:
            raise RuntimeError(f"Failed to construct MelodyModel: {e}")

        # ------------ 5) Instantiate manager & derive default embedding file if needed ------------
        try:
            mgr = capella_embeddings_manager.EmbeddingManager()
            if not embedding_file:
                aird_stem = Path(path_to_model).stem
                # hash the effective embedding model to avoid collisions across backends/models
                sha8 = hashlib.sha1((mgr.model or "").encode("utf-8")).hexdigest()[:8]
                embedding_file = f"{aird_stem}.embeddings.{sha8}.json"
            mgr.set_files(path_to_model or "", embedding_file)
        except Exception as e:
            raise RuntimeError(f"Capella embeddings setup error: {e}")

        # ------------ 6) Run embeddings & query ------------
        try:
            mgr.create_model_embeddings(model_obj)  # handles up-to-date checks internally
            selected = mgr.query_and_select_top_objects(query, top_n=top_n) or []
        except Exception as e:
            raise RuntimeError(f"Capella embeddings error: {e}")

        # ------------ 7) Normalize selected objects → serializable records ------------
        records: List[Dict[str, Any]] = []
        names:   List[str] = []

        def _safe(obj, attr, default=None):
            try:
                return getattr(obj, attr, default)
            except Exception:
                return default

        for obj in selected:
            rec: Dict[str, Any] = {}

            # uuid/id
            if hasattr(obj, "uuid") or hasattr(obj, "id"):
                rec["uuid"] = str(_safe(obj, "uuid") or _safe(obj, "id") or "")
            elif isinstance(obj, dict):
                rec["uuid"] = str(obj.get("uuid") or obj.get("id") or "")
            else:
                rec["uuid"] = str(obj)

            # name
            if hasattr(obj, "name"):
                rec["name"] = str(_safe(obj, "name") or "")
            elif isinstance(obj, dict) and "name" in obj:
                rec["name"] = str(obj["name"])
            else:
                rec["name"] = ""

            # type
            rec["type"] = type(obj).__name__

            # id (explicit if present)
            rec["id"] = str(_safe(obj, "id") or "") if hasattr(obj, "id") else (
                str(obj.get("id")) if isinstance(obj, dict) and "id" in obj else ""
            )

            # optional attrs
            attrs = {}
            for k in ("category", "kind", "state"):
                if hasattr(obj, k):
                    attrs[k] = _safe(obj, k)
                elif isinstance(obj, dict) and k in obj:
                    attrs[k] = obj[k]
            if attrs:
                rec["attrs"] = attrs

            records.append(rec)
            if rec.get("name"):
                names.append(rec["name"])

        # ------------ 8) Metadata for downstream tools ------------
        try:
            info = mgr.get_embedding_file_info() or {}
        except Exception:
            info = {}

        content = {
            "query": query,
            "model_path": path_to_model,
            "count": len(records),
            "matches": records,
            "embedding_file": embedding_file,
            "manager_model": getattr(mgr, "model", None),
        }
        meta = {
            "source": "query_capella_model",
            "top_n": top_n,
            "embedding_file": embedding_file,
            "embedding_info": info,
        }

        sel = artifacts.add_artifact(
            package_name=pkg_name,
            type_="capella_selection",
            content=content,
            metadata=meta,
        )

        msg = f"✅ Query completed: {len(records)} match(es) saved in selection '{sel.id[:8]}'"
        return {
            "message": msg,
            "artifact_ids": {"selection_artifact_id": sel.id},
            "count": len(records),
            "preview": records[:5],
            "embedding_file": embedding_file,
        }
