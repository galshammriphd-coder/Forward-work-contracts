"""AI-Powered Project Auto-Initiation: upload -> analyse -> generate -> review -> activate.
The session draft is a sandbox; live tables are written only by `activate`, after approval."""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import config, models as m, security
from ..ai import charter, generators
from ..rag import parsers
from . import core, knowledge

SECTIONS = ["profile", "wbs", "schedule", "risks", "budget", "documents"]


def start(db: Session, user: m.User, filename: str, data: bytes) -> m.InitiationSession:
    knowledge._check(filename, data)
    folder = config.STORAGE_DIR / "_initiation"
    folder.mkdir(parents=True, exist_ok=True)
    s = m.InitiationSession(user_id=user.id, filename=knowledge._safe_name(filename), draft={}, approvals={})
    db.add(s)
    db.flush()
    path = folder / f"{s.id}_{s.filename}"
    path.write_bytes(data)
    s.storage_path = str(path)
    segs = parsers.parse(path, filename)  # ParseError propagates with a clear message
    if not segs:
        raise parsers.ParseError("No readable text was found in this file.")
    s.draft = charter.analyze(segs, s.filename)
    s.language = s.draft["language"]
    security.audit(db, user, "initiation.upload", "initiation_session", s.id, None, {"file": s.filename})
    from . import automation
    automation.emit(db, "charter.uploaded", {"session_id": s.id, "filename": s.filename})
    db.flush()
    return s


def _touch(s: m.InitiationSession, draft: dict):
    s.draft = dict(draft)  # reassign so the JSON column is marked dirty


def generate(db: Session, s: m.InitiationSession, step: str) -> m.InitiationSession:
    d = dict(s.draft)
    cal = core.calendar(db)
    if step == "wbs":
        out = generators.generate_wbs(d, cal)
        d.update(phases=out["phases"], wbs=out["wbs"], activities=out["activities"], wbs_assumptions=out["assumptions"])
        d.pop("schedule", None)
    elif step == "schedule":
        if not d.get("activities"):
            raise ValueError("Generate the WBS first")
        out = generators.generate_schedule(d, cal)
        d["activities"], d["milestones"] = out["activities"], out["milestones"]
        d["schedule"] = {k: out[k] for k in ("finish", "duration_days", "critical_path", "warnings", "start")}
    elif step == "risks":
        d["risks"] = generators.generate_risks(d, core.get_settings(db)["risk_thresholds"])
    elif step == "documents":
        d["documents"] = generators.generate_documents(d)
    else:
        raise ValueError(f"Unknown step {step}")
    s.status = "generated"
    # regenerating a section invalidates its approval
    s.approvals = {k: v for k, v in (s.approvals or {}).items() if k != step and not (step == "wbs" and k == "schedule")}
    _touch(s, d)
    db.flush()
    return s


def update_draft(db: Session, s: m.InitiationSession, patch: dict) -> m.InitiationSession:
    """User edits. Edited profile values are re-tagged 'user'; edited activities trigger a recalculation."""
    d = dict(s.draft)
    for f, v in (patch.get("profile") or {}).items():
        old = d["profile"].get(f) or {}
        if v in (None, ""):
            d["profile"].pop(f, None)
        elif old.get("value") != v:
            d["profile"][f] = {"value": v, "raw": v, "tag": "user", "source": None}
    d["missing"] = [x for x in d.get("missing", []) if x not in d["profile"]]
    for key in ("activities", "risks", "milestones", "documents", "phases", "wbs"):
        if key in patch:
            d[key] = patch[key]
    if "lists" in patch:
        d["lists"] = {**d.get("lists", {}), **patch["lists"]}
    if "activities" in patch and d.get("schedule"):
        _touch(s, d)
        return generate(db, s, "schedule")
    _touch(s, d)
    db.flush()
    return s


def approve(db: Session, s: m.InitiationSession, user: m.User, section: str, approved: bool = True) -> m.InitiationSession:
    if section not in SECTIONS:
        raise ValueError(f"Unknown section {section}")
    ap = dict(s.approvals or {})
    if approved:
        ap[section] = {"by": user.email, "at": datetime.utcnow().isoformat()}
    else:
        ap.pop(section, None)
    s.approvals = ap
    db.flush()
    if section == "profile" and approved:
        from . import automation
        automation.emit(db, "charter.approved", {"session_id": s.id})
    return s


