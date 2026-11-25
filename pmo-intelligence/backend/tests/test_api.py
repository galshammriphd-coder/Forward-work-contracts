"""End-to-end functional tests through the HTTP API against a seeded database."""
import io

from app.seed import DEMO_PASSWORD, sample_charter_en


def test_login_me_and_bad_password(client, auth):
    assert client.post("/api/auth/login", json={"email": "director@pmo.local", "password": "wrong"}).status_code == 401
    assert client.get("/api/dashboard").status_code == 401
    me = client.get("/api/auth/me", headers=auth()).json()
    assert me["role_key"] == "pmo_director" and "password_hash" not in me


def test_demo_data_shape(client, auth):
    h = auth()
    assert len(client.get("/api/r/portfolios", headers=h).json()) == 2
    assert len(client.get("/api/r/programs", headers=h).json()) == 3
    projects = client.get("/api/projects", headers=h).json()
    assert len(projects) == 10
    by = {p["code"]: p for p in projects}
    assert by["SEC-01"]["status"] == "completed"
    assert by["DX-04"]["metrics"]["over_budget"]                      # over budget
    assert by["DX-02"]["metrics"]["delayed"] and by["DX-02"]["metrics"]["evm"]["SPI"] < 0.9   # delayed
    assert by["DX-01"]["metrics"]["evm"]["SPI"] > 1                   # ahead
    assert by["DX-03"]["metrics"]["risk_counts"]["critical"] >= 3     # high risk
    assert by["DA-01"]["needs_intervention"]                         # needs executive intervention


def test_dashboard_kpis_are_consistent(client, auth):
    d = client.get("/api/dashboard", headers=auth()).json()
    k = d["kpis"]
    assert k["total"] == 10 == sum(d["by_status"].values())
    assert k["budget"] == sum(p["budget"] for p in d["projects"])
    assert abs(k["actual"] - sum(p["actual"] for p in d["projects"])) < 1
    assert len(d["heatmap"]) == 5 and d["alerts"] and len(d["risk_trend"]) >= 12
    assert sum(c["count"] for row in d["heatmap"] for c in row) == sum(d["by_risk"].values())


def test_create_portfolio_program_and_manual_project(client, auth):
    h = auth()
    pf = client.post("/api/r/portfolios", headers=h, json={"code": "PF-T", "name_ar": "محفظة اختبار", "name_en": "Test portfolio", "budget": 1000}).json()
    pg = client.post("/api/r/programs", headers=h, json={"code": "PG-T", "name_ar": "برنامج اختبار", "name_en": "Test programme", "portfolio_id": pf["id"]}).json()
    p = client.post("/api/projects", headers=h, json={"name_ar": "مشروع يدوي", "name_en": "Manual project", "portfolio_id": pf["id"], "program_id": pg["id"],
                                                      "budget": 500000, "start_date": "2027-01-04", "end_date": "2027-06-30"}).json()
    assert p["code"].startswith("PRJ-") and p["status"] == "planned"
    # the "project created" automation started the approval workflow
    assert any(a["project_id"] == p["id"] and a["status"] == "pending" for a in client.get("/api/approvals", headers=h).json())
    assert client.post("/api/projects", headers=h, json={"budget": 1}).status_code == 400
    assert client.patch(f"/api/r/portfolios/{pf['id']}", headers=h, json={"budget": 2000}).json()["budget"] == 2000


