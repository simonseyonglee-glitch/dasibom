"""
다시봄 (Dasibom) - 테스트용 백엔드 서버
====================================================
- FastAPI + SQLite (파일 자동생성, 별도 DB 설치 불필요)
- 첫 실행 시 스키마/시드 데이터 자동 주입
- 정적 HTML 파일 서빙 + REST API 제공

실행:
    pip install fastapi uvicorn[standard]
    python server.py

브라우저:
    구직자 페이지   http://localhost:8000/app.html
    기업 페이지     http://localhost:8000/employer.html
    관리자 페이지   http://localhost:8000/admin_live.html
    API docs       http://localhost:8000/docs
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, List, Optional

from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field

# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent.resolve()
# DB 경로: 환경변수 우선. Render 등에서 영구 디스크 마운트 시 /data 사용 권장.
DB_PATH = Path(os.environ.get("DASIBOM_DB", str(BASE_DIR / "dasibom.db")))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
STATIC_DIR = BASE_DIR  # 같은 폴더에서 HTML 서빙

# ---------------------------------------------------------------------------
# DB 유틸
# ---------------------------------------------------------------------------
def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

@contextmanager
def db():
    conn = get_conn()
    try:
        yield conn
    finally:
        conn.close()

def now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def hash_pw(pw: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(8)
    h = hashlib.sha256(f"{salt}:{pw}".encode()).hexdigest()
    return f"{salt}${h}"

def verify_pw(pw: str, stored: str) -> bool:
    try:
        salt, _ = stored.split("$", 1)
    except ValueError:
        return False
    return hash_pw(pw, salt) == stored

# ---------------------------------------------------------------------------
# 스키마 (SQLite 호환)
# ---------------------------------------------------------------------------
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id          TEXT PRIMARY KEY,
    email            TEXT NOT NULL UNIQUE,
    password_hash    TEXT NOT NULL,
    phone            TEXT,
    role             TEXT NOT NULL DEFAULT 'jobseeker'
        CHECK(role IN ('jobseeker','employer','mentor','admin')),
    status           TEXT NOT NULL DEFAULT 'active'
        CHECK(status IN ('active','dormant','suspended','withdrawn')),
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    last_login_at    TEXT
);

CREATE TABLE IF NOT EXISTS user_profiles (
    user_id          TEXT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    name             TEXT NOT NULL,
    birth_year       INTEGER,
    region_sido      TEXT,
    region_sigungu   TEXT,
    career_gap_months INTEGER NOT NULL DEFAULT 0,
    desired_work_types TEXT NOT NULL DEFAULT '[]',  -- JSON array
    desired_weekly_hours INTEGER,
    bio              TEXT,
    profile_complete_pct INTEGER NOT NULL DEFAULT 0,
    updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS companies (
    company_id       TEXT PRIMARY KEY,
    business_no      TEXT NOT NULL UNIQUE,
    name             TEXT NOT NULL,
    logo_initial     TEXT,                          -- 로고 대체 한글자
    industry         TEXT,
    size             TEXT CHECK(size IN ('startup','small','medium','large','enterprise')),
    region_sido      TEXT,
    region_sigungu   TEXT,
    description      TEXT,
    female_ratio     REAL,
    female_mgr_ratio REAL,
    flex_usage_ratio REAL,
    wcert_status     TEXT NOT NULL DEFAULT 'applied'
        CHECK(wcert_status IN ('applied','under_review','approved','rejected','expired','revoked')),
    wcert_score      REAL,
    owner_user_id    TEXT REFERENCES users(user_id),
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS job_categories (
    category_id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name_ko TEXT NOT NULL,
    sort_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS job_postings (
    job_id           TEXT PRIMARY KEY,
    company_id       TEXT NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
    title            TEXT NOT NULL,
    category_id      INTEGER REFERENCES job_categories(category_id),
    description      TEXT NOT NULL,
    qualifications   TEXT,
    work_types       TEXT NOT NULL DEFAULT '[]',  -- JSON array
    weekly_hours_min INTEGER,
    weekly_hours_max INTEGER,
    salary_type      TEXT NOT NULL DEFAULT 'monthly',
    salary_min       INTEGER,
    salary_max       INTEGER,
    region_sido      TEXT,
    region_sigungu   TEXT,
    is_remote_ok     INTEGER NOT NULL DEFAULT 0,
    gap_track        INTEGER NOT NULL DEFAULT 0,
    senior_preferred INTEGER NOT NULL DEFAULT 0,
    no_exp_ok        INTEGER NOT NULL DEFAULT 0,
    status           TEXT NOT NULL DEFAULT 'pending_review'
        CHECK(status IN ('draft','pending_review','published','closed','rejected','expired')),
    view_count       INTEGER NOT NULL DEFAULT 0,
    apply_count      INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    published_at     TEXT
);

CREATE TABLE IF NOT EXISTS job_applications (
    application_id   TEXT PRIMARY KEY,
    user_id          TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    job_id           TEXT NOT NULL REFERENCES job_postings(job_id) ON DELETE CASCADE,
    status           TEXT NOT NULL DEFAULT 'submitted'
        CHECK(status IN ('submitted','screening','document_passed','interview_scheduled',
                         'interview_done','final_passed','rejected','withdrawn',
                         'offer_accepted','offer_declined')),
    cover_letter     TEXT,
    ai_match_score   INTEGER,
    applied_at       TEXT NOT NULL DEFAULT (datetime('now')),
    status_updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, job_id)
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reports (
    report_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    reporter_id  TEXT REFERENCES users(user_id),
    target_type  TEXT NOT NULL,
    target_id    TEXT NOT NULL,
    reason_code  TEXT NOT NULL,
    detail       TEXT,
    status       TEXT NOT NULL DEFAULT 'received'
        CHECK(status IN ('received','investigating','resolved','rejected')),
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON job_postings(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_apps_user ON job_applications(user_id, status);
CREATE INDEX IF NOT EXISTS idx_companies_wcert ON companies(wcert_status);
"""

