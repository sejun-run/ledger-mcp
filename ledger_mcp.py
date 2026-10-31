"""Requirements & decision ledger MCP server.

Records what each stakeholder (human or AI agent) said, what was decided and why,
and what remains unverified. Produces a Q&A-ready report.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Literal

from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

Kind = Literal["problem", "requirement", "constraint", "assumption", "question", "decision", "risk"]
Status = Literal["open", "done", "verified", "dropped", "answered"]

LEDGER_PATH = Path(os.environ.get("LEDGER_PATH", "ledger.json"))  # relative to cwd = the workspace

INSTRUCTIONS = """\
This ledger drives the working process. Stakeholders (AI coworkers) talk to the HUMAN in a separate panel you
cannot see. The human relays their statements to you in chat. Rules:
1. FIRST call `start(task=...)`. It returns the kickoff checklist.
   Then explore the workspace (tree, brief, data files, code) and log what you learn with source="workspace:<path>".
2. Draft interview questions for the human to ask the stakeholders: log each as kind=question, source="codex",
   rationale=<why you need it / who to ask>. Print the list for the human.
3. When the human pastes stakeholder statements, log them (use `log_many` for several at once) with
   source=<which stakeholder>. Mark answered questions `answered` with the answer in the note.
   NEVER invent requirements that the human did not relay. Unknown -> question. Guess -> assumption.
4. Call `next()` after each relay and whenever unsure. It tells you the phase and what to do now.
5. The task is broad. Log each candidate problem as kind=problem (rationale=impact / feasibility in the time left).
   Choose a scope that fits the budget and log it as a decision whose text starts with "SCOPE:", linking the chosen
   problem ids; mark the others `dropped` with a note. Do not build before a SCOPE decision exists.
6. Conflicts or changes -> `decision` with `rationale`, linking affected ids.
7. `verified` only with evidence in the note. `done` = implemented, unchecked.
8. Before submitting: `report()` and paste its output into the deliverable. The ledger file itself
   (ledger.json in the workspace) is part of the deliverable: keep it, commit it if there is a repo.
"""


class Entry(BaseModel):
    id: int
    kind: Kind
    text: str
    source: str = ""
    rationale: str = ""
    status: Status = "open"
    notes: list[str] = Field(default_factory=list)
    links: list[int] = Field(default_factory=list)
    created: str


class Ledger(BaseModel):
    task: str = ""
    started: str = ""  # ISO timestamp
    entries: list[Entry] = Field(default_factory=list)

    @classmethod
    def load(cls) -> "Ledger":
        if LEDGER_PATH.exists():
            return cls.model_validate_json(LEDGER_PATH.read_text())
        return cls()

    def save(self) -> None:
        LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        LEDGER_PATH.write_text(self.model_dump_json(indent=2))

    def get(self, id: int) -> Entry:
        for e in self.entries:
            if e.id == id:
                return e
        raise ValueError(f"no entry with id {id}")


def _now() -> str:
    return datetime.now().strftime("%H:%M")


def _fmt(e: Entry) -> str:
    line = f"- [{e.id}] ({e.status}) {e.text}"
    if e.source:
        line += f"  — source: {e.source}"
    if e.rationale:
        line += f"\n    why: {e.rationale}"
    if e.links:
        line += f"\n    links: {e.links}"
    for n in e.notes:
        line += f"\n    note: {n}"
    return line


mcp = MCPServer("ledger", instructions=INSTRUCTIONS)


@mcp.tool()
def log(kind: Kind, text: str, source: str = "", rationale: str = "", links: list[int] | None = None) -> dict:
    """Record a requirement, constraint, assumption, question, decision or risk.

    source: who said it (e.g. "PM agent", "ops agent", "task brief", "me").
    rationale: for decisions, why this option; for risks, the mitigation.
    links: ids of related entries (e.g. requirements a decision resolves).
    """
    ledger = Ledger.load()
    next_id = max((e.id for e in ledger.entries), default=0) + 1
    entry = Entry(id=next_id, kind=kind, text=text, source=source, rationale=rationale,
                  links=links or [], created=_now())
    ledger.entries.append(entry)
    ledger.save()
    return entry.model_dump()


class LogItem(BaseModel):
    kind: Kind
    text: str
    source: str = ""
    rationale: str = ""
    links: list[int] = Field(default_factory=list)


@mcp.tool()
def log_many(items: list[LogItem]) -> str:
    """Record several entries at once, e.g. after the human pastes a chunk of stakeholder conversation.
    Each item: kind, text, source (who said it), optional rationale/links. Returns the assigned ids."""
    ledger = Ledger.load()
    next_id = max((e.id for e in ledger.entries), default=0) + 1
    out = []
    for it in items:
        ledger.entries.append(Entry(id=next_id, created=_now(), **it.model_dump()))
        out.append(f"[{next_id}] {it.kind}: {it.text}" + (f" — {it.source}" if it.source else ""))
        next_id += 1
    ledger.save()
    return "\n".join(out)


@mcp.tool()
def update(id: int, status: Status | None = None, note: str | None = None, links: list[int] | None = None) -> dict:
    """Update an entry's status and/or append a note (e.g. verification evidence, answer to a question)."""
    ledger = Ledger.load()
    entry = ledger.get(id)
    if status:
        entry.status = status
    if note:
        entry.notes.append(f"{_now()} {note}")
    if links:
        entry.links = sorted(set(entry.links) | set(links))
    ledger.save()
    return entry.model_dump()


