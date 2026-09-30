# HOOPLY — 농구 동호회 팀 매칭 서비스 기획·설계서

**버전** v1.0 · **작성일** 2026\-09\-08 · **개정** 2026\-09\-30 · **단계** 구현 완료 · 운영 중 (https://hooply-green.vercel.app)

> **v1.0 주요 변경 (v0.3 기획 → 구현 반영)** — 서비스명 **HOOPLY** 확정 · 팀장(OWNER)과 관리자 팀 승인 · **3팀 배정**(참석 16명 이상, 선택) · 로테이션 자동 제안(F17) 제외 · 설문 v2(12문항, 자기 위치는 팀 가입 후 팀별로) · 지난 기록 추가 · 카카오 로그인·공유 · **AI 설명(F20)** · **전술 추천(F21)** · **전술판·팀 전술(F22)** · 배지 · 시작 안내 · 도움말 · 기술 스택을 실제 운영 구성(Neon · Render · Vercel · LangChain)으로
>
> **문서 지도** — 이 문서는 서비스 전체의 기획과 **설계 근거**(실력 모델 · 시뮬레이션 · 케미 정책 · 배정 알고리즘)를 담는다. 세부 명세는 `docs/` 에 있다: 01 서비스 정의(FR · NFR) · 02 화면 설계 · 03 데이터 모델 · 04 API 명세(+ OpenAPI) · 05 데모 시나리오 · 06 배지 · 07 AI 전술 요구사항 · eval_result(AI 검증 결과). **이 문서와 docs 가 다르면 docs 가 정본**이다.

Table of Contents

* * *

# 1\. 서비스 개요

## 1\.1 서비스명

**HOOPLY** 로 확정했다. 기획 단계의 후보(픽앤롤 · 코트메이트 · 밸런스코트 · 하프타임) 중 "코트메이트"는 데모 팀 이름("일요 코트메이트")으로 남아 있다.

## 1\.2 서비스 목적 (배경)

농구 동호회·픽업 게임에서 **'팀을 어떻게 나눌까'** 는 매번 반복되는 의사결정이다. 동호회와 픽업 게임에서는 인원이 부족한 경우가 많아 **게스트를 부르는 경우가 많아서 그때그때 인원이 가변적이고, 게스트의 실력을 모르는 경우도 많다.** 따라서 팀 결정은 보통 다음과 같은 방식으로 이뤄진다.

1. 참여하는 인원들의 실력을 가장 잘 알고 있는 사람이 팀을 결정
2. 키 순서 혹은 가위바위보로 팀을 결정
3. 친한 사람들 우선으로 팀을 결정

그런데 이 방식으로 팀을 구성하면 다음과 같은 문제가 생길 수 있다.

- 실력 균형이 맞지 않음
- 원하는 포지션으로 경기에 참여할 수 없음
- 팀 구성 근거가 없음

이런 문제가 발생하면 참여자들이 재미를 느끼지 못하고, 팀 구성에 불만을 느낄 수밖에 없다. 따라서 본 서비스는 **개인의 실력과 선호·가능 포지션을 종합하여 팀을 구성**함으로써 매니저의 팀 구성 부담을 덜어주고, 동호회 참여자들의 만족감을 향상시키는 것이 목적이다.

동시에, **최소한의 경기 기록을 데이터화**하여 각 개인의 실력과 팀원 간의 케미를 정량화하고, 이를 팀 구성 기능을 개선하는 데 사용한다.

**게스트 문제가 이 서비스의 난이도를 결정합니다.** 참석자가 고정된 리그라면 실력 데이터가 안정적으로 쌓이지만, 매번 처음 보는 게스트가 2\~4명 섞이는 픽업 환경에서는 **데이터가 없는 사람을 어떻게 배정에 넣을 것인가**가 핵심 과제가 됩니다. 이 문서에서는 게스트를 계정 없이도 참가자로 등록·누적할 수 있는 구조(6장)와, 데이터가 없을 때 매니저 판단을 사전값으로 받는 장치(8장)로 대응합니다.

## 1\.3 사용자 문제 (페인포인트)

| \# | 대상 | 문제 | 원인 |
| --- | --- | --- | --- |
| P1 | 팀 매니저 | 매 활동마다 팀 구성에 대한 부담과 번거로움 | 매주 참석자가 바뀌는 동호회 특성상 매번 처음부터 재설계 |
| P2 | 팀 매니저 | 팀 구성에 대한 불만 응대 | 배정 근거가 매니저 머릿속에만 있음 |
| P3 | 팀 매니저 | 팀 구성의 근거를 설명하기 어려움 | 배정 근거가 매니저 머릿속에만 있음 |
| P4 | 팀 매니저 | 기록이 남지 않아 다음 팀 구성을 개선할 수 없음 | 개인 스탯 기록에 높은 비용 |
| P5 | 참가자 / 게스트 | 실력 불균형으로 재미없는 경기 | 객관적 실력 데이터 부재, 주관적 판단 의존 |
| P6 | 참가자 / 게스트 | 중요 포지션이 한쪽에 쏠려 제대로 된 경기가 성립하지 않음 | 빅맨·핸들러 자원이 희소한 경우가 많음 |
| P7 | 참가자 / 게스트 | 원하는 포지션으로 경기에 참여할 수 없음 | 빅맨·핸들러 자원이 희소한 경우가 많음 |
| P8 | 참가자 / 게스트 | 팀 구성에 대한 불만 | 포지션·실력 문제로 원하지 않는 사람과 팀이 될 수 있음 |

## 1\.4 핵심 가치

**1\. 추천은 알고리즘이, 최종 결정권은 사람이 (Human\-in\-the\-loop)**
알고리즘이 기준(실력 우선 / 친화도 우선 / 종합)에 따라 3개의 후보안을 추천하고, 매니저가 그중 고르거나 직접 수정한다.

**2\. 아마추어의 현실을 반영한 배정**
실력 총합이 아니라 **중요 포지션(1번·5번)을 먼저 확보한 뒤** 실력·친화도·선호 포지션을 고려해 최적화한다.

**3\. 설명 가능한 결과**
팀 구성에 대한 근거를 매니저에게는 수치로, 플레이어에게는 문장으로 제시한다.

**4\. 기록 부담 최소화**
모든 스탯을 일일이 기록하지 않고, 쿼터별로 **누가 뛰었는지와 팀별 점수만** 입력해 계산한 코트 마진으로 실력 지표를 산출하고 팀 구성 기능을 개선한다.

**5\. 판단은 규칙이, 문장은 AI가 (v1.0)**
배정 · 전술 추천의 판단은 검증 가능한 규칙이 하고, AI(LangChain + Gemini)는 그 근거를 읽기 쉬운 문장으로만 바꾼다. AI 가 실패하면 규칙 설명이 그대로 나온다 (14장).

## 1\.5 주요 기능

| \# | 기능 | 설명 | 해결 |
| --- | --- | --- | --- |
| F1 | 온보딩 실력 설문 | 12문항(행동 앵커 · 다중선택), 팀별 z-score 로 사전 실력값 산출. 팀 가입 후 "이 동호회에서 내 실력 위치" 1문항 | P5, P7 |
| F2 | 팀 생성 및 팀 초대 | 8자리 팀 코드, 카카오톡 초대 링크(코드 자동 입력). **관리자 승인 후** 5명 이상이면 활성화 | P1 |
| F3 | 팀원 및 권한 관리 | 팀장(생성자) > 매니저 > 플레이어. 팀장이 매니저를 지정 · 해제, 마지막 매니저 보호, 팀장 자진 해제 시 승계 | P1 |
| F4 | 일정 등록 및 참석 응답 | 일정 · 응답 마감, 참석/불참, 매니저 대리 응답, 응답 미리 마감, 일정 수정 · 삭제 | P1 |
| F5 | 자동 팀 배정 | 묶음을 슈퍼노드로 축약해 2팀 완전 탐색, 전략 3안. **참석 16명 이상이면 3팀(블랙 · 화이트 · 레드) 선택 — 지역 탐색** | P1, P5, P6 |
| F6 | 배정 결과 설명 | 예상 실력 차 · 포지션 커버리지 · 게스트 가정을 문장으로 (AI 설명이 있으면 폴백으로) | P2, P3 |
| F7 | 배정안 수정 | 선수 옮기기 · 맞교체(묶음은 통째로), 지표 즉시 재계산, 초기화, 확정 → 참석자 공개 | P3 |
| F8 | 쿼터별 경기 기록 | 쿼터 스코어 + 팀별 출전 5명, 경기 후 일괄 저장, 시간 정규화 마진. 3팀이면 쿼터마다 대진(두 팀) 선택 | P4 |
| F9 | 경기 후 피어 투표 | "다음에 같이 뛰고 싶은 사람" 우리 팀 2 + 상대 팀 2, 이유 태그, 매니저 독려 공유 | P8 |
| F10 | 실력·친화도 갱신 | 기대 마진 대비 잔차 Elo(첫 2회 게이트), 함께 참석 대비 지목 비율의 선호 점수 | P4, P5 |
| F11 | 개인 대시보드 · 기록 탭 | 참석 · 출전 · 쿼터별 마진, 활동일 추세, 월간 코트 마진 랭킹, 행동 배지, 팀 리더보드 | P4 |
| F12 | 관리자 콘솔 | SQLAdmin: 팀 승인/거절, 원시 데이터 열람, 지표 보정(이력 · 감사 로그) | — |
| F13 | 게스트 참가자 | 팀원 누구나 이름 · 등급 · 키 · 포지션으로 회차 참석 등록, 동명이인 확인, 재방문 재사용, 회원 병합 · 본인 확인 병합 | P5 |
| F14 | 매니저 실력 정렬 | 드래그 순위를 사전값에 0.5 가중으로 결합 (초기 5~7개월 배정 품질의 핵심, 9.3절) | P5 |
| F15 | 배정 제약 (회차별) | 같은 팀 묶기 · 갈라놓기. 다음 회차 자동 해제, 직전 회차 불러오기 | P8 |
| F16 | 팀 사전 배치 | 팀 칸에 직접 배치하고 나머지를 알고리즘이 채움 | P8 |
| ~~F17~~ | ~~로테이션 자동 제안~~ | **범위에서 제외** — 기록을 경기 후에 입력하고 쉬는 순서는 현장에서 정하므로 쓸 곳이 없었다 | — |
| F18 | 지난 기록 추가 | 앱 도입 전 모임을 일자 · 참석 · 쿼터로 입력해 지표에 반영 | P4 |
| F19 | 카카오 로그인 · 공유 | OAuth 로그인 · 계정 연결, 팀 초대 · 투표 독려 · 확정 팀 구성 이미지 카카오톡 공유 | — |
| F20 | AI 배정 설명 | 매니저용 배정 설명 · 팀원용 "AI 한마디" (LangChain + Gemini). 판단은 규칙, AI 는 문장만 (14장) | P2, P3 |
| F21 | 전술 추천 | 확정된 팀마다 역할 적합도로 전술 3개와 자리 배치를 자동 추천, "AI 코치" 설명 (14장) | P6, P7 |
| F22 | 전술판 · 팀 전술 | 하프코트 단계 재생 · 수비 시뮬레이션 · 팀원이 그리는 전술 편집기(역할 자동 추출) · 댓글 · 별표 (14장) | P7 |

부가 기능: 행동 배지 20종(docs/06) · 새 가입자 시작 안내와 기능별 첫 안내 · 도움말 · 프로필 사진 · 기본 팀 설정 · 비밀번호 찾기(메일).

> **v0.3 대비:** F13~F16 은 설계 검토 중 추가됐고 모두 구현했다. F17 은 제외했다. F18~F22 는 구현하면서 더했다.

# 2\. 타겟 사용자 및 이용 환경

## 2\.1 1차 타겟 — 동호회 매니저 / 총무

- 20\~45세, 주 1회 이상 정기 모임 운영
- 참석자 명단 관리와 팀 나누기를 매번 직접 수행
- **페인포인트:** 시간 소모 \+ 결과에 대한 불만 응대
- **성공 기준:** 팀 나누기에 드는 시간이 줄어듦, 팀 배정에 대한 불만이 사라짐

## 2\.2 2차 타겟 — 동호회 소속 참가자

- 실력 편차가 큰 아마추어
- **페인포인트:** 재미없는 경기, 자기 실력과 선호에 맞지 않는 역할 배정
- **성공 기준:** 만족도 증가

## 2\.3 3차 타겟 — 픽업게임 / 동호회 관리자

- 다수 동호회를 운영하거나 픽업 게임을 운영하는 주체
- 데이터 품질 관리, 이상치 보정, 문의 대응

## 2\.4 이용 환경 전제

- **모바일 웹 우선.** 체육관에서 한 손으로 쓰는 상황을 기준으로 설계
- 팀 코드와 일정 링크는 **카카오톡 공유**로 유통된다고 가정
- **기록 입력은 매니저가 경기 후에 수행.** 경기 중 실시간 입력을 전제하지 않으므로, 쿼터 기록 화면은 여러 쿼터를 한 화면에서 연속 입력하는 형태가 유리하다

## 2\.5 실제 운영 프로토콜 (설계 전제)

데이터 모델과 알고리즘이 이 전제 위에 서 있으므로 명시합니다.

| 항목 | 실제 |
| --- | --- |
| 1회 참석 인원 | **12\~14명** (게스트 포함, 매번 가변) |
| 팀 구성 | 2팀. **그날 하루는 팀이 바뀌지 않음** (v1.0: 참석 16명 이상이면 3팀도 고를 수 있고, 쿼터마다 두 팀이 뛴다) |
| 팀 인원 | 6\~7명 |
| 출전 | 팀당 5명씩. 인원이 6\~7명이면 **순서를 정해 5명 뛰고 1\~2명 쉬는 로테이션** |
| 쿼터 수 | **유동적 (7\~10쿼터).** 시간이 남거나 부족하면 그때그때 조정 |
| 쿼터 길이 | 기본 **8분** (1\~10분, 기록할 때 쿼터마다 고른다) |
| 다음 모임 | 팀을 **처음부터 새로 편성** |

이 전제가 데이터에 미치는 영향은 두 가지입니다.

1. **하루 안에서는 팀이 고정**이므로 같은 팀 구성원끼리 통계적으로 잘 분리되지 않습니다. 개인을 구분해 주는 변동 요인은 **로테이션(누가 쉬는가)** 과 **회차마다 달라지는 참석자 조합** 뿐입니다
2. **쿼터 길이가 일정하지 않을 수 있으므로** 코트 마진은 반드시 **시간 정규화(10분 환산)** 후 사용해야 합니다

9\.3절 시뮬레이션은 이 프로토콜을 그대로 구현해 수행했습니다.

# 3\. 시스템 액터 정의 및 액터별 기능

## 3\.1 액터 정의

권한은 **전역 권한**과 **팀 단위 권한**으로 나눕니다. 한 사람이 A팀에서는 매니저, B팀에서는 플레이어일 수 있기 때문입니다.

| 액터 | 범위 | 부여 방식 |
| --- | --- | --- |
| **관리자 (ADMIN)** | 전역 | DB 에서 직접 지정. 관리자 콘솔(SQLAdmin)과 `/admin` API |
| **팀장 (OWNER)** | 팀 단위 | 팀 생성자(`teams.owner_user_id`). 매니저 권한을 부여 · 회수한다. 자진 해제하면 다른 매니저에게 승계 |
| **팀 매니저 (MANAGER)** | 팀 단위 | 팀장이 위임(팀장도 매니저다). 일정 · 배정 · 기록 · 정렬 |
| **플레이어 (PLAYER)** | 팀 단위 | 팀 코드로 가입 시 기본 부여 |

미로그인 상태(비회원)에서는 초대 링크 열람, 회원가입 · 로그인, 비밀번호 찾기, 도움말만 가능합니다. 새로 만든 팀은 **관리자 승인** 뒤에 활성화됩니다(스팸 팀 방지).

### 게스트 참가자는 액터가 아니다

게스트는 계정이 없는 경우가 대부분이므로 **시스템 액터가 아니라 데이터상의 참가자**로 취급합니다.

- 팀원 누구나 이름(\+선택적으로 실력 등급 · 키 · 포지션)만으로 게스트를 등록해 그 회차 참석자에 추가한다. 고치기 · 지우기는 등록한 사람과 매니저
- 게스트도 배정 · 쿼터 기록 · 코트 마진 · 투표의 **대상**이 된다 (로그인 · 설문 · 투표 **주체**는 불가)
- 같은 게스트가 재방문하면 기존 레코드를 선택해 **데이터가 누적**된다 (내가 초대했던 게스트는 목록에서 바로 불러온다)
- 게스트가 나중에 정식 가입하면 게스트 레코드를 계정에 **연결(merge)** 하여 과거 기록을 승계한다 — 매니저가 병합하거나, 같은 이름으로 가입한 본인이 홈에서 "본인이 맞나요?" 를 확인한다

이 때문에 데이터 모델에서 **로그인 계정(`users`)과 참가자(`players`)를 분리**합니다 (6장). 경기 기록 · 배정 · 투표는 모두 `players`를 참조합니다.

## 3\.2 액터별 기능 정의

### 관리자 (ADMIN)

- 새 팀 승인 · 거절 (승인 전 팀은 일정 기능이 잠긴다)
- 전체 사용자 · 팀 · 일정 · 경기 조회, 특정 선수의 **원시 데이터 전체 열람** — 설문 응답, 쿼터별 점수 이력, 코트 마진, 피어 투표 수신 내역, 실력 지표 변동 이력
- 실력 점수 **수동 보정** (이력 · 감사 로그)

### 팀장 (OWNER) · 팀 매니저 (MANAGER)

- 팀 정보 수정, 팀 코드 재발급, 팀원 초대(카카오톡) · 제외
- (팀장) 다른 팀원에게 매니저 권한 부여 / 회수
- 일정 등록 · 수정 · 삭제, 응답 미리 마감, 대리 참석 응답, 지난 기록 추가
- **팀원 실력 정렬** (F14), 게스트 등급 즉시 수정, 게스트 → 회원 병합
- **팀 배정 실행** — 회차별 제약(묶기 · 갈라놓기 · 사전 배치), 3팀 선택, 3가지 전략 후보안 → 수정 → 확정
- 배정 결과의 수치 · 설명 · AI 배정 설명, 선수별 실력 근거 열람
- 쿼터별 경기 기록 입력 · 수정
- 전술: 그날 추천 전술의 자리 바꾸기 저장, 전술 별표, 팀 전술 · 댓글 지우기

### 플레이어 (PLAYER)

- 회원가입 및 온보딩 설문, 팀 가입 후 "이 동호회에서 내 실력 위치"
- 팀 생성(관리자 승인 대기) · 팀 코드로 가입 · 팀 나가기
- 내 프로필 · 사진 · 포지션 수정, 기본 팀 설정
- 일정 참석 / 불참 응답, 게스트 초대
- 확정된 팀 배정 결과 열람 (본인 팀 · 배정 포지션 · 상대 팀 · AI 한마디. 타인의 실력 수치는 비공개, **자기 등급만** 본다)
- 경기 후 피어 투표 (참석자만, 선택 사항)
- 기록 탭 — 참여 이력, 활동일 추세, 월간 코트 마진, 배지, 리더보드
- 전술 목록 · 전술판 · 내 팀 추천 전술, **전술 만들기**(고치기 · 지우기는 만든 사람과 매니저), 댓글

## 3\.3 권한 매트릭스

| 기능 | ADMIN | MANAGER (팀장 포함) | PLAYER | 게스트 참가자 |
| --- | :---: | :---: | :---: | :---: |
| 로그인 | ○ | ○ | ○ | ✕ (계정 없음) |
| 팀 생성 | ○ | ○ | ○ (관리자 승인 후 활성) | ✕ |
| 팀 승인 · 거절 | ○ | ✕ | ✕ | ✕ |
| 매니저 권한 부여 | ○ | △ (팀장만) | ✕ | ✕ |
| 팀원 목록 조회 | ○ (전체) | ○ (등급 포함) | △ (이름 · 포지션, 자기 등급만) | ✕ |
| 선수 상세 데이터 조회 | ○ (원시) | ○ (수치 · 근거) | △ (본인 기록만) | ✕ |
| 일정 등록 / 수정 | ○ | ○ | ✕ | ✕ |
| 참석 응답 | ○ | ○ (대리 응답 포함) | ○ | △ (등록한 사람이 대신) |
| 게스트 등록 | ○ | ○ | ○ | ✕ |
| 실력 정렬 | ○ | ○ | ✕ | ✕ |
| 팀 배정 실행 · 제약 설정 · 수정 · 확정 | ○ | ○ | ✕ | ✕ |
| 배정 결과 열람 | ○ (전체 지표) | ○ (전체 지표 · AI 배정 설명) | △ (플레이어용 뷰 · AI 한마디) | ✕ |
| 경기 기록 입력 | ○ | ○ | ✕ (조회만) | ✕ |
| 경기 기록 · 투표의 대상이 됨 | ○ | ○ | ○ | **○** |
| 경기 후 피어 투표 응답 | ○ | ○ | ○ (참석자만) | ✕ |
| 전술 만들기 · 댓글 | ○ | ○ | ○ | ✕ |
| 전술 고치기 · 지우기 | ○ | ○ | △ (만든 사람만) | ✕ |
| 추천 전술 자리 저장 · 별표 | ○ | ○ | ✕ | ✕ |
| 실력 지표 수동 보정 | ○ | △ (게스트 등급) | ✕ | ✕ |

○ 전체 허용 · △ 제한적 허용 · ✕ 불가

> 게스트가 "기록 · 투표의 **대상**은 되지만 **주체**는 아니다"라는 비대칭이 이 서비스 권한 설계의 핵심입니다. 이 구분이 6장의 `users` / `players` 분리로 이어집니다.

# 4\. 기능 요구사항 (FR)

서비스 개요(1장)와 액터 정의(3장)를 화면(5장)까지 잇는 연결 고리입니다. 모든 FR은 **문제(P) → 기능(F) → 화면(S) → API** 로 추적됩니다. 정본은 `docs/01-서비스정의.md` 4.2절이며 아래 표는 그 사본입니다.

> **v0.3 대비:** 번호를 구현 순서에 맞춰 다시 매겼다(v0.3 의 FR-01~34 와 번호가 다르다). v0.3 의 FR-26(로테이션 제안)은 F17 제외로 빠졌고, 게스트 본인 확인(FR-13a) · 지난 기록 · 기본 팀 · 프로필 사진(FR-35~37) · 3팀(FR-62 · 63)이 더해졌다. 전술 · AI 는 FR-38~61 로 `docs/07` 에 있다.

| ID | 요구사항 | 액터 | 기능 | 화면 | 주요 API |
| --- | --- | --- | --- | --- | --- |
| FR-01 | 이메일 또는 카카오로 가입·로그인한다 | 비회원 | F19 | S-01, S-02 | `POST /auth/signup`, `POST /auth/login`, `GET /auth/kakao/login-url`, `GET /auth/kakao/callback` |
| FR-02 | 비밀번호는 bcrypt 해시로 저장한다 | SYSTEM | — | — | — |
| FR-03 | 가입 직후 설문에 응답하면 실력·포지션 프로필이 생긴다 | PLAYER | F1 | S-03 | `GET /surveys/onboarding`, `POST /surveys/onboarding/responses` |
| FR-04 | 팀을 만들면 코드가 발급되고 생성자는 팀장이 된다 | PLAYER | F2 | S-05 | `POST /teams` |
| FR-05 | 팀 코드로 가입한다. 초대 링크는 코드를 미리 채운다 | PLAYER | F2 | S-06 | `POST /teams/join` |
| FR-06 | 관리자 승인 후 5명 이상이면 팀이 활성화된다 | SYSTEM, ADMIN | F2, F12 | S-07, 관리자 콘솔 | `POST /admin/teams/{id}:approve` |
| FR-07 | 팀장은 매니저 권한을 부여·회수하고, 매니저는 팀원을 제외한다 | OWNER, MANAGER | F3 | S-08 | `PATCH /teams/{id}/players/{pid}/role`, `DELETE /teams/{id}/players/{pid}` |
| FR-08 | 매니저는 일정을 등록·수정·취소하고 응답을 미리 마감할 수 있다 | MANAGER | F4 | S-09, S-10 | `POST/PATCH/DELETE /events…`, `POST /events/{id}/rsvp:close` |
| FR-09 | 플레이어는 마감 전까지 참석/불참을 바꿀 수 있다 | PLAYER | F4 | S-10 | `PUT /events/{id}/attendance` |
| FR-10 | 팀원 누구나 게스트를 이름으로 등록해 회차 참석자에 추가한다 | PLAYER | F13 | S-10, S-11 | `POST /events/{id}/guests` |
| FR-11 | 게스트 등록 시 등급(1~5)·키·포지션을 지정할 수 있고 미지정 시 클럽 평균 | PLAYER | F13 | S-11 | 같은 API |
| FR-12 | 동명이인 게스트는 기존 레코드 재사용 여부를 확인한다 | SYSTEM | F13 | S-11 | 200 `similar[]` 응답 |
| FR-13 | 게스트가 가입하면 기록을 병합·되돌릴 수 있다 | MANAGER | F13 | S-08 | `POST /players/{id}:merge`, `:unmerge` |
| FR-13a | 같은 이름의 게스트 기록이 있으면 가입한 본인이 직접 확인해 가져오거나 거절할 수 있다 | PLAYER | F13 | S-04, S-07 | `GET /me/guest-claims`, `POST /players/{id}:claim` |
| FR-14 | 매니저가 팀원 순위를 매기면 사전 실력값에 반영된다 | MANAGER | F14 | S-19 | `POST /teams/{id}/rankings` |
| FR-15 | 참석 확정자와 포지션 분포·경고를 한눈에 본다 | MANAGER | F5 | S-11 | `GET /events/{id}/attendances` |
| FR-16 | 배정을 실행하면 3가지 전략의 후보안을 받는다 | MANAGER | F5 | S-12, S-13 | `POST /events/{id}/assignments` |
| FR-17 | 회차별로 묶기·갈라놓기·사전 배치를 걸 수 있다 | MANAGER | F15, F16 | S-12 | 같은 API `constraints` |
| FR-18 | 제약은 다음 회차에 해제되며 직전 회차 것만 불러올 수 있다 | SYSTEM | F15 | S-12 | `GET /events/{id}/assignments/last-constraints` |
| FR-19 | 실현 불가능한 제약은 실행 전에 차단된다 | SYSTEM | F15 | S-12 | `POST /events/{id}/assignments:validate` |
| FR-20 | 후보안은 예상 점수 차·균형 점수·포지션 커버리지와 설명을 보여준다 | MANAGER | F6 | S-13 | `GET /assignments/runs/{id}` |
| FR-21 | 선수를 옮기거나 맞교체하면 지표가 즉시 재계산된다 | MANAGER | F7 | S-13 | `PATCH /assignments/candidates/{id}` |
| FR-22 | 확정하면 참석자에게 결과가 공개된다 (실력 수치 비공개) | MANAGER, PLAYER | F7 | S-14 | `POST …:adopt`, `GET /events/{id}/assignment/adopted` |
| FR-23 | 매니저는 일정 시작 후 쿼터별 스코어와 출전 5명을 입력한다 | MANAGER | F8 | S-15 | `PUT /events/{id}/quarters` |
| FR-24 | 쿼터 저장 시 마진이 시간 정규화되고 잔차로 실력이 갱신된다 (첫 2회 미반영, 삭제 시 롤백) | SYSTEM | F10 | — | 서버 내부 |
| FR-25 | 남의 실력은 매니저에게만 수치·등급으로 보인다. 플레이어는 **자기 등급만** 본다 | SYSTEM | F10 | S-08, S-14, S-17 | 응답 마스킹 |
| FR-26 | 일정 종료 후 참석자는 같이 뛰고 싶은 사람을 우리 팀 2·상대 팀 2까지 고른다 | PLAYER | F9 | S-16 | `GET/POST /events/{id}/post-game-survey` |
| FR-27 | 매니저는 응답 현황을 보고 독려 메시지를 카카오톡에 공유한다 | MANAGER | F9, F19 | S-10 | `GET …/post-game-survey/share-message` |
| FR-28 | 상호 지목은 선호 조합으로 친화도 전략에 반영된다 | SYSTEM | F10 | — | 서버 내부 |
| FR-29 | 플레이어는 참석·출전·쿼터별 마진 기록을 본다 | PLAYER | F11 | S-17 | `GET /players/{id}/stats` |
| FR-30 | 매니저는 선수별 실력 지표의 근거(설문·정렬·잔차·투표)를 본다 | MANAGER | F11 | S-20 | `GET /players/{id}/stats` (수치 포함) |
| FR-31 | 팀원은 참여율·출전 쿼터 리더보드를, 매니저는 잔차 리더보드를 본다 | PLAYER, MANAGER | F11 | S-21 | `GET /teams/{id}/stats/leaderboard` |
| FR-32 | 관리자는 팀을 승인·거절하고 원시 데이터를 열람하며 지표를 보정한다 | ADMIN | F12 | 관리자 콘솔 | `/admin/*` |
| FR-33 | 참석 인원이 팀 수×5 미만이면 배정이 차단된다 | SYSTEM | F5 | S-10 | `422 NOT_ENOUGH_PLAYERS` |
| FR-34 | 핸들러·빅맨이 부족하면 경고와 함께 완화한다 | SYSTEM | F5 | S-11, S-13 | `warnings[]` |
| FR-35 | 매니저는 앱 도입 전 모임을 일자·참석·쿼터로 입력할 수 있다 | MANAGER | F18 | S-22 | 일정·참석·게스트·쿼터 API 조합 |
| FR-36 | 여러 팀에 속한 사용자는 기본 팀을 정할 수 있다 | PLAYER | — | S-04, S-17 | `PATCH /me` |
| FR-37 | 프로필 사진을 올리고 바꾸거나 지울 수 있고, 팀원 목록·참석자·배정 결과의 아바타에 반영된다 | PLAYER | — | S-17 | `POST/DELETE /me/avatar`, `GET /users/{id}/avatar` |
| FR-62 | 참석이 16명 이상이면 매니저가 "3팀으로 나누기"를 체크해 세 팀(21명이면 7·7·7)으로 배정할 수 있다. 묶기·갈라놓기·사전 배치는 똑같이 지킨다 | MANAGER | F5 | S-12, S-13 | `POST /events/{id}/assignments` `team_count=3` |
| FR-63 | 3팀인 날은 쿼터마다 뛴 두 팀(대진)을 골라 기록하고, 결과는 팀별 쿼터 · 득실 · 승패로 본다 | MANAGER | F8 | S-15 | `quarters.home_squad_no · away_squad_no` |

### 전술 · AI 요구사항 (FR-38~61, 정본 `docs/07-AI전술-요구사항.md`)

| 묶음 | FR | 기능 | 내용 |
| --- | --- | --- | --- |
| 전술 데이터와 판정 | FR-38~41 | F22 | 전술은 좌표가 아니라 **동작의 순서**(시작 위치 5 · 공 · 단계 · 역할 · 상대 수비 · 상황)로 저장. 동작 7종, 코트 구역 판정(FIBA 규격), 재생 가능성 검사 |
| 프리셋 | FR-42 | F22 | 22개 (하프코트 20 · 인바운드 2), 전술마다 막혔을 때의 대안 |
| 역할 적합도와 추천 | FR-43~45 | F21 | 역할 7종 × 설문 속성의 점수식 → 팀 · 전술마다 5자리 최적 배치(비트마스크 DP) → 적합도 75 이상 상위 3개 자동 추천 · 예비 |
| 화면 | FR-46~47 | F21, F22 | 팀 화면 탭(일정 · 기록 · 전술 · 팀원), 확정된 일정 화면 = 배정 결과 + "이 팀에 맞는 전술", 전술판 단계 재생 |
| AI 공통 · 설명 | FR-48~54 | F20, F21 | LangChain + Gemini, 가명화 · 가드레일 · 캐시 · 폴백 · 사용자당 제한, 매니저 배정 설명(A) · 팀원 AI 한마디(B) · 전술 AI 코치(C), 약관 안내 · 검증 스크립트 |
| 2단계 | FR-55~61 | F22 | 수비 시뮬레이션(맨투맨 · 지역 2-3 × 스위치 · 스테이) · 팀원 전술 편집기 · 역할 자동 추출 · AI 역할 설명(D) · 댓글 · 별표 |

# 5\. UI 흐름 및 화면 설계 방안

## 5\.1 설계 원칙

1. **모바일 우선 \+ 한 손 조작.** 주요 액션 버튼은 화면 하단 고정, 최소 터치 영역 44×44pt
2. **탭 3개 이내 완료.** 특히 RSVP 응답과 쿼터 기록 입력
3. **역할별 진입점 분리.** 로그인 후 홈은 매니저/플레이어에 따라 다른 카드 구성
4. **화면 요소 \= API 필드.** 모든 화면 요소는 6장 ERD 컬럼과 7장 API 응답 필드에 1:1 대응 (화면별 필드는 `docs/02`)

## 5\.2 주요 화면 목록 (31개)

| ID | 화면 | 경로 | 액터 |
| --- | --- | --- | --- |
| S-01 | 로그인 | `/login` | 비회원 |
| S-02 | 회원가입 | `/signup` | 비회원 |
| S-03 | 온보딩 설문 | `/survey` | PLAYER |
| S-04 | 홈 | `/` | ALL |
| S-05 | 팀 생성 | `/teams/new` | PLAYER |
| S-06 | 팀 가입 | `/teams/join` | PLAYER |
| S-07 | 팀 상세 (일정 · 기록 · 전술 · 팀원 탭) | `/teams/:teamId` | ALL |
| S-08 | 팀 관리 | `/teams/:teamId/members` | MANAGER |
| S-09 | 일정 등록 · 수정 | `/teams/:teamId/events/new` · `/events/:eventId/edit` | MANAGER |
| S-10 | 일정 상세 · 참석 응답 | `/events/:eventId` | ALL |
| S-11 | 참석자 현황 · 게스트 초대 시트 | S-10 안의 섹션·바텀시트 | ALL (등록), MANAGER (현황) |
| S-12 | 팀 배정 실행 | `/events/:eventId/assign` | MANAGER |
| S-13 | 배정 결과 (후보안 비교·수정·확정) | `/assignments/runs/:runId` | MANAGER |
| S-14 | 배정 확정 결과 | `/events/:eventId/assignment` | ALL |
| S-15 | 쿼터 기록 | `/events/:eventId/quarters` | MANAGER (입력) / PLAYER (조회) |
| S-16 | 경기 후 투표 | `/events/:eventId/vote` | PLAYER (참석자) |
| S-17 | 내 프로필 · 기록 | `/me` | ALL |
| S-18 | 관리자 콘솔 | 백엔드 `/admin` (SQLAdmin) | ADMIN |
| S-19 | 매니저 실력 정렬 | `/teams/:teamId/ranking` | MANAGER |
| S-20 | 선수 실력 지표 | `/teams/:teamId/players/:playerId` | MANAGER |
| S-21 | 팀 리더보드 | `/teams/:teamId/leaderboard` | ALL |
| S-22 | 지난 기록 추가 | `/teams/:teamId/records/new` | MANAGER |
| S-23 | 동호회 내 내 위치 | `/teams/:teamId/self-rank` | PLAYER |
| S-24 | 카카오 로그인 콜백 | `/auth/kakao/callback` | 비회원·회원 |
| S-25 | 기록 탭 (S-07 안) | `/teams/:teamId` 기록 탭 | ALL |
| S-26 | 도움말 · 문의 | `/help` | 비회원·회원 |
| S-27 | 시작 안내 (홈 팝업 · 체크리스트 · 기능별 첫 안내) | `/` 외 5개 화면 | 회원 |
| S-28 | 전술 탭 (S-07 안) | `/teams/:teamId` 전술 탭 | ALL (별표는 MANAGER) |
| S-29 | 전술판 | `/tactics/:key?event=&squad=&team=` | ALL (자리 바꾸기는 MANAGER) |
| S-30 | 전술 편집기 | `/teams/:teamId/plays/new` · `/teams/:teamId/plays/:playId/edit` | ALL (고치기는 만든 사람 · MANAGER) |
| S-31 | 비밀번호 찾기 · 재설정 | `/password/forgot` · `/password/reset?token=` | 비회원 |

> 화면별 요소 · 데이터 필드 · API · 흐름은 `docs/02-UI흐름및화면설계.md` 에 있다. v0.3 의 S-11(참석자 현황)은 S-10 안의 섹션 · 하단 시트가 됐고, S-14(확정 결과)는 **확정된 일정 화면 자체**가 됐다(팀 배정 결과 → 이 팀에 맞는 전술 → 접힌 참석 관리).

## 5\.3 핵심 사용자 흐름

### 흐름 A — 신규 플레이어 온보딩

```
S-01 로그인 → (계정 없음) → 카카오로 시작하기 또는 S-02 회원가입 → S-03 온보딩 설문(필수)
   → 팀 코드 있음? ─ Yes → S-06 팀 가입 → S-23 이 동호회에서 내 위치 → S-07 팀 상세
                   └ No  → S-05 팀 생성 → 관리자 승인 대기 → 팀 코드 · 카카오톡 초대
   (처음 가입하면 홈에 시작 안내 팝업 → 팀원/매니저 체크리스트, S-27)
```

### 흐름 B — 모임 운영 (매니저)

```
S-09 일정 등록 → (팀원 참석 응답 · 게스트 초대) → S-10 참석 현황 확인 → 응답 마감
   → S-12 배정 실행 (지난 조건 불러오기 · 묶기 · 갈라놓기 · 사전 배치 · 16명 이상이면 3팀 선택)
   → S-13 후보안 3개 비교 · AI 배정 설명 → [선택 | 옮기기 · 맞교체] → 확정
   → S-14 확정된 일정 화면 (카카오톡으로 팀 구성 이미지 공유 · 이 팀에 맞는 전술)
   → 경기 → 경기 후 S-15 쿼터 기록 일괄 입력 (3팀이면 쿼터마다 대진)
   → 투표 독려 메시지 공유
```

### 흐름 C — 참여 (플레이어)

```
홈 · 팀 화면 → S-10 일정 상세 → 참석 응답 (게스트 초대 가능)
   → (매니저 확정 후) S-14 내 팀 · 포지션 · AI 한마디 · 내 팀 추천 전술 → S-29 전술판
   → 경기 후 → S-16 피어 투표(선택)
   → S-25 기록 탭에서 추세 · 월간 코트 마진 · 배지 확인
```

## 5\.4 예외 / 오류 시나리오

| 시나리오 | 발생 조건 | 화면 처리 | API 응답 |
| --- | --- | --- | --- |
| 잘못된 팀 코드 | 존재하지 않는 코드 | 입력 필드 하단 인라인 에러 | `404 TEAM_CODE_NOT_FOUND` |
| 중복 가입 | 이미 소속된 팀에 재가입 시도 | 토스트 \+ 팀 상세로 이동 | `409 ALREADY_MEMBER` |
| 카카오 계정에 이메일 없음 | 이메일 동의항목 없음 | 가입은 진행, 이메일 비움. 나중에 비밀번호 재설정으로 이메일 로그인을 더할 수 있음 | `200` \+ `email: null` |
| 팀 미활성 | 관리자 승인 전이거나 5명 미만 | 일정 등록 잠금 \+ 사유 안내 | `422 TEAM_NOT_ACTIVE` |
| **게스트 동명이인** | 같은 이름의 게스트가 이미 존재 | 기존 게스트 목록을 먼저 보여 주고 "새 게스트로 추가"를 아래에 | `200` \+ `similar[]` |
| **게스트 데이터 없음** | 실력 등급 미지정 게스트 | 칩에 `?` 배지, 클럽 평균 적용, 설명 문구에 "게스트 N명은 평균으로 가정" | `skill_confidence = 0` |
| 인원 부족 배정 | 참석자 \< 팀 수 × 5 | 버튼 비활성 \+ "참석 10명 이상 필요 · 현재 8명" | `422 NOT_ENOUGH_PLAYERS` |
| **묶음 그룹 과대 · 제약 충돌 · 분할 불가** | 그룹 \> 팀 정원, 같은 쌍을 묶고 갈라놓음 등 | 실행 전 인라인 경고, 누가 문제인지 표시 | `422 LOCK_* / CONSTRAINT_CONFLICT / SEPARATE_INFEASIBLE` |
| **사전 배치 초과** | 한 팀 칸에 정원 초과 배치 | 배치 거부 | `422 SQUAD_OVERFLOW` |
| 빅맨 · 핸들러 부족 | 4·5번 또는 1번 가능 인원 \< 팀 수 | 경고 배너(차단 아님) | `200` \+ `warnings[]` |
| RSVP 마감 후 응답 | 마감 시각 경과 | 토글 비활성 \+ "응답이 마감되었어요" (매니저는 대리 변경 가능) | `422 RSVP_CLOSED` |
| 노쇼 / 당일 인원 변동 | 확정 후 참석자 변경 | 매니저 "재배정". 쿼터 기록에서 늦게 온 사람 · 당일 게스트를 명단에 추가 | 배정 재실행 |
| **쿼터 수 변경** | 예정보다 일찍 끝나거나 더 뜀 | 쿼터 카드 추가 · 삭제 자유. 삭제 시 지표 롤백(팀 전체 재계산) | `PUT /events/{id}/quarters` |
| **쿼터 출전 인원 오류** | 한 팀에 5명이 아닌 인원 | 저장 버튼 비활성 \+ "블랙 팀 4명이 선택되었어요" | `400 INVALID_LINEUP_SIZE` |
| 권한 없음 | 플레이어가 매니저 URL 직접 접근 | 안내 \+ 홈 복귀 | `403 FORBIDDEN_ROLE` |
| 자기 자신 투표 | 피어 투표에서 본인 선택 | 본인은 후보에서 제외 | `400 SELF_VOTE_NOT_ALLOWED` |
| **게스트에게 투표** | 게스트는 대상은 되지만 응답자는 아님 | 후보 목록에는 포함, 투표 화면은 회원만 | — |
| 요청 과다 | 로그인 · 가입 · 비밀번호 찾기 반복, AI 호출 · 댓글 연타 | "요청이 너무 많아요" | `429 RATE_LIMITED` |
| AI 실패 | 키 없음 · 시간 초과 · 가드레일 위반 | 같은 자리에 규칙 설명("AI" 표시 없이) | `200` \+ `fallback: true` |
| 네트워크 오류 · 이탈 | 체육관 통신 불량, 저장 전 창 닫기 | 쿼터 입력은 기기에 임시 저장 후 복원 | — |

## 5\.5 화면 설계 산출물

화면 목록 · 요소 · 필드 · API 대응은 `docs/02` 로 관리한다. 설계 원칙 4번(화면 요소 = API 필드)은 FastAPI 의 OpenAPI(`docs/04-API명세-openapi.yaml`)와 프론트 타입(`frontend/src/api/types.ts`)으로 지키고, 핵심 흐름은 Playwright E2E(모바일 Chromium)로 매 푸시마다 확인한다.

* * *

# 6\. 데이터 모델 (ERD)

PostgreSQL(운영 Neon 18, 로컬 Docker 16) · SQLAlchemy 2.0 · Alembic 마이그레이션 **0001~0024**. 컬럼 단위 정의는 `docs/03-데이터모델.md` 가 정본이다(모델 메타데이터에서 추출). 이 장은 설계 원칙과 구조를 요약한다.

## 6\.1 설계 원칙

1. **계정(users)과 참가자(players)를 분리한다.** 게스트는 계정 없이도 배정·기록·투표의 대상이 되어야 하므로, 경기 관련 테이블은 모두 `players.id` 를 참조한다. 회원은 `players.user_id` 가 채워지고 게스트는 NULL 이다. 같은 사람이 두 팀에 있으면 `players` 행이 둘이며 실력 지표도 팀별로 관리된다.
2. **게스트 → 회원 병합은 포인터로.** `players.merged_into_player_id` 를 따라 기록을 합산하므로 되돌릴 수 있다.
3. **배정 제약은 회차별.** `assignment_constraints` 가 `assignment_runs` 에 종속되어 다음 회차에 자동 해제된다.
4. **경기는 events → quarters 직결.** 하루 팀이 고정이라 `games` 계층이 없고, 쿼터 수·길이가 유동적이라 `duration_min` 으로 정규화한다.
5. **실력값 변동은 append-only 이력**(`skill_rating_history`), 관리자 조작은 `audit_logs` 에 남긴다.
6. **상태값은 PostgreSQL ENUM 타입.** 팀 상태·역할·포지션 등 23종을 `team_status_enum`, `position_enum` 같은 전용 타입으로 두어 스키마만 봐도 열거형임이 드러나고 허용값이 한 곳에서 관리된다 (0017, 튜토리얼 두 종은 0019). 값을 더할 때는 `ALTER TYPE ... ADD VALUE`.
7. **외래키 인덱스.** 외래키에는 인덱스가 자동으로 생기지 않으므로 조회 조건·ON DELETE 검사에 쓰이는 컬럼에는 명시적으로 건다. 감사용 `*_by` 컬럼은 조회 조건으로 쓰이지 않아 두지 않는다.

## 6\.2 엔터티 그룹

| 그룹 | 테이블 | 역할 |
| --- | --- | --- |
| 계정·인증 | users, auth_identities, password_reset_tokens, revoked_tokens, user_avatars | 로그인 계정과 수단(LOCAL/KAKAO), 기본 팀, 폐기한 refresh 토큰, 프로필 사진 |
| 팀·참가자 | teams, players, guest_invite_presets, guest_claims | 팀(승인 상태 포함), 팀 소속 참가자(회원+게스트, 역할), 게스트 초대 이력, 게스트 기록 본인 확인 |
| 프로필 | player_profiles, player_positions, skill_rating_history | 사전값·실력·신뢰도·6축, 가능/선호 포지션, 변동 이력 |
| 매니저 판단 | manager_rankings, manager_ranking_entries | 실력 정렬 버전과 순위 |
| 설문 | survey_templates, survey_questions, survey_options, survey_responses, survey_answers | 온보딩 설문(버전 관리)과 응답 |
| 일정 | events, event_attendances | 모임 일정, 참석 응답(게스트 대리 등록·같은 팀 요청) |
| 배정 | assignment_runs, assignment_constraints, assignment_candidates, assignment_squads, assignment_slots | 실행·회차 제약·후보안·팀·슬롯 |
| 경기 | quarters, quarter_lineups | 쿼터 스코어, 출전자별 코트 마진 |
| 피어 평가 | post_game_surveys, post_game_votes, chemistry_scores | 경기 후 투표와 선호 조합 |
| 운영 · 기록 탭 | audit_logs, user_badges | 관리자 조작 이력, 배지(행동 기반) |
| 전술 · AI | event_play_assignments, team_plays, tactic_comments, tactic_stars, llm_results | 그날 전술 자리 배치, 팀이 만든 전술, 전술 댓글, AI 설명 캐시 (docs/07) |

## 6\.3 관계

| 관계 | 카디널리티 | FK | 비고 |
| --- | --- | --- | --- |
| users → auth_identities | 1:N | auth_identities.user_id (CASCADE) | 카카오·이메일 동시 연결, UNIQUE(provider, provider_uid) |
| users → password_reset_tokens | 1:N | user_id | 토큰은 SHA-256 해시만 저장 |
| users → revoked_tokens | 1:N | user_id (CASCADE) | 로그아웃 · 회전으로 버린 refresh 토큰 jti |
| users → user_avatars | 1:1 | user_id (PK=FK, CASCADE) | 사진 바이트 + 주소용 `cache_key` |
| users → user_badges | 1:N | user_id (CASCADE) | UNIQUE(user_id, code) |
| players(게스트) ↔ users (본인 확인) | M:N | guest_claims(guest_player_id CASCADE, user_id CASCADE) | UNIQUE(guest_player_id, user_id), CONFIRMED · DECLINED |
| users → teams (소유) | 1:N | teams.owner_user_id | 팀장. 자진 해제 시 승계 |
| users → teams (기본 팀) | N:1 | users.primary_team_id (SET NULL) | 프로필 우선 표시 |
| users → teams (승인) | N:1 | teams.approved_by (SET NULL) | 관리자 |
| users → players | 1:N | players.user_id (NULL = 게스트) | UNIQUE(team_id, user_id) |
| teams → players | 1:N | players.team_id (CASCADE) | 역할(MANAGER/PLAYER)·상태 |
| players → players | N:1 (self) | merged_into_player_id | 게스트→회원 병합 포인터 |
| players → player_profiles | 1:1 | player_id (PK=FK, CASCADE) | 팀 단위 실력 지표 |
| players → player_positions | 1:N | player_id (CASCADE) | UNIQUE(player_id, position), 최대 5행 |
| players → skill_rating_history | 1:N | player_id (CASCADE) | 변동 이력 |
| teams → manager_rankings → entries → players | 1:N → 1:N → N:1 | team_id, ranking_id (CASCADE), player_id | UNIQUE(ranking_id, player_id), (ranking_id, rank_no) |
| teams → guest_invite_presets | 1:N | team_id (CASCADE), created_by, last_player_id (SET NULL) | 초대 목록 불러오기 |
| survey_templates → questions → options | 1:N → 1:N | template_id, question_id | 버전 관리 |
| users → survey_responses → answers | 1:1 → 1:N | user_id (CASCADE, UNIQUE), response_id (CASCADE) | 1인 1회 |
| teams → events | 1:N | team_id (CASCADE) | 상태 OPEN/CLOSED/DONE/CANCELED |
| events ↔ players (참석) | M:N | event_attendances(event_id CASCADE, player_id) | UNIQUE(event_id, player_id), team_lock_request_player_id |
| events → assignment_runs → constraints | 1:N → 1:N | event_id (CASCADE), run_id (CASCADE) | LOCK/SEPARATE/PIN |
| assignment_runs → candidates → squads → slots | 1:N 체인 | run_id, candidate_id, squad_id (모두 CASCADE) | 후보 3개 → 팀 2~3개 → 슬롯, 채택 후보는 run 당 1개(부분 유니크) |
| assignment_slots → players | N:1 | player_id | UNIQUE(squad_id, player_id) |
| events → quarters → quarter_lineups | 1:N 체인 | event_id (CASCADE), quarter_id (CASCADE) | UNIQUE(event_id, quarter_no), (quarter_id, player_id) |
| quarter_lineups → players | N:1 | player_id | raw/normalized 마진 |
| events → post_game_surveys → votes | 1:N → 1:N | event_id, survey_id (CASCADE) | 응답자 1회(UNIQUE event_id, respondent), 투표 대상은 게스트 포함 |
| players ↔ players (선호 조합) | M:N self | chemistry_scores(player_a_id < player_b_id) | UNIQUE(a, b), pref_score/pref_mutual/together_events |
| users → audit_logs | 1:N | actor_user_id | 관리자 조작 |
| events → event_play_assignments | 1:N | event_id (CASCADE) | 그날 팀 · 전술별 매니저가 저장한 자리 배치 |
| teams → team_plays · tactic_comments · tactic_stars | 1:N | team_id (CASCADE) | 팀 전술 · 전술별 댓글 · 별표 (docs/07) |


## 6\.4 핵심 테이블 요약

| 테이블 | 핵심 컬럼 | 설계 포인트 |
| --- | --- | --- |
| `users` | email(NULL 허용, 소문자) · password_hash(NULL 허용) · name · nickname · height_cm · global_role · primary_team_id · position_prefs · 튜토리얼 상태 | 카카오 계정은 이메일이 없을 수 있다(11.5절). 식별은 `id`, 로그인 수단은 `auth_identities` |
| `teams` | team_code(8자) · owner_user_id(팀장) · status(PENDING/ACTIVE/ARCHIVED) · approval_status · approved_by · min_members | 관리자 승인 + 5명 이상이면 ACTIVE |
| `players` | team_id · user_id(NULL = 게스트) · kind · display_name · role(MANAGER/PLAYER) · status · created_by · merged_into_player_id · height_cm | UNIQUE(team_id, user_id), CHECK (kind = GUEST) = (user_id IS NULL). 병합은 포인터라 되돌릴 수 있다 |
| `player_profiles` | prior_overall · prior_source · skill_overall · 6축 · skill_confidence · quarters_played · cumulative_residual · self_rank_level | 실력은 **팀 단위**. 자기 위치는 팀마다 |
| `assignment_runs → candidates → squads → slots` | team_count(2·3) · params · roster_snapshot / strategy · total_score · metrics · explanation · is_adopted / squad_no · squad_name(블랙 · 화이트 · 레드) / player_id · assigned_position · is_manual_override | 한 회차에 남는 배정은 확정한 실행 하나. 채택 후보는 run 당 1개(부분 유니크) |
| `assignment_constraints` | run_id · type(LOCK/SEPARATE/PIN) · group_no · player_id · squad_no | 제약은 회차별 (9.6절) |
| `quarters` · `quarter_lineups` | quarter_no · black_score · white_score · **duration_min(기본 8)** · home_squad_no · away_squad_no / player_id · side · raw_margin · normalized_margin · residual | events 직결(`games` 없음). 3팀이면 쿼터마다 뛴 두 팀. 잔차는 재계산 가능한 형태로 |
| `post_game_surveys` · `post_game_votes` · `chemistry_scores` | 응답자(회원만) / 대상(게스트 포함) · PLAY_AGAIN · 이유 태그 / pref_score · pref_mutual · together_events · together_quarters · synergy_*(v1 에서 계산 안 함) | 선언된 선호와 관찰된 시너지를 분리 (9.4절) |
| `team_plays` · `tactic_comments` · `tactic_stars` · `event_play_assignments` | 팀이 그린 전술(JSON) · 역할 · role_source / 전술별 댓글 / 별표 / 그날 팀 · 전술별 자리 배치 | 14장, docs/07 |
| `llm_results` | chain(A~D) · cache_key · output · fallback · fail_reason · latency_ms · model | AI 결과 캐시 겸 호출 기록. 입력 원문은 저장하지 않는다 |
| `user_badges` · `guest_claims` · `user_avatars` · `revoked_tokens` | 행동 배지 / 게스트 기록 본인 확인 / 프로필 사진 / 폐기한 refresh 토큰 | docs/03, docs/06 |

## 6\.5 v0.3 설계 대비 달라진 점

- `users.birth_year` 삭제(0003) — 수집하지 않는다. 키는 가입 폼 · 프로필에서
- `teams` 에 승인 상태와 팀장, `users` 에 기본 팀 · 포지션 선호 · 튜토리얼 상태가 더해졌다
- `quarters.duration_min` 기본값 10 → **8**(0013, 실제 운영 쿼터 길이), 3팀 대진 `home_squad_no · away_squad_no`(0024)
- 상태값 23종을 PostgreSQL ENUM 타입으로(0017), 조회 · 삭제 경로 외래키 인덱스
- 새 테이블: guest_invite_presets · guest_claims · user_avatars · revoked_tokens · user_badges · event_play_assignments · llm_results · team_plays · tactic_comments · tactic_stars
- v0.3 6.4절의 `team_memberships` · `user_id` 기준 인덱스 권고는 `players` · `player_id` 기준으로 바뀌었다

* * *

# 7\. API 명세

엔드포인트 110개(`/health` 포함). 정본은 FastAPI 가 코드에서 만든 `docs/04-API명세-openapi.yaml` 이고, 요약 표는 `docs/04-API명세.md` 에 있다. 각 함수 docstring 에 권한 · 처리 · 오류 · 설계서 절이 적혀 있다.

## 7\.1 공통 규약

- Base URL: `https://hooply-backend.onrender.com/api/v1` (로컬 `http://localhost:8000/api/v1`)
- 인증: `Authorization: Bearer <access_token>` (JWT, access 30분 / refresh 14일, refresh 는 회전하고 로그아웃 · 회전된 토큰은 폐기 목록으로 막는다)
- 요청 · 응답 본문은 `application/json`, 필드명은 `snake_case`
- 목록 응답은 `{ items }` 또는 `{ items, meta: { page, size, total, has_next } }`
- 액션형 경로는 `:동사` 접미사 (`/assignments/candidates/{id}:adopt`, `/events/{id}/rsvp:close`)
- 요청 제한: 로그인 · 가입 · 비밀번호 경로(IP · 이메일), AI 호출 · 전술 댓글(사용자당 분당 10회) → `429 RATE_LIMITED`

## 7\.2 엔드포인트 그룹

| 그룹 | 개수 | 대표 엔드포인트 |
| --- | ---: | --- |
| 인증 · 프로필 | 17 | `POST /auth/signup` · `/auth/login` · `GET /auth/kakao/login-url` · `/auth/kakao/callback` · `POST /auth/refresh` · `/auth/logout` · `/auth/password/forgot` · `/auth/password/reset` · `GET/PATCH/DELETE /me` · `POST/DELETE /me/avatar` |
| 온보딩 설문 | 5 | `GET /surveys/onboarding` · `POST /surveys/onboarding/responses` · `GET /me/profile` · `PUT /me/positions` |
| 팀 · 참가자 | 9 | `POST /teams` · `POST /teams/join` · `GET/PATCH /teams/{id}` · `GET /teams/{id}/players` · `PATCH …/players/{pid}/role` |
| 게스트 관리 | 8 | `POST /events/{id}/guests` · `GET /teams/{id}/guests` · `POST /players/{id}:merge` · `:unmerge` · `:claim` |
| 매니저 실력 정렬 | 3 | `GET /teams/{id}/rankings/latest` · `POST /teams/{id}/rankings` |
| 일정 · 참석 | 13 | `POST /teams/{id}/events` · `PUT /events/{id}/attendance` · `PUT /events/{id}/attendances/{pid}` · `GET /events/{id}/attendances` · `POST /events/{id}/rsvp:close` |
| 팀 배정 | 10 | `POST /events/{id}/assignments` · `:validate` · `GET …/last-constraints` · `PATCH /assignments/candidates/{id}` · `:adopt` · `GET /events/{id}/assignment/adopted` |
| 경기 기록 | 5 | `PUT /events/{id}/quarters`(일괄) · `GET /events/{id}/quarters` · `DELETE /quarters/{id}` |
| 경기 후 설문 · 통계 | 10 | `GET/POST /events/{id}/post-game-survey` · `GET /players/{id}/stats` · `GET /teams/{id}/stats/leaderboard` · `/stats/monthly-margin` · `GET /me/badges` |
| 전술 | 17 | `GET /tactics/presets` · `GET /events/{id}/tactics/recommend` · `PUT …/tactics/{key}/slots` · `/teams/{id}/plays` CRUD · `:check` · `:ai-roles` · 댓글 · 별표 |
| AI 설명 | 3 | `POST /assignments/candidates/{id}/ai-explanation` · `GET /events/{id}/assignment/adopted/ai-message` · `POST /events/{id}/tactics/ai-recommend` |
| 시작 안내 | 2 | `GET/PUT /me/tutorial` |
| 관리자 | 7 | `GET /admin/users` · `POST /admin/teams/{id}:approve` · `GET /admin/players/{id}/raw` · `PATCH /admin/players/{id}/rating` · `GET /admin/audit-logs` |
| 시스템 | 1 | `GET /health` |

배정 실행 요청:

```
POST /api/v1/events/{event_id}/assignments
{
  "team_count": 2,                       // 참석 16명 이상이면 3 도 가능
  "strategies": ["SKILL", "CHEMISTRY", "BALANCED"],
  "constraints": {
    "lock_groups":     [[12, 45, 78], [3, 9]],
    "separate_groups": [[21, 33]],
    "pins":            [{ "player_id": 5, "squad_no": 1 }]
  }
}
```

`lock_groups` · `separate_groups` 는 페어가 아니라 **그룹 배열**이다. 2명 이상 임의 인원을 한 번에 묶어야 하기 때문이다. 값은 모두 `player_id` 이며 회차 한정이다. v0.3 의 `POSITION` 전략은 없다(9.5절).

## 7\.3 에러 코드 체계

| HTTP | code | 상황 |
| --- | --- | --- |
| 400 | VALIDATION_ERROR, INVALID_LINEUP_SIZE, SELF_VOTE_NOT_ALLOWED, TOKEN_INVALID_OR_EXPIRED | 형식·범위 위반 |
| 401 | INVALID_CREDENTIALS, TOKEN_EXPIRED, KAKAO_AUTH_FAILED | 인증 실패 |
| 403 | FORBIDDEN_ROLE, NOT_A_MEMBER, NOT_ATTENDEE, SURVEY_NOT_OPEN, FORBIDDEN_NOT_OWNER | 권한 부족·아직 열리지 않음 |
| 404 | NOT_FOUND, TEAM_CODE_NOT_FOUND, NOT_ADOPTED_YET, NO_RANKING | 리소스 없음 |
| 409 | EMAIL_DUPLICATED, ALREADY_MEMBER, ALREADY_SUBMITTED, QUARTER_EXISTS, ALREADY_ADOPTED, IDENTITY_ALREADY_LINKED, ALREADY_MERGED | 상태 충돌 |
| 422 | TEAM_NOT_ACTIVE, NOT_ENOUGH_PLAYERS, RSVP_CLOSED, INVALID_SWAP, CANNOT_DEMOTE_LAST_MANAGER, PLAYER_NOT_IN_TEAM, PLAYER_NOT_IN_SQUAD, PLAY_NOT_PLAYABLE, MERGE_KIND_MISMATCH, LOCK_GROUP_TOO_LARGE, CONSTRAINT_CONFLICT, SEPARATE_INFEASIBLE, LOCK_PARTITION_INFEASIBLE, SQUAD_OVERFLOW | 도메인 규칙 위반 (배정 제약 오류는 details 에 문제 인원 포함) |
| 429 | RATE_LIMITED | 요청이 너무 많음 — 로그인 · 가입 · 비밀번호 찾기(IP · 이메일), AI 호출 · 전술 댓글(사용자당 분당 10회) |
| 500 | INTERNAL_ERROR | 서버 오류 |

> **설계 원칙:** 형식 오류는 400, 권한은 403, 존재하지 않음은 404, 상태 충돌은 409, **도메인 규칙 위반은 422**. 프론트는 `code`로 분기하고 `message`는 그대로 노출 가능한 한국어 문구로 유지합니다.
>
> **배정 제약 오류는 `details[]`에 어떤 그룹·선수가 문제인지 담아야 합니다.** "제약을 만족할 수 없습니다"만으로는 매니저가 무엇을 풀어야 할지 알 수 없습니다.
>
> **`/auth/password/forgot`은 항상 202를 반환합니다.** 가입 여부에 따라 응답이 달라지면 계정 존재 여부를 확인하는 통로가 됩니다.

# 8\. 온보딩 설문 설계 (설문 v2)

## 8\.0 설문의 위상 — 시뮬레이션이 알려준 것

초안(v0.1)에서는 설문을 "경기 데이터가 쌓이기 전까지의 임시 사전값"으로 취급했습니다. 실제 운영 프로토콜(2.5절)을 그대로 구현해 재측정한 결과(9.3절), 정확한 위상은 다음과 같습니다.

| 기간 | 주력 신호 | 근거 |
| --- | --- | --- |
| **0\~10회 모임 (약 80쿼터)** | **설문 \+ 매니저 정렬** | 데이터만으로는 순위 상관 0.62 수준. 설문(ρ\=0.65)만으로도 0.64를 이미 확보 |
| **10\~20회 모임** | 설문과 데이터가 대등 | 20회(170쿼터)에서 데이터 단독 0.81, 설문 결합 시 0.86 |
| **20회 이후** | **경기 데이터가 주력** | 30회(255쿼터)에서 데이터 단독 0.87. 설문의 기여는 \+0.03 수준으로 줄어듦 |

**주 1회 모임 기준으로 설문은 첫 2\~3개월을 책임지고, 이후 데이터에 자리를 내줍니다.**

그런데 이 서비스에서 그 2\~3개월은 "잠깐"이 아닙니다. 사용자가 서비스를 계속 쓸지 말지가 첫 몇 회에 결정되고, **게스트는 영원히 콜드 스타트 상태**이기 때문입니다. 매번 2\~4명씩 데이터 없는 사람이 섞이는 한, 사전값을 잘 받는 장치는 계속 필요합니다.

> v0.2 문서에서는 "설문 없이 데이터만 20회 모으면 설문 하나보다 못하다"고 적었습니다. 이는 **참석률이 높은 소규모 클럽(24명 중 12명 참석)** 을 가정한 결과였고, 실제 조건(등록 30명 중 12\~14명 참석, 게스트 유입)에서는 참석자 조합이 훨씬 다양해져 데이터의 식별력이 올라갑니다. **재측정 결과로 정정합니다.**

## 8\.1 설계 제약과 원칙

- **소요 시간 2\~3분** \= 문항 14개 내외 (모바일 기준 문항당 8\~12초)
- **자기평가 편향 방어** — "실력이 몇 점인가"를 묻지 않고, **관찰 가능한 행동**으로 묻는다 (BARS, Behaviorally Anchored Rating Scale)
- **지식 게이팅(knowledge gating)** — 상위 앵커를 "실제로 그 수준이 아니면 고를 수 없는 구체적 용어·행동"으로 서술한다. 스크린 대응 문항의 최상위 선택지가 "상황에 따라 스위치·헤지·언더를 구분한다"인 이유. 초심자는 이 문장을 이해하지 못하므로 과대 응답이 구조적으로 차단된다
- **짝수 척도(4단계)** — 5점 척도는 한국 응답자에게 중앙집중편향(central tendency bias)이 강하게 나타난다. 4단계는 방향 선택을 강제한다
- **상대 평가를 반드시 포함** — 우리가 필요한 것은 절대 실력이 아니라 **동호회 내 상대 순위**다. 절대 척도 6문항보다 "본인은 이 모임에서 대략 어느 위치인가" 1문항의 정보량이 크다

## 8\.2 척도 체계 — 3종류만 쓴다

| 척도 | 사용 문항 | 선택 이유 |
| --- | --- | --- |
| **4단계 행동 앵커 (서열)** | 실력·이해도 문항 | 숫자 척도 대비 편향이 작고, 앵커 문구 자체가 지식 게이팅 역할 |
| **다중선택 칩** | 공격 옵션, 가능 포지션 | 터치 1회씩, 가장 빠름. **선택 개수 자체가 다재다능성 지표**가 되고 조합이 포지션 프로파일을 알려줌 |
| **서열 단일선택 (5택)** | 슛 거리, 자기 백분위 | 연속적 크기를 한 번에 표현 |

**금지 척도:** 1\~10 숫자 척도(사람마다 해석이 다름), "당신의 실력 점수는?"(직접 자기평가), 자유 텍스트(분석 불가·시간 소모).

## 8\.3 문항 구성 — 설문 v2 (12문항 · 11화면 · 약 2분)

v1(15문항)을 써 본 피드백으로 v2 를 만들었다(2026-09-08). 달라진 점:

- **키(A1) 삭제** — 가입 폼 · 프로필에서 받는 `users.height_cm` 을 쓴다
- **A3 경기 수준을 5단계로** 세분화 (서열 단일선택)
- **D2(가장 선호하는 포지션) 삭제** — D1 을 "선호하는 순서대로 고르는" 순서 있는 다중선택으로 바꿔 선택 순서가 곧 `preference_rank`
- **E3(동호회 내 상대 위치)를 설문에서 뺐다** — 팀을 알아야 상대 위치를 답할 수 있으므로 **팀 가입 후 팀별로** 묻는다(S-23, `player_profiles.self_rank_level`). 두 팀에 속하면 팀마다 따로 답한다
- E1 성향 · E2 체력 문구를 구체적이고 같은 형식으로

| 섹션 | \# | 문항 | 형식 |
| --- | --- | --- | --- |
| A 기본 | A2 | 농구를 해온 기간은 얼마나 되나요? | 4택 — 1년 미만 / 1\~3년 / 3\~7년 / 7년 이상 |
|  | A3 | 경험한 가장 높은 경기 수준은? | 5택 서열 — 체육시간 / 동네 야외 농구장 / 동호회 혹은 동아리 / 아마추어 대회 / 선수 출신 |
| B 공격 | B1 | 실제 경기에서 **자주 쓰는** 공격 옵션을 모두 고르세요 | 다중선택 8칩 — 캐치앤슛 3점 / 풀업·미들 점퍼 / 드라이브 후 마무리 / 픽앤롤 핸들러 / 픽앤롤 롤·팝 / 포스트업 / 오프볼 컷인 / 공격 리바운드 풋백 |
|  | B2 | 경기에서 **안정적으로** 넣을 수 있는 최대 거리는? | 5택 서열 — 골밑 레이업 / 페인트존 훅·플로터 / 자유투 라인 / 3점 라인 / 3점 라인 밖 |
|  | B3 | 볼 운반과 돌파는 어느 정도인가요? | 4택 앵커 — 드리블 돌파를 시도하지 않음 / 가벼운 압박은 벗겨냄 / 하프코트 압박에서도 볼을 운반함 / 풀코트 압박에서도 안정적으로 가져감 |
| C 수비 | C1 | 상대가 스크린을 걸었을 때 나는 | 4단계 앵커 — ① 스크린이 뭔지 잘 모르거나 그냥 따라간다 ② 피해서 따라가려 하지만 자주 놓친다 ③ 스위치를 부르고 바꿔 막는다 ④ 상황에 따라 스위치·헤지·언더를 구분해서 쓴다 |
|  | C2 | 동료 매치업이 뚫렸을 때 나는 | 4단계 앵커 — ① 내 사람만 본다 ② 헬프는 가지만 이후 내 자리로 못 돌아온다 ③ 헬프 후 내 매치업으로 복귀한다 ④ 헬프 사이드까지 읽고 미리 로테이션을 돈다 |
| D 포지션 | D1 | 수행 가능한 포지션을 **선호하는 순서대로** 고르세요 | 순서 있는 다중선택 5칩 (PG/SG/SF/PF/C) |
|  | D3A · D3B | 1번(볼 운반) · 5번(골밑)을 맡을 수 있나요? (한 화면 2줄) | 각각 3택 — 가능하고 선호함 / 가능하지만 선호하지 않음 / 불가 |
| E 성향 | E1 | 경기 중 공격에는 주로 어떻게 참여하나요? | 4단계 — 내가 공을 잡고 만들어간다 ↔ 거의 공 없이 움직이며 받으면 바로 마무리한다 |
|  | E2 | 체력은 어느 정도인가요? | 4단계 — 1쿼터를 뛰면 힘들다 / 2쿼터까지 / 3\~4쿼터까지 / 경기 내내 페이스 유지 |
| 팀 가입 후 | 자기 위치 | **이 동호회에서 본인의 실력 위치** (구 E3, 팀별) | 5택 서열 — 상위 10% / 상위 30% / 중간 / 하위 30% / 하위 10% |

> **B1이 1문항으로 하는 일:** 선택 **개수** \= 공격 다재다능성. 선택 **조합** \= 포지션 프로파일. 캐치앤슛\+컷인만 → 오프볼 윙. 픽앤롤 핸들러\+풀업 → 온볼 가드. 포스트업\+롤맨\+풋백 → 빅맨. 전술 추천의 역할 적합도(14장)도 이 조합을 쓴다.
>
> **C1 · C2 는 용어를 아는지로 실질 수준을 가른다.** 수비 이해도는 자기평가가 가장 부정확한 영역이라 상향 편향에 강한 문항으로 둔다.
>
> **D3 를 D1 에서 분리하는 이유:** 1번 · 5번은 배정 알고리즘의 **하드 제약**이다. 다중선택 안에 섞어두면 무심코 전부 체크하는 경향이 있어, 별도 질문으로 응답 비용을 만든다.
>
> **자기 위치가 단일 최고 정보량 문항이다.** 배정에 필요한 것은 절대 점수가 아니라 클럽 내 순위이고, 사람은 절대 평가보다 상대 위치 판단을 훨씬 잘한다. 겸손 편향이 있더라도 **모두가 같은 방향으로 편향되므로 순위는 보존**된다.

## 8\.4 응답 → 사전 실력값(prior) 변환

각 문항을 클럽 내 z\-score로 표준화한 뒤 가중합합니다. 절대값은 의미가 없고 **클럽 내 상대 위치만** 사용합니다.

```
prior_z = 0.30 × z(팀별 자기 위치 — 구 E3, 팀 가입 후)
        + 0.20 × z(A2 구력, A3 경기 수준)
        + 0.20 × z(B2 슛 거리, B1 옵션 개수)
        + 0.15 × z(B3 볼 운반)
        + 0.15 × z(C1, C2 수비 이해도)

세부 축(표시·포지션 매칭용):
  슛      ← B2, B1(캐치앤슛·풀업)
  볼핸들링 ← B3, B1(픽앤롤 핸들러)
  패스     ← B1(픽앤롤 핸들러·롤팝 조합), E1
  수비     ← C1, C2
  골밑     ← 키(users.height_cm), B1(포스트업·롤·풋백), D3
  체력     ← E2
```

## 8\.5 매니저 정렬 (Manager Sort) — 가장 비용 대비 효과가 큰 장치

설문 정확도 ρ를 올리는 가장 저렴한 방법은 **매니저에게 팀원 순위를 한 번 매기게 하는 것**입니다.

- **UI:** 팀원 카드를 드래그해서 실력 순으로 늘어놓는 화면. 12명 기준 약 2분
- **근거:** 사람은 절대 점수화보다 **순서 판단(ordinal judgment)** 에 훨씬 강합니다. 매니저는 이미 머릿속에서 이 순서를 쓰고 있으므로 새로운 인지 부담이 아닙니다
- **효과 (9.3절 시뮬레이션):** ρ를 0.5 → 0.8로 올리면 팀 균형이 4.16점 차 → 2.67점 차로 **36% 개선**. 이는 20회 모임치 경기 데이터를 모으는 것보다 큰 효과이며, 소요 시간은 2분입니다
- **결합:** `prior_final_z = 0.5 × prior_survey_z + 0.5 × manager_rank_z` (정렬이 있을 때). 신규 가입자는 설문값만 쓰다가 다음 정렬 때 편입
- **갱신 주기:** 분기 1회 또는 신규 3명 이상 유입 시 알림

## 8\.6 앵커 재보정 (Anchor Recalibration)

4단계 앵커의 간격이 실제로 균등한지는 알 수 없습니다. 초기에는 균등(0/1/2/3)으로 두되, 데이터가 쌓이면 **각 선택지를 고른 사람들의 실제 RAPM 평균값으로 선택지 점수를 재추정**합니다 (분기 1회 배치).

예: C1에서 ③을 고른 사람과 ④를 고른 사람의 실측 차이가 미미하다면 두 선택지의 배점을 좁힙니다. 시간이 지날수록 설문 자체가 정확해지는 구조이며, `survey_templates.version`으로 이력을 관리합니다.

# 9\. 실력·케미 산출 모델과 팀 배정 알고리즘

## 9\.1 코트 마진의 함정 — 왜 그냥 누적하면 안 되는가

원시 코트 마진(raw plus/minus)을 그대로 누적하면 **세 가지 이유로 0에 수렴하거나 실력과 무관해집니다.**

1. **제로섬 구조** — 한 쿼터에서 출전 선수 10명의 마진 합은 정의상 항상 0입니다. 전체 인원의 누적 마진 합도 항상 0입니다
2. **자기 파괴적 되먹임** — 배정 알고리즘이 잘 작동할수록 양 팀 실력이 같아지고, 마진은 노이즈만 남습니다. **서비스가 성공할수록 데이터가 무의미해집니다**
3. **역선택 편향** — 잘하는 선수일수록 약한 팀에 배정되므로, 오히려 마진이 낮게 나옵니다

실측(9.3절 실험 3, `backend/scripts/simulate_rating.py`로 재현): 앱의 실제 조건(추정치로 팀 균형 + 설문 사전값)에서 320쿼터를 누적하면 원시 누적 마진과 실제 실력의 순위 상관은 **0\.61**, 배정이 완벽해지는 극한에서는 **0\.24**까지 떨어집니다. 같은 데이터로 아래 잔차 모델을 적용하면 각각 **0\.89 / 0\.49**(RAPM 0\.92 / 0\.68)입니다. 팀 균형이 좋아질수록 원시 마진만 무너집니다.

**결론: 마진을 누적하지 말고, "기대 마진 대비 초과분(잔차)"을 누적해야 합니다.**
`잔차 = 실제 마진 − (우리 팀 실력 합 − 상대 팀 실력 합)`
이것이 사용자가 고민한 "단순 누적 대신 점수화해서 더하고 빼는" 방식의 정확한 형태이며, 스포츠 분석에서 **Adjusted Plus\-Minus (APM)** 로 확립된 접근입니다.

## 9\.2 실력 산출 모델 — 2층 구조

### 층 1. 실시간 Elo (매 쿼터 즉시 갱신, 서비스가 실제로 쓰는 값)

쿼터 저장 시:

```
1. 마진 축소변환   M' = clip(실제 마진, -15, +15) × (10 / 쿼터 길이(분))
     └ 30점 차 승리가 10점 차보다 3배 잘한 것이 아니고,
       블로우아웃에는 가비지타임이 섞이므로 상한을 둔다
2. 기대 마진       E  = Σ(우리 팀 출전 5명 r) − Σ(상대 팀 출전 5명 r)
3. 잔차            D  = M' − E
4. 갱신            r_i ← r_i + K_i × D / 5        (우리 팀은 +, 상대 팀은 −)
5. 신뢰도          n_i ← n_i + 1

   적응형 학습률   K_i = 0.35 / (1 + n_i / 20)
     └ 신규 선수는 빠르게 움직이고, 표본이 쌓이면 둔감해진다
```

`r`은 "쿼터당 득실 기여도(점)" 단위이므로 해석이 명확합니다. `r = +2.0`은 "이 선수가 코트에 있으면 팀이 쿼터당 2점 유리"라는 뜻입니다.

> **이 Elo 갱신식은 임의로 만든 것이 아닙니다.** 아래 RAPM 목적함수를 확률적 경사하강(SGD)으로 푸는 것과 수학적으로 동일합니다. 따라서 Elo로 먼저 구현하고 나중에 배치 RAPM을 얹어도 **모델이 바뀌는 것이 아니라 같은 모델을 더 정확히 푸는 것**입니다. 초보 개발자에게 안전한 경로입니다.

### 층 2. 배치 RAPM (주 1회, 층 1의 값을 보정)

쿼터 하나를 관측치 하나로 보는 능형회귀(ridge regression):

```
관측치 i (쿼터 i):
  y_i = 홈 득점 − 원정 득점  (축소변환·길이정규화 후)
  x_i = 길이 P 벡터,  홈팀 출전 +1 / 원정팀 출전 −1 / 미출전 0

목적함수:
  β̂ = argmin  ‖y − Xβ‖²  +  λ‖β − β_prior‖²
                └ 경기 데이터        └ 설문 사전값으로의 수축

닫힌 해:
  β̂ = β_prior + (XᵀX + λI)⁻¹ Xᵀ(y − X·β_prior)
```

- 일반 ridge는 계수를 0으로 수축시키지만, 여기서는 **설문 사전값 `β_prior`(8.4절)로 수축**시킵니다. 데이터가 없으면 설문값 그대로, 데이터가 쌓이면 서서히 실측으로 이동합니다
- **λ는 교차검증으로 결정합니다.** 표본이 적을수록 λ가 커져 자동으로 보수적이 됩니다. 별도의 "몇 쿼터부터 반영" 규칙이 필요 없습니다
- 항상 같이 뛰는 두 사람은 원리적으로 분리 불가능한데(다중공선성), ridge가 이 경우 두 사람을 비슷한 값으로 눌러줍니다 — 정직한 처리입니다
- 구현: `numpy.linalg.solve` 한 줄. 24명 × 300쿼터 규모는 밀리초 단위입니다

### 표시 정책

- 플레이어에게 **숫자를 보여주지 않습니다.** 5등급(A\~E)으로만 표시하거나 아예 비공개
- 등급은 **일정 단위로 갱신**합니다. 매 쿼터 등급이 흔들리면 신뢰를 잃으므로, 매니저가 경기 후 그 일정의 쿼터를 한 번에 저장할 때 다시 계산한다 (v1.0 결정 — 초안의 "8쿼터 단위"는 쓰지 않는다. 일정 하나가 7\~10쿼터라 거의 같은 주기이고, 사용자에게 설명하기 쉽다)
- 등급 변경은 추정값이 경계를 넘고 **신뢰도 하한도 함께 넘을 때만** 반영합니다

> **구현 (v1.0):** 등급은 **같은 팀 활동 회원 안에서의 위치(분위수)** 다 — 상위 10% A · 다음 20% B · 가운데 40% C · 다음 20% D · 하위 10% E (회원 10명이면 1 · 2 · 4 · 2 · 1명). 설계 전체가 절대 실력이 아니라 동호회 안의 상대 순위를 다루기 때문이다(8.1절). 게스트는 비교 대상에 넣지 않고 회원들과 비교해 등급만 매긴다(한 번 오고 안 오는 게스트가 분포를 흐리지 않게). 회원이 5명보다 적으면 절대 구간(A ≥ +2 · B ≥ +1 · C ≥ −1 · D ≥ −2 · E)을 쓴다. "신뢰도 하한" 조건은 두지 않았다. 층 1(잔차 Elo)은 구현했고 층 2(배치 RAPM)는 누적 100쿼터 이후다.

## 9\.3 시뮬레이션 검증 결과 (v0.3 재측정)

**모의 조건 — 2.5절 실제 프로토콜을 그대로 구현.** 등록 인원 30명 / 매회 **12\~14명** 참석(무작위) / **2팀으로 나눠 그날 하루 팀 고정** / 팀당 5명 출전, 나머지는 **로테이션 휴식** / 쿼터 수 **7\~10회 유동** / 개인 실력 표준편차 2점·쿼터 마진 노이즈 표준편차 6점 / 몬테카를로 반복 40\~60회 / 능형 계수 λ는 조건별 교차검증.

> 반복 횟수 때문에 각 수치에 ±0.02\~0.08의 시뮬레이션 오차가 있습니다. 개별 칸이 아니라 **추세**를 읽어야 합니다.

### 실험 1 — 개인 실력 순위 복원 (Spearman 상관)

| 모임 | 누적 쿼터 | 설문 없음 | 설문 ρ\=0.5 | 설문 ρ\=0.65 | 설문 ρ\=0.8 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0 | 0 | 0\.00 | 0\.50 | 0\.65 | 0\.80 |
| 1 | 8 | 0\.19 | 0\.51 | 0\.64 | 0\.78 |
| 3 | 26 | 0\.39 | 0\.58 | 0\.68 | 0\.79 |
| 5 | 42 | 0\.51 | 0\.62 | 0\.72 | 0\.81 |
| 8 | 68 | 0\.62 | 0\.69 | 0\.76 | 0\.84 |
| 12 | 102 | 0\.69 | 0\.75 | 0\.80 | 0\.86 |
| 20 | 170 | 0\.81 | 0\.84 | 0\.86 | 0\.89 |
| 30 | 255 | 0\.87 | 0\.89 | 0\.90 | 0\.92 |
| 45 | 383 | 0\.92 | 0\.93 | 0\.94 | 0\.94 |

**안정화 시점: 20\~30회 모임(170\~255쿼터).** 주 1회 기준 5\~7개월입니다. 그 전까지는 설문 사전값이 결과를 좌우합니다.

### 실험 2 — 팀 균형 품질 (실제 의사결정 지표, 낮을수록 좋음)

참석 12명을 2팀으로 완전탐색 배정했을 때 **두 팀의 진짜 실력 평균 차이**(점/쿼터). 기준선: **무작위 배정 0.87점** — 5명 출전 기준 **팀 득점차 약 4.3점**에 해당합니다.

| 모임 | 설문 없음 | ρ\=0.5 | ρ\=0.65 | ρ\=0.8 |
| --- | ---: | ---: | ---: | ---: |
| 0 | 0\.94 | 0\.96 | 0\.71 | 0\.61 |
| 3 | 0\.78 | 0\.71 | 0\.73 | 0\.51 |
| 8 | 0\.61 | 0\.63 | 0\.53 | 0\.56 |
| 12 | 0\.68 | 0\.48 | 0\.47 | 0\.51 |
| 20 | 0\.48 | 0\.44 | 0\.48 | 0\.36 |
| 30 | 0\.39 | 0\.36 | 0\.29 | 0\.27 |

읽을 것: **무작위 배정 대비, 좋은 설문만으로도 첫날부터 약 30% 개선**(0.87 → 0.61)되고, 20\~30회 뒤에는 60\~70% 개선(→ 0.27\~0.36)됩니다. 팀 득점차로 환산하면 **4\.3점 → 1.4점**입니다.

### 실험 3 — 원시 누적 마진 vs 잔차 모델

**재현 스크립트:** `backend/scripts/simulate_rating.py` (40회 반복, 320쿼터 시점, 참값과의 스피어만 순위 상관). 회귀 테스트 `backend/tests/test_rating_simulation.py`가 CI마다 아래 관계를 검사합니다. 설계 초안의 수치(0\.43 → 0\.86)는 스크립트가 남지 않아 재현했으며, 결과는 **팀을 얼마나 잘 균형 맞추느냐에 따라 달라지므로** 조건별로 적습니다.

| 팀 나누는 방식 | 원시 누적 마진 | 쿼터당 평균 | 잔차 Elo (앱, 9.2절 층 1) | 능형 RAPM (층 2) | 역선택 지표\* |
| --- | ---: | ---: | ---: | ---: | ---: |
| 무작위 (앱을 안 쓸 때) | 0\.78 | 0\.78 | 0\.88 | 0\.92 | −0\.36 |
| 추정치로 균형, 설문 없음 | 0\.77 | 0\.77 | 0\.89 | 0\.93 | +0\.46 |
| **추정치로 균형 + 설문 ρ=0.65 (앱의 실제 조건)** | **0\.61** | 0\.62 | **0\.89** | **0\.92** | +0\.56 |
| 참값으로 완벽 균형 (배정이 성공한 극한) | 0\.24 | 0\.25 | 0\.49 | 0\.68 | +0\.83 |

\* 참값과 "그 사람이 만난 상대 팀 강도"의 상관. 양수면 잘하는 사람일수록 강한 상대를 만난다는 뜻이며, 이때 원시 마진은 실력을 과소평가합니다.

읽을 것: 어느 조건에서든 잔차 모델이 원시 마진보다 낫고, **팀 균형이 좋아질수록 원시 마진은 0\.78 → 0\.61 → 0\.24로 무너지는 반면 잔차 모델은 0\.88 → 0\.89 → 0\.49(RAPM 0\.68)로 훨씬 덜 무너집니다.** 배정 기능이 성공할수록 원시 마진이 쓸모를 잃는다는 9.1절의 "자기 파괴적 되먹임"이 그대로 나타납니다. 완벽 균형의 극한에서는 잔차 모델도 식별력이 떨어지는데(두 팀이 늘 같으면 신호가 줄어듦), 이것이 로테이션·회차별 참석자 변동이 필요한 이유이고(실험 4), 배치 RAPM이 실시간 Elo보다 이 극한에 강합니다.

**방법과 참고 문헌.** 참값을 아는 가상 동호회(30명, 실력 SD 2점)에 2.5절 프로토콜을 그대로 적용해 시즌을 돌리고, 쿼터 마진 = 출전 5명 참값 합의 차 + 노이즈(SD 6점)로 만든 뒤, 같은 기록에서 네 지표를 계산했습니다. 팀 나누기는 앱처럼 그 시점 추정치로 합니다. 잔차 접근은 농구 분석의 Adjusted Plus-Minus(Rosenbaum 2004)와 능형 회귀로 정규화한 RAPM(Sill 2010, MIT Sloan Sports Analytics Conference)을 따르고, 실시간 갱신식은 Elo(1978)의 "기대값 대비 결과" 갱신을 RAPM 목적함수 ‖y − Xβ‖²의 관측치별 경사하강으로 유도한 것입니다(∂/∂β_i = −2·x_i·잔차). 능형 회귀는 Hoerl & Kennard(1970).

### 실험 4 — 운영 방식(팀 하루 고정)이 데이터 품질에 주는 손해

| 모임 | 팀 하루 고정 (실제 운영) | 2쿼터마다 재편성 (가상) |
| --- | ---: | ---: |
| 5 | 0\.51 | 0\.50 |
| 12 | 0\.69 | 0\.75 |
| 20 | 0\.81 | 0\.85 |
| 30 | 0\.87 | 0\.90 |

**팀을 하루 고정으로 운영해도 손해는 크지 않습니다 (20회 기준 0.81 vs 0.85).**

같은 팀 5\~7명이 하루 종일 붙어 있어 서로 잘 분리되지 않지만, **로테이션(누가 쉬는가)과 회차마다 달라지는 참석자 조합**이 그 공백을 메웁니다. 게스트가 매번 섞이는 것도 역설적으로 식별력에 도움이 됩니다.

**결론: 데이터를 위해 운영 방식을 바꾸라고 요구하지 않습니다.** 현재 방식 그대로 두어도 됩니다.

## 9\.4 케미(친화도) 정책

### 질문: 케미를 코트 마진으로 계산할 수 있는가

케미의 통계적으로 정확한 정의는 **회귀 모형의 상호작용항**입니다.

```
y = Σ β_j x_j  +  Σ γ_jk z_jk  +  ε

  z_jk = +1 (j,k가 함께 블랙 출전) / −1 (함께 화이트 출전) / 0 (그 외)
  γ_jk = 두 사람 개인 기여도의 합으로 설명되지 않는 초과분 = 시너지
```

이것이 "함께 뛰었을 때와 아닐 때를 비교"하는 방식의 **교란 통제된 정확한 버전**입니다. 단순 비교는 (a) 그때 같이 있던 다른 강한 동료, (b) 상대 팀 구성을 통제하지 못하고, (c) 20명이면 페어가 190개라 5% 유의수준에서 우연히 10개가 "유의"하게 나옵니다.

### 검증 결과: 불가능합니다

개인 효과를 회귀로 제거하고, 페어 항에 강한 능형 벌점을 주고, 부트스트랩 250회로 95% 신뢰구간을 잡아 검정력을 측정했습니다. **실제 운영 프로토콜 기준:**

| 모임 수 | 페어당 함께 뛴 쿼터 | 진짜 시너지 | 검출률 | 허위 양성률 |
| --- | ---: | ---: | ---: | ---: |
| 20회 (≈170쿼터) | 6 | 2\.0점/쿼터 | **12%** | 9% |
| 20회 | 6 | 3\.0점/쿼터 | 24% | 9% |
| 20회 | 6 | 5\.0점/쿼터 | 40% | 12% |
| 20회 | 6 | 8\.0점/쿼터 | 63% | 12% |
| 40회 (≈340쿼터) | 12 | 2\.0점/쿼터 | **16%** | 5% |
| 40회 | 12 | 3\.0점/쿼터 | 40% | 7% |
| 40회 | 12 | 5\.0점/쿼터 | 69% | 9% |
| 40회 | 12 | 8\.0점/쿼터 | 91% | 11% |

**세 가지가 동시에 나쁩니다.**

1. **표본이 절대적으로 부족합니다.** 등록 30명 중 12\~14명이 참석하는 구조에서 특정 두 사람이 20회 모임 동안 함께 출전하는 쿼터는 **평균 6쿼터**입니다. 둘 다 참석할 확률(≈0.2) × 같은 팀일 확률(≈0.5) × 둘 다 코트에 있을 확률(≈0.6)이 곱해지기 때문입니다
2. **현실적 크기의 시너지는 잡히지 않습니다.** 개인 실력 표준편차가 2점인 세계에서 8점짜리 시너지는 비현실적입니다. 현실적인 1\~3점대의 검출률은 **12\~40%** 입니다
3. **허위 양성률이 명목치를 초과합니다.** 95% 구간인데 실제 허위 양성이 5\~12%입니다. 즉 "유의하다"고 표시된 조합의 상당수가 가짜입니다

산수로도 확인됩니다. 6쿼터 표본에서 쿼터 노이즈 표준편차가 6점이면 표준오차는 6/√6 ≈ 2.4점입니다. 2점짜리 효과의 t값은 0.8 — 검정력이 나올 수 없습니다. **80% 검정력에 필요한 동반 출전은 60\~90쿼터이고, 이는 주 1회 기준 3년 이상입니다.**

**답: 케미는 코트 마진으로 계산하지 말고, 경기 후 설문으로 반영하는 것이 맞습니다.**

근거 없는 케미 점수를 "데이터 기반"이라고 제시하는 것은 감으로 팀을 나누는 것보다 나쁩니다. 틀린 결정에 권위를 씌우기 때문입니다. 반면 **피어 투표는 "이 사람과 또 뛰고 싶다"는 사실을 직접 물어본 것이므로, 추정이 아니라 관측입니다.** 표본 문제도, 교란 문제도, 다중비교 문제도 없습니다.

그리고 배정에 실제로 필요한 것도 그쪽입니다. P8("원하지 않는 사람과 팀이 될 수 있음")은 통계적 시너지가 아니라 **참가자의 선호** 문제입니다.

### 채택 정책 — 케미를 "측정"하지 않고 "선언"받는다

| 층 | 이름 | 출처 | 배정 반영 |
| --- | --- | --- | --- |
| **1차 (주력)** | 선호 조합 | 경기 후 피어 투표 "다음에 같이 뛰고 싶은 사람" — 상호 지목이면 강한 신호 | `CHEMISTRY` 전략의 주 입력. UI 표기는 **"선호 조합"** — 하지 않은 통계적 주장을 하지 않는 정직한 이름 |
| **1차 (주력)** | 명시적 제약 | 매니저가 그 회차에 직접 지정하는 묶기 (9.6절) | 하드 제약 |
| **2차 (참고)** | 관찰 시너지 | RAPM 상호작용항 \+ 부트스트랩 CI | **함께 뛴 쿼터 ≥ 20** AND **95% CI가 0을 제외** AND **\|γ̂\| ≥ 4점** 을 모두 만족할 때만 노출. 배정 가중치 상한 0.1 |

2차 층의 조건은 의도적으로 엄격합니다. 위 표대로라면 40회 모임을 해도 통과하는 페어는 거의 없을 것이고, **그것이 정직한 결과입니다.** 통과한 소수는 이렇게 표시합니다.

> 김민수 · 박지훈 — 함께 뛴 22쿼터에서 예상보다 **쿼터당 \+4.6점** (95% 신뢰구간 \+1.2 \~ \+8.0). 근거 수준: 보통

표본이 모자라는 페어는 점수를 0으로 두는 것이 아니라 **아예 표시하지 않습니다.** "케미 0점"은 "사이가 나쁘다"로 오독됩니다.

### F11 "나와 잘 맞는 참여자"는 어떻게 만드나

플레이어 대시보드의 이 기능은 **투표 데이터만으로** 구성합니다.

- 내가 지목했고 상대도 나를 지목한 사람 (상호 선호)
- 나를 "잘한 사람"으로 뽑아준 사람 / 내가 뽑은 사람
- 함께 뛴 횟수

"승률" 이나 "케미 점수" 같은 성과 지표는 넣지 않습니다. 표본이 부족해 매주 순위가 요동치고, 동호회 인간관계에 불필요한 마찰을 만듭니다.

### 데이터 모델 변경

6\.2절 `chemistry_scores` 참조. 단일 `chemistry` 컬럼을 삭제하고 `pref_score` / `pref_mutual`(선언된 선호)과 `synergy_est` / `synergy_ci_low` / `synergy_ci_high` / `synergy_significant`(관찰된 시너지)로 분리했습니다. 근거가 다른 두 신호를 한 숫자로 뭉개면 설명할 수 없기 때문입니다.

## 9\.5 배정 알고리즘

1. **입력** — 참석 확정자 N명(게스트 포함), 팀 수 T(2, 참석 16명 이상이면 3 선택), 회차별 제약(9.6절)
2. **제약 실현가능성 사전 검사** — 실패 시 실행 전에 사유와 함께 차단
3. **사전 배치(PIN) 반영** — 매니저가 팀 칸에 직접 올린 인원을 먼저 고정
4. **묶음 그룹을 슈퍼노드로 축약** (9.6절)
5. **희소 포지션** — 각 팀에 1번 가능자, 4·5번 가능자가 있도록 커버리지 결손을 벌점으로 (자원이 팀 수보다 적으면 경고 후 완화)
6. **탐색** — 2팀은 슈퍼노드 분할 **완전 탐색**(전역 최적), 3팀은 **지역 탐색**(9.7절)
7. **목적함수**

```
J = w_skill    × 팀별 평균 실력 차 (가장 강한 팀 − 가장 약한 팀)
  + w_position × Σ 포지션 커버리지 결손 페널티
  + w_pref     × (− 팀 내 선호 조합 점수 합)
  + w_role     × Σ 선호 포지션 미충족 페널티
  + w_fair     × 최근 회차 같은 팀 반복 페널티      (0.05)
  + w_guest    × 게스트 편중 페널티                 (0.05) ← 데이터 없는 인원이 한 팀에 몰리지 않게
```

8. **전략 3종으로 후보안 생성**

| 전략 | w\_skill | w\_position | w\_pref | w\_role |
| --- | ---: | ---: | ---: | ---: |
| **실력 우선** `SKILL` | 0\.70 | 0\.15 | 0\.05 | 0\.10 |
| **친화도 우선** `CHEMISTRY` | 0\.30 | 0\.15 | 0\.40 | 0\.15 |
| **종합** `BALANCED` | 0\.45 | 0\.25 | 0\.15 | 0\.15 |

> 초안에 있던 `POSITION`(포지션 우선) 전략은 제거했습니다. 희소 포지션은 5단계에서 이미 다루므로, 이를 다시 전략으로 두면 다른 두 전략과 결과가 거의 같아집니다. 후보안은 서로 뚜렷하게 달라야 매니저가 고를 이유가 생깁니다.

9. **포지션 배정 · 설명 생성** — 팀마다 선호 순위로 포지션을 정하고, 규칙 기반 템플릿으로 설명(매니저용 수치 · 플레이어용 문장). **게스트가 포함된 경우 "게스트 N명은 매니저 지정 등급(또는 평균)으로 계산했습니다"를 반드시 명시**. AI 배정 설명(F20)은 이 규칙 판단을 입력으로 받아 문장만 다시 쓴다(14장)
10. **수정 · 확정** — 매니저가 옮기기 · 맞교체하면 같은 목적함수로 그 배정안에 든 사람들만 다시 채점한다(배정 뒤 참석을 바꾼 사람은 재배정으로)

### 게스트를 배정에 넣는 방법

| 상황 | 처리 |
| --- | --- |
| 등록한 사람이 실력 등급(1\~5)을 지정 | 등급을 클럽 내 분위수로 환산해 `prior_overall`에 사용, `skill_confidence = 0.25` |
| 등급 미지정 | **클럽 평균값** 적용, `skill_confidence = 0`. 배정 화면과 설명 문구에 "데이터 없음" 명시 |
| 과거 방문 이력 있음 | 누적된 잔차 데이터를 그대로 사용 (일반 회원과 동일) |
| 게스트가 한 팀에 몰림 | 목적함수의 `w_guest` 항이 억제. 불확실성이 한쪽에 쌓이는 것을 막기 위함 |

## 9\.6 배정 제약 — 묶기 / 분리 / 사전 배치

> **요구사항 (v0.3)**
> ① 2명 이상을 묶으면 어떤 배정 기준을 선택하더라도 반드시 같은 팀이 되어야 한다
> ② 제약은 **회차마다 새로 설정**한다. 1주차에 A와 B를 묶었다고 2주차에도 묶이면 안 된다
> ③ 특정 인원을 **각 팀에 미리 꽂아두고** 나머지 자리만 알고리즘이 채우게 할 수 있어야 한다 *(2순위)*

### 세 가지 제약 유형

| 유형 | 동작 | UI 조작 | 우선순위 |
| --- | --- | --- | --- |
| **LOCK (묶기)** | 같은 그룹은 반드시 같은 팀 | 대기 칸에서 다중 선택 → `같은 팀으로 묶기` | 1순위 |
| **PIN (사전 배치)** | 지정한 팀 칸에 고정 | 참석자 칩을 팀 칸에 직접 드롭 | 2순위 |
| **SEPARATE (분리)** | 같은 그룹은 반드시 다른 팀 | 대기 칸에서 다중 선택 → `갈라놓기` | 2순위 |

> **LOCK과 PIN은 다른 기능입니다.** LOCK은 "누구와 같은 팀"만 지정하고 어느 팀인지는 알고리즘이 정합니다. PIN은 "블랙 팀"처럼 팀까지 지정합니다. 실제 상황에서 전자는 "이 둘은 붙여줘", 후자는 "블랙에 A·B, 화이트에 C·D 놓고 나머지 짜줘"에 해당합니다.

### 자료구조 — Union\-Find 슈퍼노드

LOCK을 목적함수 페널티로 구현하면 "실력 우선" 전략에서 묶음이 깨질 수 있습니다. 자료구조로 처리해야 어떤 가중치에서도 보장됩니다.

1. 모든 LOCK 페어를 union\-find로 병합 → 연결 요소가 하나의 묶음 그룹
   (A\-B와 B\-C를 묶으면 A\-B\-C가 자동으로 한 그룹. 사용자가 A\-C를 따로 지정할 필요 없음)
2. 각 그룹을 **슈퍼노드** 하나로 축약
   - `skill` \= 구성원 실력 **합**
   - `positions` \= 구성원 가능 포지션의 **합집합(멀티셋)**
   - `size` \= 인원수
3. 배정 알고리즘은 슈퍼노드 단위로만 동작 → 개별 선수를 다루지 않으므로 **제약 위반이 원천적으로 불가능**
4. 지역 탐색의 교환 단위도 슈퍼노드 (그룹은 통째로만 이동)
5. PIN된 인원은 해당 팀 칸에서 아예 제외하고 남은 정원만 계산 대상으로 삼음
6. 부수 효과로 **탐색 공간이 줄어듭니다** — 제약이 많을수록 빨라집니다

### 사전 실현가능성 검사 (실행 전 필수)

| 검사 | 조건 | 에러 |
| --- | --- | --- |
| 그룹 크기 | 최대 그룹 인원 \> 팀 정원 | `422 LOCK_GROUP_TOO_LARGE` |
| 제약 충돌 | 같은 페어가 LOCK과 SEPARATE에 동시 지정 | `422 CONSTRAINT_CONFLICT` |
| PIN 충돌 | 같은 LOCK 그룹의 두 사람이 서로 다른 팀에 PIN | `422 CONSTRAINT_CONFLICT` |
| PIN 정원 | 한 팀 칸의 PIN 인원 \> 정원 | `422 SQUAD_OVERFLOW` |
| 분리 실현성 | SEPARATE 그래프를 T색으로 채색 불가 | `422 SEPARATE_INFEASIBLE` |
| 분할 가능성 | 슈퍼노드 크기들로 팀 정원을 채우는 부분합이 없음 | `422 LOCK_PARTITION_INFEASIBLE` |
| 인원 | 참석자 \< 팀 수 × 5 | `422 NOT_ENOUGH_PLAYERS` |

검사 없이 실행하면 알고리즘이 답을 못 찾고 무한 반복하거나 **조용히 제약을 어깁니다.** 사전 검사를 명시적 단계로 두고, 프론트에서는 `POST /assignments:validate`로 실행 버튼을 누르기 전에 미리 확인합니다. 오류 응답의 `details[]`에는 **어떤 그룹·어떤 선수가 문제인지**를 담아야 매니저가 무엇을 풀어야 할지 알 수 있습니다.

### 저장 위치 — 회차별 (v0.3 변경)

초안에는 팀 단위 상시 제약 테이블(`team_constraints`)이 있었지만, 실제로는 **매 회차 새로 설정**하는 것이 맞습니다. 따라서 제약은 `assignment_runs`에 종속된 `assignment_constraints`에만 저장합니다.

- 다음 회차 배정 화면은 **항상 빈 상태**로 시작합니다
- 편의 기능으로 `직전 회차 제약 불러오기` 버튼만 제공합니다 (`GET /events/{id}/assignments/last-constraints`)
- 같은 회차에서 배정을 여러 번 재실행하면 제약은 유지되고, 새 `run`으로 복사됩니다

### API

```
POST /api/v1/events/{event_id}/assignments
{
  "team_count": 2,
  "strategies": ["SKILL", "CHEMISTRY", "BALANCED"],
  "constraints": {
    "lock_groups":     [[12, 45, 78], [3, 9]],
    "separate_groups": [[21, 33]],
    "pins":            [{ "player_id": 5, "squad_no": 1 },
                        { "player_id": 8, "squad_no": 2 }]
  }
}
```

`lock_groups`·`separate_groups`는 페어가 아니라 **그룹 배열**입니다. 2명 이상 임의 인원을 한 번에 묶어야 하기 때문입니다.

### UI (S\-12 배정 실행 화면)

```
┌─ 대기 칸 (참석자 12명) ───────────────────┐
│  [김민수] [박지훈] [이영호] [게스트 최OO?] │
│  [정하늘] [윤재석] [오세훈] [강도현]        │
│  ─ 길게 눌러 다중 선택 → 하단 액션 바 ─    │
└───────────────────────────────────────────┘
┌─ 블랙 (0/6) ────┐  ┌─ 화이트 (0/6) ──────┐
│  (비어 있음)     │  │  (비어 있음)         │
└─────────────────┘  └─────────────────────┘
        [ 3가지 안으로 팀 짜기 ]
```

- 대기 칸에서 다중 선택 → 하단 액션 바에 `같은 팀으로 묶기` / `갈라놓기`
- 묶인 그룹은 동일 색상 테두리 \+ 칩에 인원수 배지
- 팀 칸에 직접 드롭 \= 사전 배치(PIN). 정원 초과 드롭은 거부
- 게스트 칩은 `?` 배지로 구분, 탭하면 실력 등급 즉시 수정
- 상단에 `직전 회차 제약 불러오기` 링크
- 실현 불가능한 제약은 **실행 버튼을 누르기 전에** 인라인 경고로 표시

## 9\.7 계산량

실제 참석 규모(12\~16명, 2팀)에서는 **완전 탐색으로 전역 최적해를 보장**합니다.

| 인원 | 팀 구성 | 전체 조합 수 | 방식 |
| --- | --- | ---: | --- |
| 12명 | 6 \+ 6 | 462 | **완전 탐색** |
| 13\~14명 | 6 \+ 7 · 7 \+ 7 | 1,716 | **완전 탐색** |
| 16명 | 8 \+ 8 | 6,435 | **완전 탐색** |
| 16\~21명 | **3팀** (21명이면 7 · 7 · 7) | 수억 | **지역 탐색** — 21명 약 0.1초 |

- **2팀 상한:** 묶음 축약 뒤 슈퍼노드 18개까지(2^18 ≈ 26만, 약 0.6초). 넘으면 실행 전에 안내한다(실측 22개는 10초라 내렸다)
- **3팀 지역 탐색:** 욕심쟁이 초기해에서 출발해 이웃(한 명 옮기기 · 두 명 맞바꾸기)을 한 번에 채점하고 가장 좋은 이웃으로 옮기기를 반복, 국소 최적에 빠지면 무작위로 두 번 맞바꿔 흔든 뒤 다시 내려간다. 전략마다 6번 새로 출발 · 흔들기 25번 · 8번 연달아 나아지지 않으면 멈춤 · 시드 고정(같은 입력 → 같은 결과)
- **정답 기준:** 15명 이하에서는 3팀도 완전 탐색이 가능해, 지역 탐색 결과가 완전 탐색 최적해와 같은지 테스트로 검증한다(60건 중 60건 일치)

**초보 개발자에게 이것은 매우 좋은 소식이었습니다.** 핵심 규모(2팀)는 휴리스틱 없이 완전 탐색으로 끝났고, 3팀을 붙일 때도 완전 탐색 버전이 **테스트 오라클**로 남아 지역 탐색을 검증했습니다.

## 9\.8 개발 순서와 결과

| 순위 | 항목 | 결과 |
| --- | --- | --- |
| 1 | 인증(카카오 \+ 이메일) · 팀 · 참가자(회원\+게스트) | ✅ 관리자 팀 승인 · 팀장 · 게스트 본인 확인 병합까지 |
| 2 | 온보딩 설문 \+ 매니저 정렬 \+ 게스트 등급 지정 | ✅ 설문 v2 · 팀별 자기 위치 |
| 3 | 배정 알고리즘 (완전 탐색) \+ 묶기 제약 | ✅ 3팀(지역 탐색)까지 |
| 4 | 쿼터 기록 \+ 잔차 기반 실력 갱신 | ✅ 첫 2회 게이트 · 삭제 롤백(팀 전체 재계산) |
| 5 | 피어 투표 → 선호 조합 | ✅ 이유 태그 · 함께 참석 대비 정규화 · 최근 가중 |
| 6 | 사전 배치(PIN) · 분리(SEPARATE) | ✅ |
| 7 | 배치 RAPM | ⏳ 누적 100쿼터 이후 (13.3절) |
| — | 마진 기반 케미 검정 | **v1 범위에서 제외** (9.4절). `chemistry_scores.synergy_*` 컬럼만 두고 계산하지 않는다 |
| 추가 | 기록 탭 · 배지 · 시작 안내 · 도움말 · 프로필 사진 · 지난 기록 | ✅ |
| 추가 | 전술 추천 · 전술판 · 팀 전술 · AI 설명 (14장) | ✅ |

# 10\. 기술적 타당성 검토

| 항목 | 판단 | 근거 / 대응 |
| --- | :---: | --- |
| 배정 알고리즘 구현 | **가능 (쉬움)** | 12\~14명 2팀이면 조합 2천 개 이하. **완전 탐색으로 전역 최적 보장**, 실행 수 밀리초. 외부 솔버 불필요. 3팀은 지역 탐색(21명 0.1초) (9.7절) |
| 묶기/사전배치 제약 | **가능** | Union\-Find 슈퍼노드로 축약하면 제약 위반이 원천 차단되고 탐색 공간도 줄어듦. 사전 실현가능성 검사만 빠뜨리지 않으면 됨 (9.6절) |
| 코트 마진 자동 계산 | **가능** | 쿼터 저장 시 서버에서 일괄 계산. 개인 스탯 입력 불필요 — 이 서비스의 핵심 실현 가능성 근거 |
| 쿼터 수 유동 대응 | **가능** | `quarters`를 `events`에 직결하고 `duration_min`으로 시간 정규화. `games` 테이블을 없애 오히려 단순해짐 |
| 원시 마진의 지표 활용 | **불가** | 제로섬·자기 파괴적 되먹임·역선택. 앱 조건에서 320쿼터 후 순위 상관 0.61, 팀 균형이 완벽해지면 0.24까지 하락 (잔차 모델은 0.89 / 0.49). **잔차 기반 모델 필수** (9.1\~9.3절, `scripts/simulate_rating.py`) |
| 실력 지표 신뢰성 | **조건부** | 안정화까지 20\~30회 모임(170\~255쿼터, 주 1회 기준 5\~7개월). 그 전까지는 설문\+매니저 정렬이 주력. 첫 2회 데이터는 미반영 |
| **게스트 콜드 스타트** | **최대 난제** | 매회 2\~4명이 데이터 0으로 참여. 매니저 등급 지정(5단계)으로 완화하되, **완전 해결은 불가**. UX에서 "게스트는 추정입니다"를 명시하고, 목적함수에서 게스트가 한 팀에 몰리지 않게 억제 |
| 팀 하루 고정 운영 | **문제 없음** | 재편성 대비 손해가 20회 기준 0.81 vs 0.85로 작음. **운영 방식을 바꾸라고 요구하지 않음** (9.3절 실험 4) |
| 마진 기반 케미 검정 | **불가** | 페어당 함께 뛴 쿼터가 20회 모임에 평균 6쿼터. 현실적 시너지(1\~3점) 검출률 12\~40%, 허위 양성률 5\~12%. 80% 검정력에 3년 이상 필요 (9.4절). **v1 제외** |
| 선언형 선호 조합 | **가능** | 피어 투표는 추정이 아니라 관측. 표본·교란·다중비교 문제가 없음 |
| 인기 투표 편향 | **완화 가능** | 함께 뛴 인원수로 정규화 \+ 응답자별 투표 총량 보정. 실력 지표에서 투표 가중치를 0.3으로 제한 |
| 실력 점수 공개로 인한 갈등 | **설계로 회피** | 플레이어에게 수치 비공개, 자기 등급(5단계)만. 등급은 일정 단위로 갱신 |
| **카카오 로그인 연동** | **가능 (쉬움)** | OAuth 2.0 Authorization Code. **닉네임·프로필사진은 일반 앱의 기본 동의항목이라 별도 검수 없이 사용 가능**. 이메일은 비즈 앱 전환이 필요하므로 **선택 항목으로 취급**하고 이메일 없이도 가입이 되도록 설계 (11.5절) |
| 비밀번호 보관 | **가능** | 암호화가 아니라 **단방향 해시(bcrypt)**. 복호화 자체가 불가능하므로 DB가 유출돼도 원문 복원 불가 (11.5절) |
| 비밀번호 재설정 메일 | **번거로움** | SMTP/발송 서비스 설정·토큰 만료 관리가 필요. 카카오 로그인을 주 경로로 두면 이 부담이 줄어듦 |
| 개인정보 | **주의 필요** | 키만 최소 수집(생년은 수집하지 않기로 해 삭제), 체중 미수집. 프로필 공개 범위를 팀 내로 제한. **게스트는 이름 · 키 · 등급 · 포지션만 저장**하고 연락처를 받지 않음 |
| 모바일 웹 푸시 알림 | **제한적** | iOS Safari는 PWA 홈 화면 추가 시에만 웹 푸시 지원. 1차 대안은 **카카오톡 링크 공유 \+ 인앱 배지**. MVP 범위 밖 |
| 오프라인 기록 입력 | **불필요해짐** | 기록을 경기 **후**에 입력하므로 체육관 통신 불량 이슈가 사라짐. localStorage 임시 저장만 안전장치로 유지 |
| 실시간 동시 편집 | **불필요** | 매니저 1인이 기록. WebSocket 불필요 |

> **결과 (v1.0):** 위 판단은 대체로 맞았다. 카카오 로그인 · 비밀번호 재설정 메일(Resend) · 기록 임시 저장은 구현했고, 웹 푸시는 하지 않았다(카카오톡 공유 + 인앱 배지). 새로 더한 **AI 설명**은 무료 등급 한도 · 데이터 약관 · 환각이 쟁점이라 판단은 규칙, 문장만 AI, 가명 · 가드레일 · 캐시 · 폴백으로 풀었다(14장). 게스트 콜드 스타트는 여전히 최대 난제라, 등록할 때 등급 · 키 · 포지션을 받고 가입하면 본인 확인으로 기록을 이어받게 했다.

# 11\. 기술 스택

## 11\.1 선정 기준

사용자 요구는 세 가지였습니다 — **스마트폰 웹 사용 전제**, **팀 배정 알고리즘이 최우선이므로 파이썬 백엔드**, **초보 개발자가 전체를 무리 없이 구현 가능한 난이도**. 아래 스택은 이 세 가지를 동시에 만족하도록 구성했습니다.

## 11\.2 스택 구성 (실제 운영)

| 레이어 | 선택 | 선정 이유 · 쓰임 |
| --- | --- | --- |
| **Backend** | **FastAPI** (Python 3.12) | ① 알고리즘 코드(NumPy)와 같은 언어 ② **Pydantic 스키마가 곧 OpenAPI 명세** → `docs/04-API명세-openapi.yaml` 을 코드에서 생성 ③ 구조가 명시적 |
| ORM / 마이그레이션 | SQLAlchemy 2.0 \+ Alembic | ERD 를 코드로, 스키마 이력 0001~0024. 배포할 때 `alembic upgrade head` 를 먼저 돌린다 |
| 검증 | Pydantic v2 | Request/Response 스키마, 비밀번호는 `SecretStr` |
| **Database** | **PostgreSQL** — 운영 **Neon**(18), 로컬 Docker(16) | JSONB(배정 파라미터 · 전술 본문 · AI 결과), 부분 유니크 인덱스, ENUM 타입 |
| 인증 | JWT(python\-jose) \+ passlib(bcrypt), 카카오 OAuth | refresh 회전 · 폐기 목록, 로그인 경로 요청 제한 |
| 메일 | Resend | 비밀번호 재설정 링크 (키가 없으면 서버 로그) |
| 관리자 화면 | **SQLAdmin** (`/admin`) | 관리자 콘솔을 직접 만들지 않음 — 팀 승인/거절 액션만 추가 |
| 알고리즘 | NumPy | 2팀 완전 탐색 · 3팀 지역 탐색(벡터화한 이웃 채점) · 잔차 Elo. OR-Tools 는 필요 없었다 |
| **AI** | **LangChain \+ Google Gemini**(무료 등급, `langchain-google-genai`) | 구조화 출력 · 재시도 · 예비 모델. 모델은 `LLM_MODEL` 로 바꾼다. 키가 없으면 모든 AI 카드가 규칙 문장 (14장) |
| **Frontend** | **React 19 \+ TypeScript \+ Vite** | 레퍼런스가 풍부, 타입으로 API 필드 불일치 조기 발견 |
| UI | Tailwind CSS v4 \+ 직접 만든 공통 컴포넌트 | 색 토큰(라이트 · 어두운 화면), 하단 고정 버튼 · 시트 · 44px 터치 영역 |
| 상태 · 데이터 | TanStack Query \+ Zustand | 서버 상태(캐싱 · 재검증)와 인증 상태 분리 |
| API 타입 | 손으로 쓴 `frontend/src/api/types.ts` | OpenAPI 와 필드명을 맞춘다 (자동 생성 도구는 쓰지 않았다) |
| **배포** | **Render**(API) · **Vercel**(웹) · **Neon**(DB) | 무료 등급. GitHub 푸시로 자동 배포 |
| CI · 운영 작업 | GitHub Actions | 푸시마다 ruff · pytest · 타입 검사 · Vitest · 빌드 · Playwright. 매주 월요일 데모 데이터 새로 만들기, 매일 DB 백업(pg_dump) |
| 테스트 | pytest \+ httpx (백), Vitest \+ Testing Library \+ Playwright (프론트) | 권한 · 배정 제약 · 롤백 · 전술 · AI 가드레일 · 쿼리 수 예산 |
| 문서 | FastAPI `/docs` (로컬) \+ `docs/01~07` \+ 이 문서 | API 명세가 코드와 동기화 |

> **v0.3 대비:** Railway 대신 Render, 관리형 DB 는 Neon. shadcn/ui · openapi-typescript · PWA(vite-plugin-pwa) · OR-Tools 는 쓰지 않았다. 웹 푸시도 없다 — 알림은 카카오톡 공유와 인앱 배지로.

## 11\.3 컨테이너 구성 (로컬 재현)

```
docker-compose.yml
├── db      : postgres:16-alpine        (volume: pgdata)
├── api     : ./backend  (alembic upgrade → uvicorn)   → depends_on: db
└── web     : ./frontend (vite build → nginx)
```

## 11\.4 이 조합이 초보 친화적이었던 이유

1. **API 명세를 두 번 쓰지 않는다.** Pydantic 모델 하나가 검증 \+ OpenAPI 문서를 만들고, 프론트 타입은 그 문서를 보고 맞춘다
2. **관리자 화면을 만들지 않는다.** SQLAdmin 이 CRUD 화면을 자동 생성한다
3. **언어가 두 개뿐이다.** Python(백 · 알고리즘 · AI) \+ TypeScript(프론트)
4. **배포에 서버 지식이 거의 필요 없다.** Docker Compose 로 로컬을 맞추고, Render · Vercel · Neon 이 나머지를 처리한다

* * *

## 11\.5 인증 방식 결정

### 결론: 카카오 로그인을 주 경로로, 이메일/비밀번호를 보조 경로로 둘 다 구현한다

`auth_identities` 테이블(6.2절)로 로그인 수단을 계정에서 분리했기 때문에, 둘 다 지원해도 구조가 복잡해지지 않습니다. 한 사람이 카카오로 가입한 뒤 이메일을 추가 연결할 수도 있습니다.

### 질문 1 — 비밀번호를 안전하게 보관할 수 있는가

**있습니다. 그리고 정확히는 "암호화"가 아니라 "단방향 해시"입니다.** 이 구분이 중요합니다.

|  | 암호화(encryption) | 해시(hash) |
| --- | --- | --- |
| 되돌리기 | 키가 있으면 복호화 가능 | **원리적으로 불가능** |
| 비밀번호에 적합한가 | ✕ (키가 유출되면 전부 뚫림) | ○ |

비밀번호는 **복호화할 필요가 없습니다.** 로그인할 때 입력값을 같은 방식으로 해시해서 저장된 해시와 비교하면 되기 때문입니다. 그래서 서비스는 사용자의 비밀번호 원문을 절대 알지 못하고, DB가 통째로 유출돼도 원문은 복원되지 않습니다.

```python
from passlib.context import CryptContext
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

hashed = pwd.hash(plain_password)          # 가입 시 저장
pwd.verify(plain_password, hashed)         # 로그인 시 검증
```

- **알고리즘: bcrypt** (또는 Argon2id). SHA\-256 같은 범용 해시는 너무 빨라서 대입 공격에 취약하므로 **쓰면 안 됩니다**. bcrypt는 의도적으로 느리게 설계되어 있고 솔트가 자동 포함됩니다
- 비용 계수(cost)는 기본값 12 정도. 검증에 0.2\~0.3초가 걸리는데, 이 느림이 방어의 핵심입니다
- **평문 비밀번호를 로그에 남기지 않는 것**이 실무에서 가장 자주 하는 실수입니다. FastAPI의 Pydantic 모델에서 `SecretStr`을 쓰면 실수로 로그에 찍히는 것을 막을 수 있습니다
- 비밀번호 재설정은 **원문 토큰이 아니라 토큰의 SHA\-256 해시만** DB에 저장하고, 30분 만료 \+ 1회 사용으로 제한합니다 (`password_reset_tokens`)

### 질문 2 — 카카오 로그인 연동이 어려운가

**어렵지 않습니다. 그리고 원하시는 용도(이름·프로필 사진)는 가장 쉬운 구간에 있습니다.**

표준 OAuth 2.0 Authorization Code 흐름이며, 서버 코드는 100줄 안쪽입니다.

```
1. 프론트에서 카카오 인가 URL로 이동
     https://kauth.kakao.com/oauth/authorize?client_id=...&redirect_uri=...&response_type=code
2. 사용자가 동의 → redirect_uri로 code 전달
3. 백엔드가 code를 토큰으로 교환   POST https://kauth.kakao.com/oauth/token
4. 토큰으로 사용자 정보 조회        GET  https://kapi.kakao.com/v2/user/me
5. kakao 회원번호로 auth_identities 조회 → 있으면 로그인, 없으면 가입
6. 우리 서비스의 JWT를 발급
```

**준비 작업** — 카카오 디벨로퍼스에 앱 등록 → 플랫폼(Web) 등록 → **Redirect URI 등록** → 카카오 로그인 활성화 → 동의항목 설정. 개발 중에는 `localhost` Redirect URI를 등록해 테스트할 수 있고, 앱 관리자·팀원 계정으로 먼저 검증할 수 있습니다.

**동의항목이 실질적인 갈림길입니다.**

| 항목 | 필요 조건 | 이 서비스에서 |
| --- | --- | --- |
| **닉네임 · 프로필 사진** | 일반 앱의 기본 프로필 동의항목. **별도 검수 없이 사용 가능** | **필요한 전부.** 팀원을 이름·사진으로 알아보는 목적이 이것만으로 충족됨 |
| 이메일 | **비즈 앱 전환 필요.** 개인 개발자도 신청 가능하지만 별도 절차와 대기가 있음 | **선택 항목으로 취급.** 없어도 가입·이용에 지장 없게 설계 |
| 그 외(생일, 성별 등) | 추가 신청·검수 | 수집하지 않음 |

> 동의항목 정책은 바뀔 수 있으므로, 실제 구현 시점에 카카오 디벨로퍼스 콘솔의 \[앱\] → \[카카오 로그인\] → \[동의항목\] 화면에서 현재 상태를 확인하는 것이 정확합니다.

### 설계상 반드시 지켜야 할 것

1. **`users.email`을 NULL 허용으로 둔다.** 이메일을 필수로 잡아두면 비즈 앱 전환 전까지 카카오 로그인이 아예 막힙니다. 이 하나 때문에 스키마를 갈아엎는 경우가 흔합니다
2. **이메일을 계정 식별자로 쓰지 않는다.** 식별은 `users.id`, 로그인 수단은 `auth_identities`. 그래서 이메일 없는 계정이 자연스럽게 존재할 수 있습니다
3. **프로필 이미지 URL을 그대로 저장하되 만료를 가정한다.** 카카오 CDN URL은 영구 보장이 아니므로, 이미지 로드 실패 시 이니셜 아바타로 대체하는 폴백을 둡니다
4. **`state` 파라미터로 CSRF를 막는다.** 인가 URL 생성 시 난수를 발급해 세션에 저장하고 콜백에서 대조합니다
5. **동일인 중복 가입에 대비한다.** 카카오로 가입한 사람이 나중에 이메일로 또 가입할 수 있습니다. (v1.0 구현: 회원 계정끼리 합치는 기능은 두지 않았다. 대신 한 계정에 카카오를 **연결**하고(`POST /auth/kakao/link`), 카카오 전용 계정도 비밀번호 재설정으로 이메일 로그인을 더할 수 있다. 병합은 게스트 → 회원만.)

### 구현 순서

MVP에서는 **카카오 먼저** 만드는 편이 낫습니다. 이메일 경로는 비밀번호 정책·재설정 메일 발송·토큰 만료까지 딸려 오는데, 카카오는 그 전부를 카카오가 대신해 주기 때문입니다. 이메일/비밀번호는 카카오 계정이 없는 사용자를 위한 보조 경로로 뒤에 붙입니다.

# 12\. 진행 현황과 남은 일

| 단계 | 산출물 | 상태 |
| --- | --- | --- |
| 1 | 서비스명 · 목적 · 페인포인트 · 액터 · 기능 요구사항 | ✅ HOOPLY, `docs/01` |
| 2 | 화면 설계 · ERD · API 명세 · 배정 알고리즘 검증 | ✅ `docs/02` · `03` · `04`, 시뮬레이션(`scripts/simulate_rating.py`) |
| 3 | 애플리케이션 개발 (9.8절 순서) | ✅ 운영 중 — https://hooply-green.vercel.app |
| 4 | 테스트 · 디버깅 | ✅ pytest 약 210개 · Vitest 61개 · Playwright 22개, GitHub Actions |
| 5 | AI 설명 · 전술 (14장) | ✅ `docs/07` v1.9, AI 검증 `docs/eval_result.md` |
| 6 | 데모 · 포트폴리오 | ✅ `docs/05` 데모 시나리오, 데모 데이터 매주 자동 갱신 |

**MVP 범위** — 기획 단계의 MVP(인증 · 팀 · 게스트 · 설문 · 정렬 · 일정 · 배정 3안 · 묶기 · 설명 · 수정 · 쿼터 기록)와 후순위(피어 투표 · 실력/선호 갱신 · 대시보드 · 관리자 콘솔 · 사전 배치 · 분리)를 모두 구현했다. **로테이션 자동 제안(F17)만 제외**했다.

**남은 일** — 모두 데이터가 쌓여야 판단할 수 있는 것들이다 (13.3절, `docs/07` 13절).

| 항목 | 시점 |
| --- | --- |
| 배치 RAPM (9.2절 층 2) | 누적 100쿼터 |
| 앵커 재보정 (8.6절) · 목적함수 가중치 튜닝 | 누적 150쿼터 |
| 등급 분위수 비율(10 · 20 · 40 · 20 · 10%)이 실제 팀에서 납득되는지 (9.2절 표시 정책) | 실제 팀 데이터가 쌓인 뒤 |
| 전술 추천 기준값 조정 (docs/07 O4) · 역할 추출 규칙 다듬기 (O9) | 실제 팀 확정 배정 4\~6주 · 팀 전술 10개 |
| 지역 수비 모양 추가 3-2 · 1-3-1 (O10) | 요청이 있을 때 |

# 13\. 설계 고민 및 다음 단계 고려사항

확정하지 않고 남겨둔 판단들입니다. 개발 중 부딪히면 여기로 돌아옵니다.

## 13\.1 결정 기록 (v0.3 에서 열어 두었던 것)

| \# | 고민 | 선택지 | 결정 |
| --- | --- | --- | --- |
| Q1 | **서비스명** | 픽앤롤 / 코트메이트 / 밸런스코트 / 신규 | **HOOPLY** |
| Q2 | **게스트에게 설문을 시킬 것인가** | ① 등록한 사람이 등급만 지정 ② 게스트용 초간단 설문 링크 | **①** — 등급 · 키 · 포지션을 등록할 때 넣는다. 가입하면 본인 확인으로 기록을 이어받는다 |
| Q3 | **실력 수치를 매니저에게도 숨길 것인가** | ① 매니저는 수치까지 ② 매니저도 등급만 | **①** — 매니저는 수치와 근거(S-20), 플레이어는 자기 등급만 |
| Q4 | **3팀 이상 지원 시기** | ① v1부터 ② 2팀만 먼저 | **v1 에 3팀까지** — 참석 16명 이상이면 매니저가 고른다. 지역 탐색으로 풀고 완전 탐색으로 검증(9.7절). 4팀 이상은 하지 않는다 |
| Q5 | **출전 시간 균등을 배정에 반영할 것인가** | ① 쿼터 로테이션에서만 ② 팀 배정에도 가중치 | **둘 다 하지 않는다** — 쉬는 순서는 현장에서 정하고, 로테이션 자동 제안(F17)도 제외했다 |
| Q6 | **팀 이름을 고정할 것인가** | ① 블랙/화이트 고정 ② 매니저가 매번 지정 | **①** — 블랙 · 화이트 · 레드(3팀) 고정 |
| — | 인증 방식 | 카카오 / 이메일 | **둘 다** (11.5절) — 카카오를 주 경로, 이메일은 보조. 비밀번호 재설정 메일까지 |
| — | 새 팀 스팸 | 누구나 즉시 활성 / 관리자 승인 | **관리자 승인** 후 5명 이상이면 활성 |
| — | AI 의 역할 | AI 가 판단 / 규칙이 판단하고 AI 는 문장 | **규칙이 판단, AI 는 문장만** (14장). 전술 역할도 AI 가 고르게 해 봤지만 규칙보다 나아지지 않아 이유만 쓰게 했다 |

## 13\.2 개발 중 놓치기 쉬운 것

1. **첫 2회 모임 데이터를 지표에 반영하지 않는다.** 노이즈가 사전값을 악화시킵니다 (9.3절). 코드에 명시적 게이트를 두고, 지나서 잊지 않도록 상수로 뽑아둡니다
2. **쿼터 삭제 시 마진을 롤백한다.** 쿼터 수가 유동적이므로 삭제·수정이 실제로 일어납니다. 잔차 누적을 증분으로만 갱신하면 롤백이 불가능해지므로, **재계산 가능한 형태**(원본 라인업 보존 \+ 배치 재계산)로 설계합니다
3. **게스트 병합을 되돌릴 수 있게 한다.** `merged_into_player_id`를 따라가는 방식이면 되돌리기가 한 줄입니다. 물리적으로 행을 합치면 복구가 불가능합니다
4. **`players`가 팀 단위라는 점을 잊지 않는다.** 같은 사람이 두 팀에 있으면 `player_id`가 다릅니다. 실력 지표도 팀마다 별개입니다. 이것은 버그가 아니라 의도입니다
5. **제약 오류 메시지에 무엇이 문제인지 담는다.** "제약을 만족할 수 없습니다"만으로는 매니저가 무엇을 풀어야 할지 알 수 없습니다
6. **평문 비밀번호를 로그에 남기지 않는다.** Pydantic `SecretStr` 사용
7. **`users.email`을 NOT NULL로 잡지 않는다.** 카카오 로그인이 막힙니다 (11.5절)

## 13\.3 데이터가 쌓인 뒤 재검토할 것

| 시점 | 항목 |
| --- | --- |
| 누적 100쿼터 | 배치 RAPM 도입. 그 전에는 실시간 Elo만으로 충분 |
| 누적 150쿼터 | **앵커 재보정** (8.6절) — 설문 선택지별 실측 실력 평균으로 배점 재산정 |
| 누적 150쿼터 | 목적함수 가중치 튜닝. 시뮬레이션 스크립트를 실제 데이터로 교체해 재실행 |
| 누적 300쿼터 | 마진 기반 시너지 검정 재검토 (9.4절). 그래도 검정력이 안 나올 가능성이 높음 |
| 운영 6개월 | 설문 정확도 ρ 실측 — 설문 사전값과 실측 실력의 상관을 계산해 8.4절 가중치 조정 |

## 13\.4 검증 방법 (4단계 테스트·디버깅 대비)

- **배정 알고리즘:** 완전 탐색 결과를 정답 기준으로 두고, 제약이 걸린 모든 경우에 대해 "묶인 사람이 같은 팀인가"를 속성 기반 테스트(property\-based test)로 검증. 시드를 고정한 무작위 입력으로 돌린다(`tests/test_ranking_assignment.py`), 3팀은 15명 이하에서 완전 탐색 결과와 대조(`tests/test_three_teams.py`)
- **제약 실현가능성 검사:** 실현 불가능한 입력을 의도적으로 만들어 넣고 **실행 전에** 차단되는지 확인. 이 검사가 빠지면 알고리즘이 조용히 제약을 어깁니다
- **마진 계산:** 쿼터 추가 → 수정 → 삭제 순서로 조작한 뒤 지표가 원래 값으로 돌아오는지 확인
- **권한:** 플레이어 토큰으로 매니저 API를 전부 호출해 403이 나오는지 자동 검사
- **실력 모델:** `backend/scripts/simulate_rating.py`를 `tests/test_rating_simulation.py`가 회귀 테스트로 유지. 잔차 모델이 원시 마진보다 못해지거나, 완벽 균형 조건에서 원시 마진 붕괴가 재현되지 않으면 실패

* * *

# 14\. AI 설명과 전술 (v1.0 추가)

정본은 `docs/07-AI전술-요구사항.md`(v1.9) · 검증 결과는 `docs/eval_result.md`. 이 장은 설계 판단만 요약한다.

## 14\.1 원칙 — 판단은 규칙, 문장은 AI

1장의 핵심 가치 3번("설명 가능한 결과")을 더 읽기 쉽게 하려고 AI 를 붙였다. 다만 **누가 활약할지, 누구와 호흡이 맞는지, 어떤 전술 · 자리가 맞는지는 서버 규칙이 먼저 정하고**, AI 는 그 사실을 문장으로만 푼다. 틀린 결정에 AI 의 권위를 씌우지 않기 위해서다(9.4절 케미 정책과 같은 논리).

| 체인 | 무엇 | 누구에게 | 입력(가명) |
| --- | --- | --- | --- |
| A | 배정 설명 — 팀 색깔 · 활약 · 조합 · 부족한 역할 · 주의할 점 | 매니저 | 팀별 지표 · 규칙이 뽑은 활약 · 조합 · 결손 |
| B | AI 한마디 — 왜 이 포지션 · 기대 역할 · 호흡 맞출 동료 | 팀원(자기 것만) | 실력 값 없이 포지션 · 키 · 설문 강점 |
| C | 전술 AI 코치 — 전술마다 이유 · 핵심 자리 · 주의할 점 | 그날 참석자 | 추천 전술 · 자리 배치 · 강점 |
| D | 전술 편집기 자리별 이유 | 전술 만든 팀원 | 자리 이름 · 동작 · 정해진 역할 (선수 정보 없음) |

**가드레일** — 선수는 `P1…` · 팀은 `A·B`(세 팀이면 `A·B·D`) 가명으로 보내고 실명으로 되돌린다. 입력에 없는 사람 · 숫자를 말하거나 팀원용에 등급 · 순위가 나오면 그 답을 버리고 **규칙 문장으로 폴백**(화면에는 "AI" 표시 없이). 같은 입력은 캐시(`llm_results`), 사용자당 분당 10회. 무료 등급 Gemini 라 약관(데이터 사용 가능)을 도움말에 밝히고 가명만 보낸다.

**검증** — `scripts/eval_llm.py` 가 배포 서버에 데모 팀(실제 팀 데이터 제외)으로 72건을 돌린다. 2026-09-30: 폴백 0 · 자동 점검 문제 0, 새 호출 평균 응답 1.8\~3.3초.

## 14\.2 전술 추천

- **프리셋 22개**(하프코트 20 · 인바운드 2). 전술은 좌표가 아니라 **동작의 순서**로 저장하고, 전술마다 가정한 상대 수비(맨투맨/지역 2-3 × 스크린 스위치/스테이)와 막혔을 때의 대안을 둔다
- **역할 적합도** — 역할 7종(볼 핸들러 · 롤 · 팝 · 슈터 · 커터 · 포스트 · 스페이서)마다 설문 속성(8.3절 B1 조합 · 슛 거리 · 볼 운반 · 키 …)의 가중 점수. 팀 · 전술마다 5자리 최적 배치를 비트마스크 DP 로 구하고 적합도 75 이상 상위 3개를 **자동 추천**(매니저가 고르지 않음), 자리마다 예비 1~2명
- 추천은 **확정된 일정 화면**("이 팀에 맞는 전술")에만 있고, 팀 화면 전술 탭은 목록(별표 · 우리 팀 전술 · 프리셋)만 둔다

## 14\.3 전술판 · 팀 전술

- 하프코트 SVG 에서 단계별 재생(requestAnimationFrame 보간, 휴대폰 에뮬레이션 60fps), 수비 5명이 전술이 가정한 방식대로 따라 움직이는 **수비 시뮬레이션**(서버 · AI 없이 프론트 규칙 계산)
- **팀원 누구나 전술을 그린다** — 동작을 그리면 역할이 규칙으로 자동 추출되고(프리셋의 사람 역할과 82% 일치), 만든 사람 · 매니저가 고친다. 저장하면 그 팀 추천 후보에 들어간다
- AI 가 역할까지 고르게 해 봤더니 일치율이 규칙과 같았고(64% vs 65%) 맞던 자리를 틀리게 바꾸기도 해서, **AI 는 이유 문장만** 쓰고 역할은 규칙과 사람이 정하도록 바꿨다(docs/07 D23)
- 전술마다 댓글, 매니저 별표(탭 맨 위)