# ---------------------------------------------------------------------------
# 시드 데이터
# ---------------------------------------------------------------------------
SEED_CATEGORIES = [
    ("office", "사무/행정", 1),
    ("education", "교육/돌봄", 2),
    ("digital", "디지털/온라인", 3),
    ("service", "서비스/판매", 4),
    ("specialty", "전문직", 5),
]

SEED_COMPANIES = [
    {"name":"현우 에듀","biz":"123-45-67890","industry":"교육","size":"small",
     "sido":"서울","sigungu":"강남구","logo":"현","wcert":"approved","wcert_score":4.5,
     "female":0.72,"mgr":0.34,"flex":0.68,
     "desc":"방과후 영어 교육 전문 기관"},
    {"name":"그린리프","biz":"234-56-78901","industry":"친환경","size":"medium",
     "sido":"경기","sigungu":"분당구","logo":"그","wcert":"under_review","wcert_score":4.1,
     "female":0.58,"mgr":0.34,"flex":0.68,
     "desc":"친환경 라이프스타일 브랜드"},
    {"name":"노을디자인","biz":"345-67-89012","industry":"디자인","size":"startup",
     "sido":"서울","sigungu":"마포구","logo":"노","wcert":"approved","wcert_score":4.7,
     "female":0.81,"mgr":0.55,"flex":0.92,
     "desc":"브랜드 콘텐츠 스튜디오, 100% 원격근무"},
    {"name":"맘스데이케어","biz":"456-78-90123","industry":"돌봄","size":"small",
     "sido":"서울","sigungu":"마포구","logo":"맘","wcert":"approved","wcert_score":4.6,
     "female":0.89,"mgr":0.62,"flex":0.78,
     "desc":"가정 방문 아이돌봄 서비스"},
]

