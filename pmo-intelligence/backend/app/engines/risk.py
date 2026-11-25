"""Risk scoring. Score = Probability × Impact on a 1-5 scale; thresholds are settings."""
from __future__ import annotations

DEFAULT_THRESHOLDS = {"low": 4, "moderate": 9, "high": 14}
LEVELS = ["low", "moderate", "high", "critical"]


def clamp(v) -> int:
    return max(1, min(5, int(v or 1)))


def score(probability, impact) -> int:
    return clamp(probability) * clamp(impact)


def classify(s: int, thresholds: dict | None = None) -> str:
    t = thresholds or DEFAULT_THRESHOLDS
    if s <= t["low"]:
        return "low"
    if s <= t["moderate"]:
        return "moderate"
    if s <= t["high"]:
        return "high"
    return "critical"


def assess(probability, impact, thresholds=None) -> dict:
    s = score(probability, impact)
    return {"score": s, "level": classify(s, thresholds)}


def unique(risks: list[dict]) -> list[dict]:
    """A risk shared by several projects (same shared_key) or linked to several
    activities must count once in aggregated indicators. Keeps the worst instance."""
    best: dict = {}
    for r in risks:
        key = ("k", r["shared_key"]) if r.get("shared_key") else ("id", r["id"])
        if key not in best or (r.get("score") or 0) > (best[key].get("score") or 0):
            best[key] = r
    return list(best.values())


def heatmap(risks: list[dict], thresholds=None) -> list[list[dict]]:
    """5×5 matrix; rows = probability 5→1, columns = impact 1→5."""
    risks = unique(risks)
    grid = []
    for p in range(5, 0, -1):
        row = []
        for i in range(1, 6):
            cell = [r for r in risks if clamp(r["probability"]) == p and clamp(r["impact"]) == i]
            row.append({"probability": p, "impact": i, "score": p * i,
                        "level": classify(p * i, thresholds), "count": len(cell),
                        "risk_ids": [r["id"] for r in cell]})
        grid.append(row)
    return grid


def counts(risks: list[dict]) -> dict:
    out = {l: 0 for l in LEVELS}
    for r in unique(risks):
        out[r.get("level") or "low"] += 1
    return out
