-- ============================================================================
-- 다시봄 (Dasibom) - 중년여성 전용 커리어 리스타트 플랫폼
-- Database Schema (PostgreSQL 15+)
-- ----------------------------------------------------------------------------
-- 도메인 구성
--   1) 회원 (users, user_profiles, user_career_history, user_strengths)
--   2) 기업 (companies, company_admins)
--   3) W-Cert 인증 (wcert_applications, wcert_criteria_scores, wcert_reviews)
--   4) 채용공고 (job_postings, job_tags, saved_jobs)
--   5) 지원/매칭 (job_applications, application_status_logs, ai_match_scores)
--   6) 커리어 코칭 (ai_diagnoses, courses, course_enrollments, mentors, mentoring_sessions)
--   7) 운영 (admin_users, notifications, reports, audit_logs)
-- ============================================================================

-- ============================================================================
-- 0. EXTENSIONS & ENUMS
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- 검색 인덱스

-- 회원 상태
CREATE TYPE user_status     AS ENUM ('active','dormant','suspended','withdrawn');
CREATE TYPE user_role       AS ENUM ('jobseeker','employer','mentor','admin');

-- 근무 형태
CREATE TYPE work_type       AS ENUM ('full_time','part_time','flex_time','remote','hybrid','project','onsite');

-- 채용공고 상태
CREATE TYPE job_status      AS ENUM ('draft','pending_review','published','closed','rejected','expired');

-- 지원 상태 (단계별 상태머신)
CREATE TYPE application_status AS ENUM (
  'submitted',          -- 지원 완료
  'screening',          -- 서류 검토중
  'document_passed',    -- 서류 합격
  'interview_scheduled',-- 면접 예정
  'interview_done',     -- 면접 완료
  'final_passed',       -- 최종 합격
  'rejected',           -- 불합격
  'withdrawn',          -- 지원 취소
  'offer_accepted',     -- 입사 수락
  'offer_declined'      -- 입사 거절
);

-- W-Cert 인증 상태
CREATE TYPE wcert_status    AS ENUM ('applied','under_review','approved','rejected','expired','revoked');

-- 기업 규모
CREATE TYPE company_size    AS ENUM ('startup','small','medium','large','enterprise');

-- 알림 타입
CREATE TYPE noti_type       AS ENUM ('match','application','interview','course','mentor','system');

-- 신고 타입/상태
CREATE TYPE report_target   AS ENUM ('job_posting','company','user','review','message');
CREATE TYPE report_status   AS ENUM ('received','investigating','resolved','rejected');


-- ============================================================================
-- 1. 회원 (구직자 중심)
-- ============================================================================

-- 1-1. 통합 인증 계정 (구직자/기업담당자/멘토 공통)
CREATE TABLE users (
  user_id           UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
  email             VARCHAR(255)    NOT NULL UNIQUE,
  password_hash     VARCHAR(255)    NOT NULL,
  phone             VARCHAR(20)     UNIQUE,
  role              user_role       NOT NULL DEFAULT 'jobseeker',
  status            user_status     NOT NULL DEFAULT 'active',
  email_verified_at TIMESTAMPTZ,
  phone_verified_at TIMESTAMPTZ,
  last_login_at     TIMESTAMPTZ,
  marketing_opt_in  BOOLEAN         NOT NULL DEFAULT FALSE,
  created_at        TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
  deleted_at        TIMESTAMPTZ
);
CREATE INDEX idx_users_role_status ON users(role, status);