SEED_JOBS = [
    {"co":"현우 에듀","title":"초등 방과후 영어 강사 (오전반)","cat":2,
     "desc":"방과후 초등 대상 영어 수업 (1~3학년). 학교 일정에 맞춘 오전 근무.",
     "qual":"영어 교육 또는 어학 관련 전공 우대. 무경력 강사도 환영합니다.",
     "wtypes":["part_time","flex"],"wmin":12,"wmax":16,
     "salary_type":"hourly","smin":25000,"smax":30000,
     "sido":"서울","sigungu":"강남구","remote":False,"gap":True,"senior":False,"noexp":True},
    {"co":"그린리프","title":"사내 행정 어시스턴트 (시간선택제)","cat":1,
     "desc":"본사 운영지원 및 사내 행정 업무. 주 20시간 시간선택제.",
     "qual":"엑셀·구글워크스페이스 사용 가능자. 사무직 경력 보유자 우대.",
     "wtypes":["part_time","flex"],"wmin":20,"wmax":20,
     "salary_type":"monthly","smin":1800000,"smax":2200000,
     "sido":"경기","sigungu":"분당구","remote":False,"gap":True,"senior":False,"noexp":False},
    {"co":"노을디자인","title":"콘텐츠 에디터 (시니어 우대 · 100% 재택)","cat":3,
     "desc":"브랜드 인스타그램·뉴스레터 콘텐츠 기획·작성. 100% 원격근무.",
     "qual":"글쓰기에 자신 있는 분. 50세 이상 시니어 우대.",
     "wtypes":["remote","flex"],"wmin":25,"wmax":30,
     "salary_type":"monthly","smin":2600000,"smax":3200000,
     "sido":None,"sigungu":None,"remote":True,"gap":True,"senior":True,"noexp":True},
    {"co":"맘스데이케어","title":"아이돌봄 코디네이터","cat":2,
     "desc":"방문 돌봄 매칭 및 사후관리. 사무+현장 혼합 업무.",
     "qual":"육아 경험자 우대. 단축근무 가능.",
     "wtypes":["part_time","hybrid"],"wmin":25,"wmax":30,
     "salary_type":"monthly","smin":2400000,"smax":2800000,
     "sido":"서울","sigungu":"마포구","remote":False,"gap":True,"senior":False,"noexp":True},
]

def init_db():
    fresh = not DB_PATH.exists()
    with db() as conn:
        conn.executescript(SCHEMA_SQL)
        if fresh:
            print("✨ 첫 실행: 시드 데이터 주입 중...")
            # categories
            for c in SEED_CATEGORIES:
                conn.execute("INSERT INTO job_categories(code,name_ko,sort_order) VALUES(?,?,?)", c)
            # admin
            admin_id = uuid.uuid4().hex
            conn.execute(
                "INSERT INTO users(user_id,email,password_hash,role) VALUES(?,?,?,?)",
                (admin_id, "admin@dasibom.kr", hash_pw("admin1234"), "admin"),
            )
            # demo jobseeker
            user_id = uuid.uuid4().hex
            conn.execute(
                "INSERT INTO users(user_id,email,password_hash,role) VALUES(?,?,?,?)",
                (user_id, "demo@dasibom.kr", hash_pw("demo1234"), "jobseeker"),
            )
            conn.execute(
                "INSERT INTO user_profiles(user_id,name,birth_year,region_sido,region_sigungu,career_gap_months,desired_work_types,desired_weekly_hours,profile_complete_pct) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (user_id, "김민정", 1979, "서울", "강남구", 86, json.dumps(["part_time","flex","remote"]), 25, 78),
            )
            # companies + owner accounts
            co_id_by_name: dict[str, str] = {}
            for c in SEED_COMPANIES:
                emp_uid = uuid.uuid4().hex
                conn.execute(
                    "INSERT INTO users(user_id,email,password_hash,role) VALUES(?,?,?,?)",
                    (emp_uid, f"{c['biz'].replace('-','')}@employer.kr", hash_pw("emp1234"), "employer"),
                )
                cid = uuid.uuid4().hex
                co_id_by_name[c["name"]] = cid
                conn.execute(
                    "INSERT INTO companies(company_id,business_no,name,logo_initial,industry,size,region_sido,region_sigungu,"
                    "description,female_ratio,female_mgr_ratio,flex_usage_ratio,wcert_status,wcert_score,owner_user_id) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (cid,c["biz"],c["name"],c["logo"],c["industry"],c["size"],c["sido"],c["sigungu"],
                     c["desc"],c["female"],c["mgr"],c["flex"],c["wcert"],c["wcert_score"],emp_uid),
                )
            # jobs
            for j in SEED_JOBS:
                cid = co_id_by_name[j["co"]]
                jid = uuid.uuid4().hex
                conn.execute(
                    "INSERT INTO job_postings(job_id,company_id,title,category_id,description,qualifications,"
                    "work_types,weekly_hours_min,weekly_hours_max,salary_type,salary_min,salary_max,"
                    "region_sido,region_sigungu,is_remote_ok,gap_track,senior_preferred,no_exp_ok,status,published_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (jid,cid,j["title"],j["cat"],j["desc"],j["qual"],
                     json.dumps(j["wtypes"]),j["wmin"],j["wmax"],j["salary_type"],j["smin"],j["smax"],
                     j["sido"],j["sigungu"],int(j["remote"]),int(j["gap"]),int(j["senior"]),int(j["noexp"]),
                     "published", now()),
                )
            print("✅ 시드 완료 — admin: admin@dasibom.kr / admin1234   demo: demo@dasibom.kr / demo1234")

