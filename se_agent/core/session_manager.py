# se_agent/core/session_manager.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Iterable
from uuid import uuid4
import re
from jinja2 import Environment, StrictUndefined

_J = Environment(undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True)
_J.filters["tojson"] = lambda obj, indent=2: __import__("json").dumps(obj, ensure_ascii=False, indent=indent)
def _render(tmpl: str, ctx: dict) -> str:
    return _J.from_string(tmpl or "").render(**(ctx or {}))

@dataclass
class Session:
    sid: str
    spec: dict
    type: str = "interview"       # interview | checklist | form | triage | review
    step: int = 0
    answers: dict = field(default_factory=dict)
    prompt_name: str = ""
    attachments: dict = field(default_factory=dict)  # {key: {"type","origin","value"}}
    # add to Session dataclass
    llm_mode: bool = False                 # freeform facilitator on
    llm_seed: str = ""                     # the string prompt
    llm_style: str = "freeform"            # for future: 'freeform' (default)
    transcript: list = field(default_factory=list)  # [{"role":"user|assistant","text":"..."}]

    
    @property
    def steps(self):
        s = (self.spec.get("session") or {})
        return s.get("steps") or self.spec.get("steps") or []
    @property
    def total(self): return len(self.steps)

class SessionManager:
    """Tool-free, agent-led Guided Session (Interview/Checklist/Form)."""
    def __init__(self, load_ws, save_ws, now_iso):
        self._load_ws = load_ws
        self._save_ws = save_ws
        self._now_iso = now_iso

    def start(self, artifacts, pkg_name: str, prompt_spec: dict, prompt_name: str,
              attachments: Optional[Iterable[Any]] = None) -> Session:
        spec = self._normalize_spec(prompt_spec)
        t = (spec.get("session") or {}).get("type") or "interview"
        sid = uuid4().hex
        sess = Session(sid=sid, spec=spec, type=t, step=0, prompt_name=prompt_name)
        ws_art, ws = self._load_ws(artifacts, pkg_name)
        ws.setdefault("sessions", {})[sid] = self._to_dict(sess)
        ws["pending_session_sid"] = sid
        self._save_ws(artifacts, pkg_name, ws_art, ws)
        if attachments:
            self._attach_items(artifacts, pkg_name, sess, attachments)
            self.store(artifacts, pkg_name, sess)
        return sess

    def load(self, artifacts, pkg_name: str, sid: str) -> Optional[Session]:
        _, ws = self._load_ws(artifacts, pkg_name)
        raw = (ws.get("sessions") or {}).get(sid)
        return self._from_dict(raw) if raw else None

    def store(self, artifacts, pkg_name: str, sess: Session):
        ws_art, ws = self._load_ws(artifacts, pkg_name)
        ws.setdefault("sessions", {})[sess.sid] = self._to_dict(sess)
        self._save_ws(artifacts, pkg_name, ws_art, ws)

    def cancel(self, artifacts, pkg_name: str, sid: str):
        ws_art, ws = self._load_ws(artifacts, pkg_name)
        (ws.get("sessions") or {}).pop(sid, None)
        ws.pop("pending_session_sid", None)
        self._save_ws(artifacts, pkg_name, ws_art, ws)

    def next_prompt(self, sess: Session) -> Optional[str]:
        if sess.step >= sess.total: return None
        q = sess.steps[sess.step] or {}
        return q.get("ask") or f"Provide a value for '{q.get('key','q')}'."

    def record_and_advance(self, sess: Session, user_answer: str) -> Optional[str]:
        # records answer for previously asked question; returns error text or None
        if sess.step == 0: return None
        prev = sess.steps[sess.step - 1]
        key  = prev.get("key") or f"q{sess.step}"
        typ  = (prev.get("type") or "text").lower()
        ans  = (user_answer or "").strip()
        try:
            if   typ == "int":   val = int(ans)
            elif typ == "float": val = float(ans)
            elif typ == "bool":  val = ans.lower() in {"y","yes","true","1"}
            elif typ == "list":  val = [x.strip() for x in ans.split(",") if x.strip()]
            else:                 val = ans
        except Exception:
            return f"Expected {typ}. Try again."
        v = ((sess.spec.get("session") or {}).get("validate") or {}).get(key)
        if v:
            if "enum" in v and val not in v["enum"]:
                return f"Value must be one of: {', '.join(map(str,v['enum']))}"
            if "regex" in v and isinstance(val, str) and not re.match(v["regex"], val):
                return f"Does not match pattern: {v['regex']}"
        sess.answers[key] = val
        return None

    def advance(self, sess: Session): 
        if sess.step < sess.total: sess.step += 1
    def finished(self, sess: Session) -> bool:
        return sess.step >= sess.total

    def synthesize_artifact(self, sess: Session) -> dict:
        art = (sess.spec.get("artifact") 
               or (sess.spec.get("session") or {}).get("artifact")
               or {})
        ctx = {"answers": sess.answers, "title": sess.spec.get("title"), "now": self._now_iso()}
        art_type = art.get("type") or f"{sess.type}_result"
        art_name = _render(art.get("name_template") or "Session Result {{ now }}", ctx)
        content  = _render(art.get("content_template") or "{{ answers | tojson(indent=2) }}", ctx)
        return {"type": art_type, "name": art_name, "content": content}

    # --- helpers ---
    def _normalize_spec(self, spec: dict) -> dict:
        if "session" in (spec or {}):  # v2
            return spec
        # v1 (vars-only): wrap to interview
        vars_ = list((spec or {}).get("vars") or [])
        steps = [{"key": v, "ask": f"Provide a value for '{v}'.", "type": "text"} for v in vars_]
        return {
            "title": (spec or {}).get("title"),
            "session": { "type": "interview", "steps": steps },
            "artifact": {
                "type": "interview_result",
                "name_template": "Interview {{ title or 'Result' }} {{ now }}",
                "content_template": "{{ answers | tojson(indent=2) }}"
            }
        }

    def _attach_items(self, artifacts, pkg_name: str, sess: Session, items: Iterable[Any]):
        ws_art, ws = self._load_ws(artifacts, pkg_name)
        ws.setdefault("memory", {})
        for art in (items or []):
            try:
                typ = getattr(art, "type", None) or (art.get("type") if isinstance(art, dict) else "value")
                name = getattr(art, "name", None) or ((art.get("metadata", {}) or {}).get("name") if isinstance(art, dict) else "artifact")
                value = getattr(art, "content", None) if hasattr(art, "content") else (art.get("content") if isinstance(art, dict) else art)
                key = name or f"attach_{len(sess.attachments)+1}"
                sess.attachments[key] = {"type": typ or "value", "origin": name, "value": value}
                ws["memory"][key] = {"type": typ or "value", "value": value, "updated_at": self._now_iso(), "origin_artifact": name or ""}
            except Exception:
                continue
        self._save_ws(artifacts, pkg_name, ws_art, ws)


    def _to_dict(self, s: Session) -> dict:
        return {
            "sid": s.sid,
            "spec": s.spec,
            "type": s.type,
            "step": s.step,
            "answers": s.answers,
            "prompt_name": s.prompt_name,
            "attachments": s.attachments,
            "llm_mode": s.llm_mode,
            "llm_seed": s.llm_seed,
            "llm_style": s.llm_style,
            "transcript": s.transcript,
        }

    def _from_dict(self, d: dict) -> Session:
        return Session(
            sid=d["sid"],
            spec=d["spec"],
            type=d.get("type", "interview"),
            step=int(d.get("step", 0)),
            answers=d.get("answers", {}),
            prompt_name=d.get("prompt_name", ""),
            attachments=d.get("attachments", {}),
            llm_mode=bool(d.get("llm_mode", False)),
            llm_seed=d.get("llm_seed", ""),
            llm_style=d.get("llm_style", "freeform"),
            transcript=list(d.get("transcript", [])),
        )
