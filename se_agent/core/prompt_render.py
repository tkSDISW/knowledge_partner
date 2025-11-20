# se_agent/core/prompt_render.py
import re, json

_JINJA_RX  = re.compile(r"{{\s*([a-zA-Z_]\w*)\s*(?:\|[^}]*)?}}")
_DOLLAR_RX = re.compile(r"\$\{([a-zA-Z_]\w*)\}")
_BRACK_RX  = re.compile(r"\[\[([a-zA-Z_]\w*)\]\]")
_FRONT_RX  = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_FENCE_RX  = re.compile(r"```json\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)

def _front_vars(txt: str):
    m = _FRONT_RX.match(txt or "")
    if not m: return []
    block = m.group(1)
    out, in_list = [], False
    for ln in (ln.strip() for ln in block.splitlines()):
        if ln.startswith("vars:"):
            in_list = True; continue
        if in_list:
            if not ln.startswith("-"): break
            name = ln[1:].strip()
            if name: out.append(name)
    return out

def _json_vars_from_obj(obj):
    """
    Try common JSON prompt-spec shapes:
      {"vars": ["a","b"]} or {"variables":[...]} or {"fields":[{"name":"a"},...]} etc.
    """
    if not isinstance(obj, dict): return []
    candidates = []
    for key in ("vars","variables","parameters","inputs","fields","placeholders"):
        v = obj.get(key)
        if isinstance(v, list):
            for item in v:
                if isinstance(item, str):
                    candidates.append(item)
                elif isinstance(item, dict):
                    name = item.get("name") or item.get("id") or item.get("key")
                    if isinstance(name, str) and name.strip():
                        candidates.append(name.strip())
    return candidates

def _json_vars_from_text(txt: str):
    # 1) fenced ```json ... ```
    for block in _FENCE_RX.findall(txt or ""):
        try:
            obj = json.loads(block)
            found = _json_vars_from_obj(obj)
            if found: return found
        except Exception:
            pass
    # 2) try whole body as JSON
    try:
        obj = json.loads(txt or "")
        found = _json_vars_from_obj(obj)
        if found: return found
    except Exception:
        pass
    return []

def extract_vars(template_text: str) -> list[str]:
    txt = template_text or ""
    keys = set()
    keys.update(_front_vars(txt))
    keys.update(_JINJA_RX.findall(txt))
    keys.update(_DOLLAR_RX.findall(txt))
    keys.update(_BRACK_RX.findall(txt))
    keys.update(_json_vars_from_text(txt))
    return sorted(keys)


def render_template(template_text: str, values: dict[str, str]) -> str:
    if _JINJA:
        tmpl = _JINJA.from_string(template_text or "")
        return tmpl.render(**(values or {}))
    # fallback: naive replace
    out = template_text or ""
    for k, v in (values or {}).items():
        out = re.sub(r"{{\s*"+re.escape(k)+r"\s*}}", str(v), out)
    return out