# ---------------------------------------------------------------------------
# 인증
# ---------------------------------------------------------------------------
SESSION_COOKIE = "dasibom_sid"

def create_session(user_id: str) -> str:
    sid = secrets.token_urlsafe(24)
    expires = (datetime.utcnow() + timedelta(days=14)).isoformat() + "Z"
    with db() as conn:
        conn.execute("INSERT INTO sessions(session_id,user_id,expires_at) VALUES(?,?,?)",
                     (sid, user_id, expires))
    return sid

def current_user(request: Request) -> Optional[sqlite3.Row]:
    sid = request.cookies.get(SESSION_COOKIE)
    if not sid:
        return None
    with db() as conn:
        row = conn.execute(
            "SELECT u.* FROM sessions s JOIN users u ON u.user_id=s.user_id "
            "WHERE s.session_id=? AND s.expires_at > ?",
            (sid, now())
        ).fetchone()
    return row

def require_user(request: Request) -> sqlite3.Row:
    u = current_user(request)
    if not u:
        raise HTTPException(401, "로그인이 필요합니다.")
    return u

def require_role(role: str):
    def _dep(request: Request) -> sqlite3.Row:
        u = require_user(request)
        if u["role"] != role and u["role"] != "admin":
            raise HTTPException(403, f"{role} 권한이 필요합니다.")
        return u
    return _dep

# ---------------------------------------------------------------------------
# Pydantic 모델
# ---------------------------------------------------------------------------
class SignupReq(BaseModel):
    email: EmailStr
    password: str = Field(min_length=4)
    name: str
    birth_year: Optional[int] = None
    region_sido: Optional[str] = None
    region_sigungu: Optional[str] = None
    career_gap_months: int = 0
    desired_work_types: List[str] = []
    desired_weekly_hours: Optional[int] = None
    role: str = "jobseeker"

class LoginReq(BaseModel):
    email: EmailStr
    password: str

class ApplyReq(BaseModel):
    cover_letter: Optional[str] = ""

class CompanyReq(BaseModel):
    business_no: str
    name: str
    industry: Optional[str] = None
    size: Optional[str] = None
    region_sido: Optional[str] = None
    region_sigungu: Optional[str] = None
    description: Optional[str] = None
    female_ratio: Optional[float] = None
    female_mgr_ratio: Optional[float] = None
    flex_usage_ratio: Optional[float] = None
    logo_initial: Optional[str] = None

class JobReq(BaseModel):
    company_id: Optional[str] = None  # 비우면 owner의 회사
    title: str
    category_id: int
    description: str
    qualifications: Optional[str] = ""
    work_types: List[str] = []
    weekly_hours_min: Optional[int] = None
    weekly_hours_max: Optional[int] = None
    salary_type: str = "monthly"
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    region_sido: Optional[str] = None
    region_sigungu: Optional[str] = None
    is_remote_ok: bool = False
    gap_track: bool = False
    senior_preferred: bool = False
    no_exp_ok: bool = False

class StatusReq(BaseModel):
    status: str

# ---------------------------------------------------------------------------
# AI 매칭 점수 (간단 휴리스틱)
# ---------------------------------------------------------------------------
def compute_match(profile_wtypes: List[str], job_wtypes: List[str],
                  region_user: Optional[str], region_job: Optional[str],
                  remote_ok: bool) -> int:
    score = 60
    overlap = len(set(profile_wtypes) & set(job_wtypes))
    score += min(overlap * 10, 25)
    if remote_ok or (region_user and region_job and region_user == region_job):
        score += 10
    return min(max(score, 0), 100)

# ---------------------------------------------------------------------------
# FastAPI
# ---------------------------------------------------------------------------
# DB는 import 시점에 즉시 초기화 (uvicorn / TestClient 모두 동작)
init_db()

