# widgets (safe inside VBox/HBox.children)
from ipywidgets import (
    VBox, HBox, Output, Button,  Checkbox, Layout, ToggleButtons,
    Textarea, Select, Text, HTML as WHTML, Select, SelectMultiple, Accordion
)
from IPython.display import display
from .panels import (
    _collect_workspace, _collect_artifacts, _relevant_tools, _mk_table,
    _collect_prompt_artifacts, _filter_prompts
)
import os
from se_agent.core.prompt_utils import get_prompt_path_from_artifacts
# display (for rendering inside Output)
from IPython.display import display as rdisplay, HTML as RHTML

from se_agent.core.prompt_render import extract_vars, render_template

class BottomWindows:
    """
    Mode 'state' (default): 3 panes as before.
    Mode 'prompts':
      Left  = Search box
      Middle= Filtered results (newest → oldest)
      Right = Preview + actions (Insert template, Render with tool)
    """
    def __init__(self, agent, artifacts, tool_registry_like, package_name=None,
                 border=True, height_px=500,
                 user_input_widget=None,
                 system_hint_setter=None,
                 tool_runner=None):
        """
        user_input_widget: a Textarea (or obj with `.value` str) to insert text into the chat input.
        system_hint_setter: callable(str)->None (optional, if you also want “insert as system” later).
        tool_runner: callable(tool_name:str, payload:dict)->dict result
                     If None, the 'Render with tool' button will show a warning.
        """
        self.agent = agent
        self.artifacts = artifacts
        self.tool_registry_like = tool_registry_like
        self.package_name = package_name
        self.user_input_widget = user_input_widget
        self.system_hint_setter = system_hint_setter
        self.tool_runner = tool_runner
        # Variables editor (expandable)
        self.values_editor_box = VBox()                     # <— was local before
        self.values_editor = Accordion(children=[self.values_editor_box])
        self.values_editor.set_title(0, "Edit values (optional)")
        self.values_editor.selected_index = None  # collapsed by default
        
        border_css = "1px solid #ddd" if border else "none"
        padd = "6px"
        hp = f"{int(height_px)}px"

        # Header controls
        self.mode = ToggleButtons(
            options=[("State", "state"), ("Prompts", "prompts")],
            value="state",
            layout=Layout(width="260px")
        )
        self.btn_refresh = Button(description="Refresh", layout=Layout(width="120px"))
        self.btn_refresh.on_click(self._on_refresh_click)


        # Columns (scrollable)
        common = dict(border=border_css, padding=padd, height=hp, overflow_y="auto", flex="1 1 0", width="33%")
        self.col_left  = Output(layout=Layout(**common))
        self.col_mid   = Output(layout=Layout(**common))
        self.col_right = Output(layout=Layout(**common))

        self.header = HBox([self.mode, self.btn_refresh], layout=Layout(justify_content="flex-start", width="100%", gap="12px"))
        self.row    = HBox([self.col_left, self.col_mid, self.col_right], layout=Layout(width="100%", gap="12px", align_items="stretch"))

        self.mode.observe(self._on_mode_change, names="value")

    def _on_refresh_click(self, _btn=None):
        self.refresh()
    # Public
    def view(self):
        box = VBox([self.header, self.row], layout=Layout(width="100%"))
        self.refresh()
        return box

    def _render_state_mode(self):
        # 1) collect data
        ws = _collect_workspace(self.artifacts, self.package_name)
        af = _collect_artifacts(self.artifacts, self.package_name)
        tools = _relevant_tools(self.tool_registry_like, ws, af)
    
        # 2) LEFT: Workspace (table)
        with self.col_left:
            self.col_left.clear_output()
            _mk_table(ws, ["name", "type"], "⚙️ Workspace (Newest → Oldest)")
    
        # 3) MIDDLE: Artifacts table + Start Session controls
        with self.col_mid:
            self.col_mid.clear_output()
            _mk_table(af, ["name", "type"], "📦 Artifacts (Newest → Oldest)")
    
            # prompt options: artifacts of prompt-ish type OR dict content with session/steps/vars
            pkg = self.agent.artifacts.get_active_package()
            arts = list(pkg.artifacts.values()) if pkg else []
    
            def _is_prompt_like(a):
                t = (a.type or "").lower()
                if t in {"prompt", "prompt_spec", "prompt_json"}:
                    return True
                c = getattr(a, "content", None)
                return isinstance(c, dict) and any(k in c for k in ("session", "steps", "vars"))
    
            prompt_opts = [(a.name, a.name) for a in arts if _is_prompt_like(a)]
            attach_opts  = [(a.name, a.name) for a in arts]
    
            rdisplay(RHTML("<hr><b>Start Guided Session</b>"))
            rdisplay(RHTML("<i>Prompt (required)</i>"))
            sel_prompt = Select(options=prompt_opts, layout=Layout(width="100%", height="75px"))
            rdisplay(sel_prompt)
    
            rdisplay(RHTML("<i>Attach artifacts (optional)</i>"))
            sel_attach = SelectMultiple(options=attach_opts, layout=Layout(width="100%", height="75px"))
            rdisplay(sel_attach)
    
            btn_start = Button(description="Start Session (Agent)", layout=Layout(width="100%"))
            rdisplay(btn_start)

            # Ensure a default selection so .value isn't None
            if not sel_prompt.value and sel_prompt.options:
                sel_prompt.value = sel_prompt.options[0][1]  # (label, name)
            
            status = Output()
            rdisplay(status)

            def _on_start(_b=None):
                with status:
                    status.clear_output()
            
                    # sanity: tool registered?
                    if not getattr(self.agent.tools, "get", None) or not self.agent.tools.get("execute_prompt_for_session"):
                        print("❌ Tool 'execute_prompt_for_session' is not registered/imported.")
                        return
            
                    p = sel_prompt.value
                    if not p:
                        print("⚠️ Select a prompt artifact first.")
                        return
                    names = list(sel_attach.value or [])
            
                    # call the tool
                    res = self.agent.run(
                        tool_name="execute_prompt_for_session",
                        input_data={
                            "prompt_artifact_name": p,
                            "include_artifact_names": names
                        }
                    ) or {}
                   
                    # render any confirmation / errors so the user sees them
                    ui = (res.get("ui") or res.get("message")) if isinstance(res, dict) else str(res)
                    if ui:
                        rdisplay(RHTML(f"<div style='margin-top:6px'>{ui}</div>"))
            
                    # only refresh if a session is now active (otherwise leave the message visible)
                    if self._session_status().get("active"):
                        self.refresh()

            btn_start.on_click(_on_start)
    
        # 4) RIGHT: Tools list OR Conclude/Cancel if a session is active
        sess = self._session_status()
        with self.col_right:
            self.col_right.clear_output()
            if not sess.get("active"):
                rdisplay(RHTML("<b>🧰 Runnable Tools (A → Z)</b>"))
                _mk_table([{"name": n} for n in tools], ["name"], None)
            else:
                info = (
                    f"<b>Guided Session</b><br>"
                    f"Type: {sess['type'].title()}<br>"
                    f"Prompt: {sess.get('prompt') or '—'}<br>"
                    f"Progress: {sess['step']}/{sess['total']}"
                )
                rdisplay(RHTML(info))
                btn_finish = Button(description="Conclude Session", button_style="success", layout=Layout(width="100%"))
                btn_cancel = Button(description="Cancel Session", layout=Layout(width="100%"))
                rdisplay(btn_finish); rdisplay(btn_cancel)
                rdisplay(RHTML("<small>Tools are disabled during session.</small>"))
    
                def _on_finish(_b=None):
                    self.agent.handle_user_message("__finish__")
                    self.refresh()
    
                def _on_cancel(_b=None):
                    self.agent.handle_user_message("cancel")
                    self.refresh()
    
                btn_finish.on_click(_on_finish)
                btn_cancel.on_click(_on_cancel)

    
    def _session_status(self):
        from se_agent.tools.workspace_store import _load_ws
        pkg = self.agent.artifacts.get_active_package()
        if not pkg: return {"active": False}
        _, ws = _load_ws(self.agent.artifacts, pkg.name)
        sid = (ws or {}).get("pending_session_sid")
        sess = (ws or {}).get("sessions", {}).get(sid or "")
        if not sess: return {"active": False}
        stps = (sess.get("spec", {}).get("session", {}) or {}).get("steps") or sess.get("spec", {}).get("steps") or []
        return {"active": True, "sid": sid, "type": sess.get("type","interview"), "step": int(sess.get("step",0)),
                "total": len(stps), "prompt": sess.get("prompt_name","")}
    

    def _toast(self, msg: str):
        # lightweight notice in right column
        with self.col_right:
            rdisplay(RHTML(f"<div style='color:#b35; font-size:12px; margin-top:4px;'>⚠️ {msg}</div>"))
    
    def refresh(self):
        try:
            if self.mode.value == "state":
                self._render_state_mode()
            else:
                self._render_prompts_mode()
        except Exception as e:
            # show the error in-left to keep UI alive
            with self.col_left:
                self.col_left.clear_output()
                rdisplay(RHTML(f"<pre>⚠️ Bottom pane error:\n{e}</pre>"))

    # Mode change
    def _on_mode_change(self, change):
        self.refresh()


    # ---- PROMPTS MODE ----

    # in se_agent/ui/panels_widgets.py
    from se_agent.core.prompt_utils import get_prompt_path_from_artifacts
    from se_agent.core.prompt_render import extract_vars, render_template
    from IPython.display import display, HTML
    
    def _render_prompts_mode(self):
 

        
        prompt_dir = get_prompt_path_from_artifacts(self.artifacts, self.package_name)
        prompts_all = _collect_prompt_artifacts(self.artifacts, self.package_name, prompt_dir=prompt_dir)
    
        # Left: search
        with self.col_left:
            self.col_left.clear_output()
            if prompt_dir:
                rdisplay(RHTML(f"<b>🔎 Search Prompts</b><br><small>Path: <code>{prompt_dir}</code></small>"))
            else:
                rdisplay(RHTML("<b>🔎 Search Prompts</b><br><small>⚠️ No prompt path artifact found.</small>"))
            search = Text(placeholder="Filter by name, text, tags...", layout=Layout(width="100%"))
            display(search)
    
        # Middle: results
        with self.col_mid:
            self.col_mid.clear_output()
            rdisplay(RHTML("<b>🧠 Results</b>"))
            names = [p["name"] for p in prompts_all]
            sel = Select(options=names, layout=Layout(width="100%", height="100%"))
            display(sel)
        # Right: preview + variable form + actions
        with self.col_right:
            self.col_right.clear_output()
            rdisplay(RHTML("<b>📄 Template · Variables · Actions</b>"))
            preview = Textarea(value="", layout=Layout(width="100%", height="8.2em"), disabled=True)
        
            vars_list_box = Textarea(value="", layout=Layout(width="100%", height="8.2em"), disabled=False)
            chk_inline = Checkbox(
                description="Allow inline assignments (k = value) in Variables box",
                value=True
            )
            btn_render = Button(description="Render Preview", layout=Layout(width="100%"))
            btn_verify = Button(description="Verify Template & Vars", layout=Layout(width="100%"))
            btn_save = Button(description="Save as Artifact", layout=Layout(width="100%"))
            
            status   = Output(layout=Layout(border="none", padding="0", height="auto"))
        
            rdisplay(preview)
            rdisplay(RHTML("<b>Variables</b>"))
            rdisplay(vars_list_box)
            rdisplay(chk_inline)
            rdisplay(btn_render)
            rdisplay(btn_verify)
            rdisplay(btn_save)
            rdisplay(status)
        
        def _current_prompt():
            src = _filter_prompts(prompts_all, search.value) if (search.value or "").strip() else prompts_all
            name = sel.value
            return next((p for p in src if p["name"] == name), None)
            
        def _rebuild_vars_ui():
            p = _current_prompt() or {}
            keys = p.get("vars") or []
            defaults = p.get("defaults") or {}
        
            if not keys:
                vars_list_box.value = "(no variables)"
            else:
                lines = []
                for k in keys:
                    lines.append(f"{k} = {defaults[k]}" if k in defaults and str(defaults[k]) != "" else k)
                vars_list_box.value = "\n".join(lines)
        
            rows = []
            for k in keys:
                rows.append(VBox([
                    WHTML(f"<b>{k}</b>"),
                    Textarea(value=str(defaults.get(k, "")),
                             placeholder=f"Enter value for {k}",
                             layout=Layout(width="100%", height="2.6em"))
                ], layout=Layout(border="1px solid #eee", padding="4px")))
            self.values_editor_box.children = tuple(rows)

     


        def _parse_inline_assignments(self, text: str) -> dict:
            vals = {}
            for line in (text or "").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip(); v = v.strip()
                    if k:
                        vals[k] = v
            return vals
        
        def _collect_values(include_inline: bool = True) -> dict:
            """
            Precedence:
              defaults  -> editable row values (non-empty) -> inline k=v (non-empty)
            """
            p = _current_prompt() or {}
            defaults = dict(p.get("defaults") or {})
            vals = defaults.copy()
        
            # 1) hidden editor rows (treat empty as "no override")
            for group in getattr(self.values_editor_box, "children", []):
                if len(group.children) >= 2 and hasattr(group.children[1], "value"):
                    key = (group.children[0].value or "").replace("<b>", "").replace("</b>", "").strip()
                    v = group.children[1].value
                    if key and isinstance(v, str) and v.strip() != "":
                        vals[key] = v.strip()
        
            # 2) inline overrides from Variables box (k = v)
            if include_inline and chk_inline.value:
                for line in (vars_list_box.value or "").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip(); v = v.strip()
                    if k and v != "":
                        # only override declared vars (to avoid typos), but you can relax if you want
                        if k in (p.get("vars") or []):
                            vals[k] = v
        
            return vals
            
        def _update_preview_and_vars():
            p = _current_prompt()
            preview.value = (p or {}).get("text","")
            _rebuild_vars_ui()

        # ----- Actions -----
        def _on_render_preview(_btn=None):
            p     = _current_prompt() or {}
            tmpl  = p.get("text", "")
            vals  = _collect_values(include_inline=True)
    
            rendered = None
            try:
                out = (self.agent.run(
                    tool_name="render_prompt_with_values",
                    package_name=None,
                    input_data={
                        "template_text": tmpl,
                        "values": vals,
                        "template_name": p.get("name"),
                        "source_path": p.get("source_path"),
                    },
                ) or {})
                rendered = out.get("text") or out.get("rendered_text")
            except Exception:
                rendered = None
    
            if not rendered:
                try:
                    from jinja2 import Environment, StrictUndefined
                    _J = Environment(undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True)
                    rendered = _J.from_string(tmpl or "").render(**(vals or {}))
                except Exception as e:
                    preview.value = f"(preview failed) {e}"
                    return
    
            preview.value = rendered



        def _on_verify(_btn=None):
            p = _current_prompt() or {}
            t = p.get("text","") or ""
            # declared vs used
            declared = set(p.get("vars") or [])
            try:
                from jinja2 import Environment, meta, StrictUndefined
                _J = Environment(undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True)
                ast = _J.parse(t)
                used = set(meta.find_undeclared_variables(ast))
                used = {u.split(".",1)[0].split("|",1)[0] for u in used}
            except Exception:
                used = declared  # fail-soft
    
            unknown = sorted(used - declared)   # used but not declared
            unused  = sorted(declared - used)   # declared but not used
    
            with status:
                status.clear_output()
                msgs = []
                if unknown:
                    msgs.append("❌ Template uses undeclared var(s): " + ", ".join(unknown))
                if unused:
                    msgs.append("⚠️ Declared but not used: " + ", ".join(unused))
                if not msgs:
                    msgs.append("✅ Vars look consistent.")
                rdisplay(RHTML("<br>".join(f"<pre>{m}</pre>" for m in msgs)))
            
        def _on_save_artifact(_btn=None):  # ← local handler (no 'self' param)
            p     = _current_prompt() or {}
            tmpl  = p.get("text", "")
            vals  = _collect_values()
            title = p.get("name") or (p.get("meta") or {}).get("title") or "Prompt"
            pkg   = None
        
            rendered = None
            try:
                out = (self.agent.run(
                    tool_name="render_prompt_with_values",
                    package_name=pkg,
                    input_data={
                        "template_text": tmpl,
                        "values": vals,
                        "template_name": p.get("name"),
                        "source_path": p.get("source_path"),
                    },
                ) or {})
                rendered = out.get("text") or out.get("rendered_text")
            except Exception:
                rendered = None
        
            if not rendered:
                try:
                    from jinja2 import Environment, StrictUndefined
                    _J = Environment(undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True)
                    rendered = _J.from_string(tmpl or "").render(**(vals or {}))
                except Exception as e:
                    with status:
                        status.clear_output()
                        rdisplay(RHTML(f"<pre>❌ Render failed: {e}</pre>"))
                    return
        
            res = (self.agent.run(
                tool_name="save_prompt_artifact",
                package_name=pkg,
                input_data={
                    "name": title,
                    "text": rendered,
                    "source_path": p.get("source_path"),
                    "template_name": p.get("name") or (p.get("meta") or {}).get("title"),
                    "tags": p.get("tags") or (p.get("meta") or {}).get("tags") or [],
                },
            ) or {})
        
            #self._show_tool_result("save_prompt_artifact", res)
            self.refresh()
        

        btn_save.on_click(_on_save_artifact)
        
 
        
            


        # events
        search.observe(lambda ch: (_update_list := _update_results()) if ch["name"]=="value" else None, names="value")
        sel.observe(lambda ch: _update_preview_and_vars() if ch["name"]=="value" else None, names="value")
        btn_render.on_click(_on_render_preview)
        btn_verify.on_click(_on_verify)
        btn_save.on_click(_on_save_artifact)

                
        def _update_results():
            filtered = _filter_prompts(prompts_all, search.value)
            names2 = [p["name"] for p in filtered]
            sel.options = names2
            if names2:
                sel.value = names2[0]
            _update_preview_and_vars()
        _update_results()


 

