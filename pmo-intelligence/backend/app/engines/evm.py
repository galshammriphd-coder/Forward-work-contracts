"""Earned Value Management — plain arithmetic, fully testable, no AI."""
from __future__ import annotations

from datetime import date

FORMULAS = {
    "PV": "BAC × Σ(wᵢ × planned%ᵢ at data date)",
    "EV": "BAC × Σ(wᵢ × actual progress%ᵢ)",
    "AC": "Σ actual costs recorded up to data date",
    "SV": "EV − PV", "CV": "EV − AC",
    "SPI": "EV ÷ PV", "CPI": "EV ÷ AC",
    "EAC": "BAC ÷ CPI", "ETC": "EAC − AC", "VAC": "BAC − EAC",
}


def planned_fraction(start: date | None, end: date | None, on: date) -> float:
    """Linear time-phased plan between planned start and end (inclusive)."""
    if not start or not end:
        return 0.0
    if on < start:
        return 0.0
    if on >= end:
        return 1.0
    span = (end - start).days + 1
    return max(0.0, min(1.0, ((on - start).days + 1) / span))


def weights(activities: list[dict]) -> list[float]:
    """Explicit weight wins; else cost share; else duration share; else equal."""
    for key in ("weight", "estimated_cost", "duration_days"):
        vals = [max(0.0, float(a.get(key) or 0)) for a in activities]
        if sum(vals) > 0:
            s = sum(vals)
            return [v / s for v in vals]
    n = len(activities)
    return [1 / n] * n if n else []


def compute(bac: float, activities: list[dict], actual_cost: float, data_date: date) -> dict:
    """activities: dicts with planned_start, planned_end, progress (0-100) and
    optionally weight / estimated_cost / duration_days."""
    bac = float(bac or 0)
    w = weights(activities)
    planned_pct = sum(wi * planned_fraction(a.get("planned_start"), a.get("planned_end"), data_date)
                      for wi, a in zip(w, activities))
    earned_pct = sum(wi * max(0.0, min(100.0, float(a.get("progress") or 0))) / 100
                     for wi, a in zip(w, activities))
    pv, ev, ac = bac * planned_pct, bac * earned_pct, float(actual_cost or 0)
    spi = ev / pv if pv > 0 else None
    cpi = ev / ac if ac > 0 else None
    eac = bac / cpi if cpi and cpi > 0 else (bac if ac == 0 else None)
    etc = eac - ac if eac is not None else None
    vac = bac - eac if eac is not None else None
    r = lambda v, n=2: None if v is None else round(v, n)
    return {"BAC": r(bac), "PV": r(pv), "EV": r(ev), "AC": r(ac), "SV": r(ev - pv), "CV": r(ev - ac),
            "SPI": r(spi, 3), "CPI": r(cpi, 3), "EAC": r(eac), "ETC": r(etc), "VAC": r(vac),
            "planned_pct": round(planned_pct * 100, 1), "earned_pct": round(earned_pct * 100, 1),
            "data_date": data_date.isoformat(), "formulas": FORMULAS,
            "inputs": {"activities": len(activities), "weighting": _weight_basis(activities)}}


def _weight_basis(activities):
    for key in ("weight", "estimated_cost", "duration_days"):
        if sum(float(a.get(key) or 0) for a in activities) > 0:
            return key
    return "equal"


def s_curve(bac: float, activities: list[dict], costs: list[tuple], start: date, end: date,
            data_date: date, points: int = 12) -> list[dict]:
    """Planned value across the whole plan; actual cost up to the data date."""
    if not start or not end or end <= start:
        return []
    w = weights(activities)
    out = []
    span = (end - start).days
    for i in range(points + 1):
        d = date.fromordinal(start.toordinal() + round(span * i / points))
        pv = bac * sum(wi * planned_fraction(a.get("planned_start"), a.get("planned_end"), d)
                       for wi, a in zip(w, activities))
        row = {"date": d.isoformat(), "PV": round(pv, 2)}
        if d <= data_date:
            row["AC"] = round(sum(amt for cd, amt in costs if cd and cd <= d), 2)
        out.append(row)
    return out
