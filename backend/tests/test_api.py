"""End-to-end scenario through the REST API (steps 1–12 of the usage scenario)."""
import io

from fastapi.testclient import TestClient

from app.main import app

c = TestClient(app)


def _auth(email):
    r = c.post("/api/auth/register", json={"email": email, "password": "password123"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_full_scenario():
    H = _auth("researcher@test.org")
    p = c.post("/api/projects", headers=H, json={"name": "Study"}).json()
    pid = p["id"]
    csv = "id,gender,Q1,Q2,Q3,Q4,Q5,Q6\n" + "\n".join(
        f"{i},{'M' if i % 3 else 'F'},{1 + i % 5},{1 + (i * 2) % 5},{1 + (i * 3) % 5},{1 + (i + 1) % 5},{1 + (i + 2) % 5},{1 + (i * 7) % 5}" for i in range(80))
    pv = c.post(f"/api/projects/{pid}/preview", headers=H, files={"file": ("s.csv", csv.encode(), "text/csv")}).json()
    assert pv["n_rows"] == 80 and pv["n_cols"] == 8
    c.post(f"/api/projects/{pid}/upload", headers=H, files={"file": ("s.csv", io.BytesIO(csv.encode()), "text/csv")}).raise_for_status()
    d = c.get(f"/api/projects/{pid}/dictionary", headers=H).json()
    d["dimensions"] = [{"name": "A", "label": "A", "items": ["Q1", "Q2", "Q3"]}, {"name": "B", "label": "B", "items": ["Q4", "Q5", "Q6"]}]
    d["confirmed"] = True
    assert c.put(f"/api/projects/{pid}/dictionary", headers=H, json=d).status_code == 200
    c.post(f"/api/projects/{pid}/cleaning/propose", headers=H).raise_for_status()
    ov = c.get(f"/api/projects/{pid}/overview", headers=H).json()
    assert ov["kpis"]["participants"] == 80 and ov["kpis"]["dimensions"] == 2
    rec = c.post(f"/api/projects/{pid}/recommend", headers=H, json={"purpose": "difference", "dv": "A", "ivs": ["gender"]}).json()
    assert rec["recommended"]["analysis"] in ("ttest_ind", "mannwhitney")
    hyps = c.post(f"/api/projects/{pid}/hypotheses", headers=H, json={"text": "A differs by gender", "purpose": "difference", "dv": "A", "ivs": ["gender"]}).json()
    out = c.post(f"/api/projects/{pid}/hypotheses/{hyps[0]['id']}/run", headers=H, json={"kind": rec["recommended"]["analysis"], "params": rec["recommended"]["params"]}).json()
    assert out["hypotheses"][0]["decision"]["decision"] in ("supported", "not_supported")
    r = c.post(f"/api/projects/{pid}/run", headers=H, json={"kind": "reliability", "params": {}, "filters": {"gender": ["F"]}})
    assert r.status_code == 200 and r.json()["n"] == len([i for i in range(80) if i % 3 == 0])
    a = c.post(f"/api/projects/{pid}/assistant", headers=H, json={"question": "summary", "lang": "en"}).json()
    assert "no number was generated" in a["answer"]
    for fmt in ("html", "pdf", "docx", "xlsx", "csv"):
        assert c.get(f"/api/projects/{pid}/report", headers=H, params={"type": "apa", "lang": "ar", "format": fmt}).status_code == 200
    assert all(x["status"] == "identical" for x in c.post(f"/api/projects/{pid}/reproduce/verify", headers=H).json())
    # isolation between users
    assert c.get(f"/api/projects/{pid}", headers=_auth("other@test.org")).status_code == 404
    assert c.delete(f"/api/projects/{pid}", headers=H).json()["ok"]


def test_demo_project_is_labelled_synthetic():
    H = _auth("demo@test.org")
    p = c.post("/api/projects/demo", headers=H).json()
    assert p["is_synthetic"] and "SYNTHETIC" in p["name"] and p["synthetic_notice"]["ar"]
