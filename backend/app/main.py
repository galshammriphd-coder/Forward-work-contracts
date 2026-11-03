"""Research Analytics AI — REST API (FastAPI)."""
from __future__ import annotations

import copy
import io
import json
import re
from datetime import datetime, timezone

import numpy as np
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from statsmodels.stats.multitest import multipletests

from . import assistant
from .config import ALLOW_REGISTRATION, CORS_ORIGINS, FRONTEND_DIST, MAX_UPLOAD_MB
from .db import Analysis, AuditLog, AuthSession, Dataset, Project, SessionLocal, User, init_db, now
from .demo.synthetic import SYNTHETIC_NOTICE_AR, SYNTHETIC_NOTICE_EN, demo_csv_bytes
from .engine.dictionary import interpretation_bands, validate_dictionary
from .engine.ingest import parse_csv
from .engine.interpret import hypothesis_decision
from .engine.pipeline import OP_TYPES, new_op
from .engine.quality import propose_operations
from .engine.recommender import PURPOSES, recommend
from .engine.runner import REGISTRY, make_ctx, run_analysis
from .engine.utils import AnalysisError, to_jsonable
from .reports.builder import REPORT_TYPES, build_report
from .reports.render import render_csv_zip, render_docx, render_html, render_pdf, render_xlsx
from .security import hash_password, new_token, token_hash, verify_password
from .services import (analysis_frame, audit, current_dataset, data_fingerprint, frames, kpis, lifecycle, new_dictionary,
                       project_quality, set_json)
from .storage import delete_project_files, save_original

app = FastAPI(title="Research Analytics AI", version="1.0.0",
              description="AI-powered survey analytics & scientific research platform. All statistics are computed with SciPy/statsmodels/pingouin/factor_analyzer/semopy.")
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
init_db()