def test_activities_gantt_and_critical_path_recalculation(client, auth):
    h = auth()
    p = client.post("/api/projects", headers=h, json={"name_ar": "مشروع جدولة", "name_en": "Scheduling project", "start_date": "2027-01-03", "budget": 100000}).json()
    mk = lambda name, d: client.post("/api/r/activities", headers=h, json={"project_id": p["id"], "name": name, "duration_days": d, "estimated_cost": d * 1000}).json()
    a, b, c, d = mk("A", 3), mk("B", 4), mk("C", 2), mk("D", 2)
    for pred, succ in [(a, b), (a, c), (b, d), (c, d)]:
        r = client.post("/api/r/dependencies", headers=h, json={"project_id": p["id"], "predecessor_id": pred["id"], "successor_id": succ["id"], "type": "FS"})
        assert r.status_code == 200, r.text
    s = client.get(f"/api/projects/{p['id']}/schedule", headers=h).json()
    acts = {x["name"]: x for x in s["activities"]}
    assert s["critical_path"] == [a["id"], b["id"], d["id"]]
    assert acts["C"]["total_float"] == 2 and not acts["C"]["is_critical"]
    assert acts["A"]["planned_start"] == "2027-01-03" and acts["A"]["planned_end"] == "2027-01-05"  # Sun-Tue
    assert acts["B"]["planned_end"] == "2027-01-11"   # Wed, Thu, (Fri+Sat weekend), Sun, Mon
    client.post(f"/api/projects/{p['id']}/baselines", headers=h, json={"name": "BL1"})
    # change a duration -> the critical path moves
    client.patch(f"/api/r/activities/{c['id']}", headers=h, json={"duration_days": 8})
    s2 = client.get(f"/api/projects/{p['id']}/schedule", headers=h).json()
    assert s2["critical_path"] == [a["id"], c["id"], d["id"]]
    assert s2["baseline"]["finish"] == s["finish"] and s2["finish"] > s["finish"]
    # lag on a link
    dep = next(x for x in s2["dependencies"] if x["predecessor_id"] == c["id"])
    client.patch(f"/api/r/dependencies/{dep['id']}", headers=h, json={"lag_days": 3})
    assert client.get(f"/api/projects/{p['id']}/schedule", headers=h).json()["finish"] > s2["finish"]
    # a circular link is refused and nothing is saved
    r = client.post("/api/r/dependencies", headers=h, json={"project_id": p["id"], "predecessor_id": d["id"], "successor_id": a["id"]})
    assert r.status_code == 400 and "circular" in r.json()["detail"]
    assert len(client.get(f"/api/projects/{p['id']}/schedule", headers=h).json()["dependencies"]) == 4
    # progress drives status and EVM
    done = client.patch(f"/api/r/activities/{a['id']}", headers=h, json={"progress": 100}).json()
    assert done["status"] == "completed" and done["actual_end"]
    client.post("/api/r/costs", headers=h, json={"project_id": p["id"], "kind": "actual", "amount": 30000, "cost_date": "2027-01-05"})
    fin = client.get(f"/api/projects/{p['id']}/finance", headers=h).json()
    assert fin["metrics"]["actual"] == 30000 and fin["metrics"]["evm"]["AC"] == 30000 and fin["metrics"]["evm"]["BAC"] == 100000
    assert client.delete(f"/api/r/activities/{b['id']}", headers=h).status_code == 200
    assert client.delete(f"/api/projects/{p['id']}", headers=h).status_code == 200


def test_risk_create_score_heatmap_and_critical_escalation(client, auth, pid):
    h = auth()
    p = pid("DM-01")
    before = client.get(f"/api/risks/heatmap?project_id={p}", headers=h).json()
    r = client.post("/api/r/risks", headers=h, json={"project_id": p, "title": "خطر اختبار", "probability": 2, "impact": 3}).json()
    assert (r["score"], r["level"]) == (6, "moderate")
    r = client.patch(f"/api/r/risks/{r['id']}", headers=h, json={"probability": 5, "impact": 4, "residual_probability": 2, "residual_impact": 4}).json()
    assert (r["score"], r["level"], r["residual_score"]) == (20, "critical", 8)
    after = client.get(f"/api/risks/heatmap?project_id={p}", headers=h).json()
    assert after["counts"]["critical"] == before["counts"]["critical"] + 1
    alerts = client.get(f"/api/alerts?project_id={p}", headers=h).json()
    assert any(a["rule_key"] == "risk_critical" and a["entity_id"] == r["id"] for a in alerts)
    runs = client.get("/api/automation/runs", headers=h).json()
    assert any(x["trigger"] == "risk.critical" and x["status"] == "success" for x in runs)
    client.patch(f"/api/r/risks/{r['id']}", headers=h, json={"status": "closed"})
    assert not any(a["entity_id"] == r["id"] and a["rule_key"] == "risk_critical" for a in client.get(f"/api/alerts?project_id={p}", headers=h).json())


