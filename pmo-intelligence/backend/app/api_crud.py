"""Generic, permission-checked CRUD for every register in the platform.
One code path = one place where project isolation and audit are enforced."""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m, security
from .db import get_db
from .engines import risk as risk_engine
from .engines.scheduling import ScheduleError
from .services import automation, core, reports

router = APIRouter(prefix="/api/r")

# name: (model, read permission, write permission, scoped to a project?)
REG = {
    "objectives": (m.StrategicObjective, "portfolio.read", "portfolio.write", False),
    "portfolios": (m.Portfolio, "portfolio.read", "portfolio.write", False),
    "programs": (m.Program, "portfolio.read", "portfolio.write", False),
    "departments": (m.Department, "project.read", "admin.settings", False),
    "phases": (m.ProjectPhase, "project.read", "schedule.write", True),
    "deliverables": (m.Deliverable, "project.read", "schedule.write", True),
    "wbs": (m.WBSElement, "project.read", "schedule.write", True),
    "activities": (m.Activity, "project.read", "schedule.write", True),
    "dependencies": (m.Dependency, "project.read", "schedule.write", True),
    "milestones": (m.Milestone, "project.read", "schedule.write", True),
    "risks": (m.Risk, "project.read", "risk.write", True),
    "risk_responses": (m.RiskResponse, "project.read", "risk.write", False),
    "issues": (m.Issue, "project.read", "project.write", True),
    "change_requests": (m.ChangeRequest, "project.read", "project.write", True),
    "decisions": (m.Decision, "project.read", "project.write", True),
    "budgets": (m.Budget, "finance.read", "finance.write", True),
    "costs": (m.Cost, "finance.read", "finance.write", True),
    "resources": (m.Resource, "project.read", "resource.write", False),
    "assignments": (m.ResourceAssignment, "project.read", "resource.write", True),
    "stakeholders": (m.Stakeholder, "project.read", "project.write", True),
    "kpis": (m.KPI, "project.read", "project.write", True),
    "benefits": (m.Benefit, "project.read", "benefit.write", True),
    "lessons": (m.LessonLearned, "project.read", "benefit.write", True),
    "governance": (m.GovernanceItem, "project.read", "governance.write", False),
    "workflow_definitions": (m.WorkflowDefinition, "project.read", "governance.write", False),
    "alert_rules": (m.AlertRule, "project.read", "automation.write", False),
    "automation_rules": (m.AutomationRule, "project.read", "automation.write", False),
    "report_schedules": (m.ReportSchedule, "report.read", "report.read", False),
}
SCHEDULE_AFFECTING = {"activities", "dependencies"}


def _out(name: str, row) -> dict:
    d = core.to_dict(row)
    if name == "risks":
        d["activity_ids"] = [a.id for a in row.activities]
        d["deliverable_ids"] = [x.id for x in row.deliverables]
        d["responses"] = [core.to_dict(r) for r in row.responses]
    if name == "benefits":
        d.update(reports.benefit_gap(row))
    return d


def _risk_fields(db: Session, row: m.Risk):
    th = core.get_settings(db)["risk_thresholds"]
    row.probability, row.impact = risk_engine.clamp(row.probability), risk_engine.clamp(row.impact)
    a = risk_engine.assess(row.probability, row.impact, th)
    row.score, row.level = a["score"], a["level"]
    if row.residual_probability and row.residual_impact:
        row.residual_score = risk_engine.score(row.residual_probability, row.residual_impact)
    row.updated_at = datetime.utcnow()


def _activity_fields(row: m.Activity, data: dict):
    if "progress" in data:
        row.progress = max(0.0, min(100.0, float(row.progress or 0)))
        if row.progress >= 100:
            row.status, row.actual_end = "completed", row.actual_end or date.today()
            row.actual_start = row.actual_start or row.planned_start
        elif row.progress > 0:
            row.status, row.actual_start, row.actual_end = "in_progress", row.actual_start or date.today(), None
        else:
            row.status, row.actual_end = "not_started", None
    if row.duration_days is not None and row.duration_days < 0:
        raise HTTPException(400, "Duration cannot be negative")