@app.exception_handler(AnalysisError)
async def _analysis_error(_: Request, exc: AnalysisError):
    return JSONResponse(status_code=422, content={"detail": exc.en, "detail_ar": exc.ar})


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def current_user(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> User:
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(401, "Not authenticated")
    s = db.get(AuthSession, token_hash(token))
    if not s or s.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(401, "Session expired")
    user = db.get(User, s.user_id)
    if not user:
        raise HTTPException(401, "Unknown user")
    return user


def get_project(pid: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Project:
    p = db.get(Project, pid)
    if not p or (p.owner_id != user.id and user.role != "admin"):
        raise HTTPException(404, "Project not found")  # project isolation: never reveal other users' projects
    return p


# ============================================================================================
# Auth
# ============================================================================================
class Credentials(BaseModel):
    email: str
    password: str = Field(min_length=8)
    name: str = ""


@app.post("/api/auth/register")
def register(c: Credentials, db: Session = Depends(get_db)):
    if not ALLOW_REGISTRATION:
        raise HTTPException(403, "Registration disabled")
    email = c.email.strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise HTTPException(422, "Invalid email")
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Email already registered")
    is_first = db.scalar(select(User).limit(1)) is None
    u = User(email=email, name=c.name or email.split("@")[0], password_hash=hash_password(c.password), role="admin" if is_first else "researcher")
    db.add(u)
    db.flush()
    audit(db, None, u.id, "user.register", {"email": email})
    return _login(u, db)


@app.post("/api/auth/login")
def login(c: Credentials, db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(User.email == c.email.strip().lower()))
    if not u or not verify_password(c.password, u.password_hash):
        raise HTTPException(401, "Invalid email or password")
    return _login(u, db)


def _login(u: User, db: Session):
    token, th, exp = new_token()
    db.add(AuthSession(token_hash=th, user_id=u.id, expires_at=exp))
    audit(db, None, u.id, "user.login", {})
    db.commit()
    return {"token": token, "expires_at": exp.isoformat(), "user": {"id": u.id, "email": u.email, "name": u.name, "role": u.role}}


@app.post("/api/auth/logout")
def logout(authorization: str = Header(default=""), db: Session = Depends(get_db)):
    s = db.get(AuthSession, token_hash(authorization.removeprefix("Bearer ").strip()))
    if s:
        db.delete(s)
        db.commit()
    return {"ok": True}


@app.get("/api/auth/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "email": user.email, "name": user.name, "role": user.role}


# ============================================================================================
# Projects
# ============================================================================================
class ProjectIn(BaseModel):
    name: str
    description: str = ""
    settings: dict | None = None


def project_out(p: Project, detail=False) -> dict:
    ds = current_dataset(p)
    out = {"id": p.id, "name": p.name, "description": p.description, "is_synthetic": p.is_synthetic, "settings": p.settings or {},
           "created_at": p.created_at.isoformat(), "updated_at": p.updated_at.isoformat() if p.updated_at else None,
           "dataset": None if not ds else {"filename": ds.filename, "version": ds.version, "n_rows": ds.n_rows, "n_cols": ds.n_cols,
                                            "sha256": ds.sha256, "uploaded_at": ds.uploaded_at.isoformat(), "encoding": ds.encoding, "delimiter": ds.delimiter},
           "n_analyses": len(p.analyses), "dictionary_confirmed": bool((p.dictionary or {}).get("confirmed")),
           "synthetic_notice": {"en": SYNTHETIC_NOTICE_EN, "ar": SYNTHETIC_NOTICE_AR} if p.is_synthetic else None}
    if detail:
        out["lifecycle"] = lifecycle(p)
        out["hypotheses"] = p.hypotheses or []
        out["versions"] = [{"version": d.version, "filename": d.filename, "sha256": d.sha256, "uploaded_at": d.uploaded_at.isoformat(), "n_rows": d.n_rows}
                           for d in p.datasets]
    return out


DEFAULT_SETTINGS = {"alpha": 0.05, "language": "ar", "study_title": "", "sampling_method": "", "weights_variable": None,
                    "literature": [], "analysis_mode": "confirmatory", "external_ai_consent": False}


@app.get("/api/projects")
def list_projects(user: User = Depends(current_user), db: Session = Depends(get_db)):
    ps = db.scalars(select(Project).where(Project.owner_id == user.id).order_by(Project.updated_at.desc())).all()
    return [project_out(p) for p in ps]


@app.post("/api/projects")
def create_project(body: ProjectIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = Project(owner_id=user.id, name=body.name.strip() or "Untitled", description=body.description,
                settings={**DEFAULT_SETTINGS, **(body.settings or {})}, cleaning_ops=[], hypotheses=[])
    db.add(p)
    db.flush()
    audit(db, p.id, user.id, "project.create", {"name": p.name})
    db.commit()
    return project_out(p, True)


@app.post("/api/projects/demo")
def create_demo(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Creates a project pre-loaded with the clearly-labelled SYNTHETIC questionnaire dataset."""
    p = Project(owner_id=user.id, name="Demo — Service quality survey (SYNTHETIC)", is_synthetic=True,
                description=SYNTHETIC_NOTICE_EN + " / " + SYNTHETIC_NOTICE_AR,
                settings={**DEFAULT_SETTINGS, "study_title": "Service quality, trust, satisfaction and loyalty (synthetic demonstration)",
                          "sampling_method": "simulated data"}, cleaning_ops=[], hypotheses=[])
    db.add(p)
    db.flush()
    _store_dataset(p, demo_csv_bytes(), "SYNTHETIC_demo_survey.csv", None, user, db)
    p.hypotheses = [
        {"id": "h1demo", "code": "H1", "text": "There are statistically significant differences in satisfaction (SAT) between males and females.", "purpose": "difference",
         "dv": "SAT", "ivs": ["gender"], "alpha": 0.05, "analysis_id": None, "decision": None},
        {"id": "h2demo", "code": "H2", "text": "Service quality (SQ) is positively correlated with satisfaction (SAT).", "purpose": "relationship",
         "dv": "SAT", "ivs": ["SQ"], "alpha": 0.05, "analysis_id": None, "decision": None},
        {"id": "h3demo", "code": "H3", "text": "Service quality and trust predict loyalty (LOY).", "purpose": "prediction",
         "dv": "LOY", "ivs": ["SQ", "TR"], "alpha": 0.05, "analysis_id": None, "decision": None},
    ]
    db.commit()
    return project_out(p, True)


@app.get("/api/projects/{pid}")
def project_detail(p: Project = Depends(get_project)):
    return project_out(p, True)


@app.patch("/api/projects/{pid}")
def update_project(body: dict, p: Project = Depends(get_project), user: User = Depends(current_user), db: Session = Depends(get_db)):
    if "name" in body:
        p.name = body["name"]
    if "description" in body:
        p.description = body["description"]
    if "settings" in body:
        set_json(p, "settings", {**(p.settings or {}), **body["settings"]})
    audit(db, p.id, user.id, "project.update", {k: v for k, v in body.items() if k != "settings"} | ({"settings": list(body.get("settings", {}).keys())}))
    db.commit()
    return project_out(p, True)


@app.delete("/api/projects/{pid}")
def delete_project(p: Project = Depends(get_project), user: User = Depends(current_user), db: Session = Depends(get_db)):
    pid = p.id
    db.delete(p)
    db.execute(AuditLog.__table__.delete().where(AuditLog.project_id == pid))
    audit(db, None, user.id, "project.delete", {"project_id": pid})
    db.commit()
    delete_project_files(pid)
    return {"ok": True, "deleted": pid}


# ============================================================================================
# Upload / dictionary
# ============================================================================================
@app.post("/api/projects/{pid}/preview")
async def preview(file: UploadFile = File(...), delimiter: str | None = Form(None), encoding: str | None = Form(None), p: Project = Depends(get_project)):
    raw = await file.read()
    _check_size(raw)
    parsed = parse_csv(raw, delimiter=delimiter or None, encoding=encoding or None)
    from .engine.dictionary import build_dictionary
    d = build_dictionary(parsed.df)
    return to_jsonable({"filename": file.filename, "encoding": parsed.encoding, "had_bom": parsed.had_bom, "delimiter": parsed.delimiter,
                        "n_rows": parsed.n_rows, "n_cols": parsed.n_cols, "columns": list(parsed.df.columns),
                        "rows": parsed.df.head(20).to_dict(orient="records"), "warnings": parsed.warnings,
                        "duplicates": int(parsed.df.duplicated().sum()), "dictionary": d})


def _check_size(raw: bytes):
    if len(raw) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"File exceeds {MAX_UPLOAD_MB} MB")


def _store_dataset(p: Project, raw: bytes, filename: str, delimiter: str | None, user: User, db: Session):
    parsed = parse_csv(raw, delimiter=delimiter or None)
    version = (current_dataset(p).version + 1) if p.datasets else 1
    path, sha = save_original(p.id, version, raw)
    ds = Dataset(project_id=p.id, version=version, filename=filename, sha256=sha, size_bytes=len(raw), encoding=parsed.encoding,
                 delimiter=parsed.delimiter, n_rows=parsed.n_rows, n_cols=parsed.n_cols, storage_path=path)
    db.add(ds)
    p.datasets.append(ds)
    db.flush()
    p.dictionary = None
    set_json(p, "dictionary", new_dictionary(p))
    set_json(p, "cleaning_ops", [])
    audit(db, p.id, user.id, "dataset.upload", {"filename": filename, "sha256": sha, "rows": parsed.n_rows, "cols": parsed.n_cols, "version": version,
                                                "encoding": parsed.encoding, "delimiter": parsed.delimiter})
    return ds


@app.post("/api/projects/{pid}/upload")
async def upload(file: UploadFile = File(...), delimiter: str | None = Form(None), p: Project = Depends(get_project),
                 user: User = Depends(current_user), db: Session = Depends(get_db)):
    raw = await file.read()
    _check_size(raw)
    _store_dataset(p, raw, file.filename or "data.csv", delimiter, user, db)
    p.is_synthetic = False
    db.commit()
    return project_out(p, True)


@app.get("/api/projects/{pid}/dictionary")
def get_dictionary(p: Project = Depends(get_project)):
    if not p.dictionary:
        raise HTTPException(404, "No dictionary")
    return p.dictionary


@app.put("/api/projects/{pid}/dictionary")
def put_dictionary(body: dict, p: Project = Depends(get_project), user: User = Depends(current_user), db: Session = Depends(get_db)):
    ds = current_dataset(p)
    if not ds:
        raise HTTPException(400, "Upload data first")
    errors = validate_dictionary(body, list(frames_cols(p)))
    if errors:
        raise HTTPException(422, "; ".join(errors))
    lk = body.get("likert", {})
    if lk and (not lk.get("interpretation") or body.get("regenerate_bands")):
        lk["interpretation"] = interpretation_bands(lk["min"], lk["max"], lk.get("bands", min(lk["max"] - lk["min"] + 1, 5)))
    lk["points"] = int(lk.get("max", 5) - lk.get("min", 1) + 1)
    body.pop("regenerate_bands", None)
    changes = _dict_diff(p.dictionary or {}, body)
    set_json(p, "dictionary", body)
    audit(db, p.id, user.id, "dictionary.update", {"confirmed": body.get("confirmed"), "changes": changes[:50]})
    db.commit()
    return p.dictionary


def frames_cols(p: Project):
    from .services import raw_frame
    return raw_frame(current_dataset(p))[0].columns


def _dict_diff(old: dict, new: dict) -> list[str]:
    o = {v["name"]: v for v in old.get("variables", [])}
    out = []
    for v in new.get("variables", []):
        ov = o.get(v["name"], {})
        for k in ("dtype", "level", "role", "dimension", "reverse", "label"):
            if ov.get(k) != v.get(k):
                out.append(f"{v['name']}.{k}: {ov.get(k)} → {v.get(k)}")
    if [d["name"] for d in old.get("dimensions", [])] != [d["name"] for d in new.get("dimensions", [])]:
        out.append("dimensions: " + ", ".join(d["name"] for d in new.get("dimensions", [])))
    return out


@app.post("/api/projects/{pid}/dictionary/reset")
def reset_dictionary(p: Project = Depends(get_project), user: User = Depends(current_user), db: Session = Depends(get_db)):
    set_json(p, "dictionary", new_dictionary(p))
    audit(db, p.id, user.id, "dictionary.reset", {})
    db.commit()
    return p.dictionary


@app.get("/api/projects/{pid}/data")
def get_data(stage: str = "analysis", page: int = 1, size: int = 50, p: Project = Depends(get_project)):
    f = frames(p)
    df = {"raw": f.raw, "typed": f.typed, "clean": f.clean, "analysis": f.analysis}.get(stage)
    if df is None:
        raise HTTPException(400, "stage must be raw|typed|clean|analysis")
    sub = df.iloc[(page - 1) * size: page * size]
    return to_jsonable({"stage": stage, "total": len(df), "page": page, "size": size, "columns": list(df.columns),
                        "rows": [{"__row__": int(i), **r} for i, r in zip(sub.index, sub.astype(object).where(sub.notna(), None).to_dict(orient="records"))]})


# ============================================================================================
# Quality & cleaning
# ============================================================================================
@app.get("/api/projects/{pid}/quality")
def quality(p: Project = Depends(get_project)):
    q = project_quality(p)
    f = frames(p)
    q["op_log"] = f.op_log
    q["rows_after_cleaning"] = len(f.clean)
    return q


@app.get("/api/projects/{pid}/cleaning")
def get_cleaning(p: Project = Depends(get_project)):
    return {"operations": p.cleaning_ops or [], "op_types": {k: {"en": v[0], "ar": v[1]} for k, v in OP_TYPES.items()}, "log": frames(p).op_log}


@app.post("/api/projects/{pid}/cleaning/propose")
def propose(p: Project = Depends(get_project), user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = project_quality(p)
    existing = p.cleaning_ops or []
    existing_checks = {(o.get("check"), json.dumps(o["params"], sort_keys=True)) for o in existing}
    new = [o for o in propose_operations(q, p.dictionary) if (o.get("check"), json.dumps(o["params"], sort_keys=True)) not in existing_checks]
    set_json(p, "cleaning_ops", existing + new)
    audit(db, p.id, user.id, "cleaning.propose", {"n_new": len(new)})
    db.commit()
    return {"operations": p.cleaning_ops, "added": len(new)}


class OpIn(BaseModel):
    type: str
    params: dict
    reason_en: str = ""
    reason_ar: str = ""


@app.post("/api/projects/{pid}/cleaning")
def add_op(body: OpIn, p: Project = Depends(get_project), user: User = Depends(current_user), db: Session = Depends(get_db)):
    op = new_op(body.type, body.params, body.reason_en or "Manual operation added by the researcher",
                body.reason_ar or "عملية يدوية أضافها الباحث", source="manual")
    op["status"] = "accepted"
    op["decided_at"] = now().isoformat()
    set_json(p, "cleaning_ops", (p.cleaning_ops or []) + [op])
    audit(db, p.id, user.id, "cleaning.add", {"op": op})
    db.commit()
    return {"operations": p.cleaning_ops}


@app.patch("/api/projects/{pid}/cleaning/{op_id}")
def decide_op(op_id: str, body: dict, p: Project = Depends(get_project), user: User = Depends(current_user), db: Session = Depends(get_db)):
    ops = copy.deepcopy(p.cleaning_ops or [])
    op = next((o for o in ops if o["id"] == op_id), None)
    if not op:
        raise HTTPException(404, "Operation not found")
    if body.get("status") not in ("accepted", "rejected", "pending"):
        raise HTTPException(422, "status must be accepted|rejected|pending")
    old = op["status"]
    op["status"] = body["status"]
    op["decided_at"] = now().isoformat()
    if "params" in body and isinstance(body["params"], dict):
        op["params"] = body["params"]
    if body.get("note"):
        op["note"] = body["note"]
    set_json(p, "cleaning_ops", ops)
    audit(db, p.id, user.id, "cleaning.decide", {"op_id": op_id, "type": op["type"], "from": old, "to": op["status"], "reason": op["reason_en"]})
    db.commit()
    return {"operations": p.cleaning_ops}


@app.post("/api/projects/{pid}/cleaning/bulk")
def bulk_decide(body: dict, p: Project = Depends(get_project), user: User = Depends(current_user), db: Session = Depends(get_db)):
    ops = copy.deepcopy(p.cleaning_ops or [])
    ids = set(body.get("ids") or [o["id"] for o in ops if o["status"] == "pending"])
    for o in ops:
        if o["id"] in ids:
            o["status"] = body["status"]
            o["decided_at"] = now().isoformat()
    set_json(p, "cleaning_ops", ops)
    audit(db, p.id, user.id, "cleaning.bulk", {"ids": list(ids), "status": body["status"]})
    db.commit()
    return {"operations": p.cleaning_ops}


@app.post("/api/projects/{pid}/cleaning/restore")
def restore_original(p: Project = Depends(get_project), user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Restore the original data: every operation is set back to pending (nothing is lost)."""
    ops = copy.deepcopy(p.cleaning_ops or [])
    for o in ops:
        o["status"] = "pending"
    set_json(p, "cleaning_ops", ops)
    audit(db, p.id, user.id, "cleaning.restore_original", {"n_ops": len(ops)})
    db.commit()
    return {"operations": p.cleaning_ops}


@app.delete("/api/projects/{pid}/cleaning/{op_id}")
def delete_op(op_id: str, p: Project = Depends(get_project), user: User = Depends(current_user), db: Session = Depends(get_db)):
    ops = [o for o in (p.cleaning_ops or []) if o["id"] != op_id]
    set_json(p, "cleaning_ops", ops)
    audit(db, p.id, user.id, "cleaning.delete", {"op_id": op_id})
    db.commit()
    return {"operations": p.cleaning_ops}


# ============================================================================================
# Overview / variables / analyses
# ============================================================================================
@app.get("/api/projects/{pid}/overview")
def overview(p: Project = Depends(get_project)):
    k = kpis(p)
    out = {"project": project_out(p, True), "kpis": k}
    if k.get("has_data"):
        df = frames(p).analysis
        comps = {k_: v for k_, v in df.attrs.get("composites", {}).items() if k_ != "__overall__"}
        lk = p.dictionary.get("likert", {})
        out["dimension_means"] = [{"dimension": k_, "column": v, "mean": float(df[v].mean()) if df[v].notna().any() else None,
                                   "sd": float(df[v].std()) if df[v].notna().sum() > 1 else None} for k_, v in comps.items()]
        out["likert_range"] = [lk.get("min"), lk.get("max")]
        out["recent"] = [{"id": a.id, "kind": a.kind, "title_en": a.result["title_en"], "title_ar": a.result["title_ar"],
                          "created_at": a.created_at.isoformat(), "significant": (a.result.get("interpretation") or {}).get("significant")} for a in p.analyses[-6:]][::-1]
    return to_jsonable(out)


@app.get("/api/projects/{pid}/variables")
def variables(p: Project = Depends(get_project)):
    f = frames(p)
    df = f.analysis
    ctx = make_ctx(df, p.dictionary)
    comps = df.attrs.get("composites", {})
    out = []
    for c in df.columns:
        v = ctx["var"](c)
        vals = None
        if not ctx["is_numeric"](c) or df[c].nunique() <= 12:
            vals = sorted({(str(int(x)) if isinstance(x, float) and float(x).is_integer() else str(x)) for x in df[c].dropna().unique()})[:50]
        out.append({"name": c, "label": v.get("label") or c, "dtype": v.get("dtype"), "level": v.get("level"), "role": v.get("role"),
                    "dimension": v.get("dimension"), "is_likert": bool(v.get("is_likert")), "numeric": bool(ctx["is_numeric"](c)),
                    "composite": c in comps.values(), "n_unique": int(df[c].nunique()), "values": vals})
    return to_jsonable({"variables": out, "composites": comps})


class RunIn(BaseModel):
    kind: str
    params: dict = {}
    filters: dict = {}
    save: bool = True
    hypothesis_id: str | None = None


@app.get("/api/analysis-types")
def analysis_types():
    return {"types": list(REGISTRY.keys()) + ["eda"], "purposes": {k: {"en": v[0], "ar": v[1]} for k, v in PURPOSES.items()},
            "reports": {k: {"en": v[0], "ar": v[1]} for k, v in REPORT_TYPES.items()}}


@app.post("/api/projects/{pid}/run")
def run(body: RunIn, p: Project = Depends(get_project), user: User = Depends(current_user), db: Session = Depends(get_db)):
    df = analysis_frame(p, body.filters)
    alpha = float((p.settings or {}).get("alpha", 0.05))
    res = run_analysis(body.kind, df, p.dictionary, body.params, alpha)
    res["filters"] = body.filters
    res["analysis_mode"] = (p.settings or {}).get("analysis_mode", "confirmatory")
    fp = data_fingerprint(p)
    if body.save:
        a = Analysis(project_id=p.id, kind=body.kind, params=body.params, filters=body.filters, result=res, data_fingerprint=fp,
                     hypothesis_id=body.hypothesis_id)
        db.add(a)
        db.flush()
        res["id"] = a.id
        a.result = {**res}
        audit(db, p.id, user.id, "analysis.run", {"analysis_id": a.id, "kind": body.kind, "params": body.params, "filters": body.filters,
                                                  "data_fingerprint": fp})
        db.commit()
    return res


@app.get("/api/projects/{pid}/analyses")
def list_analyses(p: Project = Depends(get_project)):
    fp = data_fingerprint(p) if current_dataset(p) and p.dictionary else None
    return [{"id": a.id, "kind": a.kind, "title_en": a.result.get("title_en"), "title_ar": a.result.get("title_ar"), "params": a.params, "filters": a.filters,
             "created_at": a.created_at.isoformat(), "in_report": a.in_report, "stale": a.data_fingerprint != fp, "hypothesis_id": a.hypothesis_id,
             "category": a.result.get("category"), "significant": (a.result.get("interpretation") or {}).get("significant")} for a in p.analyses][::-1]


@app.get("/api/projects/{pid}/analyses/{aid}")
def get_analysis(aid: str, p: Project = Depends(get_project)):
    a = next((x for x in p.analyses if x.id == aid), None)
    if not a:
        raise HTTPException(404, "Analysis not found")
    return {**a.result, "id": a.id, "stale": a.data_fingerprint != data_fingerprint(p), "in_report": a.in_report}


@app.patch("/api/projects/{pid}/analyses/{aid}")
def patch_analysis(aid: str, body: dict, p: Project = Depends(get_project), db: Session = Depends(get_db)):
    a = next((x for x in p.analyses if x.id == aid), None)
    if not a:
        raise HTTPException(404)
    if "in_report" in body:
        a.in_report = bool(body["in_report"])
    db.commit()
    return {"ok": True}


@app.delete("/api/projects/{pid}/analyses/{aid}")
def delete_analysis(aid: str, p: Project = Depends(get_project), user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = next((x for x in p.analyses if x.id == aid), None)
    if not a:
        raise HTTPException(404)
    db.delete(a)
    audit(db, p.id, user.id, "analysis.delete", {"analysis_id": aid})
    db.commit()
    return {"ok": True}


@app.post("/api/projects/{pid}/recommend")
def recommend_test(body: dict, p: Project = Depends(get_project)):
    df = analysis_frame(p, body.get("filters"))
    return recommend(df, body, make_ctx(df, p.dictionary))


# ============================================================================================
# Hypotheses
# ============================================================================================
@app.post("/api/projects/{pid}/hypotheses")
def add_hypothesis(body: dict, p: Project = Depends(get_project), user: User = Depends(current_user), db: Session = Depends(get_db)):
    hyps = copy.deepcopy(p.hypotheses or [])
    h = {"id": body.get("id") or __import__("uuid").uuid4().hex[:10], "code": body.get("code") or f"H{len(hyps) + 1}", "text": body.get("text", ""),
         "purpose": body.get("purpose"), "dv": body.get("dv"), "ivs": body.get("ivs") or [], "mediator": body.get("mediator"), "moderator": body.get("moderator"),
         "alpha": float(body.get("alpha") or (p.settings or {}).get("alpha", 0.05)), "direction": body.get("direction", "two-sided"),
         "analysis_id": None, "decision": None}
    existing = next((i for i, x in enumerate(hyps) if x["id"] == h["id"]), None)
    if existing is not None:
        h["analysis_id"], h["decision"] = hyps[existing].get("analysis_id"), hyps[existing].get("decision")
        hyps[existing] = h
    else:
        hyps.append(h)
    set_json(p, "hypotheses", hyps)
    audit(db, p.id, user.id, "hypothesis.save", {"id": h["id"], "text": h["text"]})
    db.commit()
    return p.hypotheses


@app.delete("/api/projects/{pid}/hypotheses/{hid}")
def del_hypothesis(hid: str, p: Project = Depends(get_project), user: User = Depends(current_user), db: Session = Depends(get_db)):
    set_json(p, "hypotheses", [h for h in (p.hypotheses or []) if h["id"] != hid])
    audit(db, p.id, user.id, "hypothesis.delete", {"id": hid})
    db.commit()
    return p.hypotheses


@app.post("/api/projects/{pid}/hypotheses/{hid}/run")
def run_hypothesis(hid: str, body: dict, p: Project = Depends(get_project), user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Runs the test approved by the researcher (kind + params) for the hypothesis and records the decision."""
    hyps = copy.deepcopy(p.hypotheses or [])
    h = next((x for x in hyps if x["id"] == hid), None)
    if not h:
        raise HTTPException(404, "Hypothesis not found")
    kind, params = body["kind"], body.get("params", {})
    if h.get("direction") in ("greater", "less"):
        params.setdefault("alternative", h["direction"])
    df = analysis_frame(p, body.get("filters"))
    res = run_analysis(kind, df, p.dictionary, params, h["alpha"])
    dec = hypothesis_decision(res, res["interpretation"], h["alpha"])
    fp = data_fingerprint(p)
    a = Analysis(project_id=p.id, kind=kind, params=params, filters=body.get("filters") or {}, result=res, data_fingerprint=fp, hypothesis_id=hid)
    db.add(a)
    db.flush()
    h["analysis_id"], h["decision"], h["test"] = a.id, dec, kind
    h["p"] = (res.get("stats") or {}).get("p", (res.get("stats") or {}).get("llr_p"))
    if kind == "correlation":
        pairs = res["stats"]["pairs"]
        h["p"] = pairs[0]["p"] if len(pairs) == 1 else None
    _holm(hyps)
    set_json(p, "hypotheses", hyps)
    audit(db, p.id, user.id, "hypothesis.test", {"id": hid, "analysis_id": a.id, "kind": kind, "params": params, "decision": dec["decision"]})
    db.commit()
    return {"hypotheses": p.hypotheses, "result": {**res, "id": a.id}}


def _holm(hyps: list):
    """Family-wise correction across tested hypotheses (Holm–Bonferroni)."""
    tested = [h for h in hyps if h.get("p") is not None]
    if len(tested) >= 2:
        adj = multipletests([h["p"] for h in tested], method="holm")[1]
        for h, pa in zip(tested, adj):
            h["p_adjusted"] = float(pa)
            h["supported_after_correction"] = bool(pa < h["alpha"])
    for h in hyps:
        if h.get("p") is None:
            h.pop("p_adjusted", None)


# ============================================================================================
# Assistant, reports, exports, audit, reproducibility
# ============================================================================================
@app.post("/api/projects/{pid}/assistant")
def ask(body: dict, p: Project = Depends(get_project)):
    fp = data_fingerprint(p) if current_dataset(p) and p.dictionary else None
    return assistant.answer(p, body.get("question", ""), body.get("lang", "ar"), body.get("analysis_id"), fp)


MEDIA = {"html": "text/html; charset=utf-8", "pdf": "application/pdf", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
         "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "csv": "application/zip", "json": "application/json"}


@app.get("/api/projects/{pid}/report")
def report(type: str = "comprehensive", lang: str = "ar", format: str = "html", hypothesis_id: str | None = None,
           p: Project = Depends(get_project), user: User = Depends(current_user), db: Session = Depends(get_db)):
    doc = build_report(p, type, lang, hypothesis_id)
    f = frames(p)
    if format == "json":
        content = json.dumps(doc, ensure_ascii=False, default=str).encode()
    elif format == "html":
        content = render_html(doc)
    elif format == "pdf":
        content = render_pdf(doc)
    elif format == "docx":
        content = render_docx(doc)
    elif format == "xlsx":
        content = render_xlsx(doc, {"clean_data": f.analysis.reset_index().rename(columns={"index": "row_id"})})
    elif format == "csv":
        content = render_csv_zip(doc, {"clean_data": f.analysis, "original_data": f.raw})
    else:
        raise HTTPException(400, "format must be html|pdf|docx|xlsx|csv|json")
    set_json(p, "settings", {**(p.settings or {}), "report_generated": True})
    audit(db, p.id, user.id, "report.generate", {"type": type, "lang": lang, "format": format})
    db.commit()
    ext = "zip" if format == "csv" else format
    fname = f"report_{type}_{lang}.{ext}"
    return Response(content, media_type=MEDIA[format], headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@app.get("/api/projects/{pid}/export/data")
def export_data(stage: str = "analysis", format: str = "csv", p: Project = Depends(get_project), user: User = Depends(current_user), db: Session = Depends(get_db)):
    f = frames(p)
    df = {"raw": f.raw, "clean": f.clean, "analysis": f.analysis}[stage]
    audit(db, p.id, user.id, "data.export", {"stage": stage, "format": format})
    db.commit()
    if format == "xlsx":
        buf = io.BytesIO()
        df.to_excel(buf, index=True, index_label="row_id")
        return Response(buf.getvalue(), media_type=MEDIA["xlsx"], headers={"Content-Disposition": f'attachment; filename="data_{stage}.xlsx"'})
    return Response(("﻿" + df.to_csv(index=True, index_label="row_id")).encode("utf-8"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="data_{stage}.csv"'})


@app.get("/api/projects/{pid}/audit")
def audit_log(p: Project = Depends(get_project), db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditLog).where(AuditLog.project_id == p.id).order_by(AuditLog.id.desc()).limit(500)).all()
    return [{"id": r.id, "action": r.action, "details": r.details, "ts": r.ts.isoformat(), "user_id": r.user_id} for r in rows]


@app.get("/api/projects/{pid}/reproduce")
def reproducibility_manifest(p: Project = Depends(get_project)):
    """Everything needed to re-execute the analyses: data hash, dictionary, accepted operations, analyses and library versions."""
    import factor_analyzer, pandas, pingouin, scipy, sklearn, statsmodels  # noqa: E401
    try:
        import semopy
        sem_v = semopy.__version__
    except ImportError:  # pragma: no cover
        sem_v = None
    ds = current_dataset(p)
    return to_jsonable({"project": p.name, "dataset": {"filename": ds.filename, "sha256": ds.sha256, "version": ds.version} if ds else None,
                        "data_fingerprint": data_fingerprint(p) if ds and p.dictionary else None, "dictionary": p.dictionary,
                        "cleaning_operations": [o for o in (p.cleaning_ops or []) if o["status"] == "accepted"],
                        "analyses": [{"id": a.id, "kind": a.kind, "params": a.params, "filters": a.filters, "data_fingerprint": a.data_fingerprint,
                                      "created_at": a.created_at.isoformat()} for a in p.analyses],
                        "hypotheses": p.hypotheses, "settings": p.settings,
                        "versions": {"numpy": np.__version__, "pandas": pandas.__version__, "scipy": scipy.__version__, "statsmodels": statsmodels.__version__,
                                     "pingouin": pingouin.__version__, "scikit-learn": sklearn.__version__, "factor_analyzer": getattr(factor_analyzer, "__version__", "0.5.x"),
                                     "semopy": sem_v}})


@app.post("/api/projects/{pid}/reproduce/verify")
def reproduce_verify(p: Project = Depends(get_project), user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Re-runs every saved analysis from the original file and compares key statistics."""
    out = []
    fp = data_fingerprint(p)
    for a in p.analyses:
        if a.data_fingerprint != fp:
            out.append({"id": a.id, "kind": a.kind, "status": "stale"})
            continue
        try:
            df = analysis_frame(p, a.filters)
            r = run_analysis(a.kind, df, p.dictionary, a.params, a.result.get("alpha", 0.05))
            same = json.dumps(r.get("tables"), sort_keys=True, default=str) == json.dumps(a.result.get("tables"), sort_keys=True, default=str)
            out.append({"id": a.id, "kind": a.kind, "status": "identical" if same else "different"})
        except AnalysisError as e:
            out.append({"id": a.id, "kind": a.kind, "status": "error", "detail": e.en})
    audit(db, p.id, user.id, "reproduce.verify", {"results": out})
    db.commit()
    return out


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Serve the built frontend (single-process deployment)
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404)
        target = FRONTEND_DIST / full_path
        if full_path and target.is_file():
            return FileResponse(target)
        return FileResponse(FRONTEND_DIST / "index.html")
