"""Database-bound services: settings, serialisation, schedule recalculation,
project metrics, early-warning synchronisation and the executive dashboard."""
from __future__ import annotations

import copy
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import config, models as m, security
from ..engines import alerts as alert_engine
from ..engines import evm as evm_engine
from ..engines import risk as risk_engine
from ..engines import scheduling


# ---------- settings ----------
def get_settings(db: Session) -> dict:
    out = copy.deepcopy(config.DEFAULT_SETTINGS)
    for s in db.scalars(select(m.Setting)):
        if isinstance(out.get(s.key), dict) and isinstance(s.value, dict):
            out[s.key].update(s.value)
        else:
            out[s.key] = s.value
    return out


def set_setting(db: Session, key: str, value):
    row = db.get(m.Setting, key)
    if row:
        row.value = value
    else:
        db.add(m.Setting(key=key, value=value))


def calendar(db: Session) -> scheduling.Calendar:
    wc = get_settings(db)["work_calendar"]
    hol = frozenset(date.fromisoformat(h) for h in wc.get("holidays", []) if h)
    return scheduling.Calendar(tuple(wc.get("weekend", [4, 5])), hol)


# ---------- serialisation ----------
def to_dict(obj, exclude=("password_hash", "mfa_secret", "vector", "token_version")) -> dict:
    out = {}
    for c in obj.__table__.columns:
        if c.name in exclude:
            continue
        v = getattr(obj, c.name)
        out[c.name] = v.isoformat() if isinstance(v, (date, datetime)) else v
    return out


def coerce(model, data: dict) -> dict:
    """Keep only real columns and turn ISO strings into dates."""
    out = {}
    for c in model.__table__.columns:
        if c.name not in data or c.name == "id":
            continue
        v = data[c.name]
        t = c.type.__class__.__name__
        if v == "" and t not in ("String", "Text"):
            v = None
        if v is not None:
            if t == "Date" and isinstance(v, str):
                v = date.fromisoformat(v[:10])
            elif t == "DateTime" and isinstance(v, str):
                v = datetime.fromisoformat(v)
            elif t == "Integer" and not isinstance(v, bool):
                v = int(v)
            elif t == "Float":
                v = float(v)
        out[c.name] = v
    return out


# ---------- schedule ----------
def recompute_schedule(db: Session, project: m.Project) -> dict:
    """Run the CPM engine over the project's activities and persist dates, float and criticality."""
    acts = list(db.scalars(select(m.Activity).where(m.Activity.project_id == project.id)))
    if not acts:
        return {"finish": None, "duration": 0, "critical_path": []}
    deps = list(db.scalars(select(m.Dependency).where(m.Dependency.project_id == project.id)))
    start = project.start_date or min((a.planned_start for a in acts if a.planned_start), default=date.today())
    items = [{"id": a.id, "duration": a.duration_days, "parent": a.parent_id, "constraint_start": a.constraint_start} for a in acts]
    links = [{"pred": d.predecessor_id, "succ": d.successor_id, "type": d.type, "lag": d.lag_days} for d in deps]
    res = scheduling.schedule_with_summaries(items, links, start, calendar(db))
    for a in acts:
        r = res["tasks"][a.id]
        a.planned_start, a.planned_end = r["start"], r["end"]
        a.early_start, a.early_finish = r["start"], r["end"]
        a.late_start, a.late_finish = r["late_start"], r["late_end"]
        a.total_float, a.is_critical = r["total_float"], r["critical"]
    for ph in db.scalars(select(m.ProjectPhase).where(m.ProjectPhase.project_id == project.id)):
        mine = [a for a in acts if a.phase_id == ph.id]
        if mine:
            ph.start_date, ph.end_date = min(a.planned_start for a in mine), max(a.planned_end for a in mine)
            done = all((a.progress or 0) >= 100 for a in mine)
            ph.status = "completed" if done else ("in_progress" if any((a.progress or 0) > 0 for a in mine) else "not_started")
    db.flush()
    return res


def create_baseline(db: Session, project: m.Project, user: m.User | None, name: str) -> m.Baseline:
    acts = list(db.scalars(select(m.Activity).where(m.Activity.project_id == project.id)))
    for b in db.scalars(select(m.Baseline).where(m.Baseline.project_id == project.id, m.Baseline.is_current)):
        b.is_current = False
    snap = {"activities": {str(a.id): {"start": a.planned_start.isoformat() if a.planned_start else None,
                                        "end": a.planned_end.isoformat() if a.planned_end else None,
                                        "duration": a.duration_days, "cost": a.estimated_cost} for a in acts},
            "finish": max((a.planned_end for a in acts if a.planned_end), default=None),
            "budget": project.budget}
    snap["finish"] = snap["finish"].isoformat() if snap["finish"] else None
    b = m.Baseline(project_id=project.id, name=name, created_by=user.id if user else None, snapshot=snap, is_current=True)
    db.add(b)
    db.flush()
    return b