def _after_write(db: Session, name: str, project_id: int | None, user, before_phases=None):
    """Recalculate what depends on the change, then let the early-warning engine look again."""
    if not project_id:
        return
    p = db.get(m.Project, project_id)
    p.last_update_at = datetime.utcnow()
    if name in SCHEDULE_AFFECTING:
        try:
            core.recompute_schedule(db, p)
        except ScheduleError as e:
            db.rollback()
            raise HTTPException(400, f"Schedule not saved: {e}")
        if before_phases is not None:
            for ph in db.scalars(select(m.ProjectPhase).where(m.ProjectPhase.project_id == p.id)):
                if ph.status == "completed" and before_phases.get(ph.id) != "completed":
                    automation.emit(db, "phase.completed", {"project_id": p.id, "phase_id": ph.id, "phase": ph.name})
    core.run_early_warning(db, p.id)


def _project_of(db: Session, name: str, row) -> int | None:
    if name == "risk_responses":
        r = db.get(m.Risk, row.risk_id)
        return r.project_id if r else None
    return getattr(row, "project_id", None)


def _guard(db: Session, user, name: str, project_id, write: bool):
    model, rp, wp, scoped = REG[name]
    security.require(user, wp if write else rp)
    if project_id:
        security.require_project(db, user, int(project_id))
    elif scoped and write and name != "risks":
        raise HTTPException(400, "project_id is required")


@router.get("/{name}")
def list_rows(name: str, project_id: int | None = None, db: Session = Depends(get_db), user=Depends(security.current_user)):
    if name not in REG:
        raise HTTPException(404, "Unknown register")
    model, rp, _, scoped = REG[name]
    _guard(db, user, name, project_id, False)
    q = select(model)
    if hasattr(model, "project_id"):
        if project_id:
            q = q.where(model.project_id == project_id)
        else:
            ids = security.accessible_project_ids(db, user)
            if ids is not None:  # never leak rows of projects outside the user's scope
                cond = model.project_id.in_(ids)
                # rows that belong to no project: programme/portfolio risks need portfolio visibility
                if name in ("governance", "lessons", "decisions") or (name == "risks" and security.has(user, "portfolio.read")):
                    cond = cond | model.project_id.is_(None)
                q = q.where(cond)
    rows = list(db.scalars(q.order_by(model.id)))
    return [_out(name, r) for r in rows]


@router.post("/{name}")
def create_row(name: str, request: Request, data: dict = Body(...), db: Session = Depends(get_db), user=Depends(security.current_user)):
    if name not in REG:
        raise HTTPException(404, "Unknown register")
    model = REG[name][0]
    pid = data.get("project_id")
    if name == "risk_responses":
        risk = db.get(m.Risk, data.get("risk_id") or 0)
        if not risk:
            raise HTTPException(400, "risk_id is required")
        pid = risk.project_id
    _guard(db, user, name, pid, True)
    row = model(**core.coerce(model, data))
    if name == "dependencies":
        for k in ("predecessor_id", "successor_id"):
            a = db.get(m.Activity, getattr(row, k) or 0)
            if not a or a.project_id != row.project_id:  # no cross-project links
                raise HTTPException(400, "Both activities must belong to this project")
    before = {ph.id: ph.status for ph in db.scalars(select(m.ProjectPhase).where(m.ProjectPhase.project_id == pid))} if pid else None
    if name == "risks":
        _risk_fields(db, row)
        if not row.code:
            n = len(list(db.scalars(select(m.Risk.id).where(m.Risk.project_id == pid)))) + 1
            row.code = f"R-{n:03d}"
        row.activities = [a for a in (db.get(m.Activity, i) for i in data.get("activity_ids", [])) if a and a.project_id == pid]
        row.deliverables = [x for x in (db.get(m.Deliverable, i) for i in data.get("deliverable_ids", [])) if x and x.project_id == pid]
    if name == "activities":
        _activity_fields(row, data)
        if not row.code:
            n = len(list(db.scalars(select(m.Activity.id).where(m.Activity.project_id == pid)))) + 1
            row.code = f"ACT-{n:03d}"
    db.add(row)
    try:
        db.flush()
    except Exception as e:
        db.rollback()
        raise HTTPException(400, f"Could not save: {getattr(e, 'orig', e)}")
    security.audit(db, user, f"{name}.create", name, row.id, pid, {"data": {k: v for k, v in data.items() if k != "password"}}, request)
    _after_write(db, name, pid, user, before)
    if name == "risks" and row.level == "critical":
        automation.emit(db, "risk.critical", {"project_id": pid, "risk_id": row.id, "title": row.title, "score": row.score})
    db.commit()
    return _out(name, row)


