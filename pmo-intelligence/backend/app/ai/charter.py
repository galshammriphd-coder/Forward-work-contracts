"""Charter analysis: parsed document -> project intelligence with provenance.

Rule: nothing is invented. A value is either *extracted* (with page/section/snippet),
*calculated* from extracted values, or listed under `missing`."""
from __future__ import annotations

from datetime import date

from ..rag import facts
from ..rag.parsers import Segment
from ..rag.text import detect_language, normalize

PROFILE_FIELDS = ["name", "code", "description", "sponsor", "manager", "business_owner", "department", "priority",
                  "strategic_objective", "business_case", "scope", "out_of_scope", "budget", "start_date",
                  "end_date", "duration"]
REQUIRED = ["name", "sponsor", "manager", "scope", "budget", "start_date", "end_date"]
LIST_FIELDS = ["objectives", "deliverables", "stakeholders", "success_criteria", "kpis", "assumptions",
               "constraints", "dependencies", "requirements", "approvals"]
LIST_REQUIRED = ["objectives", "deliverables", "stakeholders", "milestones", "risks"]


def _field(value, source, tag="extracted", raw=None):
    return {"value": value, "raw": raw if raw is not None else value, "tag": tag, "source": source}


def _scale(text: str) -> int | None:
    """Map 'High / عالية / 4' to the 1-5 scale; None when the charter gives nothing."""
    n = normalize(text or "")
    for words, v in ((("very high", "مرتفع جدا", "عاليه جدا", "حرج"), 5), (("high", "مرتفع", "عالي", "عاليه", "كبير"), 4),
                     (("medium", "moderate", "متوسط", "متوسطه"), 3), (("very low", "منخفض جدا"), 1),
                     (("low", "منخفض", "منخفضه", "ضعيف"), 2)):
        if any(w in n for w in words):
            return v
    digits = [int(ch) for ch in n if ch.isdigit()]
    return digits[0] if len(digits) == 1 and 1 <= digits[0] <= 5 else None


def _col(header: list[str], names: tuple) -> int | None:
    for i, h in enumerate(header):
        if any(x in normalize(h) for x in names):
            return i
    return None


