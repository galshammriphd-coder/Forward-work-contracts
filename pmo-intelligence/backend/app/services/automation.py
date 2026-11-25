"""Workflow engine (stage gates & approvals) and the no-code automation engine
(event / schedule / rule / AI / manual triggers) with a full run log."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m

EVENTS = ["project.created", "charter.uploaded", "charter.approved", "project.activated", "document.uploaded",
          "alert.created", "risk.critical", "phase.completed", "project.completed", "approval.decided", "schedule.tick"]
ACTIONS = ["notify", "start_workflow", "request_gate_approval", "run_early_warning", "create_closure_report",
           "reindex_knowledge", "generate_wbs", "start_ai_analysis", "ai_summary_alert", "webhook"]


# ---------- workflow ----------
def start_workflow(db: Session, key: str, project: m.Project | None, user: m.User | None) -> m.WorkflowInstance:
    d = db.scalar(select(m.WorkflowDefinition).where(m.WorkflowDefinition.key == key, m.WorkflowDefinition.is_active))
    if not d or not d.steps:
        raise ValueError(f"No active workflow '{key}'")
    inst = m.WorkflowInstance(definition_id=d.id, project_id=project.id if project else None,
                              started_by=user.id if user else None, history=[])
    db.add(inst)
    db.flush()
    _open_step(db, d, inst, project)
    return inst


def _open_step(db: Session, d: m.WorkflowDefinition, inst: m.WorkflowInstance, project: m.Project | None):
    from .core import notify
    step = d.steps[inst.current_step]
    db.add(m.Approval(instance_id=inst.id, project_id=inst.project_id, step_index=inst.current_step,
                      title=step.get("name_ar") or step.get("name_en"), approver_role=step.get("approver_role"),
                      due_date=date.today() + timedelta(days=int(step.get("sla_days") or 5))))
    notify(db, [step.get("approver_role") or "pmo_director"], project,
           f"اعتماد مطلوب: {step.get('name_ar')}", project.name_ar if project else None, "advisory")


def decide(db: Session, approval: m.Approval, user: m.User, approve: bool, note: str = "") -> m.WorkflowInstance | None:
    if approval.status != "pending":
        raise ValueError("This approval has already been decided")
    if approval.approver_role and user.role.key not in (approval.approver_role, "super_admin", "pmo_director"):
        raise PermissionError(f"Only the {approval.approver_role} role can decide this step")
    approval.status = "approved" if approve else "rejected"
    approval.decided_by, approval.decided_at, approval.note = user.id, datetime.utcnow(), note
    inst = db.get(m.WorkflowInstance, approval.instance_id) if approval.instance_id else None
    project = db.get(m.Project, approval.project_id) if approval.project_id else None
    if inst:
        d = db.get(m.WorkflowDefinition, inst.definition_id)
        step = d.steps[inst.current_step]
        inst.history = (inst.history or []) + [{"step": inst.current_step, "name": step.get("name_en"), "decision": approval.status,
                                                "by": user.email, "at": datetime.utcnow().isoformat(), "note": note}]
        if not approve:
            inst.status, inst.completed_at = "rejected", datetime.utcnow()
        else:
            if project and step.get("sets_stage"):
                project.stage = step["sets_stage"]
                if step.get("sets_status"):
                    project.status = step["sets_status"]
            if inst.current_step + 1 < len(d.steps):
                inst.current_step += 1
                _open_step(db, d, inst, project)
            else:
                inst.status, inst.completed_at = "completed", datetime.utcnow()
    db.flush()
    emit(db, "approval.decided", {"project_id": approval.project_id, "status": approval.status, "title": approval.title})
    return inst


# ---------- automation ----------
def _match(conditions: list, payload: dict) -> bool:
    for c in conditions or []:
        v, target, op = payload.get(c.get("field")), c.get("value"), c.get("op", "eq")
        try:
            ok = {"eq": v == target, "ne": v != target, "gt": v is not None and float(v) > float(target),
                  "lt": v is not None and float(v) < float(target), "in": v in (target if isinstance(target, list) else [target]),
                  "contains": target is not None and str(target) in str(v or "")}[op]
        except (TypeError, ValueError, KeyError):
            ok = False
        if not ok:
            return False
    return True


def _do(db: Session, action: dict, payload: dict) -> str:
    from . import core
    kind = action.get("type")
    project = db.get(m.Project, payload["project_id"]) if payload.get("project_id") else None
    if kind == "notify":
        msg = (action.get("message") or "{title}").format_map({**{"title": "", "project": project.name_ar if project else ""}, **payload})
        n = core.notify(db, action.get("roles") or ["pmo_director"], project, msg, action.get("body"),
                        action.get("severity", "advisory"), include_manager=action.get("include_manager", False),
                        channel=action.get("channel", "in_app"))
        return f"notified {n} user(s)"
    if kind == "start_workflow":
        inst = start_workflow(db, action.get("workflow", "project_lifecycle"), project, None)
        return f"workflow instance {inst.id} started"
    if kind == "request_gate_approval":
        ph = db.get(m.ProjectPhase, payload.get("phase_id")) if payload.get("phase_id") else None
        if not ph:
            return "no phase in event"
        ph.gate_status = "requested"
        db.add(m.Approval(project_id=ph.project_id, title=f"اعتماد بوابة المرحلة: {ph.name}",
                          approver_role=action.get("role", "pmo_director"), due_date=date.today() + timedelta(days=5)))
        return f"gate approval requested for phase {ph.id}"
    if kind == "run_early_warning":
        r = core.run_early_warning(db, payload.get("project_id"))
        return f"early warning: {r['created']} new, {r['resolved']} resolved"
    if kind == "create_closure_report":
        from . import reports
        if not project:
            return "no project in event"
        doc = reports.save_as_document(db, project, "closure", "ar")
        return f"closure report stored as document {doc.id}"
    if kind == "reindex_knowledge":
        from . import knowledge
        n = knowledge.reindex_project(db, payload["project_id"]) if payload.get("project_id") else 0
        return f"re-indexed {n} document(s)"
    if kind == "generate_wbs":
        from . import initiation
        s = db.get(m.InitiationSession, payload.get("session_id")) if payload.get("session_id") else None
        if not s:
            return "no initiation session in event"
        initiation.generate(db, s, "wbs")
        return f"WBS draft generated for session {s.id}"
    if kind == "start_ai_analysis":
        return "analysis runs inside the upload request; nothing further to do"
    if kind == "ai_summary_alert":
        from . import copilot
        if not project:
            return "no project in event"
        text = copilot.project_brief(db, project, "ar")
        n = core.notify(db, action.get("roles") or ["pmo_director"], project, f"ملخص ذكي: {project.name_ar}", text, "advisory")
        return f"AI brief sent to {n} user(s)"
    if kind == "webhook":
        # Integration point (Teams / Power Automate / Jira / ERP). Sends event metadata only —
        # never document content — to a URL an automation administrator typed in.
        import httpx
        url = (action.get("url") or "").strip()
        if not url.lower().startswith(("https://", "http://")):
            raise ValueError("webhook needs an http(s) URL")
        body = {"event": payload.get("_event"), "project_code": project.code if project else None,
                "project": project.name_en if project else None, "title": payload.get("title"),
                "severity": payload.get("severity"), "rule_key": payload.get("rule_key")}
        r = httpx.post(url, json=body, timeout=10)
        r.raise_for_status()
        return f"webhook delivered ({r.status_code})"
    raise ValueError(f"unknown action {kind}")


def run_rule(db: Session, rule: m.AutomationRule, payload: dict, trigger: str) -> m.AutomationRun:
    run = m.AutomationRun(rule_id=rule.id, project_id=payload.get("project_id"), trigger=trigger, status="success")
    db.add(run)
    try:
        if not _match(rule.conditions, payload):
            run.status, run.result = "skipped", "conditions not met"
        else:
            with db.begin_nested():  # a failing action must not undo the caller's work
                run.result = "; ".join(_do(db, a, payload) for a in (rule.actions or []))
    except Exception as e:
        run.status, run.error = "failed", f"{type(e).__name__}: {e}"
    run.finished_at = datetime.utcnow()
    rule.last_run_at = run.finished_at
    db.flush()
    return run


_depth = 0


def emit(db: Session, event: str, payload: dict) -> list[m.AutomationRun]:
    global _depth
    if _depth > 2:  # guard against rules that trigger each other forever
        return []
    _depth += 1
    try:
        rules = db.scalars(select(m.AutomationRule).where(m.AutomationRule.enabled, m.AutomationRule.event == event,
                                                          m.AutomationRule.trigger_type.in_(["event", "rule", "ai"])))
        # an event that does not meet a rule's conditions is not a run; only real executions are logged
        payload = {**payload, "_event": event}
        return [run_rule(db, r, payload, event) for r in rules if _match(r.conditions, payload)]
    finally:
        _depth -= 1


def run_scheduled(db: Session, now: datetime | None = None) -> int:
    """Called by the background ticker: runs schedule-triggered rules and report schedules that are due."""
    now = now or datetime.utcnow()
    gap = {"hourly": timedelta(hours=1), "daily": timedelta(days=1), "weekly": timedelta(days=7), "monthly": timedelta(days=30)}
    n = 0
    for r in db.scalars(select(m.AutomationRule).where(m.AutomationRule.enabled, m.AutomationRule.trigger_type == "schedule")):
        if not r.last_run_at or now - r.last_run_at >= gap.get(r.schedule or "daily", timedelta(days=1)):
            run_rule(db, r, {}, f"schedule:{r.schedule}")
            n += 1
    purge(db, now)
    from . import reports
    for s in db.scalars(select(m.ReportSchedule).where(m.ReportSchedule.enabled)):
        if not s.last_run_at or now - s.last_run_at >= gap.get(s.frequency, timedelta(days=7)):
            reports.run_schedule(db, s)
            n += 1
    return n


def purge(db: Session, now: datetime | None = None) -> dict:
    """Data-retention policy from Settings. The audit trail is deliberately left alone."""
    from sqlalchemy import delete
    from .core import get_settings
    now = now or datetime.utcnow()
    r = get_settings(db).get("retention", {})
    out = {}
    for key, model, col, extra in (("notifications_days", m.Notification, m.Notification.created_at, None),
                                   ("automation_runs_days", m.AutomationRun, m.AutomationRun.started_at, None),
                                   ("resolved_alerts_days", m.Alert, m.Alert.resolved_at, m.Alert.status == "resolved")):
        days = int(r.get(key) or 0)
        if days > 0:
            q = delete(model).where(col < now - timedelta(days=days))
            if extra is not None:
                q = q.where(extra)
            out[key] = db.execute(q).rowcount
    return out