def current_baseline(db: Session, project_id: int) -> m.Baseline | None:
    return db.scalar(select(m.Baseline).where(m.Baseline.project_id == project_id, m.Baseline.is_current)
                     .order_by(m.Baseline.id.desc()))


# ---------- metrics ----------
def leaf_activities(acts: list[m.Activity]) -> list[m.Activity]:
    parents = {a.parent_id for a in acts if a.parent_id}
    return [a for a in acts if a.id not in parents]


def project_metrics(db: Session, p: m.Project, today: date | None = None, thresholds: dict | None = None) -> dict:
    today = today or date.today()
    acts = leaf_activities(list(db.scalars(select(m.Activity).where(m.Activity.project_id == p.id))))
    costs = db.execute(select(m.Cost.kind, func.coalesce(func.sum(m.Cost.amount), 0)).where(
        m.Cost.project_id == p.id).group_by(m.Cost.kind)).all()
    actual = float(dict(costs).get("actual", 0))
    committed = float(dict(costs).get("commitment", 0))
    adicts = [{"planned_start": a.planned_start, "planned_end": a.planned_end, "progress": a.progress,
               "weight": a.weight, "estimated_cost": a.estimated_cost, "duration_days": a.duration_days} for a in acts]
    data_date = min(today, p.end_date) if p.status == "completed" and p.end_date else today
    e = evm_engine.compute(p.budget or 0, adicts, actual, data_date)
    late = [a for a in acts if a.planned_end and a.planned_end < today and (a.progress or 0) < 100]
    crit_late = [a for a in late if a.is_critical]
    risks = [{"id": r.id, "score": r.score, "level": r.level, "shared_key": r.shared_key, "status": r.status}
             for r in db.scalars(select(m.Risk).where(m.Risk.project_id == p.id)) if r.status != "closed"]
    rc = risk_engine.counts(risks)
    finish = max((a.planned_end for a in acts if a.planned_end), default=p.end_date)
    slip = max(((today - a.planned_end).days for a in crit_late), default=0)
    forecast = finish + timedelta(days=slip) if finish else None
    bl = current_baseline(db, p.id)
    bfin = date.fromisoformat(bl.snapshot["finish"]) if bl and bl.snapshot.get("finish") else p.end_date
    spi, cpi = e["SPI"], e["CPI"]
    over = (p.budget or 0) > 0 and actual > p.budget
    if p.status == "completed":
        health = "green"
    elif over or (spi is not None and spi < 0.8) or (cpi is not None and cpi < 0.8) or rc["critical"] >= 2 or len(crit_late) >= 2:
        health = "red"
    elif (spi is not None and spi < 0.9) or (cpi is not None and cpi < 0.9) or rc["critical"] or rc["high"] >= 3 or late:
        health = "amber"
    else:
        health = "green"
    return {"progress": e["earned_pct"], "planned_progress": e["planned_pct"], "evm": e, "budget": p.budget or 0,
            "actual": actual, "committed": committed, "remaining": (p.budget or 0) - actual - committed,
            "late_activities": len(late), "critical_late": len(crit_late), "activities": len(acts),
            "risk_counts": rc, "open_risks": sum(rc.values()), "health": health, "over_budget": over,
            "forecast_finish": forecast.isoformat() if forecast else None,
            "baseline_finish": bfin.isoformat() if bfin else None,
            "schedule_variance_days": (forecast - bfin).days if forecast and bfin else 0,
            "delayed": p.status == "active" and (bool(late) or (spi is not None and spi < 0.9) or bool(forecast and bfin and forecast > bfin)),
            "data_date": data_date.isoformat()}


def project_card(db: Session, p: m.Project, today=None) -> dict:
    d = to_dict(p)
    d["manager_name_ar"] = p.manager.name_ar if p.manager else None
    d["manager_name_en"] = p.manager.name_en if p.manager else None
    d["metrics"] = project_metrics(db, p, today)
    return d


def visible_projects(db: Session, user: m.User) -> list[m.Project]:
    ids = security.accessible_project_ids(db, user)
    q = select(m.Project).order_by(m.Project.code)
    if ids is not None:
        if not ids:
            return []
        q = q.where(m.Project.id.in_(ids))
    return list(db.scalars(q))


