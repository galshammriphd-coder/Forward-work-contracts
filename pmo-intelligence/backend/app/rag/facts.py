"""Rule-based fact extraction from parsed documents (Arabic + English).
Used by charter analysis and by document comparison. Every fact keeps its source."""
from __future__ import annotations

import re
from datetime import date

from .parsers import Segment
from .text import normalize

SCALAR = {
    "name": ["اسم المشروع", "عنوان المشروع", "project name", "project title"],
    "code": ["رمز المشروع", "رقم المشروع", "project id", "project code"],
    "description": ["وصف المشروع", "نبذه عن المشروع", "الوصف", "project description", "description", "overview"],
    "sponsor": ["راعي المشروع", "الراعي", "project sponsor", "sponsor", "executive sponsor"],
    "manager": ["مدير المشروع", "project manager"],
    "business_owner": ["مالك الاعمال", "مالك المشروع", "الجهه المالكه", "الجهه المستفيده", "business owner", "project owner"],
    "strategic_objective": ["الهدف الاستراتيجي", "الارتباط الاستراتيجي", "strategic objective", "strategic alignment"],
    "business_case": ["مبررات المشروع", "دراسه الجدوي", "المبررات", "مبرر المشروع", "business case", "justification", "project justification"],
    "scope": ["نطاق المشروع", "نطاق العمل", "النطاق", "project scope", "scope", "in scope", "scope of work"],
    "out_of_scope": ["خارج النطاق", "خارج نطاق المشروع", "الاستثناءات", "out of scope", "exclusions"],
    "budget": ["الميزانيه المعتمده", "ميزانيه المشروع", "الميزانيه", "الميزانيه التقديريه", "اجمالي الميزانيه", "التكلفه الاجماليه", "الموازنه",
               "approved budget", "project budget", "budget", "total budget", "estimated budget", "total cost"],
    "start_date": ["تاريخ البدايه", "تاريخ البدء", "تاريخ بدء المشروع", "بدايه المشروع", "start date", "project start", "planned start"],
    "end_date": ["تاريخ النهايه", "تاريخ الانتهاء", "تاريخ انتهاء المشروع", "نهايه المشروع", "end date", "finish date", "project end", "planned finish", "completion date"],
    "duration": ["مده المشروع", "المده الزمنيه", "المده", "project duration", "duration"],
    "department": ["الاداره", "الاداره المنفذه", "القطاع", "department", "division"],
    "priority": ["الاولويه", "priority"],
    "progress": ["نسبه الانجاز", "نسبه الانجاز الكليه", "نسبه الانجاز الفعليه", "الانجاز الفعلي", "overall progress", "progress", "percent complete", "actual progress"],
    "actual_cost": ["المصروفات الفعليه", "المصروف الفعلي", "التكلفه الفعليه", "اجمالي المصروفات", "actual cost", "actual spend", "actual expenditure", "spent to date"],
    "doc_date": ["تاريخ التقرير", "تاريخ الوثيقه", "تاريخ الاصدار", "تاريخ الاجتماع", "التاريخ", "report date", "document date", "issue date", "meeting date", "date"],
}
LIST = {
    "objectives": ["اهداف المشروع", "الاهداف", "project objectives", "objectives", "goals"],
    "deliverables": ["المخرجات", "مخرجات المشروع", "المخرجات الرئيسيه", "deliverables", "key deliverables", "project deliverables"],
    "stakeholders": ["اصحاب المصلحه", "الاطراف المعنيه", "stakeholders", "key stakeholders"],
    "success_criteria": ["معايير النجاح", "success criteria"],
    "kpis": ["مؤشرات الاداء", "موشرات الاداء", "مؤشرات الاداء الرئيسيه", "kpis", "key performance indicators", "performance indicators"],
    "assumptions": ["الافتراضات", "assumptions"],
    "constraints": ["القيود", "المحددات", "constraints"],
    "dependencies": ["الاعتماديات", "الاعتمادات والمتطلبات", "dependencies"],
    "risks": ["المخاطر", "المخاطر الاوليه", "المخاطر الرئيسيه", "initial risks", "risks", "key risks", "high-level risks"],
    "milestones": ["المعالم الرئيسيه", "المعالم", "الجدول الزمني والمعالم", "milestones", "key milestones", "major milestones"],
    "requirements": ["المتطلبات", "متطلبات المشروع", "requirements", "high-level requirements"],
    "approvals": ["الاعتمادات", "التواقيع", "approvals", "sign-off", "signatures"],
    "decisions": ["القرارات", "قرارات الاجتماع", "decisions"],
    "actions": ["الاجراءات", "المهام", "بنود العمل", "الالتزامات", "action items", "actions"],
    "challenges": ["التحديات", "المشكلات", "challenges", "issues"],
}
_SCALAR_N = {k: [normalize(v) for v in vs] for k, vs in SCALAR.items()}
_LIST_N = {k: [normalize(v) for v in vs] for k, vs in LIST.items()}
_CLEAN = re.compile(r"^[\s\d.\-–—•*#()\[\]:：]+|[\s:：*]+$")