def analyze(segments: list[Segment], filename: str) -> dict:
    data = facts.extract(segments, filename)
    sc, ls = data["scalars"], data["lists"]
    lang = detect_language(" ".join(s.text for s in segments[:30]))
    profile, conflicts, missing = {}, [], []

    for f in PROFILE_FIELDS:
        vals = sc.get(f)
        if not vals:
            continue
        v = vals[0]
        if f == "budget":
            amt = facts.parse_amount(v["value"])
            if amt is None:
                continue
            profile[f] = _field(amt, v["source"], raw=v["value"])
            distinct = {facts.parse_amount(x["value"]) for x in vals} - {None}
            if len(distinct) > 1:
                conflicts.append({"field": "budget", "severity": "high",
                                  "message_ar": "الميثاق يذكر أكثر من قيمة للميزانية: " + "، ".join(x["value"] for x in vals),
                                  "message_en": "The charter states more than one budget: " + "; ".join(x["value"] for x in vals),
                                  "sources": [x["source"] for x in vals]})
        elif f in ("start_date", "end_date"):
            d = facts.parse_date(v["value"])
            if d:
                profile[f] = _field(d.isoformat(), v["source"], raw=v["value"])
        elif f == "duration":
            mo = facts.parse_duration_months(v["value"])
            if mo:
                profile[f] = _field(round(mo, 1), v["source"], raw=v["value"])
        else:
            profile[f] = _field(v["value"], v["source"])
            names = {normalize(x["value"]) for x in vals}
            if f in ("sponsor", "manager") and len(names) > 1:
                conflicts.append({"field": f, "severity": "medium",
                                  "message_ar": f"أكثر من اسم مذكور للحقل ({f}): " + "، ".join(x["value"] for x in vals),
                                  "message_en": f"More than one name given for {f}: " + "; ".join(x["value"] for x in vals),
                                  "sources": [x["source"] for x in vals]})

    s, e, dur = profile.get("start_date"), profile.get("end_date"), profile.get("duration")
    if s and e:
        ds, de = date.fromisoformat(s["value"]), date.fromisoformat(e["value"])
        months = round((de - ds).days / 30.44, 1)
        if de <= ds:
            conflicts.append({"field": "end_date", "severity": "high", "sources": [s["source"], e["source"]],
                              "message_ar": "تاريخ النهاية يسبق تاريخ البداية أو يساويه.",
                              "message_en": "End date is on or before the start date."})
        elif dur and abs(dur["value"] - months) > 1.5:
            conflicts.append({"field": "duration", "severity": "medium", "sources": [dur["source"], s["source"], e["source"]],
                              "message_ar": f"المدة المذكورة ({dur['raw']}) لا تطابق الفترة بين التاريخين ({months} شهراً).",
                              "message_en": f"Stated duration ({dur['raw']}) does not match the dates ({months} months)."})
        if not dur:
            profile["duration"] = _field(months, None, tag="calculated", raw=f"{months}")

    lists = {}
    for f in LIST_FIELDS:
        items = []
        for it in ls.get(f, []):
            row = {"text": it["text"], "tag": "extracted", "source": it["source"]}
            cells, head = it["cells"], it.get("header") or []
            if f == "stakeholders":
                ri = _col(head, ("role", "دور", "صفه")) if head else (1 if len(cells) > 1 else None)
                row["name"], row["role"] = cells[0], cells[ri] if ri is not None and ri < len(cells) else ""
                if not head and len(cells) == 1 and ("—" in cells[0] or " - " in cells[0] or ":" in cells[0]):
                    parts = [p.strip() for p in cells[0].replace("—", "-").replace(":", "-").split("-", 1)]
                    row["name"], row["role"] = parts[0], parts[1] if len(parts) > 1 else ""
            if f == "kpis":
                ti = _col(head, ("target", "مستهدف", "هدف")) if head else (1 if len(cells) > 1 else None)
                tv = cells[ti] if ti is not None and ti < len(cells) else ""
                row["name"], row["target_raw"] = cells[0], tv
                row["target"] = facts.parse_percent(tv) or facts.parse_amount(tv)
                row["unit"] = "%" if facts.parse_percent(tv) is not None else ""
            items.append(row)
        if items:
            lists[f] = items

    milestones = []
    for it in ls.get("milestones", []):
        d = next((facts.parse_date(c) for c in it["cells"][1:] if facts.parse_date(c)), None) or facts.parse_date(it["text"])
        name = it["cells"][0]
        if len(it["cells"]) == 1 and d:
            name = name.split("—")[0].split(" - ")[0].split(":")[0].strip() or name
        milestones.append({"name": name, "target_date": d.isoformat() if d else None, "tag": "extracted",
                           "source": it["source"], "date_missing": d is None})
        if d and s and e and not (date.fromisoformat(s["value"]) <= d <= date.fromisoformat(e["value"])):
            conflicts.append({"field": "milestones", "severity": "medium", "sources": [it["source"]],
                              "message_ar": f"المعلم «{name}» ({d}) يقع خارج فترة المشروع.",
                              "message_en": f"Milestone “{name}” ({d}) falls outside the project dates."})

    risks = []
    for it in ls.get("risks", []):
        cells, head = it["cells"], it.get("header") or []
        pi, ii = _col(head, ("probab", "likelihood", "احتمال")), _col(head, ("impact", "اثر", "تاثير"))
        mi = _col(head, ("mitigat", "response", "معالج", "استجاب", "تخفيف"))
        p = _scale(cells[pi]) if pi is not None and pi < len(cells) else None
        i = _scale(cells[ii]) if ii is not None and ii < len(cells) else None
        risks.append({"title": cells[0], "probability": p, "impact": i,
                      "mitigation": cells[mi] if mi is not None and mi < len(cells) else "",
                      "tag": "extracted", "source": it["source"], "rating_missing": p is None or i is None})

    for f in REQUIRED:
        if f not in profile:
            missing.append(f)
    for f in LIST_REQUIRED:
        present = {"milestones": milestones, "risks": risks}.get(f, lists.get(f))
        if not present:
            missing.append(f)
    if any(mm["date_missing"] for mm in milestones):
        missing.append("milestone_dates")
    return {"language": lang, "filename": filename, "profile": profile, "lists": lists, "milestones": milestones,
            "risks_extracted": risks, "missing": missing, "conflicts": conflicts,
            "stats": {"segments": len(segments), "pages": max((s.page for s in segments), default=0),
                      "tables": sum(1 for s in segments if s.kind == "table"),
                      "fields_found": len(profile), "items_found": sum(len(v) for v in lists.values()) + len(milestones) + len(risks)}}