def test_shared_risk_counted_once_in_portfolio_heatmap(client, auth):
    hm = client.get("/api/risks/heatmap", headers=auth()).json()
    assert hm["unique"] < hm["total_rows"]
    assert sum(c["count"] for row in hm["grid"] for c in row) == hm["unique"]


def test_risk_thresholds_are_configurable(client, auth, pid):
    h = auth("admin")
    client.put("/api/settings/risk_thresholds", headers=h, json={"low": 4, "moderate": 9, "high": 19})
    risks = client.get(f"/api/r/risks?project_id={pid('DX-03')}", headers=h).json()
    assert all(r["level"] == "high" for r in risks if 15 <= r["score"] <= 19)
    assert client.put("/api/settings/risk_thresholds", headers=h, json={"low": 9, "moderate": 5, "high": 14}).status_code == 400
    client.put("/api/settings/risk_thresholds", headers=h, json={"low": 4, "moderate": 9, "high": 14})


def test_budget_overrun_alert_and_resolution(client, auth):
    h = auth()
    p = client.post("/api/projects", headers=h, json={"name_ar": "مشروع ميزانية", "status": "active", "budget": 1000, "start_date": "2026-01-04", "end_date": "2027-12-30"}).json()
    c = client.post("/api/r/costs", headers=h, json={"project_id": p["id"], "kind": "actual", "amount": 1500}).json()
    keys = {a["rule_key"] for a in client.get(f"/api/alerts?project_id={p['id']}", headers=h).json()}
    assert "budget_overrun" in keys
    client.delete(f"/api/r/costs/{c['id']}", headers=h)
    assert "budget_overrun" not in {a["rule_key"] for a in client.get(f"/api/alerts?project_id={p['id']}", headers=h).json()}


def test_workflow_approval_chain(client, auth):
    h = auth()
    p = client.post("/api/projects", headers=h, json={"name_ar": "مشروع سير عمل"}).json()
    mine = lambda: [a for a in client.get("/api/approvals", headers=h).json() if a["project_id"] == p["id"] and a["status"] == "pending"]
    first = mine()[0]
    assert client.post(f"/api/approvals/{first['id']}/decide", headers=auth("member"), json={"approve": True}).status_code == 403
    assert client.post(f"/api/approvals/{first['id']}/decide", headers=h, json={"approve": True, "note": "ok"}).status_code == 200
    assert client.get(f"/api/projects/{p['id']}", headers=h).json()["stage"] == "charter"
    second = mine()[0]
    assert second["step_index"] == 1 and second["approver_role"] == "portfolio_manager"
    client.post(f"/api/approvals/{second['id']}/decide", headers=auth("portfolio"), json={"approve": True})
    third = mine()[0]
    client.post(f"/api/approvals/{third['id']}/decide", headers=h, json={"approve": False, "note": "plan incomplete"})
    inst = next(i for i in client.get("/api/workflows/instances", headers=h).json() if i["project_id"] == p["id"])
    assert inst["status"] == "rejected" and len(inst["history"]) == 3
    assert client.post(f"/api/approvals/{third['id']}/decide", headers=h, json={"approve": True}).status_code == 400


def test_custom_workflow_and_automation_rule(client, auth, pid):
    h = auth()
    wf = client.post("/api/r/workflow_definitions", headers=h, json={"key": "two_step", "name_ar": "مسار مخصص", "name_en": "Custom", "steps": [
        {"name_ar": "أ", "name_en": "A", "approver_role": "pmo_director"}, {"name_ar": "ب", "name_en": "B", "approver_role": "financial_controller"}]}).json()
    assert client.post(f"/api/projects/{pid('HR-01')}/workflows", headers=h, json={"key": "two_step"}).status_code == 200
    rule = client.post("/api/r/automation_rules", headers=h, json={"name_ar": "قاعدة يدوية", "name_en": "Manual rule", "trigger_type": "manual",
                                                                   "actions": [{"type": "notify", "roles": ["pmo_director"], "message": "تنبيه يدوي"}]}).json()
    run = client.post(f"/api/automation/rules/{rule['id']}/run", headers=h, json={"project_id": pid("HR-01")}).json()
    assert run["status"] == "success" and "notified" in run["result"]
    bad = client.post("/api/r/automation_rules", headers=h, json={"name_ar": "خاطئة", "trigger_type": "manual", "actions": [{"type": "no_such_action"}]}).json()
    failed = client.post(f"/api/automation/rules/{bad['id']}/run", headers=h, json={}).json()
    assert failed["status"] == "failed" and "unknown action" in failed["error"]   # errors are recorded, not hidden
    assert any(n["title"] == "تنبيه يدوي" for n in client.get("/api/notifications", headers=h).json())
    client.delete(f"/api/r/workflow_definitions/{wf['id']}", headers=h)