app = FastAPI(title="Dasibom Test API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

# ---------- 정적 페이지 ----------
@app.get("/")
def root():
    return RedirectResponse("/app.html")

# ---------- 인증 ----------
@app.post("/api/auth/signup")
def signup(req: SignupReq, response: Response):
    if req.role not in ("jobseeker", "employer"):
        raise HTTPException(400, "잘못된 역할입니다.")
    uid = uuid.uuid4().hex
    try:
        with db() as conn:
            conn.execute(
                "INSERT INTO users(user_id,email,password_hash,role) VALUES(?,?,?,?)",
                (uid, req.email, hash_pw(req.password), req.role),
            )
            if req.role == "jobseeker":
                conn.execute(
                    "INSERT INTO user_profiles(user_id,name,birth_year,region_sido,region_sigungu,"
                    "career_gap_months,desired_work_types,desired_weekly_hours,profile_complete_pct) "
                    "VALUES(?,?,?,?,?,?,?,?,?)",
                    (uid, req.name, req.birth_year, req.region_sido, req.region_sigungu,
                     req.career_gap_months, json.dumps(req.desired_work_types),
                     req.desired_weekly_hours, 60),
                )
    except sqlite3.IntegrityError:
        raise HTTPException(409, "이미 가입된 이메일입니다.")
    sid = create_session(uid)
    response.set_cookie(SESSION_COOKIE, sid, httponly=True, samesite="lax", max_age=14*86400)
    return {"ok": True, "user_id": uid, "role": req.role}

@app.post("/api/auth/login")
def login(req: LoginReq, response: Response):
    with db() as conn:
        row = conn.execute("SELECT * FROM users WHERE email=?", (req.email,)).fetchone()
    if not row or not verify_pw(req.password, row["password_hash"]):
        raise HTTPException(401, "이메일 또는 비밀번호가 일치하지 않습니다.")
    if row["status"] != "active":
        raise HTTPException(403, "계정이 비활성 상태입니다.")
    with db() as conn:
        conn.execute("UPDATE users SET last_login_at=? WHERE user_id=?", (now(), row["user_id"]))
    sid = create_session(row["user_id"])
    response.set_cookie(SESSION_COOKIE, sid, httponly=True, samesite="lax", max_age=14*86400)
    return {"ok": True, "user_id": row["user_id"], "role": row["role"]}

@app.post("/api/auth/logout")
def logout(response: Response, request: Request):
    sid = request.cookies.get(SESSION_COOKIE)
    if sid:
        with db() as conn:
            conn.execute("DELETE FROM sessions WHERE session_id=?", (sid,))
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}

@app.get("/api/auth/me")
def me(request: Request):
    u = current_user(request)
    if not u:
        return {"authenticated": False}
    out: dict[str, Any] = {"authenticated": True, "user_id": u["user_id"], "email": u["email"], "role": u["role"]}
    if u["role"] == "jobseeker":
        with db() as conn:
            p = conn.execute("SELECT * FROM user_profiles WHERE user_id=?", (u["user_id"],)).fetchone()
        if p:
            out["profile"] = dict(p)
            out["profile"]["desired_work_types"] = json.loads(p["desired_work_types"] or "[]")
    if u["role"] == "employer":
        with db() as conn:
            c = conn.execute("SELECT * FROM companies WHERE owner_user_id=?", (u["user_id"],)).fetchone()
        if c:
            out["company"] = dict(c)
    return out

# ---------- 카테고리 ----------
@app.get("/api/categories")
def categories():
    with db() as conn:
        rows = conn.execute("SELECT * FROM job_categories ORDER BY sort_order").fetchall()
    return [dict(r) for r in rows]

# ---------- 공고 ----------
@app.get("/api/jobs")
def list_jobs(request: Request, status: str = "published", q: str = "",
              category_id: Optional[int] = None, only_remote: bool = False,
              gap_only: bool = False, limit: int = 50):
    sql = "SELECT j.*, c.name AS company_name, c.logo_initial, c.wcert_status FROM job_postings j " \
          "JOIN companies c ON c.company_id = j.company_id WHERE 1=1"
    params: list[Any] = []
    if status != "all":
        sql += " AND j.status=?"; params.append(status)
    if q:
        sql += " AND (j.title LIKE ? OR c.name LIKE ?)"; params.extend([f"%{q}%", f"%{q}%"])
    if category_id:
        sql += " AND j.category_id=?"; params.append(category_id)
    if only_remote:
        sql += " AND j.is_remote_ok=1"
    if gap_only:
        sql += " AND j.gap_track=1"
    sql += " ORDER BY j.created_at DESC LIMIT ?"
    params.append(limit)
    with db() as conn:
        rows = conn.execute(sql, params).fetchall()
    user = current_user(request)
    profile_wtypes: list[str] = []
    user_region: Optional[str] = None
    if user and user["role"] == "jobseeker":
        with db() as conn:
            p = conn.execute("SELECT * FROM user_profiles WHERE user_id=?", (user["user_id"],)).fetchone()
        if p:
            profile_wtypes = json.loads(p["desired_work_types"] or "[]")
            user_region = p["region_sido"]
    out = []
    for r in rows:
        d = dict(r)
        d["work_types"] = json.loads(r["work_types"] or "[]")
        if user and user["role"] == "jobseeker":
            d["match_score"] = compute_match(profile_wtypes, d["work_types"], user_region, r["region_sido"], bool(r["is_remote_ok"]))
        else:
            d["match_score"] = None
        out.append(d)
    return out

