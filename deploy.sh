#!/bin/bash
# 다시봄 원클릭 배포 스크립트
MSG="${1:-자동 업데이트}"
rm -f .git/*.lock .git/index.lock 2>/dev/null
git add -A
git commit -m "$MSG" && git push
echo "✅ 완료 — 3분 후 https://dasibom.onrender.com 에 반영"