@mcp.tool()
def show(kind: Kind | None = None, status: Status | None = None) -> str:
    """List entries, optionally filtered by kind and/or status."""
    entries = [e for e in Ledger.load().entries
               if (kind is None or e.kind == kind) and (status is None or e.status == status)]
    if not entries:
        return "(no entries)"
    return "\n".join(_fmt(e) for e in entries)



TOTAL_MIN = int(os.environ.get("LEDGER_MINUTES", "240"))
PHASES = (  # (end fraction, name)
    (0.17, "discover"),
    (0.75, "build"),
    (0.88, "verify"),
    (1.01, "submit"),
)

KICKOFF = """\
# Kickoff
The human will interview the AI coworkers in a separate panel and relay answers here.
0. Explore the workspace FIRST: list the directory tree, read any brief/README/spec, open each data file
   (head + schema), note existing code and tests. Log every fact you find with source="workspace:<path>"
   (requirement/constraint if stated, assumption if inferred). Then summarise findings to the human.
1. Ask the human: who are the stakeholders/coworkers available, and is there material not in the workspace?
2. Draft 5-8 interview questions, informed by what the workspace left unclear, and log each as kind=question (source="codex", rationale=<who to ask / why>).
   Cover: success criteria, inputs/data and formats, deadline/cadence, who uses the result, what must NOT change,
   known pain points, how success will be judged.
3. Print the questions grouped by stakeholder so the human can copy-paste them.
4. As answers arrive: update(question_id, status="answered", note=<answer>) and log the resulting
   requirements/constraints with source=<stakeholder>. Use log_many for a pasted chunk.
5. SCOPING: log every candidate problem you hear about as kind=problem (source, rationale=impact vs. feasibility
   in the remaining time). Propose 1 scope to the human, confirm with the stakeholders via the human, then log a
   decision "SCOPE: <what is in> / out: <what is not>" linking the chosen problem ids. Mark the rest `dropped`.
Target before build: a SCOPE decision, >=5 requirements inside that scope, >=2 constraints, no blocking questions.
"""

PHASE_GUIDE = {
    "discover": "Keep gathering via the human. Convert vague statements into testable requirements with source. "
                "If something blocks design, log a question and ask the human to relay it now.",
    "build": "Deliverable is most likely a local web app: get a minimal running version on localhost within "
             "~30 min (one page, real data), then iterate requirement by requirement. Verify by actually hitting it "
             "(curl / browser), not by reading code. Implement open requirements in priority order. On conflicts log a `decision` with rationale and links. "
             "Mark implemented items `done`. Re-ask stakeholders when a requirement is ambiguous instead of guessing.",
    "verify": "Stop adding features. For every `done` item, run a check and `update(status=verified, note=<evidence>)`. "
              "Anything you cannot verify -> `log(kind=risk, rationale=<mitigation>)`.",
    "submit": "Call `report()` and paste it into the deliverable. Prepare to explain each decision and each item under "
              "'Where this could fail'.",
}