@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    with db() as conn:
        r = conn.execute(
            "SELECT j.*, c.name AS company_name, c.logo_initial, c.wcert_status, c.industry "
            "FROM job_postings j JOIN companies c ON c.company_id=j.company_id WHERE job_id=?",
            (job_id,)).fetchone()
    if not r:
        raise HTTPException(404)
    with db() as conn:
        conn.execute("UPDATE job_postings SET view_count=view_count+1 WHERE job_id=?", (job_id,))
    d = dict(r)
    d["work_types"] = json.loads(r["work_types"] or "[]")
    return d

@app.post("/api/jobs")
def create_job(req: JobReq, user=Depends(require_role("employer"))):
    company_id = req.company_id
    if not company_id:
        with db() as conn:
            c = conn.execute("SELECT company_id FROM companies WHERE owner_user_id=?", (user["user_id"],)).fetchone()
        if not c:
            raise HTTPException(400, "먼저 기업을 등록하세요.")
        company_id = c["company_id"]
    jid = uuid.uuid4().hex
    with db() as conn:
        conn.execute(
            "INSERT INTO job_postings(job_id,company_id,title,category_id,description,qualifications,"
            "work_types,weekly_hours_min,weekly_hours_max,salary_type,salary_min,salary_max,"
            "region_sido,region_sigungu,is_remote_ok,gap_track,senior_preferred,no_exp_ok,status) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (jid, company_id, req.title, req.category_id, req.description, req.qualifications,
             json.dumps(req.work_types), req.weekly_hours_min, req.weekly_hours_max,
             req.salary_type, req.salary_min, req.salary_max,
             req.region_sido, req.region_sigungu,
             int(req.is_remote_ok), int(req.gap_track), int(req.senior_preferred), int(req.no_exp_ok),
             "pending_review"),
        )
    return {"ok": True, "job_id": jid, "status": "pending_review"}

@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str, user=Depends(require_user)):
    with db() as conn:
        j = conn.execute("SELECT j.*, c.owner_user_id FROM job_postings j "
                         "JOIN companies c ON c.company_id=j.company_id WHERE j.job_id=?", (job_id,)).fetchone()
        if not j:
            raise HTTPException(404)
        if user["role"] != "admin" and j["owner_user_id"] != user["user_id"]:
            raise HTTPException(403)
        conn.execute("DELETE FROM job_postings WHERE job_id=?", (job_id,))
    return {"ok": True}

# ---------- 지원 ----------
@app.post("/api/jobs/{job_id}/apply")
def apply_job(job_id: str, req: ApplyReq, user=Depends(require_role("jobseeker"))):
    with db() as conn:
        j = conn.execute("SELECT * FROM job_postings WHERE job_id=? AND status='published'", (job_id,)).fetchone()
        if not j:
            raise HTTPException(404, "공고를 찾을 수 없습니다.")
        p = conn.execute("SELECT * FROM user_profiles WHERE user_id=?", (user["user_id"],)).fetchone()
    pw = json.loads(p["desired_work_types"] or "[]") if p else []
    jw = json.loads(j["work_types"] or "[]")
    match = compute_match(pw, jw, p["region_sido"] if p else None, j["region_sido"], bool(j["is_remote_ok"]))
    aid = uuid.uuid4().hex
    try:
        with db() as conn:
            conn.execute(
                "INSERT INTO job_applications(application_id,user_id,job_id,cover_letter,ai_match_score) "
                "VALUES(?,?,?,?,?)",
                (aid, user["user_id"], job_id, req.cover_letter, match),
            )
            conn.execute("UPDATE job_postings SET apply_count=apply_count+1 WHERE job_id=?", (job_id,))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "이미 지원한 공고입니다.")
    return {"ok": True, "application_id": aid, "match_score": match}

