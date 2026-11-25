"""Arabic/English text normalisation, tokenisation and a bilingual concept map
so that "الميزانية", "ميزانية", "budget" and "التكلفة المعتمدة" can find each other."""
from __future__ import annotations

import re

_TASHKEEL = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_TOKEN = re.compile(r"[A-Za-z]+(?:[-'][A-Za-z]+)*|[ء-ي]+|\d+(?:[.,]\d+)*")

def normalize(text: str) -> str:
    t = _TASHKEEL.sub("", text or "").translate(_AR_DIGITS)
    t = re.sub("[إأآٱ]", "ا", t)
    t = t.replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي")
    return t.lower()


STOP = set(normalize("""the a an of to in on for and or is are was were be been by with as at from this that these those
it its into than then there their has have had will shall may can not no do does what which who whom how when
where why per about project في من على الى إلى عن مع هذا هذه ذلك تلك التي الذي هو هي ما ماذا هل كم متى اين أين
كيف او أو ثم قد لقد كان كانت يكون تكون ان أن إن لا لم لن كل بعض بين عند حتى اي أي له لها به بها فيه فيها
المشروع مشروع متوقع متوقعه رئيسي رئيسيه مذكور مذكوره وارد وارده محدد محدده اهم جميع تم يتم
expected main key mentioned stated given please tell me list show""").split())

# canonical concept -> surface forms (already normalised)
CONCEPTS = {
    "budget": ["budget", "ميزانيه", "موازنه", "funding", "تمويل"],
    "cost": ["cost", "costs", "تكلفه", "تكاليف"],
    "risk": ["risk", "risks", "خطر", "مخاطر", "مخاطره", "threat"],
    "schedule": ["schedule", "timeline", "جدول", "زمني", "زمنيه", "مده", "duration"],
    "sponsor": ["sponsor", "راعي"],
    "manager": ["manager", "مدير"],
    "objective": ["objective", "objectives", "goal", "goals", "هدف", "اهداف"],
    "scope": ["scope", "نطاق"],
    "deliverable": ["deliverable", "deliverables", "مخرج", "مخرجات", "output", "outputs"],
    "milestone": ["milestone", "milestones", "معلم", "معالم"],
    "decision": ["decision", "decisions", "قرار", "قرارات", "resolved", "decided"],
    "delay": ["delay", "delayed", "late", "تاخر", "تاخير", "متاخر", "متاخره"],
    "assumption": ["assumption", "assumptions", "افتراض", "افتراضات"],
    "constraint": ["constraint", "constraints", "قيد", "قيود"],
    "action": ["action", "actions", "task", "tasks", "اجراء", "اجراءات", "مهمه", "مهام", "التزام", "التزامات", "commitment", "commitments"],
    "meeting": ["meeting", "minutes", "اجتماع", "محضر", "محاضر"],
    "progress": ["progress", "completion", "انجاز", "تقدم"],
    "expense": ["expense", "expenses", "spend", "spent", "actual", "مصروف", "مصروفات", "فعلي", "فعليه", "صرف"],
    "stakeholder": ["stakeholder", "stakeholders", "مصلحه", "اصحاب"],
    "change": ["change", "changes", "تغيير", "تغييرات", "تعديل"],
    "recommendation": ["recommendation", "recommendations", "توصيه", "توصيات"],
    "start": ["start", "begin", "بدايه", "بدء"],
    "end": ["end", "finish", "completion", "نهايه", "انتهاء"],
    "challenge": ["challenge", "challenges", "issue", "issues", "problem", "تحدي", "تحديات", "مشكله", "مشكلات", "مشاكل"],
    "approve": ["approved", "approval", "معتمد", "معتمده", "اعتماد"],
    "responsible": ["responsible", "owner", "مسؤول", "مالك"],
    "contract": ["contract", "vendor", "supplier", "عقد", "مورد", "متعهد"],
    "quality": ["quality", "جوده"],
    "pending": ["pending", "open", "معلق", "معلقه", "مفتوح"],
}
_SURFACE = {s: c for c, forms in CONCEPTS.items() for s in forms}


def _stem(tok: str) -> tuple[str, str]:
    """-> (prefix-stripped form, fully stemmed form)."""
    if tok[0].isascii():
        for suf in ("ing", "ed", "es", "s"):
            if len(tok) > len(suf) + 3 and tok.endswith(suf):
                return tok, tok[: -len(suf)]
        return tok, tok
    for pre in ("وال", "بال", "كال", "فال", "لل", "ال", "و", "ب", "ل"):
        if tok.startswith(pre) and len(tok) - len(pre) >= 3:
            tok = tok[len(pre):]
            break
    for suf in ("ات", "ون", "ين", "ها", "هم", "نا", "ه"):
        if tok.endswith(suf) and len(tok) - len(suf) >= 3:
            return tok, tok[: -len(suf)]
    return tok, tok


def tokens(text: str, keep_stop: bool = False) -> list[str]:
    out = []
    for raw in _TOKEN.findall(normalize(text)):
        if not keep_stop and raw in STOP:
            continue
        mid, stem = _stem(raw)
        if not keep_stop and (mid in STOP or stem in STOP):
            continue
        out.append(_SURFACE.get(raw) or _SURFACE.get(mid) or _SURFACE.get(stem) or stem)
    return out


def detect_language(text: str) -> str:
    ar = len(re.findall(r"[؀-ۿ]", text or ""))
    en = len(re.findall(r"[A-Za-z]", text or ""))
    return "ar" if ar >= en else "en"


_SENT = re.compile(r"(?<=[.!?؟。])\s+|\n+")


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT.split(text or "") if s and len(s.strip()) > 2]


INJECTION_PATTERNS = [re.compile(p, re.I) for p in [
    r"ignore (all |any )?(the )?(previous|prior|above) (instructions|rules|prompts?)",
    r"disregard (all |the )?(previous|prior|system)", r"you are now", r"system prompt",
    r"reveal .{0,40}(secret|confidential|password|other projects?)", r"act as (an? )?(admin|system|developer)",
    r"override .{0,30}(permission|polic|access)", r"do not (cite|mention) (the )?sources?",
    r"تجاهل .{0,20}(التعليمات|القواعد|الاوامر|الأوامر)", r"اكشف .{0,40}(سري|السري|كلمه|كلمة|المشاريع الاخرى|المشاريع الأخرى)",
    r"تجاوز .{0,30}(الصلاحيات|السياسات)", r"انت الان|أنت الآن", r"تعليمات النظام",
    r"(اعرض|أظهر|اظهر) .{0,30}(مشاريع اخرى|مشاريع أخرى|جميع المشاريع)",
]]


def looks_like_injection(text: str) -> bool:
    return any(p.search(text or "") for p in INJECTION_PATTERNS)