def _elapsed_min(ledger: Ledger) -> float | None:
    if not ledger.started:
        return None
    return (datetime.now() - datetime.fromisoformat(ledger.started)).total_seconds() / 60


def _phase(ledger: Ledger) -> str:
    el = _elapsed_min(ledger)
    if el is None:
        return "discover"
    frac = el / TOTAL_MIN
    return next(name for end, name in PHASES if frac < end)


@mcp.tool()
def start(task: str) -> str:
    """Call this FIRST. Records the task and start time, returns the kickoff checklist."""
    ledger = Ledger.load()
    if ledger.started:
        return f"Already started at {ledger.started[11:16]} for task: {ledger.task}\n\n{KICKOFF}"
    ledger.task = task
    ledger.started = datetime.now().isoformat(timespec="seconds")
    ledger.save()
    return f"Started {ledger.started[11:16]}, budget {TOTAL_MIN} min.\n\n{KICKOFF}"


@mcp.tool(name="next")
def next_step() -> str:
    """What to do now: current phase (by elapsed time), ledger health, and concrete next actions."""
    ledger = Ledger.load()
    e = ledger.entries
    el = _elapsed_min(ledger)
    phase = _phase(ledger)
    k = lambda kind, st=None: [x for x in e if x.kind == kind and (st is None or x.status == st)]
    reqs = k("requirement")
    lines = [f"# Phase: {phase}" + (f"  ({el:.0f}/{TOTAL_MIN} min)" if el is not None else "  (start() not called yet)")]
    lines.append(f"requirements: {len(reqs)} total, {len(k('requirement','open'))} open, "
                 f"{len(k('requirement','done'))} done, {len(k('requirement','verified'))} verified | "
                 f"constraints {len(k('constraint'))} | assumptions {len(k('assumption'))} "
                 f"({len([a for a in k('assumption') if a.status != 'verified'])} unverified) | "
                 f"open questions {len([q for q in k('question') if q.status != 'answered'])} | "
                 f"decisions {len(k('decision'))} | risks {len(k('risk'))}")
    lines += ["", PHASE_GUIDE[phase], ""]

    todo = []
    if el is None:
        todo.append("call start(task=...)")
    scope = [d for d in k("decision") if d.text.upper().startswith("SCOPE")]
    if len(k("problem")) < 3 and phase == "discover":
        todo.append("fewer than 3 candidate problems logged: ask the human what pain points each stakeholder raised")
    if not scope:
        todo.append("no SCOPE decision yet: pick one problem that fits the remaining time, confirm via the human, "
                    "log decision 'SCOPE: ...' linking the chosen problem ids" + (" — do NOT build yet" if phase != "discover" else ""))
    if phase == "discover" and (len(reqs) < 5 or len(k("constraint")) < 2):
        todo.append("fewer than 5 requirements / 2 constraints logged: ask the human for more stakeholder input")
    if phase != "discover" and not reqs:
        todo.append("no requirements logged: go back and interview before building")
    oq = [q for q in k("question") if q.status != "answered"]
    if oq:
        todo.append(f"open questions {[q.id for q in oq]}: ask the human to relay them to the stakeholders, then update(status=answered, note=<answer>)")
    if phase in ("verify", "submit"):
        done = k("requirement", "done")
        if done:
            todo.append(f"verify done items {[d.id for d in done]} with evidence")
        ua = [a for a in k("assumption") if a.status != "verified"]
        if ua:
            todo.append(f"verify or convert to risk: assumptions {[a.id for a in ua]}")
    if phase == "submit":
        todo.append("call report() and paste into deliverable")
    if not k("decision") and phase in ("build", "verify", "submit"):
        todo.append("no decisions logged yet: record at least the key design choice with rationale")
    lines += ["## Next actions"] + ([f"- {t}" for t in todo] or ["- nothing blocking; continue the phase guide above"])
    return "\n".join(lines)


@mcp.prompt()
def kickoff(task: str) -> str:
    """Start the task: register it in the ledger and begin stakeholder interviews."""
    return (f"Call the ledger `start` tool with task={task!r}. Then follow the kickoff checklist it returns: "
            "interview every stakeholder/agent, logging each statement with its source before writing any code. "
            "Call `next` when you think discovery is complete.")


