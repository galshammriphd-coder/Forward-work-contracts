"""Calculation engines: pure functions with hand-checked expected values."""
from datetime import date

import pytest

from app.engines import alerts, evm, risk, scheduling as s

MON_FRI = s.Calendar(weekend=(5, 6))
START = date(2026, 1, 5)  # a Monday


def run(tasks, links):
    return s.compute([s.Task(i, d) for i, d in tasks], [s.Link(*l) for l in links], START, MON_FRI)


def test_critical_path_textbook_network():
    # A(3) -> B(4) -> D(2);  A -> C(2) -> D.  Critical path A-B-D = 9 days, C has 2 days of float.
    r = run([(1, 3), (2, 4), (3, 2), (4, 2)], [(1, 2), (1, 3), (2, 4), (3, 4)])
    assert r.duration == 9
    assert r.critical_path == [1, 2, 4]
    assert r.tasks[3].total_float == 2 and not r.tasks[3].critical
    assert (r.tasks[2].es, r.tasks[2].ef) == (3, 7)
    assert (r.tasks[3].ls, r.tasks[3].lf) == (5, 7)


def test_dates_skip_weekends_and_holidays():
    r = run([(1, 5), (2, 1)], [(1, 2)])
    assert r.tasks[1].start == date(2026, 1, 5) and r.tasks[1].end == date(2026, 1, 9)  # Mon-Fri
    assert r.tasks[2].start == date(2026, 1, 12)  # next Monday
    cal = s.Calendar(weekend=(5, 6), holidays=frozenset({date(2026, 1, 6)}))
    r2 = s.compute([s.Task(1, 2)], [], START, cal)
    assert r2.tasks[1].end == date(2026, 1, 7)  # Tuesday is a holiday
    saudi = s.Calendar(weekend=(4, 5))
    assert saudi.next_working(date(2026, 1, 9)) == date(2026, 1, 11)  # Fri -> Sun


@pytest.mark.parametrize("typ,lag,es,ef", [
    ("FS", 0, 4, 6), ("FS", 2, 6, 8), ("FS", -1, 3, 5),  # lag and lead
    ("SS", 1, 1, 3), ("FF", 0, 2, 4), ("FF", 3, 5, 7), ("SF", 5, 3, 5)])
def test_relationship_types_with_lead_and_lag(typ, lag, es, ef):
    r = run([(1, 4), (2, 2)], [(1, 2, typ, lag)])
    assert (r.tasks[2].es, r.tasks[2].ef) == (es, ef)


def test_recalculates_when_duration_or_dependency_changes():
    base = run([(1, 3), (2, 4), (3, 2), (4, 2)], [(1, 2), (1, 3), (2, 4), (3, 4)])
    longer = run([(1, 3), (2, 4), (3, 7), (4, 2)], [(1, 2), (1, 3), (2, 4), (3, 4)])
    assert longer.duration == base.duration + 3 and longer.critical_path == [1, 3, 4]
    unlinked = run([(1, 3), (2, 4), (3, 2), (4, 2)], [(1, 2), (1, 3), (3, 4)])
    assert unlinked.duration == 7


def test_cycle_and_self_link_are_rejected():
    with pytest.raises(s.ScheduleError, match="circular"):
        run([(1, 1), (2, 1)], [(1, 2), (2, 1)])
    with pytest.raises(s.ScheduleError):
        run([(1, 1)], [(1, 1)])


def test_milestone_and_constraint():
    r = s.compute([s.Task(1, 0), s.Task(2, 3, constraint_start=date(2026, 1, 14))], [], START, MON_FRI)
    assert r.tasks[1].start == r.tasks[1].end
    assert r.tasks[2].start == date(2026, 1, 14)


def test_summary_rollup_and_delay_impact():
    items = [{"id": "P", "duration": 99, "parent": None}, {"id": "a", "duration": 2, "parent": "P"}, {"id": "b", "duration": 3, "parent": "P"}, {"id": "c", "duration": 1, "parent": None}]
    r = s.schedule_with_summaries(items, [{"pred": "a", "succ": "b"}, {"pred": "P", "succ": "c"}], START, MON_FRI)
    assert r["duration"] == 6 and r["tasks"]["P"]["summary"]
    assert r["tasks"]["P"]["start"] == date(2026, 1, 5) and r["tasks"]["P"]["end"] == date(2026, 1, 9)
    tasks = [s.Task(1, 3), s.Task(2, 4), s.Task(3, 2), s.Task(4, 2)]
    links = [s.Link(1, 2), s.Link(1, 3), s.Link(2, 4), s.Link(3, 4)]
    assert s.delay_impact(tasks, links, START, 3, 1, MON_FRI)["slip_working_days"] == 0  # inside float
    assert s.delay_impact(tasks, links, START, 3, 5, MON_FRI)["slip_working_days"] == 3
    assert s.delay_impact(tasks, links, START, 2, 2, MON_FRI)["slip_working_days"] == 2  # critical