def _key(label: str, table: dict) -> str | None:
    n = _CLEAN.sub("", normalize(label))
    n = re.sub(r"\s+", " ", n)
    best = None
    for k, variants in table.items():
        for v in variants:
            if n == v or n == "ال" + v:
                return k
            if (n.startswith(v + " ") or n.endswith(" " + v)) and len(n) <= len(v) + 14:
                if best is None or len(v) > best[1]:
                    best = (k, len(v))
    return best[0] if best else None


_MULT = {"مليار": 1e9, "billion": 1e9, "bn": 1e9, "مليون": 1e6, "ملايين": 1e6, "million": 1e6, "m": 1e6, "mn": 1e6,
         "الف": 1e3, "آلاف": 1e3, "الاف": 1e3, "thousand": 1e3, "k": 1e3}
_AMOUNT = re.compile(r"(\d{1,3}(?:[,٬]\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*(مليار|مليون|ملايين|ألف|الف|آلاف|الاف|billion|million|thousand|bn|mn|m|k)?\b", re.I)


def parse_amount(text: str) -> float | None:
    t = normalize(text).replace("٬", ",")
    best = None
    for mt in _AMOUNT.finditer(t):
        num = float(mt.group(1).replace(",", ""))
        unit = (mt.group(2) or "").lower()
        val = num * _MULT.get(normalize(unit), 1)
        if re.fullmatch(r"(19|20)\d\d", mt.group(1)) and not unit:
            continue
        if best is None or val > best:
            best = val
    return best


