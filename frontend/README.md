# 프론트엔드 (초안)

설계서 11.2절 스택: React 19 + TypeScript + Vite + Tailwind CSS v4 + TanStack Query + Zustand.
모바일 웹 우선 (5.1절) — 화면 폭 28rem 기준, 주요 액션은 하단 고정.

## 실행

```bash
# 백엔드가 localhost:8000 에 떠 있어야 함 (docker compose up db + uvicorn, 또는 docker compose up)
cd frontend
npm install
npm run dev        # http://localhost:5173  (/api → 8000 프록시)
```

## 색 체계

| 이름 | 용도 | 대표 값 |
| --- | --- | --- |
| `court-*` (메인, 오렌지) | 주요 액션 버튼, 활성 탭, 강조 | `court-500` #F26B1D |
| `navy-*` (서브, 남색) | 헤더, 제목, 보조 버튼 | `navy-800` #14213D |
| `team-black` / `team-white` | 배정 결과·쿼터 기록의 두 팀 | #111827 / #FAFAF9 |
| `stone-*` | 배경, 테두리, 보조 텍스트 | Tailwind 기본 |
| `emerald` / `amber` / `rose` | 성공 / 경고 / 오류 | Tailwind 기본 |

규칙: 한 화면에 `court` 버튼은 하나(주요 액션)만. 나머지는 `navy` 또는 `ghost`.

## 화면 ↔ 파일

| 화면 | 파일 | 상태 |
| --- | --- | --- |
| S-01 로그인 · S-02 회원가입 | `pages/auth.tsx` | API 연결 |
| S-03 온보딩 설문 | `pages/survey.tsx` | API 연결 |
| S-04 홈(다가오는 일정 · 내 팀 목록 · 메인 팀 설정 · 팀 추가) · S-17 프로필(팀 선택 · 팀별 설정 · 내 기록) | `pages/home.tsx` | API 연결 |
| S-05 팀 생성 · S-06 가입 · S-07 상세(일정 탭) · S-08 팀원 관리(게스트·병합 제안) | `pages/team.tsx` | API 연결 |
| S-09 일정 등록 · S-10 일정 상세/RSVP · S-11 참석 현황·게스트 초대 시트 | `pages/events.tsx` | API 연결 |
| S-19 매니저 실력 정렬 | `pages/ranking.tsx` | API 연결 |
| S-12 배정 실행 · S-13 결과(교체·확정) · S-14 확정 결과(플레이어) | `pages/assignment.tsx` | API 연결 |
| S-15 쿼터 기록 (입력 · 결과 보기) | `pages/quarters.tsx` | API 연결 |
| S-16 피어 투표 (같은 팀 2 · 상대 팀 2 · 이유 칩 · 완료 화면) | `pages/vote.tsx` | API 연결 |
| 매니저 실력 지표 화면 (사전값·정렬·잔차·투표 근거) · 기록 조각 | `pages/player-detail.tsx` | API 연결 |
| 지난 기록 추가 (과거 일정 → 참석·게스트 → 쿼터 기록) | `pages/records.tsx` | API 연결 |
| 팀 리더보드 (참여율 · 출전 쿼터 · 잔차) | `pages/leaderboard.tsx` | API 연결 |

`api/client.ts` 가 Bearer 토큰 첨부와 7.4절 오류 본문 변환, 401 시 refresh 재시도를 담당한다.