def test_rbac_and_project_scope(client, auth, pid):
    member, viewer = auth("member"), auth("viewer")
    visible = {p["code"] for p in client.get("/api/projects", headers=member).json()}
    assert visible == {"DX-01", "DX-02"}                         # only projects the member belongs to
    assert client.get(f"/api/projects/{pid('DX-03')}", headers=member).status_code == 404   # hidden, not "forbidden"
    assert client.get(f"/api/r/risks?project_id={pid('DX-03')}", headers=member).status_code == 404
    assert all(r["project_id"] in {pid("DX-01"), pid("DX-02")} for r in client.get("/api/r/risks", headers=member).json())
    assert client.post("/api/r/risks", headers=member, json={"project_id": pid("DX-02"), "title": "x"}).status_code == 403
    assert client.get(f"/api/projects/{pid('DX-02')}/finance", headers=member).status_code == 403
    assert client.post("/api/projects", headers=viewer, json={"name_ar": "x"}).status_code == 403
    assert client.get("/api/audit", headers=viewer).status_code == 403
    assert client.get("/api/admin/users", headers=auth()).status_code == 403            # PMO director is not a user admin
    assert len(client.get("/api/admin/users", headers=auth("admin")).json()) == 13
    pm2 = {p["code"] for p in client.get("/api/projects", headers=auth("pm2")).json()}
    assert "DX-02" not in pm2 and "DX-03" in pm2
    assert client.get("/api/dashboard", headers=auth("pm2")).json()["kpis"]["total"] == len(pm2)


def test_user_admin_and_session_revocation(client, auth):
    h = auth("admin")
    u = client.post("/api/admin/users", headers=h, json={"email": "new@pmo.local", "name_en": "New", "role_key": "team_member", "password": "Passw0rd!x"}).json()
    tok = client.post("/api/auth/login", json={"email": "new@pmo.local", "password": "Passw0rd!x"}).json()["token"]
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"}).status_code == 200
    client.patch(f"/api/admin/users/{u['id']}", headers=h, json={"password": "An0ther!pass"})
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"}).status_code == 401   # old session revoked
    client.patch(f"/api/admin/users/{u['id']}", headers=h, json={"is_active": False})
    assert client.post("/api/auth/login", json={"email": "new@pmo.local", "password": "An0ther!pass"}).status_code == 401
    assert client.post("/api/admin/users", headers=h, json={"email": "weak@pmo.local", "role_key": "team_member", "password": "123"}).status_code == 400


