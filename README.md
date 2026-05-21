# 다시봄 (Dasibom) — 테스트 서버 가이드

중년여성 전용 커리어 리스타트 플랫폼 **라이브 데모**입니다.
회원가입 → 공고 지원 → 기업 등록 → 관리자 승인까지 전체 흐름이 실제 DB(SQLite)에 저장됩니다.

## 1. 필요한 것
- Python 3.10 이상 (macOS는 기본 탑재)

## 2. 설치 & 실행

터미널에서 프로젝트 폴더로 이동 후:

```bash
# 1) 필요한 라이브러리 설치 (최초 1회)
pip3 install -r requirements.txt

# 2) 서버 실행
python3 server.py
```

콘솔에 다음 메시지가 보이면 성공입니다.

```
✨ 첫 실행: 시드 데이터 주입 중...
✅ 시드 완료 — admin: admin@dasibom.kr / admin1234   demo: demo@dasibom.kr / demo1234
INFO:     Uvicorn running on http://127.0.0.1:8000
```

## 3. 페이지 접속

| 페이지 | 주소 | 용도 |
|---|---|---|
| 구직자 | http://localhost:8000/app.html | 회원가입·공고검색·지원·마이페이지 |
| 기업 | http://localhost:8000/employer.html | 기업 등록·공고 등록·관리 |
| 관리자 | http://localhost:8000/admin_live.html | 회원·기업·공고·신고 CRUD |
| API Docs | http://localhost:8000/docs | Swagger UI (모든 엔드포인트 확인) |

## 4. 데모 계정

| 역할 | 이메일 | 비밀번호 |
|---|---|---|
| 관리자 | admin@dasibom.kr | admin1234 |
| 구직자 (데모) | demo@dasibom.kr | demo1234 |

기업 계정은 직접 회원가입 후 사용하세요.

## 5. 빠른 테스트 시나리오

1. **구직자**: app.html → `회원가입` → 공고 카드 클릭 → 자기소개 작성 → `지원하기`
2. **기업**: employer.html → 기업 회원가입 → 기업 정보 등록 → 공고 등록 (검토 대기 상태)
3. **관리자**: admin_live.html → 로그인 → 공고 관리에서 검토 대기 공고 `승인` → 구직자가 다시 검색하면 표시됨

## 6. 데이터

- DB 파일: `dasibom.db` (SQLite, 자동 생성)
- 초기화하려면 서버 종료 후 `dasibom.db` 삭제 → 재실행하면 시드 데이터가 재생성됩니다.

## 7. 파일 구조

```
.
├── server.py            # FastAPI 서버 + DB 자동 초기화/시드
├── requirements.txt     # 의존성 (fastapi, uvicorn, pydantic[email])
├── dasibom_schema.sql   # PostgreSQL용 정식 스키마 (참고용)
├── dasibom.html         # 디자인 프로토타입 (정적)
├── dasibom_admin.html   # 관리자 디자인 프로토타입 (정적)
├── app.html             # ★ 구직자 라이브 페이지 (API 연동)
├── employer.html        # ★ 기업 라이브 페이지 (API 연동)
├── admin_live.html      # ★ 관리자 라이브 페이지 (API 연동)
└── dasibom.db           # SQLite DB (자동 생성)
```

## 8. 주요 API 엔드포인트

| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | /api/auth/signup | 회원가입 (jobseeker / employer) |
| POST | /api/auth/login | 로그인 (세션 쿠키) |
| POST | /api/auth/logout | 로그아웃 |
| GET  | /api/auth/me | 내 정보 + 프로필/회사 |
| GET  | /api/jobs | 공고 목록 (검색·필터·AI 매칭점수) |
| POST | /api/jobs | 공고 등록 (기업 권한) |
| POST | /api/jobs/{id}/apply | 공고 지원 (구직자) |
| GET  | /api/applications/me | 내 지원 내역 |
| POST | /api/companies | 기업 등록 |
| PATCH | /api/companies/{id}/wcert | W-Cert 상태 변경 (관리자) |
| GET  | /api/admin/stats | 관리자 KPI |
| GET  | /api/admin/users | 회원 목록 (관리자) |
| PATCH | /api/admin/jobs/{id}/status | 공고 승인/반려 (관리자) |