# ---------- early warning ----------
def _overallocated(db: Session, today: date) -> dict:
    load: dict = {}
    for a in db.scalars(select(m.ResourceAssignment)):
        if (a.start_date is None or a.start_date <= today) and (a.end_date is None or a.end_date >= today):
            load.setdefault(a.resource_id, []).append(a)
    out: dict = {}
    for rid, assigns in load.items():
        r = db.get(m.Resource, rid)
        total = sum(a.allocation_pct or 0 for a in assigns)
        if r and total > (r.capacity_pct or 100):
            for a in assigns:
                out.setdefault(a.project_id, {})[rid] = {"id": rid, "name": r.name, "load": total}
    return {pid: list(v.values()) for pid, v in out.items()}


def snapshot(db: Session, p: m.Project, metrics: dict, over: dict) -> dict:
    g = lambda model: list(db.scalars(select(model).where(model.project_id == p.id)))
    return {
        "id": p.id, "status": p.status, "budget": metrics["budget"], "actual": metrics["actual"],
        "committed": metrics["committed"], "evm": metrics["evm"],
        "baseline_finish": date.fromisoformat(metrics["baseline_finish"]) if metrics["baseline_finish"] else None,
        "forecast_finish": date.fromisoformat(metrics["forecast_finish"]) if metrics["forecast_finish"] else None,
        "last_update": p.last_update_at.date() if p.last_update_at else None,
        "activities": [{"id": a.id, "name": a.name, "planned_end": a.planned_end, "progress": a.progress,
                        "is_critical": a.is_critical, "total_float": a.total_float} for a in leaf_activities(g(m.Activity))],
        "milestones": [{"id": x.id, "name": x.name, "target_date": x.target_date, "status": x.status} for x in g(m.Milestone)],
        "risks": [{"id": r.id, "title": r.title, "score": r.score, "status": r.status, "response_deadline": r.response_deadline,
                   "residual_score": r.residual_score} for r in g(m.Risk)],
        "issues": [{"id": i.id, "title": i.title, "status": i.status, "raised_at": i.raised_at} for i in g(m.Issue)],
        "approvals": [{"id": a.id, "title": a.title, "status": a.status, "requested_at": a.requested_at.date() if a.requested_at else None} for a in g(m.Approval)],
        "decisions": [{"id": d.id, "title": d.title, "status": d.status, "due_date": d.due_date} for d in g(m.Decision)],
        "kpis": [{"id": k.id, "name": k.name, "target": k.target, "actual": k.actual, "direction": k.direction} for k in g(m.KPI)],
        "overallocated": over.get(p.id, []),
    }


def _bump(sev: str) -> str:
    i = alert_engine.SEVERITIES.index(sev)
    return alert_engine.SEVERITIES[min(i + 1, 3)]


def run_early_warning(db: Session, project_id: int | None = None, today: date | None = None) -> dict:
    """Evaluate every rule, open new alerts, resolve cleared ones, notify and escalate."""
    from . import automation  # local import: automation also calls back into this module
    today = today or date.today()
    rules = {r.key: r for r in db.scalars(select(m.AlertRule))}
    th = {k: r.threshold for k, r in rules.items() if r.threshold is not None}
    q = select(m.Project)
    if project_id:
        q = q.where(m.Project.id == project_id)
    over = _overallocated(db, today)
    created = resolved = 0
    for p in db.scalars(q):
        findings = alert_engine.evaluate(snapshot(db, p, project_metrics(db, p, today), over), th, today)
        live = set()
        existing = {a.dedupe_key: a for a in db.scalars(select(m.Alert).where(
            m.Alert.project_id == p.id, m.Alert.status != "resolved"))}
        for f in findings:
            rule = rules.get(f["rule_key"])
            if rule is not None and not rule.enabled:
                continue
            cat, sev = alert_engine.RULES[f["rule_key"]][0], (rule.severity if rule else alert_engine.RULES[f["rule_key"]][1])
            if f["bump"]:
                sev = _bump(sev)
            key = f"{p.id}:{f['rule_key']}:{f['entity_type']}:{f['entity_id']}"
            live.add(key)
            if key in existing:
                a = existing[key]
                a.title_ar, a.title_en, a.severity = f["title_ar"], f["title_en"], sev
                continue
            a = m.Alert(project_id=p.id, rule_key=f["rule_key"], category=cat, severity=sev, title_ar=f["title_ar"],
                        title_en=f["title_en"], recommendation_ar=f["recommendation_ar"], recommendation_en=f["recommendation_en"],
                        entity_type=f["entity_type"], entity_id=f["entity_id"], dedupe_key=key)
            db.add(a)
            db.flush()
            created += 1
            roles = (rule.recipient_roles if rule else None) or ["pmo_director"]
            notify(db, roles, p, a.title_ar, a.recommendation_ar, sev, alert=a, include_manager=True)
            automation.emit(db, "alert.created", {"project_id": p.id, "rule_key": f["rule_key"], "severity": sev,
                                                 "category": cat, "title": a.title_ar, "alert_id": a.id})
        for key, a in existing.items():
            if key not in live:
                a.status, a.resolved_at = "resolved", datetime.utcnow()
                resolved += 1
        for a in db.scalars(select(m.Alert).where(m.Alert.project_id == p.id, m.Alert.status == "open", m.Alert.escalated.is_(False))):
            rule = rules.get(a.rule_key)
            if rule and rule.escalate_after_days and rule.escalate_to_role and a.created_at and \
                    (datetime.utcnow() - a.created_at).days >= rule.escalate_after_days:
                a.escalated = True
                notify(db, [rule.escalate_to_role], p, "تصعيد: " + (a.title_ar or ""), a.recommendation_ar, "critical", alert=a)
    db.flush()
    return {"created": created, "resolved": resolved}