def activate(db: Session, s: m.InitiationSession, user: m.User, portfolio_id=None, program_id=None, department_id=None) -> m.Project:
    if s.status == "activated":
        raise ValueError("This session has already created a project")
    d = s.draft
    need = [x for x in SECTIONS if x not in (s.approvals or {})]
    if need:
        raise ValueError("Approve these sections before activating: " + ", ".join(need))
    P = lambda f: (d["profile"].get(f) or {}).get("value")
    if not P("name"):
        raise ValueError("The project needs a name before it can be created")
    seq = (db.scalar(select(func.count()).select_from(m.Project)) or 0) + 1
    code = P("code") or f"PRJ-{date.today().year}-{seq:03d}"
    if db.scalar(select(m.Project).where(m.Project.code == code)):
        code = f"{code}-{s.id}"
    mgr = None
    if P("manager"):
        mgr = db.scalar(select(m.User).where((m.User.name_ar == P("manager")) | (m.User.name_en == P("manager"))))
    lst = lambda f: "\n".join(i["text"] for i in d["lists"].get(f, []))
    acts = d.get("activities", [])
    start = date.fromisoformat(P("start_date")) if P("start_date") else (date.fromisoformat(d["schedule"]["start"]) if d.get("schedule") else None)
    end = date.fromisoformat(P("end_date")) if P("end_date") else (date.fromisoformat(d["schedule"]["finish"]) if d.get("schedule", {}).get("finish") else None)
    name = P("name")
    p = m.Project(code=code, name_ar=name, name_en=name, description=P("description"), sponsor=P("sponsor"),
                  business_owner=P("business_owner"), manager_id=mgr.id if mgr else user.id, status="planned", stage="planning",
                  priority={"high": "high", "عالية": "high", "عاليه": "high", "low": "low", "منخفضة": "low"}.get(str(P("priority") or "").strip().lower(), "medium"),
                  start_date=start, end_date=end, budget=float(P("budget") or 0), business_case=P("business_case"),
                  scope=P("scope"), out_of_scope=P("out_of_scope"), success_criteria=lst("success_criteria"),
                  assumptions=lst("assumptions"), constraints=lst("constraints"), dependencies_text=lst("dependencies"),
                  portfolio_id=portfolio_id, program_id=program_id, department_id=department_id, created_from="charter")
    db.add(p)
    db.flush()
    db.add(m.ProjectMember(project_id=p.id, user_id=user.id, project_role="creator"))
    if mgr and mgr.id != user.id:
        db.add(m.ProjectMember(project_id=p.id, user_id=mgr.id, project_role="manager"))

    phase_id, deliv_id, wbs_id, act_id = {}, {}, {}, {}
    for ph in d.get("phases", []):
        row = m.ProjectPhase(project_id=p.id, name=ph["name"], order=ph["order"])
        db.add(row); db.flush()
        phase_id[ph["key"]] = row.id
    for it in d["lists"].get("deliverables", []):
        row = m.Deliverable(project_id=p.id, name=it["text"], phase_id=phase_id.get("exec"), source_tag=it.get("tag", "extracted"))
        db.add(row); db.flush()
        deliv_id[it["text"]] = row.id
    for w in d.get("wbs", []):
        row = m.WBSElement(project_id=p.id, parent_id=wbs_id.get(w["parent"]), code=w["code"], name=w["name"], kind=w["kind"],
                           phase_id=phase_id.get(w["phase"]), deliverable_id=deliv_id.get(w.get("deliverable")),
                           order=len(wbs_id), source_tag=w.get("tag", "ai"))
        db.add(row); db.flush()
        wbs_id[w["key"]] = row.id
    for i, a in enumerate(acts):
        row = m.Activity(project_id=p.id, wbs_id=wbs_id.get(a["wbs"]), phase_id=phase_id.get(a["phase"]),
                         deliverable_id=deliv_id.get(a.get("deliverable")), parent_id=act_id.get(a.get("parent")),
                         code=a["code"], wbs_code=a.get("wbs_code"), name=a["name"], description=a.get("description"),
                         responsible_name=a.get("responsible_name"), supporting_team=a.get("supporting_team"),
                         duration_days=int(a["duration_days"]), priority=a.get("priority", "medium"),
                         required_resources=a.get("required_resources"), estimated_cost=float(a.get("estimated_cost") or 0),
                         completion_criteria=a.get("completion_criteria"), weight=float(a.get("weight") or 0), order=i,
                         planned_start=date.fromisoformat(a["planned_start"]) if a.get("planned_start") else None,
                         planned_end=date.fromisoformat(a["planned_end"]) if a.get("planned_end") else None,
                         source_tag=a.get("tag", "ai"))
        db.add(row); db.flush()
        act_id[a["key"]] = row.id
    for a in acts:
        for dep in a.get("deps", []):
            if dep["pred"] in act_id:
                db.add(m.Dependency(project_id=p.id, predecessor_id=act_id[dep["pred"]], successor_id=act_id[a["key"]],
                                    type=dep.get("type", "FS"), lag_days=int(dep.get("lag", 0))))
    db.flush()
    core.recompute_schedule(db, p)  # authoritative dates come from the engine, not from the draft
    core.create_baseline(db, p, user, "Baseline 1 (initiation)")
    for x in d.get("milestones", []):
        if x.get("target_date"):
            db.add(m.Milestone(project_id=p.id, name=x["name"], target_date=date.fromisoformat(x["target_date"]),
                               acceptance_criteria=x.get("acceptance_criteria"), owner_name=P("manager"), source_tag=x.get("tag", "ai")))
    for r in d.get("risks", []):
        row = m.Risk(project_id=p.id, code=r["code"], scope_level=r["scope_level"], title=r["title"], description=r.get("description"),
                     category=r.get("category"), probability=r["probability"], impact=r["impact"], score=r["score"], level=r["level"],
                     owner_name=r.get("owner_name"), mitigation=r.get("mitigation"), contingency=r.get("contingency"), trigger=r.get("trigger"),
                     response_deadline=date.fromisoformat(r["response_deadline"]) if r.get("response_deadline") else None,
                     residual_probability=r.get("residual_probability"), residual_impact=r.get("residual_impact"),
                     residual_score=r.get("residual_score"), phase_id=phase_id.get(r.get("phase")), source_tag=r.get("tag", "ai"))
        row.activities = [db.get(m.Activity, act_id[k]) for k in r.get("related_activities", []) if k in act_id]
        if r.get("related_deliverable") in deliv_id:
            row.deliverables = [db.get(m.Deliverable, deliv_id[r["related_deliverable"]])]
        db.add(row)
    for it in d["lists"].get("stakeholders", []):
        db.add(m.Stakeholder(project_id=p.id, name=it.get("name") or it["text"], role=it.get("role"), source_tag="extracted"))
    for it in d["lists"].get("kpis", []):
        db.add(m.KPI(project_id=p.id, name=it.get("name") or it["text"], target=it.get("target"), unit=it.get("unit"), source_tag="extracted"))
    if p.budget:
        for ph in d.get("phases", []):
            amt = sum(a.get("estimated_cost") or 0 for a in acts if a["phase"] == ph["key"] and not a.get("is_summary"))
            db.add(m.Budget(project_id=p.id, phase_id=phase_id[ph["key"]], category=ph["name"], planned_amount=amt,
                            approved_amount=amt, fiscal_year=(start or date.today()).year))
    db.flush()
    # the charter itself becomes the first document of the project's knowledge base
    ch = knowledge.save_upload(db, user, p, s.filename, Path(s.storage_path).read_bytes(), doc_type="charter",
                               approval_status="approved", doc_date=date.today(), tags=["charter"], fire_event=False)
    db.add(m.ProjectCharter(project_id=p.id, content=d["profile"], source_document_id=ch.id, status="approved",
                            approved_by=user.id, approved_at=datetime.utcnow()))
    for doc in d.get("documents", []):
        if doc["key"] == "charter":
            continue
        knowledge.save_upload(db, user, p, f"{doc['key']}.md", doc["content"].encode("utf-8"), name=doc["title"],
                              doc_type="management_plan", approval_status="draft", doc_date=date.today(),
                              folder="/management", tags=["generated"], source_tag="ai", fire_event=False)
    s.status, s.project_id = "activated", p.id
    security.audit(db, user, "project.create_from_charter", "project", p.id, p.id, {"session": s.id, "code": p.code})
    from . import automation
    automation.emit(db, "project.created", {"project_id": p.id, "created_from": "charter"})
    db.flush()
    return p