-- 1-2. 구직자 상세 프로필
CREATE TABLE user_profiles (
  profile_id            UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id               UUID         NOT NULL UNIQUE REFERENCES users(user_id) ON DELETE CASCADE,
  name                  VARCHAR(50)  NOT NULL,
  birth_year            INTEGER      CHECK (birth_year BETWEEN 1940 AND 2010),
  region_sido           VARCHAR(20),                 -- 서울/경기/...
  region_sigungu        VARCHAR(40),                 -- 강남구/분당구/...
  career_gap_months     INTEGER      NOT NULL DEFAULT 0 CHECK (career_gap_months >= 0),
  desired_work_types    work_type[]  NOT NULL DEFAULT '{}',  -- 다중 선호
  desired_weekly_hours  INTEGER      CHECK (desired_weekly_hours BETWEEN 0 AND 60),
  desired_start_date    DATE,
  bio                   TEXT,
  avatar_url            TEXT,
  profile_complete_pct  SMALLINT     NOT NULL DEFAULT 0 CHECK (profile_complete_pct BETWEEN 0 AND 100),
  created_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_profiles_region ON user_profiles(region_sido, region_sigungu);

-- 1-3. 이전 경력 (단절 이전 경력)
CREATE TABLE user_career_history (
  career_id        BIGSERIAL    PRIMARY KEY,
  user_id          UUID         NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  company_name     VARCHAR(120) NOT NULL,
  job_title        VARCHAR(120) NOT NULL,
  job_category_id  INTEGER      REFERENCES job_categories(category_id) DEFERRABLE INITIALLY DEFERRED,
  start_date       DATE         NOT NULL,
  end_date         DATE,
  description      TEXT,
  is_current       BOOLEAN      NOT NULL DEFAULT FALSE,
  created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_career_user ON user_career_history(user_id);

-- 1-4. 단절 기간 경험 (AI 강점 환산용 - 가사/봉사/학습/육아 등)
CREATE TABLE user_gap_experiences (
  exp_id          BIGSERIAL    PRIMARY KEY,
  user_id         UUID         NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  experience_type VARCHAR(40)  NOT NULL,  -- 'household','volunteer','study','childcare','side_project'
  title           VARCHAR(120) NOT NULL,
  description     TEXT,
  start_date      DATE,
  end_date        DATE,
  derived_skills  TEXT[],                  -- AI가 추출한 강점 키워드
  created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_gap_user ON user_gap_experiences(user_id);

-- 1-5. 강점 점수 (AI 진단 산출)
CREATE TABLE user_strengths (
  user_id          UUID         PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
  strength_score   SMALLINT     NOT NULL DEFAULT 0 CHECK (strength_score BETWEEN 0 AND 100),
  top_keywords     TEXT[]       NOT NULL DEFAULT '{}',
  digital_score    SMALLINT     CHECK (digital_score BETWEEN 0 AND 100),
  comm_score       SMALLINT     CHECK (comm_score BETWEEN 0 AND 100),
  detail_score     SMALLINT     CHECK (detail_score BETWEEN 0 AND 100),
  leadership_score SMALLINT     CHECK (leadership_score BETWEEN 0 AND 100),
  last_evaluated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ============================================================================
-- 2. 기업
-- ============================================================================

CREATE TABLE companies (
  company_id        UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
  business_no       VARCHAR(20)     NOT NULL UNIQUE,    -- 사업자등록번호
  name              VARCHAR(120)    NOT NULL,
  logo_url          TEXT,
  industry          VARCHAR(60),
  size              company_size,
  homepage_url      TEXT,
  description       TEXT,
  region_sido       VARCHAR(20),
  region_sigungu    VARCHAR(40),
  address_detail    VARCHAR(200),
  female_ratio      NUMERIC(4,1),                       -- 여성 직원 비율 %
  female_mgr_ratio  NUMERIC(4,1),                       -- 관리직 여성 비율 %
  flex_usage_ratio  NUMERIC(4,1),                       -- 유연근무 실사용률 %
  wcert_status      wcert_status    NOT NULL DEFAULT 'applied',
  wcert_score       NUMERIC(4,2)    CHECK (wcert_score BETWEEN 0 AND 5),
  wcert_issued_at   TIMESTAMPTZ,
  wcert_expires_at  TIMESTAMPTZ,
  created_at        TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_companies_wcert ON companies(wcert_status);
CREATE INDEX idx_companies_region ON companies(region_sido, region_sigungu);
CREATE INDEX idx_companies_name_trgm ON companies USING gin (name gin_trgm_ops);

-- 기업 담당자 (1:N)
CREATE TABLE company_admins (
  ca_id        BIGSERIAL    PRIMARY KEY,
  company_id   UUID         NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
  user_id      UUID         NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  role         VARCHAR(20)  NOT NULL DEFAULT 'manager',  -- owner | manager | viewer
  created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  UNIQUE(company_id, user_id)
);


-- ============================================================================
-- 3. W-Cert 인증 시스템
-- ============================================================================

CREATE TABLE wcert_applications (
  app_id            BIGSERIAL       PRIMARY KEY,
  company_id        UUID            NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
  status            wcert_status    NOT NULL DEFAULT 'applied',
  submitted_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
  reviewed_at       TIMESTAMPTZ,
  reviewed_by       UUID            REFERENCES users(user_id),
  reviewer_comment  TEXT,
  evidence_docs     JSONB           NOT NULL DEFAULT '[]'::jsonb,  -- [{name,url,uploaded_at}]
  total_score       NUMERIC(4,2),
  created_at        TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_wcert_app_status ON wcert_applications(status, submitted_at DESC);

-- 6가지 정량 기준별 점수
CREATE TABLE wcert_criteria_scores (
  cs_id          BIGSERIAL    PRIMARY KEY,
  app_id         BIGINT       NOT NULL REFERENCES wcert_applications(app_id) ON DELETE CASCADE,
  criterion_code VARCHAR(40)  NOT NULL,   -- 'flex_usage','female_mgr','gap_track','leave_usage','pay_gap','review_score'
  raw_value      NUMERIC(10,2),
  score          NUMERIC(4,2) NOT NULL,    -- 0~5
  passed         BOOLEAN      NOT NULL DEFAULT FALSE,
  evaluated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  UNIQUE(app_id, criterion_code)
);

-- 재직 여성 익명 평가
CREATE TABLE wcert_reviews (
  review_id      BIGSERIAL    PRIMARY KEY,
  company_id     UUID         NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
  user_hash      VARCHAR(64)  NOT NULL,  -- 익명: SHA256(user_id+salt) 만 저장
  rating_overall NUMERIC(2,1) NOT NULL CHECK (rating_overall BETWEEN 1 AND 5),
  rating_flex    NUMERIC(2,1) CHECK (rating_flex BETWEEN 1 AND 5),
  rating_growth  NUMERIC(2,1) CHECK (rating_growth BETWEEN 1 AND 5),
  rating_culture NUMERIC(2,1) CHECK (rating_culture BETWEEN 1 AND 5),
  pros           TEXT,
  cons           TEXT,
  tenure_months  INTEGER,
  is_visible     BOOLEAN      NOT NULL DEFAULT TRUE,
  created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  UNIQUE(company_id, user_hash)
);
CREATE INDEX idx_wcert_reviews_company ON wcert_reviews(company_id);


-- ============================================================================
-- 4. 채용공고
-- ============================================================================

-- 직군 마스터 (사무/행정, 교육/돌봄, 디지털, 서비스, 전문직 등)
CREATE TABLE job_categories (
  category_id   SERIAL       PRIMARY KEY,
  parent_id     INTEGER      REFERENCES job_categories(category_id),
  code          VARCHAR(40)  NOT NULL UNIQUE,
  name_ko       VARCHAR(60)  NOT NULL,
  sort_order    INTEGER      NOT NULL DEFAULT 0,
  is_active     BOOLEAN      NOT NULL DEFAULT TRUE
);

-- 채용공고 본체
CREATE TABLE job_postings (
  job_id            UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
  company_id        UUID         NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
  title             VARCHAR(200) NOT NULL,
  category_id       INTEGER      NOT NULL REFERENCES job_categories(category_id),
  description       TEXT         NOT NULL,
  responsibilities  TEXT,
  qualifications    TEXT,
  preferred         TEXT,
  benefits          TEXT,

  -- 유연근무 정책 (다시봄 필수)
  work_types        work_type[]  NOT NULL CHECK (cardinality(work_types) > 0),
  weekly_hours_min  INTEGER      CHECK (weekly_hours_min BETWEEN 0 AND 60),
  weekly_hours_max  INTEGER      CHECK (weekly_hours_max BETWEEN 0 AND 60),
  work_start_time   TIME,
  work_end_time     TIME,
  remote_ratio_pct  SMALLINT     CHECK (remote_ratio_pct BETWEEN 0 AND 100),
  school_schedule   BOOLEAN      NOT NULL DEFAULT FALSE,    -- 학사일정 맞춤

  -- 보수
  salary_type       VARCHAR(20)  NOT NULL,        -- annual | monthly | hourly
  salary_min        INTEGER,
  salary_max        INTEGER,
  salary_currency   VARCHAR(3)   NOT NULL DEFAULT 'KRW',

  -- 위치
  region_sido       VARCHAR(20),
  region_sigungu    VARCHAR(40),
  is_remote_ok      BOOLEAN      NOT NULL DEFAULT FALSE,

  -- 우대/타깃
  gap_track         BOOLEAN      NOT NULL DEFAULT FALSE,    -- 경력단절 채용트랙
  senior_preferred  BOOLEAN      NOT NULL DEFAULT FALSE,    -- 50세 이상 우대
  no_exp_ok         BOOLEAN      NOT NULL DEFAULT FALSE,    -- 무경력 OK

  -- 상태
  status            job_status   NOT NULL DEFAULT 'draft',
  reviewed_by       UUID         REFERENCES users(user_id),
  reviewed_at       TIMESTAMPTZ,
  reject_reason     TEXT,

  published_at      TIMESTAMPTZ,
  expires_at        TIMESTAMPTZ,
  view_count        INTEGER      NOT NULL DEFAULT 0,
  apply_count       INTEGER      NOT NULL DEFAULT 0,

  created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

  CHECK (weekly_hours_max IS NULL OR weekly_hours_min IS NULL OR weekly_hours_max >= weekly_hours_min),
  CHECK (salary_max IS NULL OR salary_min IS NULL OR salary_max >= salary_min)
);
CREATE INDEX idx_job_status_pub   ON job_postings(status, published_at DESC);
CREATE INDEX idx_job_company      ON job_postings(company_id);
CREATE INDEX idx_job_category     ON job_postings(category_id);
CREATE INDEX idx_job_region       ON job_postings(region_sido, region_sigungu);
CREATE INDEX idx_job_title_trgm   ON job_postings USING gin (title gin_trgm_ops);

-- 공고 태그 (자유 라벨)
CREATE TABLE job_tags (
  tag_id   SERIAL       PRIMARY KEY,
  label    VARCHAR(40)  NOT NULL UNIQUE
);
CREATE TABLE job_posting_tags (
  job_id  UUID    NOT NULL REFERENCES job_postings(job_id) ON DELETE CASCADE,
  tag_id  INTEGER NOT NULL REFERENCES job_tags(tag_id) ON DELETE CASCADE,
  PRIMARY KEY (job_id, tag_id)
);

-- 관심 공고
CREATE TABLE saved_jobs (
  user_id    UUID         NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  job_id     UUID         NOT NULL REFERENCES job_postings(job_id) ON DELETE CASCADE,
  saved_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  PRIMARY KEY (user_id, job_id)
);


-- ============================================================================
-- 5. 지원/매칭
-- ============================================================================

CREATE TABLE job_applications (
  application_id   UUID                 PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id          UUID                 NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  job_id           UUID                 NOT NULL REFERENCES job_postings(job_id) ON DELETE CASCADE,
  status           application_status   NOT NULL DEFAULT 'submitted',
  cover_letter     TEXT,
  resume_snapshot  JSONB,                -- 지원 시점 이력서 스냅샷
  ai_match_score   SMALLINT             CHECK (ai_match_score BETWEEN 0 AND 100),
  applied_at       TIMESTAMPTZ          NOT NULL DEFAULT NOW(),
  status_updated_at TIMESTAMPTZ         NOT NULL DEFAULT NOW(),
  feedback         TEXT,                 -- 합/불합격 피드백
  UNIQUE(user_id, job_id)
);
CREATE INDEX idx_apps_user_status ON job_applications(user_id, status);
CREATE INDEX idx_apps_job_status  ON job_applications(job_id, status);
CREATE INDEX idx_apps_applied_at  ON job_applications(applied_at DESC);

-- 지원 상태 변경 이력 (감사·통계용)
CREATE TABLE application_status_logs (
  log_id          BIGSERIAL           PRIMARY KEY,
  application_id  UUID                NOT NULL REFERENCES job_applications(application_id) ON DELETE CASCADE,
  from_status     application_status,
  to_status       application_status  NOT NULL,
  changed_by      UUID                REFERENCES users(user_id),
  changed_at      TIMESTAMPTZ         NOT NULL DEFAULT NOW(),
  memo            TEXT
);
CREATE INDEX idx_app_logs_app ON application_status_logs(application_id, changed_at DESC);

-- AI 매칭 점수 캐시 (배치 산출 → 추천 페이지에 즉시 노출)
CREATE TABLE ai_match_scores (
  user_id        UUID         NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  job_id         UUID         NOT NULL REFERENCES job_postings(job_id) ON DELETE CASCADE,
  match_score    SMALLINT     NOT NULL CHECK (match_score BETWEEN 0 AND 100),
  reasons        JSONB        NOT NULL DEFAULT '[]'::jsonb,
  computed_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  PRIMARY KEY (user_id, job_id)
);
CREATE INDEX idx_match_score_user ON ai_match_scores(user_id, match_score DESC);


-- ============================================================================
-- 6. 커리어 코칭 / 리스킬링 / 멘토링
-- ============================================================================

-- AI 진단 결과
CREATE TABLE ai_diagnoses (
  diag_id         BIGSERIAL    PRIMARY KEY,
  user_id         UUID         NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  taken_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  raw_input       JSONB        NOT NULL,   -- 입력 폼 원본
  result_summary  JSONB        NOT NULL,   -- {strength_score, top_jobs, recommended_courses, advice}
  llm_version     VARCHAR(40)
);
CREATE INDEX idx_diag_user_time ON ai_diagnoses(user_id, taken_at DESC);

-- 리스킬링 과정
CREATE TABLE courses (
  course_id        UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
  title            VARCHAR(200) NOT NULL,
  provider         VARCHAR(120),
  category_id      INTEGER      REFERENCES job_categories(category_id),
  total_hours      SMALLINT     NOT NULL,
  is_free          BOOLEAN      NOT NULL DEFAULT TRUE,
  certificate      BOOLEAN      NOT NULL DEFAULT TRUE,
  match_boost_pct  SMALLINT     NOT NULL DEFAULT 0,    -- 수료 시 매칭률 가산
  description      TEXT,
  thumbnail_url    TEXT,
  is_active        BOOLEAN      NOT NULL DEFAULT TRUE,
  created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_courses_active ON courses(is_active, category_id);

-- 수강 내역
CREATE TABLE course_enrollments (
  enrollment_id   BIGSERIAL    PRIMARY KEY,
  user_id         UUID         NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  course_id       UUID         NOT NULL REFERENCES courses(course_id) ON DELETE CASCADE,
  enrolled_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  completed_hours SMALLINT     NOT NULL DEFAULT 0,
  completed_at    TIMESTAMPTZ,
  certificate_url TEXT,
  UNIQUE(user_id, course_id)
);

-- 멘토 (users.role='mentor')
CREATE TABLE mentors (
  user_id         UUID         PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
  display_name    VARCHAR(80)  NOT NULL,
  title           VARCHAR(160),                -- 前 LG 사무관리 12년 등
  expertise_tags  TEXT[]       NOT NULL DEFAULT '{}',
  bio             TEXT,
  is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
  hourly_fee_krw  INTEGER      NOT NULL DEFAULT 0,
  free_first      BOOLEAN      NOT NULL DEFAULT TRUE,
  rating_avg      NUMERIC(2,1) NOT NULL DEFAULT 0,
  session_count   INTEGER      NOT NULL DEFAULT 0,
  created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- 멘토링 세션
CREATE TABLE mentoring_sessions (
  session_id    BIGSERIAL    PRIMARY KEY,
  mentor_id     UUID         NOT NULL REFERENCES mentors(user_id) ON DELETE CASCADE,
  mentee_id     UUID         NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  scheduled_at  TIMESTAMPTZ  NOT NULL,
  duration_min  SMALLINT     NOT NULL DEFAULT 30,
  status        VARCHAR(20)  NOT NULL DEFAULT 'requested',  -- requested|confirmed|done|cancelled|noshow
  meet_url      TEXT,
  topic         VARCHAR(200),
  rating        SMALLINT     CHECK (rating BETWEEN 1 AND 5),
  review        TEXT,
  created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_mentoring_mentee ON mentoring_sessions(mentee_id, scheduled_at DESC);
CREATE INDEX idx_mentoring_mentor ON mentoring_sessions(mentor_id, scheduled_at DESC);


-- ============================================================================
-- 7. 운영 (관리자/알림/신고/감사)
-- ============================================================================

-- 관리자 (users.role='admin' 와 매핑되는 권한 테이블)
CREATE TABLE admin_users (
  user_id      UUID         PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
  level        VARCHAR(20)  NOT NULL DEFAULT 'ops',   -- super | ops | reviewer
  permissions  JSONB        NOT NULL DEFAULT '[]'::jsonb,
  created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- 알림
CREATE TABLE notifications (
  noti_id      BIGSERIAL    PRIMARY KEY,
  user_id      UUID         NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  type         noti_type    NOT NULL,
  title        VARCHAR(200) NOT NULL,
  body         TEXT,
  link_url     TEXT,
  is_read      BOOLEAN      NOT NULL DEFAULT FALSE,
  created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  read_at      TIMESTAMPTZ
);
CREATE INDEX idx_noti_user_unread ON notifications(user_id, is_read, created_at DESC);

-- 신고
CREATE TABLE reports (
  report_id      BIGSERIAL      PRIMARY KEY,
  reporter_id    UUID           REFERENCES users(user_id) ON DELETE SET NULL,
  target_type    report_target  NOT NULL,
  target_id      VARCHAR(64)    NOT NULL,
  reason_code    VARCHAR(40)    NOT NULL,    -- 'fake_job','discrimination','spam','harassment','other'
  detail         TEXT,
  status         report_status  NOT NULL DEFAULT 'received',
  handled_by     UUID           REFERENCES users(user_id),
  handled_at     TIMESTAMPTZ,
  resolution     TEXT,
  created_at     TIMESTAMPTZ    NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_reports_status ON reports(status, created_at DESC);
CREATE INDEX idx_reports_target ON reports(target_type, target_id);

-- 감사 로그
CREATE TABLE audit_logs (
  log_id      BIGSERIAL    PRIMARY KEY,
  actor_id    UUID         REFERENCES users(user_id),
  action      VARCHAR(80)  NOT NULL,
  entity      VARCHAR(40)  NOT NULL,
  entity_id   VARCHAR(64),
  diff        JSONB,
  ip_address  INET,
  user_agent  TEXT,
  created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_audit_actor_time ON audit_logs(actor_id, created_at DESC);
CREATE INDEX idx_audit_entity     ON audit_logs(entity, entity_id);


-- ============================================================================
-- 8. 트리거 (updated_at 자동 갱신)
-- ============================================================================
CREATE OR REPLACE FUNCTION trg_set_updated_at() RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER t_users_upd          BEFORE UPDATE ON users          FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();
CREATE TRIGGER t_profiles_upd       BEFORE UPDATE ON user_profiles  FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();
CREATE TRIGGER t_companies_upd      BEFORE UPDATE ON companies      FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();
CREATE TRIGGER t_jobs_upd           BEFORE UPDATE ON job_postings   FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();


-- ============================================================================
-- 9. 운영용 뷰 (관리자 대시보드 KPI)
-- ============================================================================

-- 일별 가입자 수
CREATE OR REPLACE VIEW v_daily_signups AS
SELECT date_trunc('day', created_at)::date AS d,
       COUNT(*) FILTER (WHERE role='jobseeker') AS jobseeker_cnt,
       COUNT(*) FILTER (WHERE role='employer')  AS employer_cnt
FROM users
GROUP BY 1
ORDER BY 1 DESC;

-- 공고 매칭/지원 KPI
CREATE OR REPLACE VIEW v_job_kpi AS
SELECT
  j.job_id,
  j.title,
  c.name           AS company_name,
  j.view_count,
  j.apply_count,
  COUNT(a.application_id)                                         AS total_apps,
  COUNT(*) FILTER (WHERE a.status='final_passed')                 AS hired_cnt,
  AVG(a.ai_match_score)                                           AS avg_match
FROM job_postings j
LEFT JOIN companies c       ON c.company_id     = j.company_id
LEFT JOIN job_applications a ON a.job_id        = j.job_id
GROUP BY j.job_id, j.title, c.name, j.view_count, j.apply_count;

-- W-Cert 심사 대기열
CREATE OR REPLACE VIEW v_wcert_queue AS
SELECT a.app_id, c.name AS company_name, c.business_no,
       a.status, a.submitted_at, a.total_score,
       EXTRACT(DAY FROM NOW()-a.submitted_at) AS waiting_days
FROM wcert_applications a
JOIN companies c ON c.company_id = a.company_id
WHERE a.status IN ('applied','under_review')
ORDER BY a.submitted_at ASC;


-- ============================================================================
-- 10. 시드 데이터 (마스터 카테고리만)
-- ============================================================================

INSERT INTO job_categories (parent_id, code, name_ko, sort_order) VALUES
 (NULL, 'office',     '사무/행정',           1),
 (NULL, 'education',  '교육/돌봄',           2),
 (NULL, 'digital',    '디지털/온라인',       3),
 (NULL, 'service',    '서비스/판매',         4),
 (NULL, 'specialty',  '전문직',              5),
 (NULL, 'creative',   '크리에이티브',        6),
 (NULL, 'health',     '의료/건강',           7);

-- ============================================================================
-- END
-- ============================================================================