def notify(db: Session, role_keys: list[str], project: m.Project | None, title: str, body: str | None,
           severity: str = "informational", alert: m.Alert | None = None, include_manager=False, channel="in_app") -> int:
    users = {u.id: u for u in db.scalars(select(m.User).join(m.Role).where(m.Role.key.in_(role_keys), m.User.is_active))}
    if project is not None:
        users = {i: u for i, u in users.items() if security.can_access_project(db, u, project.id)}
        if include_manager and project.manager_id:
            users[project.manager_id] = project.manager
    for u in users.values():
        db.add(m.Notification(user_id=u.id, project_id=project.id if project else None, alert_id=alert.id if alert else None,
                              title=title, body=body, severity=severity, channel=channel,
                              link=f"/projects/{project.id}" if project else None))
    return len(users)


def snapshot_risks(db: Session, today: date | None = None):
    today = today or date.today()
    if db.scalar(select(func.count()).select_from(m.RiskSnapshot).where(m.RiskSnapshot.snapshot_date == today)):
        return
    th = get_settings(db)["risk_thresholds"]
    for p in db.scalars(select(m.Project)):
        rs = [{"id": r.id, "score": r.score, "level": risk_engine.classify(r.score or 1, th), "shared_key": None}
              for r in db.scalars(select(m.Risk).where(m.Risk.project_id == p.id, m.Risk.status != "closed"))]
        c = risk_engine.counts(rs)
        db.add(m.RiskSnapshot(snapshot_date=today, project_id=p.id, **c))


