"""Deterministic CPM scheduling engine (no AI). Pure functions over plain data.

Time is counted in working days from the project start. An activity with
duration d that starts on working-day index s occupies indices s .. s+d-1;
its "finish" f = s + d is the index of the first free day after it.

Relationship constraints (lag may be negative = lead):
  FS: ES(succ) >= EF(pred) + lag        SS: ES(succ) >= ES(pred) + lag
  FF: EF(succ) >= EF(pred) + lag        SF: EF(succ) >= ES(pred) + lag
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta


class ScheduleError(ValueError):
    pass


@dataclass
class Calendar:
    weekend: tuple = (4, 5)  # Python weekday(): Mon=0 … Fri=4, Sat=5
    holidays: frozenset = frozenset()

    def is_working(self, d: date) -> bool:
        return d.weekday() not in self.weekend and d not in self.holidays

    def next_working(self, d: date) -> date:
        while not self.is_working(d):
            d += timedelta(days=1)
        return d

    def add(self, start: date, n: int) -> date:
        """Date of the n-th working day after `start` (start itself is index 0)."""
        d = self.next_working(start)
        step = 1 if n >= 0 else -1
        for _ in range(abs(n)):
            d += timedelta(days=step)
            while not self.is_working(d):
                d += timedelta(days=step)
        return d

    def index(self, start: date, d: date) -> int:
        """Working-day index of date `d` relative to `start` (rounds forward)."""
        s = self.next_working(start)
        d = self.next_working(d)
        if d < s:
            return 0
        n, cur = 0, s
        while cur < d:
            cur += timedelta(days=1)
            if self.is_working(cur):
                n += 1
        return n

    def working_days_between(self, a: date, b: date) -> int:
        """Inclusive count of working days in [a, b]."""
        if b < a:
            return 0
        n, cur = 0, a
        while cur <= b:
            n += self.is_working(cur)
            cur += timedelta(days=1)
        return n


@dataclass
class Task:
    id: int
    duration: int
    constraint_start: date | None = None
    # outputs
    es: int = 0
    ef: int = 0
    ls: int = 0
    lf: int = 0
    total_float: int = 0
    critical: bool = False
    start: date | None = None
    end: date | None = None
    late_start: date | None = None
    late_end: date | None = None


@dataclass
class Link:
    pred: int
    succ: int
    type: str = "FS"
    lag: int = 0


@dataclass
class ScheduleResult:
    tasks: dict = field(default_factory=dict)
    duration: int = 0
    finish: date | None = None
    critical_path: list = field(default_factory=list)


def _topo(tasks: dict, links: list) -> list:
    indeg = {i: 0 for i in tasks}
    out = {i: [] for i in tasks}
    for l in links:
        indeg[l.succ] += 1
        out[l.pred].append(l.succ)
    queue = sorted(i for i, n in indeg.items() if n == 0)
    order = []
    while queue:
        n = queue.pop(0)
        order.append(n)
        for m in out[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                queue.append(m)
    if len(order) != len(tasks):
        stuck = sorted(i for i, n in indeg.items() if n > 0)
        raise ScheduleError(f"circular dependency among activities {stuck}")
    return order


def compute(tasks: list[Task], links: list[Link], project_start: date,
            calendar: Calendar | None = None) -> ScheduleResult:
    cal = calendar or Calendar()
    tmap = {t.id: t for t in tasks}
    links = [l for l in links if l.pred in tmap and l.succ in tmap]
    for l in links:
        if l.type not in ("FS", "SS", "FF", "SF"):
            raise ScheduleError(f"unknown relationship type {l.type}")
        if l.pred == l.succ:
            raise ScheduleError(f"activity {l.pred} depends on itself")
    order = _topo(tmap, links)
    preds, succs = {i: [] for i in tmap}, {i: [] for i in tmap}
    for l in links:
        preds[l.succ].append(l)
        succs[l.pred].append(l)

    # forward pass
    for i in order:
        t = tmap[i]
        d = max(0, int(t.duration or 0))
        es = cal.index(project_start, t.constraint_start) if t.constraint_start else 0
        for l in preds[i]:
            p = tmap[l.pred]
            if l.type == "FS":
                es = max(es, p.ef + l.lag)
            elif l.type == "SS":
                es = max(es, p.es + l.lag)
            elif l.type == "FF":
                es = max(es, p.ef + l.lag - d)
            else:  # SF
                es = max(es, p.es + l.lag - d)
        t.es, t.ef = max(0, es), max(0, es) + d
    total = max((t.ef for t in tmap.values()), default=0)

    # backward pass
    for i in reversed(order):
        t = tmap[i]
        d = t.ef - t.es
        lf = total
        for l in succs[i]:
            s = tmap[l.succ]
            if l.type == "FS":
                lf = min(lf, s.ls - l.lag)
            elif l.type == "SS":
                lf = min(lf, s.ls - l.lag + d)
            elif l.type == "FF":
                lf = min(lf, s.lf - l.lag)
            else:  # SF
                lf = min(lf, s.lf - l.lag + d)
        t.lf, t.ls = lf, lf - d
        t.total_float = t.ls - t.es
        t.critical = t.total_float <= 0

    for t in tmap.values():
        d = t.ef - t.es
        t.start = cal.add(project_start, t.es)
        t.end = cal.add(project_start, t.ef - 1) if d > 0 else t.start
        t.late_start = cal.add(project_start, max(0, t.ls))
        t.late_end = cal.add(project_start, max(0, t.lf - 1)) if d > 0 else t.late_start

    path = sorted((t for t in tmap.values() if t.critical), key=lambda t: (t.es, t.ef, t.id))
    return ScheduleResult(tasks=tmap, duration=total,
                          finish=cal.add(project_start, max(0, total - 1)) if tmap else None,
                          critical_path=[t.id for t in path])


def delay_impact(tasks: list[Task], links: list[Link], project_start: date, activity_id: int,
                 delay_days: int, calendar: Calendar | None = None) -> dict:
    """What happens to the project finish if one activity takes `delay_days` longer."""
    import copy
    base = compute(copy.deepcopy(tasks), links, project_start, calendar)
    changed = copy.deepcopy(tasks)
    for t in changed:
        if t.id == activity_id:
            t.duration = (t.duration or 0) + delay_days
    after = compute(changed, links, project_start, calendar)
    return {"finish_before": base.finish, "finish_after": after.finish,
            "slip_working_days": after.duration - base.duration,
            "float_before": base.tasks[activity_id].total_float}


def schedule_with_summaries(items: list[dict], links: list[dict], project_start: date,
                            calendar: Calendar | None = None) -> dict:
    """items: {id, duration, parent, constraint_start}. Activities that have children are
    summaries: they are not scheduled themselves, their dates roll up from the children.
    A link that touches a summary is applied to each of its leaf descendants."""
    children: dict = {}
    for it in items:
        if it.get("parent") is not None:
            children.setdefault(it["parent"], []).append(it["id"])

    def leaves(i):
        return [x for c in children[i] for x in leaves(c)] if i in children else [i]

    tasks = [Task(it["id"], int(it.get("duration") or 0), it.get("constraint_start"))
             for it in items if it["id"] not in children]
    ids = {it["id"] for it in items}
    seen, expanded = set(), []
    for l in links:
        if l["pred"] not in ids or l["succ"] not in ids:
            continue
        for p in leaves(l["pred"]):
            for s in leaves(l["succ"]):
                if p != s and (p, s) not in seen:
                    seen.add((p, s))
                    expanded.append(Link(p, s, l.get("type") or "FS", int(l.get("lag") or 0)))
    res = compute(tasks, expanded, project_start, calendar)
    out = {t.id: {"start": t.start, "end": t.end, "late_start": t.late_start, "late_end": t.late_end,
                  "total_float": t.total_float, "critical": t.critical, "summary": False}
           for t in res.tasks.values()}

    def roll(i):
        if i in out:
            return out[i]
        kids = [roll(c) for c in children[i]]
        out[i] = {"start": min(k["start"] for k in kids), "end": max(k["end"] for k in kids),
                  "late_start": min(k["late_start"] for k in kids), "late_end": max(k["late_end"] for k in kids),
                  "total_float": min(k["total_float"] for k in kids), "critical": any(k["critical"] for k in kids),
                  "summary": True}
        return out[i]

    for i in children:
        if i in ids:
            roll(i)
    return {"tasks": out, "finish": res.finish, "duration": res.duration, "critical_path": res.critical_path}
