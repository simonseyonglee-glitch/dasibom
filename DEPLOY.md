# 다시봄 인터넷 배포 가이드 (Render.com · 무료)

이 가이드대로 따라 하면 약 **15분** 안에 `https://dasibom-xxxx.onrender.com` 형태의 실제 인터넷 주소로 다시봄이 공개됩니다.

---

## 준비물

1. GitHub 계정 (https://github.com — 없으면 무료 가입, 1분 소요)
2. Render 계정 (https://render.com — 없으면 무료 가입, GitHub 계정으로 로그인 가능)

---

## 1단계 · GitHub에 코드 올리기

### 방법 A · 웹 업로드 (가장 쉬움, 터미널 불필요)

1. GitHub.com 로그인 → 오른쪽 위 `＋` 아이콘 → **New repository**
2. Repository name: `dasibom` (원하는 이름 가능)
3. Public 또는 Private 선택 → **Create repository**
4. 생성된 빈 저장소 페이지에서 `uploading an existing file` 링크 클릭
5. **프로젝트 폴더 안의 모든 파일을 드래그&드롭으로 업로드**
   - 단, `dasibom.db` 와 `__pycache__/` 폴더는 올리지 마세요 (`.gitignore`에 이미 포함됨)
   - 올려야 할 파일들:
     ```
     server.py
     requirements.txt
     runtime.txt
     Procfile
     render.yaml
     .gitignore
     app.html
     employer.html
     admin_live.html
     dasibom.html
     dasibom_admin.html
     dasibom_schema.sql
     README.md
     ```
6. 화면 아래 **Commit changes** 버튼 클릭

### 방법 B · 터미널 사용 (Git 익숙한 경우)

```bash
cd "/Users/simon/Documents/Claude/Projects/중년여성 전용 잡 매칭 플랫폼 제작"
git init
git add .
git commit -m "다시봄 초기 배포"
git branch -M main
git remote add origin https://github.com/[본인계정]/dasibom.git
git push -u origin main
```

---

## 2단계 · Render에서 자동 배포

1. https://render.com 에 GitHub 계정으로 로그인
2. 대시보드 오른쪽 위 **New +** 버튼 → **Blueprint** 선택
3. **Connect a repository** → 방금 만든 `dasibom` 저장소 선택 → **Connect**
4. Render가 자동으로 `render.yaml` 파일을 인식해 설정을 보여줍니다.
   - 서비스 이름, 빌드 명령어, 실행 명령어, 영구 디스크 — 자동 입력됨
5. **Apply** 버튼 클릭

빌드가 시작되고, 약 **3~5분 후** "Live" 상태가 됩니다.

---

## 3단계 · 접속 확인

배포가 끝나면 화면 위쪽에 주소가 표시됩니다.

```
https://dasibom-xxxx.onrender.com
```

각 페이지 URL은 다음과 같습니다.

| 페이지 | 주소 |
|---|---|
| 구직자 | `https://dasibom-xxxx.onrender.com/app.html` |
| 기업 | `https://dasibom-xxxx.onrender.com/employer.html` |
| 관리자 | `https://dasibom-xxxx.onrender.com/admin_live.html` |
| API 문서 | `https://dasibom-xxxx.onrender.com/docs` |

데모 계정 (배포 직후 자동 생성됨):
- 관리자: `admin@dasibom.kr` / `admin1234`
- 구직자: `demo@dasibom.kr` / `demo1234`

---

## 4단계 · (선택) 사용자 정의 도메인 연결

회사 도메인이 있다면 Render의 **Settings → Custom Domain** 에서 추가할 수 있습니다.
예: `www.dasibom.kr`

DNS 설정 방법(CNAME 입력)은 Render가 안내합니다.

---

## ⚠️ 무료 플랜 제약사항

| 항목 | 무료 플랜 | 해결책 |
|---|---|---|
| 15분간 트래픽 없으면 절전 | 다음 접속 시 약 30초 응답 지연 | $7/월 Starter 플랜으로 변경 |
| DB 영구 디스크 1GB | 충분 (수만 명 데이터) | — |
| 월 750시간 무료 | 단일 서비스라면 충분 | — |
| HTTPS 자동 적용 | ✅ | — |

---

## 5단계 · 배포 후 보안 강화 (꼭 권장)

배포가 성공하면 즉시 다음을 처리하세요.

### 5-1. 기본 관리자 비밀번호 변경

배포된 사이트에 한 번도 접속하지 않은 상태에서:

1. 로컬에서 `server.py` 파일 열기
2. 시드 데이터 부분의 `admin1234` 를 본인만 아는 강한 비밀번호로 변경
3. GitHub에 다시 push → Render가 자동 재배포

또는 배포 후 관리자로 로그인 → DB 수정 API를 만들거나 Render Shell에서 직접 변경.

### 5-2. CORS 제한

`server.py` 의 `allow_origins=["*"]` 를 실제 도메인으로 한정:

```python
allow_origins=["https://dasibom-xxxx.onrender.com"]
```

### 5-3. 환경변수로 비밀키 분리

세션 토큰을 강화하려면 Render 대시보드의 **Environment** 탭에서 `SECRET_KEY` 환경변수 추가 후, `server.py`에서 활용.

---

## 데이터 백업

Render 대시보드 → 서비스 선택 → **Shell** 탭에서:

```bash
cat /var/data/dasibom.db > /tmp/backup.db
```

또는 SQLite 덤프:

```bash
sqlite3 /var/data/dasibom.db .dump > /tmp/backup.sql
```

다운로드해서 안전한 곳에 보관하세요.

---

## 자주 묻는 질문

**Q. 배포가 실패해요.**
A. Render 대시보드의 **Logs** 탭에서 빨간색 에러 메시지 확인. 보통 `requirements.txt`에 누락된 패키지 때문입니다.

**Q. 페이지가 404 에러가 나요.**
A. 주소에서 `.html` 빼고 입력하셨는지 확인. `/app.html` 처럼 확장자까지 입력해야 합니다.

**Q. 데이터를 초기화하고 싶어요.**
A. Render Shell에서 `rm /var/data/dasibom.db` 실행 후 서비스 재시작 → 시드 데이터가 다시 만들어집니다.

**Q. Render 대신 Railway/Fly.io를 쓰고 싶어요.**
A. `Procfile`이 이미 호환됩니다. Railway는 GitHub 연결 → Deploy만 누르면 됩니다.

**Q. 로컬에서는 잘 되는데 배포 후 로그인이 안돼요.**
A. HTTPS 환경에서 쿠키가 막힐 수 있습니다. `server.py`의 `set_cookie` 부분에 `secure=True` 추가하세요.

---

## 정리

- `render.yaml` 덕분에 클릭 몇 번으로 완전 자동 배포
- 영구 디스크(1GB)로 SQLite 데이터 안전 보관
- 무료 플랜에서 절전 모드 외엔 기능 제약 없음
- 실제 운영 단계에서 PostgreSQL로 옮길 때는 `dasibom_schema.sql` 그대로 사용 가능