# ---------- executive dashboard ----------
def dashboard(db: Session, user: m.User, today: date | None = None) -> dict:
    today = today or date.today()
    projects = visible_projects(db, user)
    cards = [project_card(db, p, today) for p in projects]
    ids = [p.id for p in projects]
    n = len(cards)
    by = lambda key: {k: sum(1 for c in cards if c[key] == k) for k in sorted({c[key] for c in cards if c[key]})}
    active = [c for c in cards if c["status"] == "active"]
    tb = sum(c["budget"] or 0 for c in cards)
    ta = sum(c["metrics"]["actual"] for c in cards)
    tc = sum(c["metrics"]["committed"] for c in cards)
    overall = (sum((c["budget"] or 0) * c["metrics"]["progress"] for c in cards) / tb) if tb else 0
    on_sched = [c for c in active if (c["metrics"]["evm"]["SPI"] or 1) >= 0.9]
    on_budget = [c for c in active if (c["metrics"]["evm"]["CPI"] or 1) >= 0.9 and not c["metrics"]["over_budget"]]
    on_target = [c for c in active if c["metrics"]["health"] == "green"]
    high_risk = [c for c in cards if c["metrics"]["risk_counts"]["critical"] > 0 and c["status"] != "completed"]
    depts = {d.id: d for d in db.scalars(select(m.Department))}
    progs = {x.id: x for x in db.scalars(select(m.Program))}
    ports = {x.id: x for x in db.scalars(select(m.Portfolio))}
    all_risks = [{"id": r.id, "score": r.score, "level": r.level, "shared_key": r.shared_key, "probability": r.probability,
                  "impact": r.impact} for r in db.scalars(select(m.Risk).where(m.Risk.project_id.in_(ids), m.Risk.status != "closed"))] if ids else []
    trend = []
    if ids:
        rows = db.execute(select(m.RiskSnapshot.snapshot_date, func.sum(m.RiskSnapshot.low), func.sum(m.RiskSnapshot.moderate),
                                 func.sum(m.RiskSnapshot.high), func.sum(m.RiskSnapshot.critical))
                          .where(m.RiskSnapshot.project_id.in_(ids)).group_by(m.RiskSnapshot.snapshot_date)
                          .order_by(m.RiskSnapshot.snapshot_date)).all()
        trend = [{"date": r[0].isoformat(), "low": r[1], "moderate": r[2], "high": r[3], "critical": r[4]} for r in rows[-12:]]
    alerts = []
    if ids:
        order = {s: i for i, s in enumerate(reversed(alert_engine.SEVERITIES))}
        rows = list(db.scalars(select(m.Alert).where(m.Alert.project_id.in_(ids), m.Alert.status != "resolved")))
        rows.sort(key=lambda a: (order.get(a.severity, 9), -a.id))
        code = {p.id: p for p in projects}
        alerts = [{**to_dict(a), "project_code": code[a.project_id].code, "project_name_ar": code[a.project_id].name_ar,
                   "project_name_en": code[a.project_id].name_en} for a in rows]

    def group(items, key, lookup):
        out = []
        for gid in sorted({c[key] for c in items if c[key]}):
            sub = [c for c in items if c[key] == gid]
            b = sum(c["budget"] or 0 for c in sub)
            out.append({"id": gid, "name_ar": lookup[gid].name_ar, "name_en": lookup[gid].name_en, "projects": len(sub),
                        "budget": b, "actual": sum(c["metrics"]["actual"] for c in sub),
                        "progress": round(sum((c["budget"] or 0) * c["metrics"]["progress"] for c in sub) / b, 1) if b else 0,
                        "planned": round(sum((c["budget"] or 0) * c["metrics"]["planned_progress"] for c in sub) / b, 1) if b else 0})
        return out

    spis = [c["metrics"]["evm"]["SPI"] for c in active if c["metrics"]["evm"]["SPI"] is not None]
    cpis = [c["metrics"]["evm"]["CPI"] for c in active if c["metrics"]["evm"]["CPI"] is not None]
    score = round(100 * (0.4 * (len(on_target) / len(active) if active else 1) + 0.3 * min(1, sum(spis) / len(spis) if spis else 1)
                         + 0.3 * min(1, sum(cpis) / len(cpis) if cpis else 1)))
    return {
        "as_of": today.isoformat(),
        "kpis": {"total": n, "active": len(active), "planned": sum(1 for c in cards if c["status"] == "planned"),
                 "delayed": sum(1 for c in cards if c["metrics"]["delayed"]), "on_hold": sum(1 for c in cards if c["status"] == "on_hold"),
                 "completed": sum(1 for c in cards if c["status"] == "completed"), "high_risk": len(high_risk),
                 "needs_intervention": sum(1 for c in cards if c["needs_intervention"]),
                 "budget": tb, "actual": ta, "committed": tc, "progress": round(overall, 1),
                 "on_target_pct": round(100 * len(on_target) / len(active)) if active else None,
                 "schedule_adherence": round(100 * len(on_sched) / len(active)) if active else None,
                 "budget_adherence": round(100 * len(on_budget) / len(active)) if active else None,
                 "portfolio_score": score},
        "by_status": by("status"), "by_priority": by("priority"),
        "by_department": group(cards, "department_id", depts),
        "by_program": group(cards, "program_id", progs), "by_portfolio": group(cards, "portfolio_id", ports),
        "by_risk": risk_engine.counts(all_risks), "heatmap": risk_engine.heatmap(all_risks, get_settings(db)["risk_thresholds"]),
        "risk_trend": trend, "alerts": alerts,
        "projects": [{"id": c["id"], "code": c["code"], "name_ar": c["name_ar"], "name_en": c["name_en"], "status": c["status"],
                      "priority": c["priority"], "needs_intervention": c["needs_intervention"],
                      "intervention_reason": c["intervention_reason"], "department_id": c["department_id"],
                      "portfolio_id": c["portfolio_id"], "program_id": c["program_id"], "end_date": c["end_date"],
                      "manager_name_ar": c["manager_name_ar"], "manager_name_en": c["manager_name_en"],
                      **{k: c["metrics"][k] for k in ("progress", "planned_progress", "health", "budget", "actual", "committed",
                                                      "delayed", "over_budget", "open_risks", "schedule_variance_days", "late_activities")},
                      "spi": c["metrics"]["evm"]["SPI"], "cpi": c["metrics"]["evm"]["CPI"],
                      "critical_risks": c["metrics"]["risk_counts"]["critical"]} for c in cards],
    }