def test_evm_worked_example():
    acts = [{"planned_start": date(2026, 1, 1), "planned_end": date(2026, 1, 10), "progress": 100, "estimated_cost": 400},
            {"planned_start": date(2026, 1, 11), "planned_end": date(2026, 1, 20), "progress": 25, "estimated_cost": 600}]
    e = evm.compute(1000, acts, 700, date(2026, 1, 15))
    assert e["PV"] == 700 and e["EV"] == 550 and e["AC"] == 700
    assert e["SV"] == -150 and e["CV"] == -150
    assert e["SPI"] == pytest.approx(0.786, abs=1e-3) and e["CPI"] == pytest.approx(0.786, abs=1e-3)
    assert e["EAC"] == pytest.approx(1272.73, abs=0.01)
    assert e["ETC"] == pytest.approx(572.73, abs=0.01) and e["VAC"] == pytest.approx(-272.73, abs=0.01)
    assert set(e["formulas"]) >= {"PV", "EV", "AC", "SV", "CV", "SPI", "CPI", "EAC", "ETC", "VAC"}


def test_evm_edge_cases():
    e = evm.compute(1000, [], 0, date(2026, 1, 1))
    assert e["SPI"] is None and e["CPI"] is None and e["EAC"] == 1000
    assert evm.planned_fraction(date(2026, 1, 1), date(2026, 1, 10), date(2025, 12, 1)) == 0
    assert evm.planned_fraction(date(2026, 1, 1), date(2026, 1, 10), date(2026, 2, 1)) == 1
    assert evm.weights([{"duration_days": 1}, {"duration_days": 3}]) == [0.25, 0.75]


@pytest.mark.parametrize("p,i,score,level", [(1, 4, 4, "low"), (1, 5, 5, "moderate"), (3, 3, 9, "moderate"), (2, 5, 10, "high"),
                                              (2, 7, 10, "high"), (3, 5, 15, "critical"), (5, 5, 25, "critical"), (0, 0, 1, "low")])
def test_risk_score_and_default_bands(p, i, score, level):
    assert risk.assess(p, i) == {"score": score, "level": level}


def test_risk_thresholds_customisable_and_shared_counted_once():
    assert risk.classify(12, {"low": 5, "moderate": 12, "high": 19}) == "moderate"
    rs = [{"id": 1, "probability": 5, "impact": 4, "score": 20, "level": "critical", "shared_key": "v"},
          {"id": 2, "probability": 4, "impact": 4, "score": 16, "level": "critical", "shared_key": "v"},
          {"id": 3, "probability": 2, "impact": 2, "score": 4, "level": "low", "shared_key": None}]
    assert risk.counts(rs) == {"low": 1, "moderate": 0, "high": 0, "critical": 1}
    grid = risk.heatmap(rs)
    assert len(grid) == 5 and all(len(r) == 5 for r in grid)
    assert sum(c["count"] for row in grid for c in row) == 2
    assert grid[0][3]["count"] == 1 and grid[0][3]["level"] == "critical"  # P5 x I4


def test_early_warning_rules():
    today = date(2026, 6, 1)
    snap = {"id": 1, "status": "active", "budget": 100, "actual": 120, "committed": 0,
            "evm": {"SPI": 0.7, "CPI": 0.85, "planned_pct": 60, "earned_pct": 40, "EAC": 130},
            "baseline_finish": date(2026, 9, 1), "forecast_finish": date(2026, 9, 20), "last_update": date(2026, 5, 1),
            "activities": [{"id": 1, "name": "A", "planned_end": date(2026, 5, 20), "progress": 50, "is_critical": True, "total_float": 0},
                           {"id": 2, "name": "B", "planned_end": date(2026, 5, 25), "progress": 100, "is_critical": False, "total_float": 3}],
            "milestones": [{"id": 1, "name": "M", "target_date": date(2026, 5, 15), "status": "pending"}],
            "risks": [{"id": 1, "title": "R", "score": 20, "status": "open", "response_deadline": date(2026, 5, 1), "residual_score": 12}],
            "issues": [{"id": 1, "title": "I", "status": "open", "raised_at": date(2026, 4, 1)}],
            "approvals": [{"id": 1, "title": "Ap", "status": "pending", "requested_at": date(2026, 5, 1)}],
            "decisions": [{"id": 1, "title": "D", "status": "pending", "due_date": date(2026, 5, 1)}],
            "kpis": [{"id": 1, "name": "K", "target": 100, "actual": 50, "direction": "up"}], "overallocated": []}
    keys = {f["rule_key"] for f in alerts.evaluate(snap, today=today)}
    assert keys == {"critical_activity_late", "milestone_late", "finish_slip", "progress_rate_low", "spi_low", "cpi_low", "budget_overrun",
                    "kpi_missed", "risk_critical", "risk_response_overdue", "residual_high", "approval_stalled", "no_updates",
                    "issue_open_long", "decision_pending"}
    assert alerts.evaluate({**snap, "status": "completed"}, today=today) == []
    relaxed = {f["rule_key"] for f in alerts.evaluate(snap, {"spi_low": 0.5, "risk_critical": 25}, today)}  # thresholds are configurable
    assert "spi_low" not in relaxed and "risk_critical" not in relaxed