def test_mfa_totp(client):
    from app import security
    tok = client.post("/api/auth/login", json={"email": "auditor@pmo.local", "password": DEMO_PASSWORD}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    secret = client.post("/api/auth/mfa/setup", headers=h).json()["secret"]
    assert client.post("/api/auth/mfa/enable", headers=h, json={"code": "000000"}).status_code == 400
    assert client.post("/api/auth/mfa/enable", headers=h, json={"code": security.totp(secret)}).json()["mfa_enabled"]
    assert client.post("/api/auth/login", json={"email": "auditor@pmo.local", "password": DEMO_PASSWORD}).json() == {"mfa_required": True}
    ok = client.post("/api/auth/login", json={"email": "auditor@pmo.local", "password": DEMO_PASSWORD, "code": security.totp(secret)})
    assert ok.status_code == 200
    client.post("/api/auth/mfa/enable", headers=h, json={"disable": True})


def test_audit_trail_records_sensitive_operations(client, auth, pid):
    h = auth()
    r = client.post("/api/r/issues", headers=h, json={"project_id": pid("DM-01"), "title": "مشكلة للتدقيق"}).json()
    client.patch(f"/api/r/issues/{r['id']}", headers=h, json={"severity": "high"})
    client.delete(f"/api/r/issues/{r['id']}", headers=h)
    log = client.get("/api/audit?limit=50", headers=auth("auditor")).json()
    actions = [a["action"] for a in log if a["entity_id"] == r["id"] and a["entity_type"] == "issues"]
    assert actions == ["issues.delete", "issues.update", "issues.create"]
    upd = next(a for a in log if a["action"] == "issues.update" and a["entity_id"] == r["id"])
    assert upd["detail"]["changes"]["severity"] == ["medium", "high"] and upd["user_email"] == "director@pmo.local"
    assert any(a["action"] == "auth.login_failed" for a in client.get("/api/audit?action=login_failed", headers=auth("auditor")).json())


def test_raci_resources_stakeholders(client, auth, pid):
    h = auth()
    p = pid("DX-02")
    raci = client.get(f"/api/projects/{p}/raci", headers=h).json()
    act = raci["activities"][-1]["id"]
    assert act in raci["needs_one_accountable"]
    client.put(f"/api/projects/{p}/raci", headers=h, json={"activity_id": act, "party": raci["parties"][0], "raci": "A"})
    assert act not in client.get(f"/api/projects/{p}/raci", headers=h).json()["needs_one_accountable"]
    assert client.put(f"/api/projects/{p}/raci", headers=h, json={"activity_id": act, "party": "x", "raci": "Z"}).status_code == 400
    util = client.get("/api/resources/utilization", headers=h).json()
    over = [r for r in util if r["conflict"]]
    assert over and all(r["load"] > r["capacity_pct"] for r in over)      # conflicts detected (e.g. 70% + 50%)
    assert any(r["free"] > 0 for r in util)
    st = client.post("/api/r/stakeholders", headers=h, json={"project_id": p, "name": "جهة اختبار", "power": 5, "interest": 1}).json()
    assert st["power"] == 5 and client.delete(f"/api/r/stakeholders/{st['id']}", headers=h).status_code == 200


def test_benefits_are_measured_not_assumed(client, auth, pid):
    h = auth()
    bens = client.get(f"/api/r/benefits?project_id={pid('SEC-01')}", headers=h).json()
    unmeasured = next(b for b in bens if b["actual"] is None)
    assert unmeasured["realization"] is None                    # completed project, benefit still not realised
    lower = next(b for b in bens if b["baseline"] == 24)
    assert lower["realization"] == 83.3 and lower["gap"] == -3   # 24 -> 9 toward a target of 6
    rep = client.post("/api/reports/build", headers=h, json={"type": "benefits", "lang": "en"}).json()
    roi = next(s for s in rep["sections"] if s["kind"] == "kpis")
    assert any(i["label"] == "ROI %" for i in roi["items"])
    strat = client.get("/api/strategy", headers=h).json()
    assert len(strat["objectives"]) == 4 and any(o["benefit_realization"] is not None for o in strat["objectives"])


def test_reports_build_and_export_all_formats(client, auth, pid):
    h = auth()
    types = client.get("/api/meta", headers=h).json()["report_types"]
    assert len(types) == 12
    for t in types:
        body = {"type": t["key"], "lang": "ar", "project_id": pid("DX-02") if t["needs_project"] else None}
        rep = client.post("/api/reports/build", headers=h, json=body)
        assert rep.status_code == 200, (t["key"], rep.text)
        assert rep.json()["sections"], t["key"]
    assert client.post("/api/reports/build", headers=h, json={"type": "project_status"}).status_code == 400
    sig = {"pdf": b"%PDF", "docx": b"PK", "xlsx": b"PK"}
    for fmt in sig:
        for lang in ("ar", "en"):
            r = client.post("/api/reports/export", headers=h, json={"type": "project_status", "project_id": pid("DX-02"), "lang": lang, "format": fmt, "comment": "تعليق"})
            assert r.status_code == 200 and r.content.startswith(sig[fmt]) and len(r.content) > 2000
    import openpyxl
    x = client.post("/api/reports/export", headers=h, json={"type": "executive_portfolio", "lang": "en", "format": "xlsx"}).content
    wb = openpyxl.load_workbook(io.BytesIO(x))
    assert "Project performance" in wb.sheetnames and wb["Project performance"].max_row >= 11


def test_copilot_respects_scope_and_labels_sources(client, auth):
    full = client.post("/api/copilot/ask", headers=auth(), json={"question": "ما أولويات التدخل؟"}).json()
    assert full["scope_projects"] >= 10 and {b["kind"] for b in full["blocks"]} == {"calculated", "analysis"}
    lim = client.post("/api/copilot/ask", headers=auth("pm2"), json={"question": "What are the top risks?"}).json()
    names = " ".join(str(r) for b in lim["blocks"] if b.get("table") for r in b["table"]["rows"])
    assert "Data Centre" not in names and lim["lang"] == "en"       # DX-02 is outside pm2's scope
    cmp_ = client.post("/api/copilot/ask", headers=auth(), json={"question": "قارن بين DX-02 و DX-04"}).json()
    assert len(cmp_["blocks"][0]["table"]["head"]) == 3
    assert client.post("/api/copilot/ask", headers=auth("member"), json={"question": "x"}).status_code == 403


def test_initiation_wizard_end_to_end(client, auth):
    h = auth("pm1")
    up = client.post("/api/initiation", headers=h, files={"file": ("charter.txt", sample_charter_en().encode(), "text/plain")})
    assert up.status_code == 200, up.text
    s = up.json()
    d, sid = s["draft"], s["id"]
    pr = d["profile"]
    assert pr["name"]["value"] == "Warehouse Management System" and pr["budget"]["value"] == 2750000
    assert pr["sponsor"]["value"] == "Khalid Al-Harbi" and pr["start_date"]["value"] == "2027-01-10"
    assert pr["budget"]["tag"] == "extracted" and pr["budget"]["source"]["section"] == "Key data" and pr["budget"]["source"]["page"] == 1
    assert pr["duration"]["tag"] == "calculated"                       # not in the charter -> computed, not invented
    assert len(d["lists"]["deliverables"]) == 4 and len(d["milestones"]) == 4 and len(d["risks_extracted"]) == 2
    assert d["risks_extracted"][0]["probability"] == 4 and d["risks_extracted"][0]["impact"] == 3
    assert d["lists"]["stakeholders"][0] | {} and d["lists"]["stakeholders"][0]["role"] == "Sponsor"
    assert "manager" not in d["missing"] and d["conflicts"] == []
    # activating before review is refused
    assert client.post(f"/api/initiation/{sid}/activate", headers=h, json={}).status_code == 400
    # approving the extracted profile fires the "generate WBS" automation
    s = client.post(f"/api/initiation/{sid}/approve", headers=h, json={"section": "profile"}).json()
    acts = s["draft"]["activities"]
    assert acts and all(a["tag"] == "ai" for a in acts) and {w["kind"] for w in s["draft"]["wbs"]} == {"phase", "deliverable", "work_package"}
    assert any(a["parent"] for a in acts)                                # subtasks exist
    s = client.post(f"/api/initiation/{sid}/generate/schedule", headers=h).json()
    sch = s["draft"]["schedule"]
    assert sch["critical_path"] and sch["finish"] <= "2027-10-31" and all(a["planned_start"] for a in s["draft"]["activities"])
    assert any(m["tag"] == "ai" for m in s["draft"]["milestones"]) and sum(m["tag"] == "extracted" for m in s["draft"]["milestones"]) == 4
    s = client.post(f"/api/initiation/{sid}/generate/risks", headers=h).json()
    risks = s["draft"]["risks"]
    assert {"project", "phase", "deliverable", "work_package", "activity"} <= {r["scope_level"] for r in risks}
    assert sum(r["tag"] == "extracted" for r in risks) == 2 and all(r["score"] == r["probability"] * r["impact"] for r in risks)
    s = client.post(f"/api/initiation/{sid}/generate/documents", headers=h).json()
    assert len(s["draft"]["documents"]) == 19
    # user edit: retagged, and editing an activity recalculates the schedule
    acts = s["draft"]["activities"]
    leaf = next(a for a in acts if a.get("is_critical") and not a.get("is_summary"))
    leaf["duration_days"] += 10
    s2 = client.patch(f"/api/initiation/{sid}", headers=h, json={"profile": {"sponsor": "Edited Sponsor"}, "activities": acts}).json()
    assert s2["draft"]["profile"]["sponsor"]["tag"] == "user" and s2["draft"]["schedule"]["finish"] > sch["finish"]
    assert "schedule" not in s2["approvals"]
    for sec in s2["sections"]:
        client.post(f"/api/initiation/{sid}/approve", headers=h, json={"section": sec})
    out = client.post(f"/api/initiation/{sid}/activate", headers=h, json={}).json()
    p = client.get(f"/api/projects/{out['project_id']}", headers=h).json()
    assert p["created_from"] == "charter" and p["budget"] == 2750000 and p["sponsor"] == "Edited Sponsor"
    assert p["counts"]["activities"] == len(acts) and p["counts"]["risks"] == len(risks) and p["counts"]["documents"] == 19
    assert p["charter"]["status"] == "approved"
    sched = client.get(f"/api/projects/{out['project_id']}/schedule", headers=h).json()
    assert sched["baseline"] and sched["critical_path"] and len(sched["dependencies"]) > 10
    # the new project's knowledge base answers from the charter, with a citation
    conv = client.post(f"/api/projects/{out['project_id']}/conversations", headers=h).json()
    msg = client.post(f"/api/conversations/{conv['id']}/messages", headers=h, json={"question": "Who is the project sponsor?"}).json()
    assert "Khalid Al-Harbi" in msg["content"] and msg["citations"][0]["document"] == "charter.txt"
    assert client.post(f"/api/initiation/{sid}/activate", headers=h, json={}).status_code == 400   # cannot activate twice


def test_initiation_flags_missing_and_conflicting_data(client, auth):
    text = "# Charter\n\nProject Name: Thin Charter\nApproved Budget: SAR 100,000\nTotal Budget: SAR 250,000\nStart Date: 2027-05-01\nEnd Date: 2027-03-01\n"
    d = client.post("/api/initiation", headers=auth("pm1"), files={"file": ("thin.txt", text.encode(), "text/plain")}).json()["draft"]
    assert {"sponsor", "manager", "scope", "deliverables", "risks"} <= set(d["missing"])
    assert {c["field"] for c in d["conflicts"]} == {"budget", "end_date"}
    assert "sponsor" not in d["profile"]                                 # nothing invented


def test_upload_validation(client, auth, pid):
    h = auth("pm1")
    p = pid("DX-02")
    bad = client.post(f"/api/projects/{p}/documents", headers=h, files={"file": ("run.exe", b"MZ..", "application/octet-stream")})
    assert bad.status_code == 422
    fake = client.post(f"/api/projects/{p}/documents", headers=h, files={"file": ("fake.pdf", b"not a pdf at all", "application/pdf")}).json()
    assert fake["processing_status"] == "failed" and "does not match" in fake["processing_error"]
    client.delete(f"/api/documents/{fake['id']}", headers=h)
    assert client.post(f"/api/projects/{p}/documents", headers=h, files={"file": ("e.txt", b"", "text/plain")}).status_code == 422
    assert client.post(f"/api/projects/{p}/documents", headers=auth("pm1"), data={"confidentiality": "3"},
                       files={"file": ("s.txt", b"secret text here", "text/plain")}).status_code == 403   # above own clearance


def test_global_search_and_meta(client, auth):
    res = client.get("/api/search?q=مركز البيانات", headers=auth()).json()
    assert any(r["type"] == "project" for r in res)
    assert all(r["project_id"] for r in client.get("/api/search?q=الخوادم", headers=auth("member")).json())
    assert client.get("/api/health").json()["status"] == "ok"