@router.patch("/{name}/{row_id}")
def update_row(name: str, row_id: int, request: Request, data: dict = Body(...), db: Session = Depends(get_db), user=Depends(security.current_user)):
    if name not in REG:
        raise HTTPException(404, "Unknown register")
    model = REG[name][0]
    row = db.get(model, row_id)
    if not row:
        raise HTTPException(404, "Not found")
    pid = _project_of(db, name, row)
    _guard(db, user, name, pid, True)
    data.pop("project_id", None)  # a row never moves to another project
    before = {ph.id: ph.status for ph in db.scalars(select(m.ProjectPhase).where(m.ProjectPhase.project_id == pid))} if pid else None
    was_level = getattr(row, "level", None) if name == "risks" else None
    changes = {}
    for k, v in core.coerce(model, data).items():
        if getattr(row, k) != v:
            changes[k] = [str(getattr(row, k)), str(v)]
            setattr(row, k, v)
    if name == "risks":
        _risk_fields(db, row)
        if "activity_ids" in data:
            row.activities = [a for a in (db.get(m.Activity, i) for i in data["activity_ids"]) if a and a.project_id == pid]
        if "deliverable_ids" in data:
            row.deliverables = [x for x in (db.get(m.Deliverable, i) for i in data["deliverable_ids"]) if x and x.project_id == pid]
    if name == "activities":
        _activity_fields(row, data)
        if row.source_tag == "ai" and changes:
            row.source_tag = "user"
    if name == "milestones" and row.status == "achieved" and not row.actual_date:
        row.actual_date = date.today()
    if name == "issues" and row.status == "closed" and not row.closed_at:
        row.closed_at = date.today()
    db.flush()
    security.audit(db, user, f"{name}.update", name, row.id, pid, {"changes": changes}, request)
    _after_write(db, name, pid, user, before)
    if name == "risks" and row.level == "critical" and was_level != "critical":
        automation.emit(db, "risk.critical", {"project_id": pid, "risk_id": row.id, "title": row.title, "score": row.score})
    db.commit()
    return _out(name, row)


@router.delete("/{name}/{row_id}")
def delete_row(name: str, row_id: int, request: Request, db: Session = Depends(get_db), user=Depends(security.current_user)):
    if name not in REG:
        raise HTTPException(404, "Unknown register")
    model = REG[name][0]
    row = db.get(model, row_id)
    if not row:
        raise HTTPException(404, "Not found")
    pid = _project_of(db, name, row)
    _guard(db, user, name, pid, True)
    label = getattr(row, "name", None) or getattr(row, "title", None) or getattr(row, "name_ar", None)
    db.delete(row)
    try:
        db.flush()
    except Exception:
        db.rollback()
        raise HTTPException(409, "This record is still used by other records. Remove those links first.")
    security.audit(db, user, f"{name}.delete", name, row_id, pid, {"label": label}, request)
    _after_write(db, name, pid, user)
    db.commit()
    return {"ok": True}