@mcp.prompt()
def verify() -> str:
    """Switch to verification: check every done item and record evidence."""
    return ("Call ledger `next`, then `show(kind='requirement', status='done')`. For each item run a concrete check "
            "(test, script, manual inspection) and `update(id, status='verified', note=<evidence>)`. "
            "Anything you cannot verify: `log(kind='risk', text=..., rationale=<mitigation>)`.")


@mcp.prompt()
def wrapup() -> str:
    """Produce the final report and paste it into the deliverable."""
    return ("Call ledger `report`. Paste the full output into the deliverable (README or final document). "
            "Then write a short explanation, for each decision, of why it was chosen, and for each item under "
            "'Where this could fail', what would break and how you would detect it.")

@mcp.tool()
def report() -> str:
    """Q&A-ready markdown summary: requirements by status, decisions with rationale, open questions,
    unverified items and risks. Call before final submission."""
    ledger = Ledger.load()
    entries = ledger.entries
    by = lambda k: [e for e in entries if e.kind == k]
    el = _elapsed_min(ledger)
    out = ["# Ledger report", f"task: {ledger.task or '(not set)'}" + (f" | elapsed {el:.0f} min" if el is not None else ""), ""]

    scope = [d for d in by("decision") if d.text.upper().startswith("SCOPE")]
    probs = by("problem")
    if scope or probs:
        out += ["## Scope"] + [_fmt(d) for d in scope]
        chosen = {i for d in scope for i in d.links}
        if probs:
            out += ["### candidate problems"] + [_fmt(e) + ("  ✔ in scope" if e.id in chosen else "") for e in probs]
        out.append("")

    out += ["## Requirements"]
    reqs = by("requirement")
    for st in ("verified", "done", "open", "dropped"):
        group = [e for e in reqs if e.status == st]
        if group:
            out += [f"### {st} ({len(group)})"] + [_fmt(e) for e in group]
    out.append("")

    for title, kind in (("Constraints", "constraint"), ("Decisions", "decision"), ("Risks", "risk")):
        group = by(kind)
        if group:
            out += [f"## {title}"] + [_fmt(e) for e in group] + [""]

    open_q = [e for e in by("question") if e.status != "answered"]
    answered = [e for e in by("question") if e.status == "answered"]
    if open_q or answered:
        out += ["## Questions"]
        if open_q:
            out += ["### still open"] + [_fmt(e) for e in open_q]
        if answered:
            out += ["### answered"] + [_fmt(e) for e in answered]
        out.append("")

    weak = [e for e in entries if e.kind == "assumption" and e.status != "verified"] + \
           [e for e in reqs if e.status == "done"]
    out += ["## Where this could fail (unverified)"]
    out += [_fmt(e) for e in weak] or ["- nothing unverified"]

    sources = sorted({e.source for e in entries if e.source})
    if sources:
        out += ["", "## Sources consulted", ", ".join(sources)]
    return "\n".join(out)


@mcp.tool()
def reset(confirm: bool = False) -> str:
    """Delete all entries. Requires confirm=true."""
    if not confirm:
        return "pass confirm=true to wipe the ledger"
    Ledger().save()
    return "ledger cleared"


def http_app():
    """Streamable HTTP app. Optional protection: LEDGER_PATH_PREFIX serves at /<prefix>/mcp (URL-as-secret),
    LEDGER_TOKEN requires `Authorization: Bearer <token>`."""
    from starlette.middleware import Middleware
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse

    from mcp.server.transport_security import TransportSecuritySettings

    token = os.environ.get("LEDGER_TOKEN")

    class Bearer(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            if token and request.headers.get("authorization") != f"Bearer {token}":
                return JSONResponse({"error": "unauthorized"}, status_code=401)
            return await call_next(request)

    prefix = os.environ.get("LEDGER_PATH_PREFIX", "").strip("/")
    app = mcp.streamable_http_app(
        host="0.0.0.0",
        streamable_http_path=f"/{prefix}/mcp" if prefix else "/mcp",
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    app.add_middleware(Bearer)
    return app


def main() -> None:
    import sys

    if "--http" in sys.argv:
        import uvicorn

        uvicorn.run(http_app(), host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
    else:
        mcp.run()


if __name__ == "__main__":
    main()