_MONTHS = {"يناير": 1, "فبراير": 2, "مارس": 3, "ابريل": 4, "مايو": 5, "يونيو": 6, "يوليو": 7, "اغسطس": 8, "سبتمبر": 9,
           "اكتوبر": 10, "نوفمبر": 11, "ديسمبر": 12, "january": 1, "february": 2, "march": 3, "april": 4, "may": 5,
           "june": 6, "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
           "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}


def parse_date(text: str) -> date | None:
    t = normalize(text)
    try:
        mt = re.search(r"(20\d\d)[-/.](\d{1,2})[-/.](\d{1,2})", t)
        if mt:
            return date(int(mt.group(1)), int(mt.group(2)), int(mt.group(3)))
        mt = re.search(r"(\d{1,2})[-/.](\d{1,2})[-/.](20\d\d)", t)
        if mt:
            return date(int(mt.group(3)), int(mt.group(2)), int(mt.group(1)))
        mt = re.search(r"(\d{1,2})\s+([a-zء-ي]+)\s+(20\d\d)", t)
        if mt and mt.group(2) in _MONTHS:
            return date(int(mt.group(3)), _MONTHS[mt.group(2)], int(mt.group(1)))
        mt = re.search(r"([a-z]+)\s+(\d{1,2}),?\s+(20\d\d)", t)
        if mt and mt.group(1) in _MONTHS:
            return date(int(mt.group(3)), _MONTHS[mt.group(1)], int(mt.group(2)))
        mt = re.search(r"([a-zء-ي]+)\s+(20\d\d)", t)
        if mt and mt.group(1) in _MONTHS:
            return date(int(mt.group(2)), _MONTHS[mt.group(1)], 1)
    except ValueError:
        return None
    return None


def parse_duration_months(text: str) -> float | None:
    t = normalize(text)
    mt = re.search(r"(\d+(?:\.\d+)?)\s*(شهر|اشهر|شهرا|month|months|سنه|سنوات|year|years|اسبوع|اسابيع|week|weeks|يوم|ايام|day|days)", t)
    if not mt:
        return None
    n, u = float(mt.group(1)), mt.group(2)
    if u in ("سنه", "سنوات", "year", "years"):
        return n * 12
    if u in ("اسبوع", "اسابيع", "week", "weeks"):
        return n / 4.345
    if u in ("يوم", "ايام", "day", "days"):
        return n / 30.44
    return n


def parse_percent(text: str) -> float | None:
    mt = re.search(r"(\d+(?:\.\d+)?)\s*[%٪]", normalize(text))
    return float(mt.group(1)) if mt else None


def _src(seg: Segment, snippet: str, doc: str = "") -> dict:
    return {"document": doc, "page": seg.page, "section": seg.section, "snippet": snippet.strip()[:300]}


_BULLET = re.compile(r"^\s*(?:[-–—•*▪◦●]|\d+[.)\-]|[٠-٩]+[.)\-]|[a-zأ-ي][.)])\s+")


def extract(segments: list[Segment], doc_name: str = "") -> dict:
    """-> {"scalars": {field: [{value, source}]}, "lists": {field: [{text, cells, source}]}}"""
    scalars: dict = {}
    lists: dict = {}

    def put(field, value, seg, snippet):
        value = value.strip(" :：|-–")
        if value:
            scalars.setdefault(field, []).append({"value": value, "source": _src(seg, snippet, doc_name)})

    for seg in segments:
        sec_list = _key(seg.section, _LIST_N) if seg.section else None
        sec_scalar = _key(seg.section, _SCALAR_N) if seg.section and not sec_list else None
        lines = seg.text.split("\n")
        if seg.kind == "table":
            body = lines
            header = [c.strip() for c in lines[0].split("|")] if lines else []
            if sec_list:
                looks_header = len(lines) > 1 and not any(ch.isdigit() for ch in lines[0]) and len(header) > 1
                for ln in (lines[1:] if looks_header else lines):
                    cells = [c.strip() for c in ln.split("|")]
                    if cells and cells[0]:
                        lists.setdefault(sec_list, []).append({
                            "text": cells[0], "cells": cells, "header": header if looks_header else [],
                            "source": _src(seg, ln, doc_name)})
                continue
            for ln in body:
                cells = [c.strip() for c in ln.split("|")]
                if len(cells) >= 2:
                    k = _key(cells[0], _SCALAR_N)
                    if k:
                        put(k, " ".join(c for c in cells[1:] if c), seg, ln)
            continue
        consumed = []
        for ln in lines:
            mt = re.match(r"^(.{2,60}?)\s*[:：]\s*(.+)$", ln)
            k = _key(mt.group(1), _SCALAR_N) if mt else None
            if k and (k != "doc_date" or parse_date(mt.group(2))):
                put(k, mt.group(2), seg, ln)
            else:
                consumed.append(ln)
        if sec_list:
            for ln in consumed:
                item = _BULLET.sub("", ln).strip()
                if len(item) > 2:
                    lists.setdefault(sec_list, []).append({"text": item, "cells": [item], "header": [],
                                                           "source": _src(seg, ln, doc_name)})
        elif sec_scalar and consumed:
            body = " ".join(_BULLET.sub("", l).strip() for l in consumed)
            put(sec_scalar, body, seg, body)
    return {"scalars": scalars, "lists": lists}