@app.get("/api/applications/me")
def my_apps(user=Depends(require_role("jobseeker"))):
    with db() as conn:
        rows = conn.execute(
            "SELECT a.*, j.title, c.name AS company_name, c.logo_initial "
            "FROM job_applications a JOIN job_postings j ON j.job_id=a.job_id "
            "JOIN companies c ON c.company_id=j.company_id "
            "WHERE a.user_id=? ORDER BY a.applied_at DESC",
            (user["user_id"],)
        ).fetchall()
    return [dict(r) for r in rows]

@app.patch("/api/applications/{app_id}/status")
def update_app_status(app_id: str, req: StatusReq, user=Depends(require_user)):
    if user["role"] not in ("admin", "employer"):
        raise HTTPException(403)
    with db() as conn:
        conn.execute("UPDATE job_applications SET status=?, status_updated_at=? WHERE application_id=?",
                     (req.status, now(), app_id))
    return {"ok": True}

# ---------- 기업 ----------
@app.get("/api/companies")
def list_companies(wcert: Optional[str] = None):
    sql = "SELECT * FROM companies"
    params: list[Any] = []
    if wcert:
        sql += " WHERE wcert_status=?"
        params.append(wcert)
    sql += " ORDER BY created_at DESC"
    with db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]

@app.post("/api/companies")
def create_company(req: CompanyReq, user=Depends(require_role("employer"))):
    with db() as conn:
        existed = conn.execute("SELECT 1 FROM companies WHERE owner_user_id=?", (user["user_id"],)).fetchone()
        if existed:
            raise HTTPException(409, "이미 등록한 기업이 있습니다.")
    cid = uuid.uuid4().hex
    try:
        with db() as conn:
            conn.execute(
                "INSERT INTO companies(company_id,business_no,name,logo_initial,industry,size,region_sido,region_sigungu,"
                "description,female_ratio,female_mgr_ratio,flex_usage_ratio,owner_user_id) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (cid, req.business_no, req.name, (req.logo_initial or req.name[:1]),
                 req.industry, req.size, req.region_sido, req.region_sigungu, req.description,
                 req.female_ratio, req.female_mgr_ratio, req.flex_usage_ratio, user["user_id"]),
            )
    except sqlite3.IntegrityError:
        raise HTTPException(409, "이미 등록된 사업자번호입니다.")
    return {"ok": True, "company_id": cid}

@app.patch("/api/companies/{cid}/wcert")
def update_wcert(cid: str, req: StatusReq, user=Depends(require_role("admin"))):
    if req.status not in ("applied","under_review","approved","rejected","revoked"):
        raise HTTPException(400, "잘못된 상태값")
    with db() as conn:
        conn.execute("UPDATE companies SET wcert_status=? WHERE company_id=?", (req.status, cid))
    return {"ok": True}

@app.delete("/api/companies/{cid}")
def delete_company(cid: str, user=Depends(require_role("admin"))):
    with db() as conn:
        conn.execute("DELETE FROM companies WHERE company_id=?", (cid,))
    return {"ok": True}

# ---------- 관리자: 통계/회원/공고 ----------
@app.get("/api/admin/stats")
def admin_stats(user=Depends(require_role("admin"))):
    with db() as conn:
        u_cnt = conn.execute("SELECT COUNT(*) c FROM users WHERE role='jobseeker'").fetchone()["c"]
        c_cnt = conn.execute("SELECT COUNT(*) c FROM companies").fetchone()["c"]
        wc_cnt = conn.execute("SELECT COUNT(*) c FROM companies WHERE wcert_status='approved'").fetchone()["c"]
        j_cnt = conn.execute("SELECT COUNT(*) c FROM job_postings WHERE status='published'").fetchone()["c"]
        pend_cnt = conn.execute("SELECT COUNT(*) c FROM job_postings WHERE status='pending_review'").fetchone()["c"]
        ap_cnt = conn.execute("SELECT COUNT(*) c FROM job_applications").fetchone()["c"]
        passed = conn.execute("SELECT COUNT(*) c FROM job_applications WHERE status='final_passed'").fetchone()["c"]
        rep_cnt = conn.execute("SELECT COUNT(*) c FROM reports WHERE status='received'").fetchone()["c"]
    return {"jobseekers": u_cnt, "companies": c_cnt, "wcert_approved": wc_cnt,
            "jobs_published": j_cnt, "jobs_pending": pend_cnt,
            "applications": ap_cnt, "final_passed": passed, "reports_open": rep_cnt}

