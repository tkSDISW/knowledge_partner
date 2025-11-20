# se_agent/tools/generate_capella_context_diagram.py
from se_agent.core.tool_patterns import  DisplayTool

class GenerateCapellaContextDiagramTool(DisplayTool):
    """
    Display: render Capella context diagrams for one or more model objects.

    Inputs (one of):
      • selection_name : name of 'capella_selection' (list of {uuid, name, ...})
      • uuids           : list[str] of UUIDs
      • uuid            : single UUID string

    Model resolution (preferred via saved artifacts):
      • model_path_name : name of artifact with content=str path to .aird (e.g., "Bike_Path")
      • resources_name  : name of artifact with content=dict (e.g., "Bike_Resources")

    Optional:
      • limit            : int, only render the first N targets

    Behavior:
      • Builds a capellambse.MelodyModel
      • For each UUID: obj = model.by_uuid(uuid); capellambse_helper.display_context_diagram(obj)
      • Returns a short HTML summary (no artifact created)
    """

    name = "generate_capella_context_diagram"
    description = (
        "Render Capella *context diagrams* for one or more objects and show a short summary. "
        "Preferred inputs: selection_name (name of a 'capella_selection' artifact from embeddings), "
        "model_path_name (e.g. 'Bike_Path'), and resources_name (e.g. 'Bike_Resources'). "
        "Alternatives: pass uuids=[...] or a single uuid string. Optional: limit (int) to cap how many diagrams to render. "
        "The tool builds a capellambse.MelodyModel and for each UUID calls "
        "capella_tools.capellambse_helper.display_context_diagram(obj), which renders inline. "
        "No artifact is created; only diagrams + a concise HTML summary are shown. "
        "Planner rules: (1) Prefer selection_name from prior 'capella_selection'; "
        "(2) Always include model_path_name and resources_name; "
        "(3) Use limit for large selections. "
        "Example action: "
        "{\"actions\":[{\"tool\":\"generate_capella_context_diagram\",\"input\":{"
        "\"selection_name\":\"MB_messy_selection\",\"model_path_name\":\"Bike_Path\",\"resources_name\":\"Bike_Resources\",\"limit\":3"
        "}}]}"
    )
    category = "display"  # DisplayTool -> no artifact

    # minimal name lookup consistent with your registry
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

    def render(self, input_data, artifacts, package_name=None):
        # ---- parse targets
        selection_name = input_data.get("selection_name")
        uuids = input_data.get("uuids")
        single_uuid = input_data.get("uuid")

        targets = []
        pkg_name = self._pkg_name(artifacts, package_name)

        if selection_name and artifacts:
            sel_art = self._get_by_name(artifacts, pkg_name, selection_name)
            if not sel_art or not isinstance(sel_art.content, list):
                return f"<p style='color:red'>❌ Selection name '{selection_name}' not found or not a list.</p>"
            for it in sel_art.content:
                if isinstance(it, dict) and it.get("uuid"):
                    targets.append({"uuid": str(it["uuid"]), "name": it.get("name", "")})
        elif isinstance(uuids, list) and uuids:
            targets = [{"uuid": str(u), "name": ""} for u in uuids]
        elif isinstance(single_uuid, str) and single_uuid:
            targets = [{"uuid": single_uuid, "name": ""}]
        else:
            return "<p style='color:red'>❌ Provide selection_name, uuids (list), or uuid (string).</p>"

        limit = input_data.get("limit")
        if isinstance(limit, int) and limit > 0:
            targets = targets[:limit]

        # ---- resolve model path/resources via namees
        model_path_name = input_data.get("model_path_name")
        resources_name  = input_data.get("resources_name")

        if not (model_path_name and resources_name):
            return "<p style='color:red'>❌ Provide model_path_name and resources_name.</p>"

        art_path = self._get_by_name(artifacts, pkg_name, model_path_name) if artifacts else None
        art_res  = self._get_by_name(artifacts, pkg_name, resources_name) if artifacts else None
        if not art_path or not isinstance(art_path.content, str):
            return f"<p style='color:red'>❌ Artifact '{model_path_name}' not found or content is not a string path.</p>"
        if not art_res or not isinstance(art_res.content, dict):
            return f"<p style='color:red'>❌ Artifact '{resources_name}' not found or content is not a dict.</p>"

        path_to_model = art_path.content
        resources = art_res.content

        # ---- imports
        try:
            import capellambse
        except Exception as e:
            return f"<p style='color:red'>❌ Missing capellambse: {e}</p>"

        try:
            from capella_tools import capellambse_helper
        except Exception as e:
            return f"<p style='color:red'>❌ Missing capella_tools.capellambse_helper: {e}</p>"

        # ---- build model
        try:
            model = capellambse.MelodyModel(path_to_model, resources=resources)
        except Exception as e:
            return f"<p style='color:red'>❌ Failed to construct MelodyModel: {e}</p>"

        # ---- render diagrams
        rendered = 0
        names = []
        errors = []
        for t in targets:
            u = t["uuid"]
            try:
                obj = model.by_uuid(u)
                capellambse_helper.display_context_diagram(obj)   # renders inline
                rendered += 1
                names.append(getattr(obj, "name", "") or t.get("name") or u)
            except Exception as e:
                errors.append({"uuid": u, "error": str(e)})

        # ---- concise HTML summary (agent will show this; diagrams already displayed)
        shown = ", ".join(names[:5]) + ("…" if len(names) > 5 else "")
        err_html = ""
        if errors:
            err_items = "".join(f"<li><code>{e['uuid']}</code>: {e['error']}</li>" for e in errors[:5])
            if len(errors) > 5:
                err_items += "<li>…</li>"
            err_html = f"<details><summary>⚠️ {len(errors)} error(s)</summary><ul>{err_items}</ul></details>"

        return (
            "<div>"
            f"<p><b>Context diagrams:</b> rendered {rendered}/{len(targets)}</p>"
            f"<p><b>Objects:</b> {shown or '(none)'} </p>"
            f"{err_html}"
            "</div>"
        )