@app.get("/api/admin/users")
def admin_users(user=Depends(require_role("admin"))):
    with db() as conn:
        rows = conn.execute(
            "SELECT u.user_id,u.email,u.role,u.status,u.created_at,u.last_login_at,"
            "p.name,p.region_sido,p.region_sigungu,p.career_gap_months,p.profile_complete_pct "
            "FROM users u LEFT JOIN user_profiles p ON p.user_id=u.user_id ORDER BY u.created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]

@app.patch("/api/admin/users/{uid}/status")
def admin_user_status(uid: str, req: StatusReq, user=Depends(require_role("admin"))):
    with db() as conn:
        conn.execute("UPDATE users SET status=? WHERE user_id=?", (req.status, uid))
    return {"ok": True}

@app.delete("/api/admin/users/{uid}")
def admin_user_delete(uid: str, user=Depends(require_role("admin"))):
    with db() as conn:
        conn.execute("DELETE FROM users WHERE user_id=?", (uid,))
    return {"ok": True}

@app.get("/api/admin/jobs")
def admin_jobs(user=Depends(require_role("admin")), status: str = "all"):
    sql = ("SELECT j.*, c.name AS company_name, c.logo_initial FROM job_postings j "
           "JOIN companies c ON c.company_id=j.company_id")
    params: list[Any] = []
    if status != "all":
        sql += " WHERE j.status=?"; params.append(status)
    sql += " ORDER BY j.created_at DESC"
    with db() as conn:
        rows = conn.execute(sql, params).fetchall()
    out = []
    for r in rows:
        d = dict(r); d["work_types"] = json.loads(r["work_types"] or "[]")
        out.append(d)
    return out

@app.patch("/api/admin/jobs/{jid}/status")
def admin_job_status(jid: str, req: StatusReq, user=Depends(require_role("admin"))):
    if req.status not in ("draft","pending_review","published","closed","rejected","expired"):
        raise HTTPException(400)
    extra = ""
    params = [req.status]
    if req.status == "published":
        extra = ", published_at=?"; params.append(now())
    params.append(jid)
    with db() as conn:
        conn.execute(f"UPDATE job_postings SET status=?{extra} WHERE job_id=?", params)
    return {"ok": True}

@app.get("/api/admin/applications")
def admin_apps(user=Depends(require_role("admin"))):
    with db() as conn:
        rows = conn.execute(
            "SELECT a.*, j.title, c.name AS company_name, p.name AS applicant_name, u.email "
            "FROM job_applications a "
            "JOIN job_postings j ON j.job_id=a.job_id "
            "JOIN companies c ON c.company_id=j.company_id "
            "LEFT JOIN user_profiles p ON p.user_id=a.user_id "
            "JOIN users u ON u.user_id=a.user_id "
            "ORDER BY a.applied_at DESC LIMIT 100"
        ).fetchall()
    return [dict(r) for r in rows]

# ---------- 신고 ----------
@app.post("/api/reports")
def create_report(target_type: str, target_id: str, reason_code: str, detail: str = "",
                  user=Depends(require_user)):
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO reports(reporter_id,target_type,target_id,reason_code,detail) VALUES(?,?,?,?,?)",
            (user["user_id"], target_type, target_id, reason_code, detail),
        )
        rid = cur.lastrowid
    return {"ok": True, "report_id": rid}

@app.get("/api/admin/reports")
def admin_reports(user=Depends(require_role("admin"))):
    with db() as conn:
        rows = conn.execute("SELECT * FROM reports ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]

@app.patch("/api/admin/reports/{rid}/status")
def admin_report_status(rid: int, req: StatusReq, user=Depends(require_role("admin"))):
    with db() as conn:
        conn.execute("UPDATE reports SET status=? WHERE report_id=?", (req.status, rid))
    return {"ok": True}

# ---------- 정적 파일 (HTML/JS) ----------
# /로 접근 시 app.html. 다른 정적 파일은 직접 경로로 접근.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/{filename}")
def serve_html(filename: str):
    if not (filename.endswith(".html") or filename.endswith(".css") or filename.endswith(".js")):
        raise HTTPException(404)
    fp = STATIC_DIR / filename
    if not fp.exists():
        raise HTTPException(404)
    return FileResponse(fp)

# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run("server:app", host=host, port=port, reload=False)
