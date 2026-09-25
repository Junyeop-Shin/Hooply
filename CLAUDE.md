# 농구 동호회 팀 매칭 서비스 기획·설계서

**버전** v0.3 · **작성일** 2026\-09\-08 · **단계** 기획 및 기능 정의 → 시스템 설계

> **v0.3 주요 변경** — 서비스 개요·페인포인트·주요기능을 기획자 정리본 기준으로 교체 · **게스트 참가자** 개념 도입(데이터 모델 전역 영향) · 실제 운영 프로토콜(팀 하루 고정 \+ 로테이션, 쿼터 수 유동)을 반영해 시뮬레이션 재수행 · 배정 제약을 상시 저장에서 **회차별 설정**으로 변경 · 인증 방식 결정

Table of Contents

* * *

# 1\. 서비스 개요

## 1\.1 서비스명

**미정.** 확정 전까지 문서에서는 "본 서비스"로 칭합니다.

| 후보 | 의미 |
| --- | --- |
| 픽앤롤 (Pick & Roll) | 농구 전술 용어이자 "선수를 Pick 해서 팀을 Roll out 한다"는 이중 의미 |
| 코트메이트 (CourtMate) | 코트 위의 동료를 찾아준다 |
| 밸런스코트 (BalanceCourt) | 균형 잡힌 코트 |
| 하프타임 (Halftime) | 경기 사이 팀을 재정비하는 순간 |

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

## 1\.5 주요 기능

| \# | 기능 | 설명 |
| --- | --- | --- |
| F1 | 온보딩 실력 설문 | 가입 시 초기 실력, 가능 및 선호 포지션 산출 |
| F2 | 팀 생성 및 팀 초대 | 플레이어가 팀을 만들면 팀 코드 발급, 5명 이상 모이면 팀 활성화 |
| F3 | 팀원 및 권한 관리 | 매니저가 팀원 조회/제외, 다른 플레이어에게 매니저 권한 부여 |
| F4 | 일정 등록 및 참석 응답 | 매니저가 일정을 등록하면, 플레이어가 참석/불참 응답 |
| F5 | 자동 팀 배정 | 참석 확정자 기준으로 3가지 팀 편성안 추천 |
| F6 | 배정 결과 설명 | 참가자의 실력·포지션·케미를 근거로 매니저에게 설명 문구 제공 |
| F7 | 배정안 수정 | 매니저가 배정 결과에서 선수 구성을 수정, 재계산된 지표 즉시 표시 |
| F8 | 쿼터별 경기 기록 | 쿼터 라인업·스코어를 입력하면 코트 마진 자동 누적 계산 |
| F9 | 경기 후 피어 설문 | 경기를 마치면 같은 팀·상대 팀에서 "오늘 잘한 사람", "다음에 같이 뛰고 싶은 사람" 각 2명 선택 |
| F10 | 실력·친화도 갱신 | 설문 사전값 \+ 코트 마진 \+ 피어 투표를 결합해 실력/케미 지표 갱신 |
| F11 | 플레이어 개인 대시보드 | 내 참여 이력, 코트 마진 추이, 포지션 분포, 본인과 잘 맞는 참여자 분석 |
| F12 | 관리자 콘솔 | 전체 사용자·팀·경기 조회, 선수 개인 원시 데이터 열람, 지표 수동 보정 |

### 설계 검토 과정에서 추가된 기능

| \# | 기능 | 추가 이유 |
| --- | --- | --- |
| F13 | **게스트 참가자 등록** | 1\.2절이 전제한 게스트 상황을 기능으로 받아야 함. 매니저가 계정 없는 게스트를 이름과 대략적 실력만으로 그 회차 참석자에 추가. 재방문 시 같은 레코드를 재사용해 데이터 누적, 나중에 정식 가입하면 병합 |
| F14 | **매니저 실력 정렬** | 매니저가 팀원 카드를 드래그해 실력 순서를 한 번 매기는 기능. 초기 6개월간 배정 품질을 좌우하는 가장 저렴한 장치 (9.3절 근거) |
| F15 | **배정 제약 설정 (회차별)** | 그 회차에 한해 2명 이상을 같은 팀으로 묶기. 다음 회차에는 자동 해제 |
| F16 | **팀 사전 배치** *(2순위)* | 특정 인원을 미리 각 팀에 꽂아두고 나머지 자리를 알고리즘이 채우는 기능 |
| F17 | **로테이션 자동 제안** | 팀이 6\~8명일 때 출전 시간이 균등해지도록 다음 쿼터 출전 5명을 자동 체크. 기록 입력 부담(P4)을 추가로 낮춤 |

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
| 팀 구성 | 2팀. **그날 하루는 팀이 바뀌지 않음** |
| 팀 인원 | 6\~7명 |
| 출전 | 팀당 5명씩. 인원이 6\~7명이면 **순서를 정해 5명 뛰고 1\~2명 쉬는 로테이션** |
| 쿼터 수 | **유동적 (7\~10쿼터).** 시간이 남거나 부족하면 그때그때 조정 |
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
| **관리자 (ADMIN)** | 전역 | 시스템에서 직접 지정 |
| **팀 매니저 (MANAGER)** | 팀 단위 | 팀 생성 시 자동 부여, 기존 매니저가 위임 가능 |
| **플레이어 (PLAYER)** | 팀 단위 | 팀 코드로 가입 시 기본 부여 |

미로그인 상태(비회원)에서는 초대 링크 열람과 회원가입만 가능합니다.

### 게스트 참가자는 액터가 아니다

게스트는 계정이 없는 경우가 대부분이므로 **시스템 액터가 아니라 데이터상의 참가자**로 취급합니다.

- 매니저가 이름(\+선택적으로 대략적 실력 등급)만으로 게스트를 등록하고, 그 회차 참석자 목록에 추가한다
- 게스트도 배정·쿼터 기록·코트 마진의 대상이 된다 (로그인·설문·투표는 불가)
- 같은 게스트가 재방문하면 기존 레코드를 선택해 **데이터가 누적**된다
- 게스트가 나중에 정식 가입하면 게스트 레코드를 계정에 **연결(merge)** 하여 과거 기록을 승계한다

이 때문에 데이터 모델에서 **로그인 계정(`users`)과 참가자(`players`)를 분리**합니다 (6장). 경기 기록·배정·투표는 모두 `players`를 참조합니다.

## 3\.2 액터별 기능 정의

### 관리자 (ADMIN)

- 전체 사용자·팀·일정·경기 조회
- 특정 선수의 **원시 데이터 전체 열람** — 설문 응답, 쿼터별 점수 이력, 코트 마진 로그, 피어 투표 수신 내역, 실력 지표 변동 이력
- 실력 점수 및 케미 지표 **수동 보정**
- 팀 강제 비활성화, 계정 정지
- 설문 템플릿 버전 관리

### 팀 매니저 (MANAGER)

- 팀 정보 수정, 팀 코드 재발급
- 팀원 목록 조회
- 팀원 초대 및 제외
- 다른 플레이어에게 매니저 권한 부여 / 회수
- 일정 등록·수정·취소, 참석 투표 마감
- **게스트 참가자 등록 및 관리** (F13)
- **팀원 실력 정렬** (F14)
- **팀 배정 실행** — 팀 수 지정, 회차별 제약 설정, 3가지 전략 후보안 생성
- 배정 결과 설명 열람
- 배정안 선택 및 수동 수정
- 배정 확정 → 플레이어에게 공개
- 쿼터별 경기 기록 입력·수정
- 신규 선수 초기 실력 지표 보정

### 플레이어 (PLAYER)

- 회원가입 및 온보딩 설문 응답
- 팀 생성 → 팀 코드 발급 → 공유
- 팀 코드로 팀 가입
- 내 프로필 조회·수정
- 일정 목록 조회 및 참석 / 불참 응답
- 확정된 팀 배정 결과 열람 (본인 팀·배정 포지션·상대 팀·설명. 타인의 실력 수치는 비공개)
- 경기 후 피어 설문 응답 (선택 사항)
- 내 대시보드 — 참여 이력, 코트 마진 추이, 포지션 분포, 본인과 잘 맞는 참여자

## 3\.3 권한 매트릭스

| 기능 | ADMIN | MANAGER | PLAYER | 게스트 참가자 |
| --- | :---: | :---: | :---: | :---: |
| 로그인 | ○ | ○ | ○ | ✕ (계정 없음) |
| 팀 생성 | ○ | ○ | ○ | ✕ |
| 팀 코드로 가입 | ○ | ○ | ○ | ✕ |
| 팀원 목록 조회 | ○ (전체) | ○ (소속 팀) | △ (이름·포지션만) | ✕ |
| 선수 상세 데이터 조회 | ○ (원시) | △ (등급·요약) | ✕ (본인만) | ✕ |
| 매니저 권한 부여 | ○ | ○ | ✕ | ✕ |
| 일정 등록 / 수정 | ○ | ○ | ✕ | ✕ |
| 참석 응답 | ○ | ○ | ○ | △ (매니저가 대신 등록) |
| 게스트 등록·관리 | ○ | ○ | ✕ | ✕ |
| 실력 정렬 | ○ | ○ | ✕ | ✕ |
| 팀 배정 실행·제약 설정 | ○ | ○ | ✕ | ✕ |
| 배정 결과 열람 | ○ (전체 지표) | ○ (전체 지표) | △ (플레이어용 뷰) | ✕ |
| 배정안 수정·확정 | ○ | ○ | ✕ | ✕ |
| 경기 기록 입력 | ○ | ○ | ✕ | ✕ |
| 경기 기록의 대상이 됨 | ○ | ○ | ○ | **○** |
| 경기 후 피어 설문 응답 | ○ | ○ | ○ (참석자만) | ✕ |
| 피어 설문의 대상이 됨 | ○ | ○ | ○ | **○** |
| 실력 지표 수동 보정 | ○ | △ (신규 1회) | ✕ | ✕ |

○ 전체 허용 · △ 제한적 허용 · ✕ 불가

> 게스트가 "기록·투표의 **대상**은 되지만 **주체**는 아니다"라는 비대칭이 이 서비스 권한 설계의 핵심입니다. 이 구분이 6장의 `users` / `players` 분리로 이어집니다.

# 4\. 기능 요구사항 (FR)

서비스 개요(1장)와 액터 정의(3장)를 화면(5장)까지 잇는 연결 고리입니다. 모든 FR은 **문제(P) → 기능(F) → 화면(S)** 로 추적됩니다.

| ID | 요구사항 | 액터 | 문제 | 기능 | 화면 |
| --- | --- | --- | --- | --- | --- |
| FR\-01 | 카카오 계정 또는 이메일/비밀번호로 회원가입하고 로그인할 수 있다 | PLAYER | — | — | S\-01, S\-02 |
| FR\-02 | 비밀번호는 복호화 불가능한 형태로 저장되며, 이메일로 재설정할 수 있다 | SYSTEM | — | — | S\-01 |
| FR\-03 | 가입 직후 온보딩 설문에 응답하면 초기 실력·포지션 프로필이 생성된다 | PLAYER | P5, P7 | F1 | S\-03 |
| FR\-04 | 팀을 생성하면 팀 코드가 발급되고 생성자는 MANAGER가 된다 | PLAYER | P1 | F2 | S\-05 |
| FR\-05 | 팀 코드로 팀에 가입할 수 있다 | PLAYER | P1 | F2 | S\-06 |
| FR\-06 | 팀 인원이 5명 이상이 되면 팀이 활성화되고 일정 기능이 열린다 | SYSTEM | — | F2 | S\-07 |
| FR\-07 | 매니저는 팀원을 조회·제외하고 매니저 권한을 부여·회수할 수 있다 | MANAGER | P1 | F3 | S\-08 |
| FR\-08 | 매니저는 일정(날짜·시간·장소·응답 마감)을 등록·수정·취소할 수 있다 | MANAGER | P1 | F4 | S\-09 |
| FR\-09 | 플레이어는 일정별로 참석/불참을 응답하고 마감 전까지 변경할 수 있다 | PLAYER | P1 | F4 | S\-10 |
| FR\-10 | **매니저는 계정이 없는 게스트를 이름으로 등록해 그 회차 참석자에 추가할 수 있다** | MANAGER | P5 | F13 | S\-11 |
| FR\-11 | **게스트 등록 시 매니저가 대략적 실력 등급(1\~5)과 가능 포지션을 지정할 수 있고, 미지정 시 클럽 평균값이 적용된다** | MANAGER | P5 | F13 | S\-11 |
| FR\-12 | **같은 게스트가 재방문하면 기존 레코드를 검색·선택해 기록을 누적할 수 있다** | MANAGER | P4 | F13 | S\-11 |
| FR\-13 | **게스트가 정식 가입하면 게스트 레코드를 계정에 연결해 과거 기록을 승계한다** | MANAGER | P4 | F13 | S\-08 |
| FR\-14 | **매니저는 팀원 카드를 드래그해 실력 순서를 매기고, 그 순서가 사전 실력값에 반영된다** | MANAGER | P5 | F14 | S\-19 |
| FR\-15 | 매니저는 참석 확정자 목록과 포지션 분포를 한눈에 확인할 수 있다 | MANAGER | P6 | F5 | S\-11 |
| FR\-16 | 매니저는 팀 수를 지정해 배정을 실행하고 3가지 전략(실력/친화도/종합)의 후보안을 받는다 | MANAGER | P1, P5 | F5 | S\-12 |
| FR\-17 | **매니저는 그 회차에 한해 2명 이상을 하나의 그룹으로 묶을 수 있고, 어떤 전략을 선택해도 그룹은 반드시 같은 팀에 배정된다** | MANAGER | P8 | F15 | S\-12 |
| FR\-18 | **회차별 제약은 다음 회차에 자동 해제되며, 직전 회차 제약을 불러오는 것만 선택적으로 지원한다** | SYSTEM | P1 | F15 | S\-12 |
| FR\-19 | **매니저는 특정 인원을 각 팀에 미리 배치하고 나머지 자리를 알고리즘이 채우게 할 수 있다** *(2순위)* | MANAGER | P8 | F16 | S\-12 |
| FR\-20 | 실현 불가능한 제약(그룹 과대·충돌·분할 불가)은 실행 전에 차단되고 사유가 안내된다 | SYSTEM | P6 | F15 | S\-12 |
| FR\-21 | 각 후보안은 팀별 평균 실력·실력 편차·포지션 커버리지를 표시하고 자연어 설명을 포함한다 | MANAGER | P2, P3 | F6 | S\-12, S\-13 |
| FR\-22 | 매니저는 후보안 내 두 선수를 교체하고 즉시 재계산된 지표를 확인할 수 있다 | MANAGER | P3 | F7 | S\-13 |
| FR\-23 | 매니저가 배정을 확정하면 참석자에게 결과가 공개된다 | MANAGER | P2 | F7 | S\-13 |
| FR\-24 | 플레이어는 본인 팀 구성·배정 포지션·상대 팀·설명을 볼 수 있다 (타인 실력 수치 비공개) | PLAYER | P2, P8 | F6 | S\-14 |
| FR\-25 | **매니저는 경기 후 쿼터별로 양 팀 출전 5명과 스코어를 입력한다. 쿼터 수는 유동적이며 회차마다 다를 수 있다** | MANAGER | P4 | F8 | S\-15 |
| FR\-26 | **시스템은 출전 시간이 균등해지도록 다음 쿼터 출전 5명을 자동 제안하며, 매니저가 수정할 수 있다** | SYSTEM | P4 | F17 | S\-15 |
| FR\-27 | 쿼터 저장 시 코트 마진이 시간 정규화되어 계산되고, **기대 마진 대비 잔차**로 실력 지표가 갱신된다 | SYSTEM | P4, P5 | F8, F10 | — |
| FR\-28 | 실력 지표는 플레이어에게 수치가 아닌 5등급으로만 표시되며, 8쿼터 단위로만 갱신 표시된다 | SYSTEM | P8 | F10 | S\-14, S\-17 |
| FR\-29 | 경기 종료 후 참석자는 같은 팀·상대 팀에서 각 2명씩 "오늘 잘한 사람"과 "다음에 같이 뛰고 싶은 사람"을 선택할 수 있다 | PLAYER | P5 | F9 | S\-16 |
| FR\-30 | 상호 지목된 조합은 "선호 조합"으로 배정에 반영된다 (통계적 시너지 주장은 하지 않는다) | SYSTEM | P8 | F10 | — |
| FR\-31 | 플레이어는 본인의 참여 이력·마진 추이·포지션 분포·잘 맞는 참여자를 볼 수 있다 | PLAYER | P4 | F11 | S\-17 |
| FR\-32 | 관리자는 전체 사용자·팀·경기와 선수별 원시 데이터를 조회하고 지표를 보정할 수 있다 | ADMIN | P4 | F12 | S\-18 |
| FR\-33 | 참석 인원이 최소 인원(팀 수 × 5)에 미달하면 배정 실행이 차단되고 사유가 안내된다 | SYSTEM | P6 | F5 | S\-12 |
| FR\-34 | 빅맨(4·5번) 또는 핸들러(1번) 자원이 팀 수보다 부족하면 경고와 함께 대안이 제시된다 | SYSTEM | P6 | F5 | S\-12 |

> **v0.3 추가 화면:** S\-19 매니저 실력 정렬 (드래그 순위, MANAGER 전용). 게스트 등록은 S\-11 참석자 현황 화면 안에서 처리합니다.

# 5\. UI 흐름 및 화면 설계 방안

## 5\.1 설계 원칙

1. **모바일 우선 \+ 한 손 조작.** 주요 액션 버튼은 화면 하단 고정, 최소 터치 영역 44×44pt
2. **탭 3개 이내 완료.** 특히 RSVP 응답과 쿼터 기록 입력
3. **역할별 진입점 분리.** 로그인 후 홈은 매니저/플레이어에 따라 다른 카드 구성
4. **화면 요소 \= API 필드.** 모든 화면 요소는 6장 ERD 컬럼과 7장 API 응답 필드에 1:1 대응 (아래 표의 "데이터 필드" 열)

## 5\.2 주요 화면 목록

| ID | 화면 | 액터 | 주요 구성 요소 | 데이터 필드 |
| --- | --- | --- | --- | --- |
| S\-01 | 로그인 | 비회원 | **카카오로 시작하기(주 버튼)**, 이메일/비밀번호 입력, 비밀번호 찾기, 회원가입 링크 | `email`, `password` |
| S\-02 | 회원가입 | 비회원 | 이메일, 비밀번호, 이름, 닉네임, 출생년도, 키(cm) | `users.*` |
| S\-03 | 온보딩 설문 | PLAYER | 진행률 바, 문항 카드(4단계 앵커·다중선택 칩·서열), 이전/다음 | `survey_questions`, `survey_answers` |
| S\-04 | 홈 (역할별) | ALL | 다가오는 일정 카드, 내 팀 목록, 미응답 배지 | `events`, `teams`, `event_attendances.status` |
| S\-05 | 팀 생성 | PLAYER | 팀명, 소개, 홈 코트 → 팀 코드 노출 \+ 카카오 공유 | `teams.*` |
| S\-06 | 팀 가입 | PLAYER | 팀 코드 입력, 팀 미리보기, 가입 확인 | `teams.team_code` |
| S\-07 | 팀 상세 | ALL | 팀명, 인원수, 상태 배지, 일정 탭 / 팀원 탭 | `teams.*`, `team_memberships` |
| S\-08 | 팀원 관리 | MANAGER | 팀원 리스트(이름·포지션·실력 등급·참여율), 역할 변경, 제외, **게스트 목록 탭 / 계정 연결** | `team_memberships.role`, `players` |
| S\-09 | 일정 등록 | MANAGER | 날짜, 시작/종료 시간, 장소, 응답 마감일, 메모 | `events.*` |
| S\-10 | 일정 상세 / RSVP | PLAYER | 일정 정보, 참석/불참 토글, 현재 참석자 수, 마감 D\-day | `event_attendances.status` |
| S\-11 | 참석자 현황 · 게스트 등록 | MANAGER | 참석/불참/미응답 3열 · 포지션 분포 요약 바 · 빅맨·핸들러 수 경고 · **`+ 게스트 추가` 버튼 → 이름 입력, 기존 게스트 검색, 실력 등급 1\~5, 가능 포지션 칩** | `event_attendances`, `players`, `player_positions` |
| S\-12 | 팀 배정 실행 | MANAGER | **상단 대기 칸(참석자 풀) \+ 하단 팀 칸 2개** · 팀 수 선택 · 전략 3탭 · 대기 칸에서 다중 선택 → `같은 팀으로 묶기` · 팀 칸에 직접 드롭 \= 사전 배치 · 실행 버튼 | `assignment_runs.params`, `assignment_constraints` |
| S\-13 | 배정 결과 (매니저) | MANAGER | 후보안 탭 3개, 팀별 카드(평균 실력·편차·포지션 아이콘), 설명 아코디언, 선수 드래그 swap, 확정 버튼 | `assignment_candidates`, `assignment_squads`, `assignment_slots` |
| S\-14 | 배정 결과 (플레이어) | PLAYER | 내 팀 강조 카드, 배정 포지션 배지, 팀원 목록, 상대 팀, 설명 문구 | 위와 동일 (실력 수치 마스킹) |
| S\-15 | 쿼터 기록 입력 | MANAGER | **쿼터 카드 세로 누적형** — 쿼터별 스코어 스테퍼 2개 \+ 팀별 출전 5명 체크 그리드 · `+ 쿼터 추가` / `쿼터 삭제` · **자동 제안 버튼**(출전 시간 균등) · 경기 후 일괄 저장 | `quarters.*`, `quarter_lineups` |
| S\-16 | 경기 후 피어 설문 | PLAYER | 같은 팀 2명 / 상대 팀 2명 선택 (잘한 사람 · 또 뛰고 싶은 사람) | `post_game_votes` |
| S\-17 | 내 프로필 / 대시보드 | PLAYER | 실력 등급(수치 아님), 포지션 분포 도넛, 마진 추이 라인, 참여 이력, **잘 맞는 참여자 목록** | `player_profiles`, `quarter_lineups`, `chemistry_scores` |
| S\-18 | 관리자 콘솔 | ADMIN | 사용자·팀·경기 테이블, 선수 원시 데이터 뷰, 지표 보정 폼 | 전체 |
| S\-19 | **매니저 실력 정렬** | MANAGER | 팀원 카드 세로 리스트, 드래그로 순서 변경, 상단에 `상위 ↑ / 하위 ↓` 안내, 저장 | `manager_rankings` |

> **S\-12의 "대기 칸 \+ 팀 칸" 구조가 두 제약 기능을 하나의 화면에서 자연스럽게 표현합니다.** 대기 칸 안에서 묶으면 "같은 팀"(F15), 팀 칸에 직접 올리면 "사전 배치"(F16)입니다. 실행 버튼을 누르면 대기 칸에 남은 인원만 알고리즘이 채웁니다.

## 5\.3 핵심 사용자 흐름

### 흐름 A — 신규 플레이어 온보딩

```
S-01 로그인 → (계정 없음) → S-02 회원가입 → S-03 온보딩 설문(필수)
   → 팀 코드 있음? ─ Yes → S-06 팀 가입 → S-07 팀 상세
                   └ No  → S-05 팀 생성 → 팀 코드 발급 → 카카오 공유
```

### 흐름 B — 모임 운영 (매니저)

```
S-09 일정 등록 → (플레이어 RSVP 수집) → S-11 참석자 현황 확인
   → S-12 배정 실행 (팀 수·전략·제약 지정)
   → S-13 후보안 비교 → [선택 | swap 수정] → 확정
   → S-15 쿼터 기록 입력 (경기 중 반복)
   → 경기 종료 → 피어 설문 링크 발송
```

### 흐름 C — 참여 (플레이어)

```
알림/홈 배지 → S-10 일정 상세 → 참석 응답
   → (매니저 확정 후) S-14 배정 결과 열람
   → 경기 후 → S-16 피어 설문 응답(선택)
   → S-17 내 대시보드에서 마진 갱신 확인
```

## 5\.4 예외 / 오류 시나리오

| 시나리오 | 발생 조건 | 화면 처리 | API 응답 |
| --- | --- | --- | --- |
| 잘못된 팀 코드 | 존재하지 않거나 만료된 코드 | 입력 필드 하단 인라인 에러 | `404 TEAM_CODE_NOT_FOUND` |
| 중복 가입 | 이미 소속된 팀에 재가입 시도 | 토스트 \+ 팀 상세로 이동 | `409 ALREADY_MEMBER` |
| 카카오 계정에 이메일 없음 | 이메일 동의항목 미신청 상태 | 가입은 진행하되 이메일 필드 비움. 비밀번호 재설정 불가 안내 | `201` \+ `email: null` |
| 동일인 중복 가입 | 카카오로 가입한 사람이 이메일로 또 가입 | 매니저가 S\-08에서 두 계정 병합 요청 | `409 POSSIBLE_DUPLICATE` |
| 팀 미활성 | 인원 5명 미만인 팀에서 일정 등록 | 버튼 비활성 \+ "5명 이상 모이면 일정을 만들 수 있어요 (현재 3명)" | `422 TEAM_NOT_ACTIVE` |
| **게스트 동명이인** | 같은 이름의 게스트가 이미 존재 | 등록 시 기존 게스트 목록을 먼저 보여주고 "새 게스트로 추가" 선택지를 아래에 배치 | `200` \+ `similar[]` |
| **게스트 데이터 없음** | 실력 등급 미지정 게스트 | 배정 화면 칩에 `?` 배지, 클럽 평균값 적용, 설명 문구에 "게스트 2명은 평균으로 가정" 명시 | `players.skill_confidence = 0` |
| 인원 부족 배정 | 참석자 \< 팀 수 × 5 | 실행 버튼 비활성 \+ "2팀을 만들려면 최소 10명이 필요해요 (현재 8명)" | `422 NOT_ENOUGH_PLAYERS` |
| **묶음 그룹 과대** | 그룹 인원 \> 팀 정원 | 묶는 즉시 인라인 경고, 실행 차단 | `422 LOCK_GROUP_TOO_LARGE` |
| **제약 분할 불가** | 그룹 크기 조합으로 팀 정원을 못 채움 | "4명 그룹과 5명 그룹으로는 6명씩 두 팀을 만들 수 없어요" | `422 LOCK_PARTITION_INFEASIBLE` |
| **사전 배치 초과** | 한 팀 칸에 정원 초과 배치 | 드롭 자체를 거부 \+ 흔들림 애니메이션 | `422 SQUAD_OVERFLOW` |
| 빅맨 부족 | 4·5번 가능 인원 \< 팀 수 | 경고 배너(차단 아님) \+ 대안 제시 | `200` \+ `warnings[]` |
| 신규·게스트 데이터 부족 | 경기 이력 0 | 카드에 "데이터 부족" 배지, 신뢰도 낮음 표시 | `skill_confidence < 0.3` |
| RSVP 마감 후 응답 | 마감 시각 경과 | 토글 비활성 \+ "응답이 마감되었어요" | `422 RSVP_CLOSED` |
| 노쇼 / 당일 인원 변동 | 확정 후 참석자 변경 | "재배정" 버튼 노출, 기존 배정안은 이력 보존 | 배정 재실행 |
| **쿼터 수 변경** | 예정보다 일찍 끝나거나 더 뜀 | 쿼터 카드 추가·삭제 자유. 삭제 시 해당 쿼터 마진 롤백 | `DELETE /quarters/{id}` |
| **쿼터 출전 인원 오류** | 한 팀에 5명이 아닌 인원 체크 | 저장 버튼 비활성 \+ "블랙 팀 4명이 선택되었어요" | `400 INVALID_LINEUP_SIZE` |
| 권한 없음 | 플레이어가 매니저 URL 직접 접근 | 403 페이지 \+ 홈 복귀 | `403 FORBIDDEN_ROLE` |
| 자기 자신 투표 | 피어 설문에서 본인 선택 | 본인 항목을 선택 목록에서 제외 | `400 SELF_VOTE_NOT_ALLOWED` |
| **게스트에게 투표** | 게스트는 투표 대상이 될 수 있으나 응답자는 될 수 없음 | 투표 대상 목록에는 포함, 설문 링크는 발송 안 함 | — |
| 네트워크 오류 | 체육관 통신 불량 | 쿼터 입력은 localStorage 임시 저장 후 재전송 | — |

## 5\.5 와이어프레임 제작 방안

1. **화면 목록 → 로우파이(Lo\-fi) 스케치.** S\-01\~S\-18 전체를 흑백 박스로 먼저 그린다. 여기서 검증할 것은 "요구사항 FR\-01\~24가 모두 어떤 화면에 들어갔는가" 뿐이다
2. **핵심 3개 화면만 하이파이(Hi\-fi).** S\-12 배정 실행, S\-13 배정 결과, S\-15 쿼터 입력. 이 서비스의 가치가 집중된 화면
3. **플로우 다이어그램 별도 작성.** 화면 간 전이와 조건 분기(5.3절)를 별도 다이어그램으로. 화면 목록만으로는 예외 경로가 드러나지 않는다
4. **도구:** Figma (팀 협업·프로토타입 링크 공유) 또는 Excalidraw (빠른 로우파이). 문서화 목적이라면 Mermaid 플로우차트로 흐름만 코드로 관리하는 것도 유효
5. **검증 체크:** 각 화면 요소에 대응 API 필드를 주석으로 달아두면 7장 API 명세와의 불일치를 조기에 발견할 수 있다

* * *

# 6\. 데이터 모델 (ERD)

## 6\.1 엔터티 개요

| 그룹 | 엔터티 | 역할 |
| --- | --- | --- |
| 계정·인증 | `users`, `auth_identities`, `password_reset_tokens` | 로그인 계정과 로그인 수단(카카오/이메일) |
| 팀·참가자 | `teams`, `players` | 팀과 그 팀의 참가자(회원 \+ 게스트). `players`가 팀 소속과 역할을 겸함 |
| 프로필 | `player_profiles`, `player_positions`, `skill_rating_history` | 실력·포지션 지표와 변동 이력 |
| 매니저 판단 | `manager_rankings`, `manager_ranking_entries` | 매니저가 매긴 실력 순서 (버전 관리) |
| 설문 | `survey_templates`, `survey_questions`, `survey_options`, `survey_responses`, `survey_answers` | 온보딩 설문(버전 관리 포함) |
| 일정 | `events`, `event_attendances` | 모임 일정과 참석 응답 (게스트는 매니저가 대신 등록) |
| 배정 | `assignment_runs`, `assignment_constraints`, `assignment_candidates`, `assignment_squads`, `assignment_slots` | 배정 실행·회차별 제약·후보안·최종 편성 |
| 경기 | `quarters`, `quarter_lineups` | 쿼터별 스코어와 출전 기록, 코트 마진 |
| 피어 평가 | `post_game_surveys`, `post_game_votes`, `chemistry_scores` | 경기 후 투표와 선호 조합 |
| 운영 | `audit_logs` | 관리자 보정 등 민감 조작 이력 |

**v0.3에서 사라진 테이블:** `team_memberships`(→ `players`에 흡수), `games`(→ `quarters`가 `events` 직결), `team_constraints`(→ `assignment_constraints`로 회차별 전환)

## 6\.2 주요 테이블 정의

### 설계 원칙: 계정(users)과 참가자(players)를 분리한다

게스트는 계정이 없지만 경기 기록·배정·투표의 **대상**이 됩니다(3.1절). 따라서 로그인 주체와 경기 참가자를 같은 테이블에 두면 게스트마다 가짜 계정을 만들어야 하고, 나중에 그 사람이 정식 가입하면 기록이 두 갈래로 갈라집니다.

- `users` — 로그인할 수 있는 계정
- `players` — 특정 팀에 속한 참가자. 회원이면 `user_id`가 채워지고, 게스트면 `NULL`
- **경기 기록·배정·설문·지표는 전부 `player_id`를 참조합니다**

부수 효과로 팀 소속(`team_memberships`)이 `players`에 흡수되어 테이블이 하나 줄고, 실력 지표가 **팀 단위**로 관리됩니다. 클럽마다 상대 수준이 다르므로 이쪽이 더 정확합니다.

### users — 로그인 계정

| 컬럼 | 타입 | 제약 |
| --- | --- | --- |
| id | BIGSERIAL | **PK** |
| email | VARCHAR(255) | UNIQUE, **NULL 허용** (카카오 계정에 이메일이 없을 수 있음) |
| password\_hash | VARCHAR(255) | NULL 허용 (소셜 전용 계정) · bcrypt 해시 |
| name | VARCHAR(50) | NOT NULL |
| nickname | VARCHAR(50) |  |
| profile\_image\_url | TEXT | 카카오 프로필 이미지 URL 또는 업로드 경로 |
| birth\_year | SMALLINT | CHECK 1940\~현재 |
| height\_cm | SMALLINT | CHECK 120\~250 |
| global\_role | VARCHAR(10) | `ADMIN` / `USER`, DEFAULT `USER` |
| onboarding\_completed | BOOLEAN | DEFAULT false |
| created\_at / updated\_at / deleted\_at | TIMESTAMPTZ | soft delete |

### auth\_identities — 로그인 수단 (users 1:N)

한 계정에 카카오와 이메일을 모두 연결할 수 있게 분리합니다.

| 컬럼 | 타입 | 제약 |
| --- | --- | --- |
| id | BIGSERIAL | **PK** |
| user\_id | BIGINT | **FK** → users.id, ON DELETE CASCADE |
| provider | VARCHAR(10) | `LOCAL` / `KAKAO` |
| provider\_uid | VARCHAR(64) | 카카오 회원번호. LOCAL이면 email |
| linked\_at | TIMESTAMPTZ |  |
| — | — | **UNIQUE (provider, provider\_uid)** |

### password\_reset\_tokens

| 컬럼 | 타입 | 비고 |
| --- | --- | --- |
| id | BIGSERIAL | **PK** |
| user\_id | BIGINT | **FK** → users.id |
| token\_hash | CHAR(64) | 원문 토큰은 저장하지 않고 SHA\-256 해시만 |
| expires\_at | TIMESTAMPTZ | 발급 후 30분 |
| used\_at | TIMESTAMPTZ | NULL이면 미사용 |

### teams

| 컬럼 | 타입 | 제약 |
| --- | --- | --- |
| id | BIGSERIAL | **PK** |
| name | VARCHAR(50) | NOT NULL |
| description | TEXT |  |
| team\_code | CHAR(8) | UNIQUE, NOT NULL (대문자\+숫자) |
| owner\_user\_id | BIGINT | **FK** → users.id, NOT NULL |
| status | VARCHAR(10) | `PENDING` / `ACTIVE` / `ARCHIVED`, DEFAULT `PENDING` |
| min\_members | SMALLINT | DEFAULT 5 |
| home\_court | VARCHAR(100) |  |
| created\_at / updated\_at | TIMESTAMPTZ |  |

### players — 참가자 (팀 소속 \+ 게스트 통합)

| 컬럼 | 타입 | 제약 |
| --- | --- | --- |
| id | BIGSERIAL | **PK** |
| team\_id | BIGINT | **FK** → teams.id, ON DELETE CASCADE |
| user\_id | BIGINT | **FK** → users.id, **NULL 허용** (NULL \= 게스트) |
| kind | VARCHAR(10) | `MEMBER` / `GUEST` |
| display\_name | VARCHAR(50) | NOT NULL (게스트는 매니저가 입력한 이름) |
| role | VARCHAR(10) | `MANAGER` / `PLAYER`, DEFAULT `PLAYER` (게스트는 `PLAYER` 고정) |
| status | VARCHAR(10) | `ACTIVE` / `LEFT` / `REMOVED` |
| created\_by | BIGINT | **FK** → users.id (게스트 등록자) |
| role\_granted\_by | BIGINT | **FK** → users.id, NULL 허용 |
| merged\_into\_player\_id | BIGINT | **FK** → players.id, NULL 허용 (게스트→회원 병합 시 흡수처) |
| joined\_at | TIMESTAMPTZ | NOT NULL |
| — | — | **UNIQUE (team\_id, user\_id) WHERE user\_id IS NOT NULL** |
| — | — | **CHECK (kind \= 'GUEST') \= (user\_id IS NULL)** |

**게스트 → 회원 병합 절차**
게스트가 팀 코드로 가입하면 새 `players` 행이 생깁니다. 매니저가 S\-08에서 "이 사람은 지난주 게스트 김OO입니다"를 선택하면, 게스트 행의 `merged_into_player_id`에 새 행 id를 기록하고 `status`를 `LEFT`로 바꿉니다. 지표 계산 시 `merged_into_player_id`를 따라 올라가 기록을 합산하므로 **과거 데이터가 보존**되고, 잘못 병합해도 되돌릴 수 있습니다.

### player\_profiles — players 1:1

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| player\_id | BIGINT | **PK, FK** → players.id |
| prior\_overall | NUMERIC(4,1) | 사전 실력값 (설문 \+ 매니저 정렬, 게스트는 매니저 지정 등급) |
| prior\_source | VARCHAR(20) | `SURVEY` / `MANAGER` / `DEFAULT` (게스트 미지정 시 클럽 평균) |
| skill\_overall | NUMERIC(4,1) | 현재 종합 실력 (쿼터당 득실 기여, 점) |
| skill\_shooting / ball\_handling / passing / defense / rebound\_post / stamina | NUMERIC(4,1) | 세부 6축 |
| skill\_confidence | NUMERIC(3,2) | 0\~1, 표본 기반 신뢰도 (게스트 초기값 0) |
| quarters\_played | INTEGER | DEFAULT 0 |
| cumulative\_residual | NUMERIC(7,2) | 기대 마진 대비 잔차 누적 (원시 마진이 아님) |
| avg\_margin\_per\_quarter | NUMERIC(5,2) | 표시용 파생값 |
| peer\_vote\_score | NUMERIC(4,1) | 정규화된 피어 투표 점수 |
| updated\_at | TIMESTAMPTZ |  |

### player\_positions — players 1:N

id **PK** · player\_id **FK** → players.id · position VARCHAR(2) (`PG`/`SG`/`SF`/`PF`/`C`) · can\_play BOOLEAN · preference\_rank SMALLINT NULL · self\_rating SMALLINT CHECK 1\~5 · **UNIQUE (player\_id, position)**

### manager\_rankings / manager\_ranking\_entries — 매니저 실력 정렬 (F14)

`manager_rankings`\: id **PK** · team\_id **FK** → teams.id · ranked\_by **FK** → users.id · created\_at · is\_active BOOLEAN

`manager_ranking_entries`\: id **PK** · ranking\_id **FK** ON DELETE CASCADE · player\_id **FK** → players.id · rank\_no SMALLINT NOT NULL · **UNIQUE (ranking\_id, player\_id)** · **UNIQUE (ranking\_id, rank\_no)**

> 정렬을 덮어쓰지 않고 버전으로 쌓습니다. 매니저가 바뀌거나 정렬이 이상해졌을 때 되돌릴 수 있어야 하고, 정렬 자체가 사전값의 품질을 추적하는 자료가 되기 때문입니다.

### events / event\_attendances

`events`\: id **PK** · team\_id **FK** → teams.id · title · event\_date DATE NOT NULL · start\_time · end\_time · venue VARCHAR(100) · rsvp\_deadline TIMESTAMPTZ · status (`OPEN`/`CLOSED`/`DONE`/`CANCELED`) · created\_by **FK** → users.id

`event_attendances`\: id **PK** · event\_id **FK** ON DELETE CASCADE · player\_id **FK** → players.id · status (`ATTEND`/`ABSENT`/`PENDING`) · note · responded\_at · registered\_by **FK** → users.id NULL (게스트는 매니저가 대신 등록) · **UNIQUE (event\_id, player\_id)**

### 배정 5개 테이블

| 테이블 | 주요 컬럼 | 관계 |
| --- | --- | --- |
| `assignment_runs` | id **PK**, event\_id **FK**, executed\_by **FK**→users, team\_count SMALLINT, params JSONB(가중치), roster\_snapshot JSONB, created\_at | events 1:N |
| `assignment_constraints` | id **PK**, run\_id **FK** ON DELETE CASCADE, type (`LOCK`/`SEPARATE`/`PIN`), group\_no SMALLINT NULL, player\_id **FK**→players, squad\_no SMALLINT NULL | runs 1:N |
| `assignment_candidates` | id **PK**, run\_id **FK**, strategy (`SKILL`/`CHEMISTRY`/`BALANCED`), total\_score NUMERIC, metrics JSONB, explanation TEXT, is\_adopted BOOLEAN | runs 1:N |
| `assignment_squads` | id **PK**, candidate\_id **FK**, squad\_no SMALLINT, squad\_name VARCHAR(20) DEFAULT `블랙`/`화이트`, avg\_skill NUMERIC(4,1) | candidates 1:N |
| `assignment_slots` | id **PK**, squad\_id **FK**, player\_id **FK**→players, assigned\_position VARCHAR(2), is\_manual\_override BOOLEAN, **UNIQUE (squad\_id, player\_id)** | squads 1:N |

**제약 표현 방식** — `assignment_constraints` 한 테이블로 세 기능을 모두 표현합니다.

- `LOCK` \+ 같은 `group_no` → 반드시 같은 팀 (2명 이상 임의 인원)
- `SEPARATE` \+ 같은 `group_no` → 반드시 다른 팀
- `PIN` \+ `squad_no` → 지정한 팀에 사전 배치

**제약은 회차별입니다 (v0.3 변경).** 초안에는 팀 단위 상시 제약 테이블(`team_constraints`)이 있었으나, 실제로는 "1주차에 A와 B를 묶고 다음 주에는 안 묶는" 식으로 매번 다르게 설정합니다. 따라서 제약은 `assignment_runs`에 종속시키고, 편의 기능으로 **"직전 회차 제약 불러오기"** 버튼만 제공합니다.

> 한 `assignment_run` 안에서 `is_adopted = true`인 candidate는 최대 1개 (부분 유니크 인덱스).

### quarters / quarter\_lineups — 경기 기록

초안에 있던 `games` 테이블을 **제거**했습니다. 실제 운영에서 하루의 경기는 "고정된 두 팀이 여러 쿼터를 연속으로 뛰는" 형태이므로, 경기라는 중간 계층 없이 `events → quarters`로 직결하는 편이 단순하고 정확합니다.

`quarters`\: id **PK** · event\_id **FK** → events.id ON DELETE CASCADE · quarter\_no SMALLINT NOT NULL · black\_score SMALLINT CHECK ≥ 0 · white\_score SMALLINT CHECK ≥ 0 · **duration\_min SMALLINT DEFAULT 10** · recorded\_by **FK** → users.id · created\_at · **UNIQUE (event\_id, quarter\_no)**

`quarter_lineups`\: id **PK** · quarter\_id **FK** ON DELETE CASCADE · player\_id **FK** → players.id · side VARCHAR(5) (`BLACK`/`WHITE`) · position VARCHAR(2) NULL · raw\_margin SMALLINT · **normalized\_margin NUMERIC(5,2)** · **UNIQUE (quarter\_id, player\_id)**

**코트 마진 계산 (쿼터 수·길이가 유동적이라 정규화가 필수)**

```
raw_margin        = (내 팀 득점) − (상대 팀 득점)
normalized_margin = raw_margin × (10 / duration_min)
```

쿼터 저장 시 서버에서 출전 10명 전원에 대해 일괄 계산합니다. 개인 스탯 입력은 전혀 필요 없습니다. **실력 지표에 반영되는 값은 이 마진이 아니라 기대 마진 대비 잔차입니다** (9.2절).

### post\_game\_surveys / post\_game\_votes / chemistry\_scores

`post_game_surveys`\: id **PK** · event\_id **FK** · respondent\_player\_id **FK** → players.id · submitted\_at · **UNIQUE (event\_id, respondent\_player\_id)** · **CHECK** 응답자는 `kind = 'MEMBER'`

`post_game_votes`\: id **PK** · survey\_id **FK** ON DELETE CASCADE · target\_player\_id **FK** → players.id (게스트도 대상 가능) · vote\_type (`BEST_PERFORMER`/`PLAY_AGAIN`) · target\_side (`SAME_TEAM`/`OPPONENT`) · **UNIQUE (survey\_id, target\_player\_id, vote\_type)** · **CHECK** 자기 자신 불가

`chemistry_scores` — players M:N players (self\-referencing):

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| id | BIGSERIAL | **PK** |
| player\_a\_id / player\_b\_id | BIGINT | **FK** → players.id · **CHECK (a \< b)** 중복 쌍 방지 |
| together\_quarters | INTEGER | 함께 출전한 쿼터 수 |
| pref\_score | NUMERIC(3,2) | 피어 투표 기반 선호도 (0\~1) |
| pref\_mutual | BOOLEAN | 상호 지목 여부 |
| synergy\_est | NUMERIC(4,2) | RAPM 상호작용 추정치 (참고용) |
| synergy\_ci\_low / synergy\_ci\_high | NUMERIC(4,2) | 부트스트랩 95% 구간 |
| synergy\_significant | BOOLEAN | 9\.4절 3조건 통과 여부 |
| updated\_at | TIMESTAMPTZ |  |
| — | — | **UNIQUE (player\_a\_id, player\_b\_id)** |

> 초안의 단일 `chemistry` 컬럼은 삭제했습니다. 근거가 다른 두 신호(선언된 선호 / 관찰된 시너지)를 한 숫자로 뭉개면 설명할 수 없기 때문입니다 (9.4절).

### skill\_rating\_history

id **PK** · player\_id **FK** · source (`SURVEY`/`MANAGER_SORT`/`RESIDUAL`/`PEER_VOTE`/`MANAGER_ADJUST`/`ADMIN_ADJUST`/`MERGE`) · before\_value · after\_value · delta · ref\_type · ref\_id · reason TEXT · created\_at

## 6\.3 관계 요약

| 관계 | 카디널리티 | 비고 |
| --- | --- | --- |
| users → auth\_identities | **1:N** | 한 계정에 카카오·이메일 동시 연결 가능 |
| users → players | **1:N** | 한 사람이 여러 팀에 참가 |
| teams → players | **1:N** | 게스트 포함 |
| users ↔ teams | **M:N** | `players`를 통해 성립 (역할 속성 보유) |
| players → players | **N:1 (self)** | `merged_into_player_id` — 게스트→회원 병합 |
| players → player\_profiles | **1:1** | 실력 지표는 **팀 단위**로 관리 |
| players → player\_positions | **1:N** | 최대 5행 |
| teams → manager\_rankings → entries → players | **1:N → 1:N → N:1** | 정렬 버전 관리 |
| teams → events | **1:N** |  |
| events ↔ players (참석) | **M:N** | `event_attendances` |
| events → assignment\_runs | **1:N** | 재배정 시 이력 누적 |
| assignment\_runs → constraints | **1:N** | 회차별 묶기/분리/사전배치 |
| assignment\_runs → candidates → squads → slots | **1:N 체인** | 후보 3개 → 팀 2\~4개 → 슬롯 |
| assignment\_slots → players | **N:1** |  |
| events → quarters → quarter\_lineups | **1:N 체인** | 쿼터 수 유동 |
| quarter\_lineups → players | **N:1** |  |
| players ↔ players (선호 조합) | **M:N self\-referencing** | `chemistry_scores` |
| events → post\_game\_surveys → votes → players | **1:N → 1:N → N:1** | 응답자는 회원만, 대상은 게스트 포함 |

## 6\.4 인덱스 권고

- `event_attendances (event_id, status)` — 참석자 조회
- `quarter_lineups (user_id)` — 개인 마진 집계
- `team_memberships (user_id, status)` — 내 팀 목록
- `chemistry_scores (user_a_id)`, `(user_b_id)` — 케미 조회
- `assignment_candidates (run_id) WHERE is_adopted` — 확정안 조회

* * *

# 7\. API 명세

## 7\.1 공통 규약

- Base URL: `/api/v1`
- 인증: `Authorization: Bearer <access_token>` (JWT, access 30분 / refresh 14일)
- 요청·응답 본문은 `application/json`, 필드명은 `snake_case`
- 목록 응답은 `{ "items": [...], "meta": { "page", "size", "total" } }` 형태로 통일
- OpenAPI 스키마는 FastAPI가 자동 생성 (`/docs`, `/openapi.json`)

## 7\.2 공통 스키마 (`$ref` 재사용 대상)

| 스키마 | 용도 |
| --- | --- |
| `ErrorResponse` | `{ code, message, details[] }` — 모든 4xx/5xx 공통 |
| `PageMeta` | `{ page, size, total, has_next }` |
| `UserSummary` | `{ id, name, nickname, profile_image_url }` |
| `PlayerCard` | `UserSummary` \+ `{ skill_grade, primary_position, playable_positions[], attendance_rate }` |
| `PlayerCardDetailed` | `PlayerCard` \+ `{ skill_overall, skill_axes{}, skill_confidence, avg_margin }` — MANAGER/ADMIN 전용 |
| `PositionEnum` | `PG` \| `SG` \| `SF` \| `PF` \| `C` |
| `StrategyEnum` | `SKILL` \| `CHEMISTRY` \| `POSITION` \| `BALANCED` |
| `SquadView` | `{ squad_no, squad_name, avg_skill, members: PlayerCard[] }` |

## 7\.3 엔드포인트

### 인증 · 프로필

| Method | Path | 설명 | 주요 응답 |
| --- | --- | --- | --- |
| POST | `/auth/signup` | 이메일 회원가입 | `201` · `409 EMAIL_DUPLICATED` |
| POST | `/auth/login` | 이메일 로그인 | `200 {access_token, refresh_token}` · `401 INVALID_CREDENTIALS` |
| GET | `/auth/kakao/login-url` | 카카오 인가 URL 생성 (state 포함) | `200 {url, state}` |
| GET | `/auth/kakao/callback` | 인가 코드 수신 → 토큰 교환 → 가입/로그인 | `200 {access_token, refresh_token, is_new}` · `401 KAKAO_AUTH_FAILED` |
| POST | `/auth/kakao/link` | 기존 계정에 카카오 연결 | `200` · `409 IDENTITY_ALREADY_LINKED` |
| POST | `/auth/refresh` | 토큰 갱신 | `200` · `401 TOKEN_EXPIRED` |
| POST | `/auth/password/forgot` | 재설정 메일 발송 | `202` (계정 존재 여부를 노출하지 않기 위해 항상 202) |
| POST | `/auth/password/reset` | Body `{token, new_password}` | `200` · `400 TOKEN_INVALID_OR_EXPIRED` |
| GET | `/me` | 내 정보 \+ 연결된 로그인 수단 \+ 온보딩 완료 여부 | `200 UserDetail` |
| PATCH | `/me` | 프로필 수정 | `200` · `400 VALIDATION_ERROR` |
| GET | `/me/teams` | 내 소속 팀 목록 (역할 포함) | `200 {items: TeamMembershipView[]}` |

### 온보딩 설문

| Method | Path | 설명 | 응답 |
| --- | --- | --- | --- |
| GET | `/surveys/onboarding` | 활성 설문 문항·선택지 조회 | `200 SurveyTemplate` |
| POST | `/surveys/onboarding/responses` | 응답 제출 → 프로필 생성 | `201 PlayerProfile` · `409 ALREADY_SUBMITTED` |
| GET | `/me/profile` | 내 실력·포지션 프로필 | `200 PlayerCard` |
| PUT | `/me/positions` | 가능/선호 포지션 수정 | `200` |

### 팀 · 참가자

| Method | Path | 설명 | 응답 |
| --- | --- | --- | --- |
| POST | `/teams` | 팀 생성 (생성자 MANAGER) | `201 {id, team_code}` |
| POST | `/teams/join` | Body `{team_code}` 로 가입 | `200` · `404 TEAM_CODE_NOT_FOUND` · `409 ALREADY_MEMBER` |
| GET | `/teams/{team_id}` | 팀 상세 | `200` · `403 NOT_A_MEMBER` |
| PATCH | `/teams/{team_id}` | 팀 정보 수정 (MANAGER) | `200` · `403 FORBIDDEN_ROLE` |
| POST | `/teams/{team_id}/code:regenerate` | 팀 코드 재발급 | `200 {team_code}` |
| GET | `/teams/{team_id}/players` | Query `?kind=MEMBER\|GUEST&status=&sort=skill\|name` | `200 {items: PlayerCard[]}` |
| PATCH | `/teams/{team_id}/players/{player_id}/role` | 권한 부여/회수 | `200` · `422 CANNOT_DEMOTE_LAST_MANAGER` |
| DELETE | `/teams/{team_id}/players/{player_id}` | 팀원 제외 | `204` |

### 게스트 관리 (F13)

| Method | Path | 설명 | 응답 |
| --- | --- | --- | --- |
| POST | `/teams/{team_id}/guests` | 게스트 등록. Body `{display_name, skill_grade?(1~5), playable_positions?[]}` | `201 PlayerCard` · `200 {similar[]}` (동명이인 후보 존재 시 확인 요청) |
| GET | `/teams/{team_id}/guests` | Query `?q=이름` 기존 게스트 검색 (재방문 시 선택용) | `200 {items}` |
| PATCH | `/players/{player_id}` | 게스트 이름·실력 등급·포지션 수정 | `200` · `403` |
| POST | `/players/{guest_player_id}:merge` | Body `{into_player_id}` 게스트를 회원 계정에 병합 | `200` · `409 ALREADY_MERGED` · `422 MERGE_KIND_MISMATCH` |
| POST | `/players/{player_id}:unmerge` | 병합 되돌리기 | `200` |

### 매니저 실력 정렬 (F14)

| Method | Path | 설명 | 응답 |
| --- | --- | --- | --- |
| GET | `/teams/{team_id}/rankings/latest` | 현재 활성 정렬 조회 | `200 {ranked_at, entries[]}` · `404 NO_RANKING` |
| POST | `/teams/{team_id}/rankings` | Body `{player_ids: [상위→하위 순서]}` 새 정렬 버전 생성 | `201` · `422 PLAYER_NOT_IN_TEAM` |
| GET | `/teams/{team_id}/rankings` | 정렬 이력 목록 | `200` |

### 일정 · 참석

| Method | Path | 설명 | 응답 |
| --- | --- | --- | --- |
| POST | `/teams/{team_id}/events` | 일정 등록 | `201` · `422 TEAM_NOT_ACTIVE` |
| GET | `/teams/{team_id}/events` | Query `?from=&to=&status=&page=&size=` | `200 {items, meta: PageMeta}` |
| GET | `/events/{event_id}` | 일정 상세 \+ 내 응답 상태 | `200` |
| PATCH · DELETE | `/events/{event_id}` | 일정 수정 · 취소 | `200` · `204` |
| PUT | `/events/{event_id}/attendance` | Body `{status, note}` 내 참석 응답 | `200` · `422 RSVP_CLOSED` |
| PUT | `/events/{event_id}/attendances/{player_id}` | 매니저가 대신 응답 (게스트 참석 등록) | `200` · `403` |
| GET | `/events/{event_id}/attendances` | Query `?status=` 참석 현황 \+ 포지션 분포 요약 | `200 {items, summary}` |

### 팀 배정 (F5, F15, F16)

| Method | Path | 설명 | 응답 |
| --- | --- | --- | --- |
| POST | `/events/{event_id}/assignments` | 배정 실행 (아래 Body 참조) | `201 AssignmentRun` · `422 NOT_ENOUGH_PLAYERS` · `422 LOCK_*` |
| POST | `/events/{event_id}/assignments:validate` | **제약 실현가능성만 검사** (실행 전 프리플라이트) | `200 {feasible, violations[]}` |
| GET | `/events/{event_id}/assignments` | 실행 이력 목록 | `200` |
| GET | `/events/{event_id}/assignments/last-constraints` | 직전 회차 제약 불러오기 | `200 {constraints}` · `404` |
| GET | `/assignments/runs/{run_id}` | 후보안 3개 \+ 지표 \+ 설명 | `200` |
| PATCH | `/assignments/candidates/{candidate_id}` | Body `{swaps:[{player_id_a, player_id_b}]}` → 재계산 지표 | `200` · `422 INVALID_SWAP` |
| POST | `/assignments/candidates/{candidate_id}:adopt` | 확정 → 플레이어 공개 | `200` · `409 ALREADY_ADOPTED` |
| GET | `/events/{event_id}/assignment/adopted` | 확정 결과 (액터별 필드 마스킹) | `200 {squads: SquadView[], explanation}` · `404 NOT_ADOPTED_YET` |

```
POST /api/v1/events/{event_id}/assignments
{
  "team_count": 2,
  "strategies": ["SKILL", "CHEMISTRY", "BALANCED"],
  "constraints": {
    "lock_groups":     [[12, 45, 78], [3, 9]],
    "separate_groups": [[21, 33]],
    "pins":            [{ "player_id": 5, "squad_no": 1 }]
  }
}
```

`lock_groups`·`separate_groups`는 페어가 아니라 **그룹 배열**로 받습니다. 2명 이상 임의 인원을 한 번에 묶어야 하기 때문입니다. 값은 모두 `player_id`이며 회차 한정입니다.

### 경기 기록 (F8, F17)

| Method | Path | 설명 | 응답 |
| --- | --- | --- | --- |
| POST | `/events/{event_id}/quarters` | 쿼터 1건 추가. Body `{quarter_no, black_score, white_score, duration_min, lineups:[{player_id, side, position?}]}` | `201` · `400 INVALID_LINEUP_SIZE` · `409 QUARTER_EXISTS` |
| PUT | `/events/{event_id}/quarters` | **여러 쿼터 일괄 저장** (경기 후 한 번에 입력하는 실제 흐름에 맞춤) | `200 {created, updated, deleted}` |
| GET | `/events/{event_id}/quarters` | 쿼터 \+ 라인업 전체 | `200` |
| PATCH | `/quarters/{quarter_id}` | 스코어·라인업 수정 (마진 재계산) | `200` |
| DELETE | `/quarters/{quarter_id}` | 쿼터 삭제 (마진 롤백) | `204` |
| GET | `/events/{event_id}/rotation-suggestion` | Query `?quarter_no=` 출전 시간 균등 기준 다음 5명 제안 | `200 {black[], white[]}` |

### 경기 후 설문 · 통계

| Method | Path | 설명 | 응답 |
| --- | --- | --- | --- |
| GET | `/events/{event_id}/post-game-survey` | 투표 대상 명단(같은 팀/상대 팀, 게스트 포함) | `200` · `403 NOT_ATTENDEE` |
| POST | `/events/{event_id}/post-game-survey` | Body `{votes:[{target_player_id, vote_type, target_side}]}` | `201` · `400 SELF_VOTE_NOT_ALLOWED` · `409 ALREADY_SUBMITTED` |
| GET | `/players/{player_id}/stats` | 참여 이력·마진 추이·포지션 분포 | `200` (본인/MANAGER/ADMIN만 상세) |
| GET | `/players/{player_id}/compatible` | 나와 잘 맞는 참여자 (F11) | `200 {items[]}` |
| GET | `/teams/{team_id}/stats/leaderboard` | Query `?metric=residual\|attendance&period=` | `200` |

### 관리자

| Method | Path | 설명 |
| --- | --- | --- |
| GET | `/admin/users` | 전체 사용자 검색·페이징 |
| GET | `/admin/players/{player_id}/raw` | 설문 원본·라인업 이력·투표 수신·지표 변동 전체 |
| PATCH | `/admin/players/{player_id}/rating` | Body `{skill_overall, reason}` → `skill_rating_history` 기록 |
| GET | `/admin/audit-logs` | 감사 로그 조회 |

## 7\.4 에러 코드 체계

| HTTP | code | 상황 |
| --- | --- | --- |
| 400 | `VALIDATION_ERROR` | 필드 형식·범위 위반 |
| 400 | `INVALID_LINEUP_SIZE` | 쿼터 출전 인원이 팀당 5명이 아님 |
| 400 | `SELF_VOTE_NOT_ALLOWED` | 피어 설문 본인 선택 |
| 400 | `TOKEN_INVALID_OR_EXPIRED` | 비밀번호 재설정 토큰 무효 |
| 401 | `INVALID_CREDENTIALS` / `TOKEN_EXPIRED` / `KAKAO_AUTH_FAILED` | 인증 실패 |
| 403 | `FORBIDDEN_ROLE` / `NOT_A_MEMBER` / `NOT_ATTENDEE` | 권한 부족 |
| 404 | `NOT_FOUND` / `TEAM_CODE_NOT_FOUND` / `NOT_ADOPTED_YET` / `NO_RANKING` | 리소스 없음 |
| 409 | `EMAIL_DUPLICATED` / `ALREADY_MEMBER` / `ALREADY_SUBMITTED` / `QUARTER_EXISTS` / `ALREADY_ADOPTED` / `IDENTITY_ALREADY_LINKED` / `ALREADY_MERGED` | 상태 충돌 |
| 422 | `TEAM_NOT_ACTIVE` / `NOT_ENOUGH_PLAYERS` / `RSVP_CLOSED` / `INVALID_SWAP` / `CANNOT_DEMOTE_LAST_MANAGER` / `PLAYER_NOT_IN_TEAM` / `MERGE_KIND_MISMATCH` | 도메인 규칙 위반 |
| 422 | `LOCK_GROUP_TOO_LARGE` / `CONSTRAINT_CONFLICT` / `SEPARATE_INFEASIBLE` / `LOCK_PARTITION_INFEASIBLE` / `SQUAD_OVERFLOW` | 배정 제약 실현 불가 |
| 429 | `RATE_LIMITED` | 과다 요청 |
| 500 | `INTERNAL_ERROR` | 서버 오류 |

> **설계 원칙:** 형식 오류는 400, 권한은 403, 존재하지 않음은 404, 상태 충돌은 409, **도메인 규칙 위반은 422**. 프론트는 `code`로 분기하고 `message`는 그대로 노출 가능한 한국어 문구로 유지합니다.
> 
> **배정 제약 오류는 `details[]`에 어떤 그룹·선수가 문제인지 담아야 합니다.** "제약을 만족할 수 없습니다"만으로는 매니저가 무엇을 풀어야 할지 알 수 없습니다.
> 
> **`/auth/password/forgot`은 항상 202를 반환합니다.** 가입 여부에 따라 응답이 달라지면 계정 존재 여부를 확인하는 통로가 됩니다.

# 8\. 온보딩 설문 설계 (v0.2)

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

## 8\.3 문항 구성 (14문항 · 약 2분 30초)

### 섹션 A — 기본 (3문항)

| \# | 문항 | 형식 |
| --- | --- | --- |
| A1 | 키 | 숫자 스테퍼 (cm) |
| A2 | 농구를 해온 기간 | 4택 — 1년 미만 / 1\~3년 / 3\~7년 / 7년 이상 |
| A3 | 경험한 가장 높은 경기 수준 | 4택 — 체육시간·친구들끼리 / 동호회·아마추어 / 학교 대표·클럽팀 / 선수 출신 |

### 섹션 B — 공격 (3문항)

| \# | 문항 | 형식 |
| --- | --- | --- |
| B1 | 실제 경기에서 **자주 쓰는** 공격 옵션을 모두 고르세요 | 다중선택 8칩 — 캐치앤슛 3점 / 풀업·미들 점퍼 / 드라이브 후 마무리 / 픽앤롤 핸들러 / 픽앤롤 롤·팝 / 포스트업 / 오프볼 컷인 / 공격 리바운드 풋백 |
| B2 | 경기에서 **안정적으로** 넣을 수 있는 최대 거리 | 5택 서열 — 골밑 레이업 / 페인트존 훅·플로터 / 자유투 라인 / 3점 라인 / 3점 라인 밖 |
| B3 | 볼 운반과 돌파 | 4택 앵커 — 드리블 돌파를 시도하지 않음 / 가벼운 압박은 벗겨냄 / 하프코트 압박에서도 볼을 운반함 / 풀코트 압박에서도 안정적으로 가져감 |

> **B1이 1문항으로 하는 일:** 선택 **개수** \= 공격 다재다능성. 선택 **조합** \= 포지션 프로파일. 캐치앤슛\+컷인만 → 오프볼 윙. 픽앤롤 핸들러\+풀업 → 온볼 가드. 포스트업\+롤맨\+풋백 → 빅맨. 포지션 문항의 교차 검증 자료로도 쓰입니다.

### 섹션 C — 수비 (2문항)

| \# | 문항 | 4단계 앵커 |
| --- | --- | --- |
| C1 | 상대가 스크린을 걸었을 때 | ① 스크린이 뭔지 잘 모르거나 그냥 따라간다 ② 피해서 따라가려 하지만 자주 놓친다 ③ 스위치를 부르고 바꿔 막는다 ④ 상황에 따라 스위치·헤지·언더를 구분해서 쓴다 |
| C2 | 동료 매치업이 뚫렸을 때 | ① 내 사람만 본다 ② 헬프는 가지만 이후 내 자리로 못 돌아온다 ③ 헬프 후 내 매치업으로 복귀한다 ④ 헬프 사이드까지 읽고 미리 로테이션을 돈다 |

> 수비 이해도는 자기평가가 가장 부정확한 영역입니다. C1·C2는 **용어를 아는지**로 실질 수준을 가르는 문항이라 상향 편향에 강합니다.

### 섹션 D — 포지션 (3문항)

| \# | 문항 | 형식 |
| --- | --- | --- |
| D1 | 수행 **가능한** 포지션 | 다중선택 5칩 (PG/SG/SF/PF/C) |
| D2 | 가장 **선호하는** 포지션 | 단일선택 |
| D3 | 희소 자원 확인 (한 화면 2줄) | "1번(볼 운반)을 맡을 수 있나요" · "5번(골밑)을 맡을 수 있나요" 각각 3택 — 가능하고 선호함 / 가능하지만 선호하지 않음 / 불가 |

> D3를 D1에서 분리하는 이유: 1번·5번은 배정 알고리즘의 **하드 제약**입니다. 다중선택 안에 섞어두면 무심코 전부 체크하는 경향이 있어, 별도 질문으로 응답 비용을 만들어야 합니다.

### 섹션 E — 성향·상대평가 (3문항)

| \# | 문항 | 형식 |
| --- | --- | --- |
| E1 | 플레이 성향 | 4단계 양극 — 온볼(내가 만들어감) ↔ 오프볼(움직여서 받음) |
| E2 | 체력 | 4택 — 1쿼터도 벅참 / 2쿼터 / 3\~4쿼터 / 계속 뛰어도 페이스 유지 |
| E3 | **이 동호회에서 본인의 실력 위치** | 5택 서열 — 상위 10% / 상위 30% / 중간 / 하위 30% / 하위 10% |

> **E3가 단일 최고 정보량 문항입니다.** 배정에 필요한 것은 절대 점수가 아니라 클럽 내 순위이고, 사람은 절대 평가보다 상대 위치 판단을 훨씬 잘합니다. 겸손 편향이 있더라도 **모두가 같은 방향으로 편향되므로 순위는 보존**됩니다.

## 8\.4 응답 → 사전 실력값(prior) 변환

각 문항을 클럽 내 z\-score로 표준화한 뒤 가중합합니다. 절대값은 의미가 없고 **클럽 내 상대 위치만** 사용합니다.

```
prior_z = 0.30 × z(E3 자기 백분위)
        + 0.20 × z(A2 구력, A3 경기 수준)
        + 0.20 × z(B2 슛 거리, B1 옵션 개수)
        + 0.15 × z(B3 볼 운반)
        + 0.15 × z(C1, C2 수비 이해도)

세부 축(표시·포지션 매칭용):
  슛      ← B2, B1(캐치앤슛·풀업)
  볼핸들링 ← B3, B1(픽앤롤 핸들러)
  패스     ← B1(픽앤롤 핸들러·롤팝 조합), E1
  수비     ← C1, C2
  골밑     ← A1(키), B1(포스트업·롤·풋백), D3
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
- 등급은 **8쿼터 단위로만 갱신 표시**합니다. 매 쿼터 등급이 흔들리면 신뢰를 잃습니다
- 등급 변경은 추정값이 경계를 넘고 **신뢰도 하한도 함께 넘을 때만** 반영합니다

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

1. **입력** — 참석 확정자 N명(게스트 포함), 팀 수 T, 회차별 제약(9.6절)
2. **제약 실현가능성 사전 검사** — 실패 시 실행 전에 사유와 함께 차단
3. **사전 배치(PIN) 반영** — 매니저가 팀 칸에 직접 올린 인원을 먼저 고정
4. **묶음 그룹을 슈퍼노드로 축약** (9.6절)
5. **하드 제약 배치** — 각 팀에 1번 가능자 ≥1, 5번 가능자 ≥1 (자원 부족 시 경고 후 완화)
6. **초기해** — 실력 내림차순 스네이크 드래프트
7. **목적함수**

```
J = w_skill    × Var(팀별 평균 실력)
  + w_position × Σ 포지션 커버리지 결손 페널티
  + w_pref     × (− 팀 내 선호 조합 점수 합)
  + w_role     × Σ 선호 포지션 미충족 페널티
  + w_fair     × 최근 N회 같은 팀 반복 페널티
  + w_guest    × 게스트 편중 페널티          ← 데이터 없는 인원이 한 팀에 몰리지 않게
```

8. **지역 탐색** — 서로 다른 팀의 노드(슈퍼노드 포함) 1:1 교환을 J가 개선되지 않을 때까지 반복, 랜덤 재시작 5\~10회
9. **전략 3종으로 후보안 생성**

| 전략 | w\_skill | w\_position | w\_pref | w\_role |
| --- | ---: | ---: | ---: | ---: |
| **실력 우선** `SKILL` | 0\.70 | 0\.15 | 0\.05 | 0\.10 |
| **친화도 우선** `CHEMISTRY` | 0\.30 | 0\.15 | 0\.40 | 0\.15 |
| **종합** `BALANCED` | 0\.45 | 0\.25 | 0\.15 | 0\.15 |

> 초안에 있던 `POSITION`(포지션 우선) 전략은 제거했습니다. 1번·5번 확보는 5단계에서 **하드 제약**으로 이미 보장되므로, 이를 다시 전략으로 두면 다른 두 전략과 결과가 거의 같아집니다. 후보안은 서로 뚜렷하게 달라야 매니저가 고를 이유가 생깁니다.

10. **설명 생성** — 규칙 기반 템플릿. 매니저용은 수치, 플레이어용은 포지션·조합 중심 문장. **게스트가 포함된 경우 "게스트 2명은 매니저 지정 등급으로 계산했습니다"를 반드시 명시**합니다

### 게스트를 배정에 넣는 방법

| 상황 | 처리 |
| --- | --- |
| 매니저가 실력 등급(1\~5)을 지정 | 등급을 클럽 내 분위수로 환산해 `prior_overall`에 사용, `skill_confidence = 0.25` |
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

실제 참석 규모(12\~14명, 2팀)에서는 **완전 탐색으로 전역 최적해를 보장**할 수 있습니다.

| 인원 | 팀 구성 | 전체 조합 수 | 방식 |
| --- | --- | ---: | --- |
| 12명 | 6 \+ 6 | 462 | **완전 탐색** |
| 13명 | 6 \+ 7 | 1,716 | **완전 탐색** |
| 14명 | 7 \+ 7 | 1,716 | **완전 탐색** |
| 16명 | 8 \+ 8 | 6,435 | **완전 탐색** |
| 20명 | 4팀 × 5 | 약 4.9억 | 스네이크 \+ 지역 탐색 |

**이 서비스의 핵심 규모에서는 휴리스틱이 아예 필요 없습니다.**

12\~14명 2팀이면 조합이 2천 개 이하입니다. 모든 조합에 대해 목적함수를 계산하고 최솟값을 고르면 됩니다 — 파이썬으로 `itertools.combinations` 한 줄이고 실행 시간은 수 밀리초입니다. 묶기 제약이 걸리면 슈퍼노드로 축약되어 더 줄어듭니다.

**초보 개발자에게 이것은 매우 좋은 소식입니다.** 지역 탐색·시뮬레이티드 어닐링·OR\-Tools 같은 것을 배우지 않아도 되고, "최적해를 못 찾았을 가능성"을 걱정할 필요도 없습니다. 3팀 이상 또는 20명 이상을 지원할 때만 휴리스틱을 붙이면 되고, 그때도 완전 탐색 버전이 정답 기준(테스트 오라클)으로 남습니다.

**구현 순서 권고:** ① 완전 탐색 \+ 목적함수부터 만들고 ② 조합 수가 임계값(예: 50만)을 넘으면 자동으로 휴리스틱으로 전환하는 분기를 나중에 추가.

## 9\.8 개발 순서 권고

| 순위 | 항목 | 근거 |
| --- | --- | --- |
| 1 | 인증(카카오 \+ 이메일) · 팀 · 참가자(회원\+게스트) | `players` 구조가 뒤의 모든 테이블을 규정하므로 가장 먼저 확정 |
| 2 | 온보딩 설문 \+ 매니저 정렬 \+ 게스트 등급 지정 | 초기 5\~7개월간 배정 품질을 사실상 결정 (9.3절 실험 1·2) |
| 3 | 배정 알고리즘 (완전 탐색) \+ 묶기 제약 | 서비스의 핵심 가치. 조합이 작아 완전 탐색으로 충분 (9.7절) |
| 4 | 쿼터 기록 \+ 잔차 기반 실력 갱신 | 데이터 축적 시작. 단, **첫 2회 데이터는 지표에 미반영** |
| 5 | 피어 투표 → 선호 조합 | 케미 기능의 실질 |
| 6 | 사전 배치(PIN) · 분리(SEPARATE) | 매니저 요청 빈도가 낮음. 묶기가 안정화된 뒤 |
| 7 | 배치 RAPM | 누적 100쿼터를 넘긴 뒤에 의미가 생김 |
| — | 마진 기반 케미 검정 | **v1 범위에서 제외** (9.4절). 300쿼터 이상 쌓인 뒤 재검토 |

# 10\. 기술적 타당성 검토

| 항목 | 판단 | 근거 / 대응 |
| --- | :---: | --- |
| 배정 알고리즘 구현 | **가능 (쉬움)** | 12\~14명 2팀이면 조합 2천 개 이하. **완전 탐색으로 전역 최적 보장**, 실행 수 밀리초. 외부 솔버·휴리스틱 불필요 (9.7절) |
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
| 실력 점수 공개로 인한 갈등 | **설계로 회피** | 플레이어에게 수치 비공개, 5등급만. 등급은 8쿼터 단위로만 갱신 표시 |
| **카카오 로그인 연동** | **가능 (쉬움)** | OAuth 2.0 Authorization Code. **닉네임·프로필사진은 일반 앱의 기본 동의항목이라 별도 검수 없이 사용 가능**. 이메일은 비즈 앱 전환이 필요하므로 **선택 항목으로 취급**하고 이메일 없이도 가입이 되도록 설계 (11.5절) |
| 비밀번호 보관 | **가능** | 암호화가 아니라 **단방향 해시(bcrypt)**. 복호화 자체가 불가능하므로 DB가 유출돼도 원문 복원 불가 (11.5절) |
| 비밀번호 재설정 메일 | **번거로움** | SMTP/발송 서비스 설정·토큰 만료 관리가 필요. 카카오 로그인을 주 경로로 두면 이 부담이 줄어듦 |
| 개인정보 | **주의 필요** | 키·생년만 최소 수집, 체중 미수집. 프로필 공개 범위를 팀 내로 제한. **게스트는 이름만 저장**하고 연락처를 받지 않음 |
| 모바일 웹 푸시 알림 | **제한적** | iOS Safari는 PWA 홈 화면 추가 시에만 웹 푸시 지원. 1차 대안은 **카카오톡 링크 공유 \+ 인앱 배지**. MVP 범위 밖 |
| 오프라인 기록 입력 | **불필요해짐** | 기록을 경기 **후**에 입력하므로 체육관 통신 불량 이슈가 사라짐. localStorage 임시 저장만 안전장치로 유지 |
| 실시간 동시 편집 | **불필요** | 매니저 1인이 기록. WebSocket 불필요 |

# 11\. 기술 스택

## 11\.1 선정 기준

사용자 요구는 세 가지였습니다 — **스마트폰 웹 사용 전제**, **팀 배정 알고리즘이 최우선이므로 파이썬 백엔드**, **초보 개발자가 전체를 무리 없이 구현 가능한 난이도**. 아래 스택은 이 세 가지를 동시에 만족하도록 구성했습니다.

## 11\.2 스택 구성

| 레이어 | 선택 | 선정 이유 |
| --- | --- | --- |
| **Backend** | **FastAPI** (Python 3.12) | ① 알고리즘 코드(NumPy)와 같은 언어 ② **Pydantic 스키마가 곧 OpenAPI 명세** → 7장 API 문서가 코드에서 자동 생성되고 `$ref` 재사용도 자동 ③ Django보다 학습 곡선이 완만하고 구조가 명시적 |
| ORM / 마이그레이션 | SQLAlchemy 2.0 \+ Alembic | 6장 ERD를 코드로 그대로 표현, 스키마 변경 이력 관리 |
| 검증 | Pydantic v2 | Request/Response 스키마를 ERD와 1:1로 유지 |
| **Database** | **PostgreSQL 16** | JSONB(배정 파라미터·설명 저장), 윈도우 함수(마진 집계), 부분 유니크 인덱스 지원 |
| 인증 | JWT (python\-jose) \+ passlib(bcrypt), 카카오 OAuth | 한국 사용자 기준 카카오 로그인이 이탈률을 크게 낮춤 |
| 관리자 화면 | **SQLAdmin** | 관리자 콘솔(S\-18)을 직접 만들지 않아도 됨 — Django admin의 장점을 FastAPI에서 확보. **초보 난이도를 낮추는 핵심 선택** |
| 알고리즘 | NumPy \+ (확장 시) OR\-Tools | 완전 탐색·지역 탐색은 순수 파이썬으로 충분 |
| **Frontend** | **React 18 \+ TypeScript \+ Vite** | 레퍼런스가 가장 풍부, 타입으로 API 필드 불일치 조기 발견 |
| UI | Tailwind CSS \+ shadcn/ui | 모바일 반응형을 빠르게. 컴포넌트를 직접 복사해 쓰므로 커스터마이징 부담 낮음 |
| 상태·데이터 | TanStack Query \+ Zustand | 서버 상태(캐싱·재검증)와 클라이언트 상태 분리 |
| API 클라이언트 | openapi\-typescript(\+ orval) | **FastAPI의 openapi.json에서 타입·훅 자동 생성** → 프론트/백 필드 불일치가 컴파일 단계에서 잡힘 |
| 모바일 | PWA (vite\-plugin\-pwa) | 홈 화면 추가, 오프라인 캐싱. 앱스토어 심사 불필요 |
| **인프라** | **Docker \+ Docker Compose** | `web` / `api` / `db` 3개 컨테이너. 로컬과 배포 환경 동일화 |
| 배포 | Railway 또는 Render (백\+DB), Vercel (프론트) | GitHub 연동 자동 배포. 초보자가 서버 세팅 없이 배포 가능 |
| CI | GitHub Actions | 푸시 시 lint \+ 테스트 |
| 테스트 | pytest \+ httpx (백), Vitest \+ Playwright (프론트) | 4단계 테스트·디버깅 단계 대응 |
| 문서 | FastAPI `/docs` (Swagger UI) \+ 본 문서 | API 명세가 코드와 항상 동기화 |

## 11\.3 컨테이너 구성

```
docker-compose.yml
├── db      : postgres:16-alpine        (volume: pgdata)
├── api     : ./backend  (uvicorn)      → depends_on: db
└── web     : ./frontend (vite build → nginx)
```

## 11\.4 이 조합이 초보 친화적인 이유

1. **API 명세를 두 번 쓰지 않는다.** Pydantic 모델 하나가 검증 \+ OpenAPI 문서 \+ 프론트 타입까지 만들어냅니다
2. **관리자 화면을 만들지 않는다.** SQLAdmin이 CRUD 화면을 자동 생성하므로 S\-18에 개발 시간을 거의 쓰지 않습니다
3. **언어가 두 개뿐이다.** Python(백·알고리즘) \+ TypeScript(프론트)
4. **배포에 서버 지식이 거의 필요 없다.** Docker Compose로 로컬을 맞추고, Railway/Vercel이 나머지를 처리합니다

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
5. **동일인 중복 가입에 대비한다.** 카카오로 가입한 사람이 나중에 이메일로 또 가입할 수 있습니다. 매니저가 팀원 관리 화면에서 두 `players`를 병합할 수 있게 해두면 됩니다 (게스트 병합과 같은 메커니즘)

### 구현 순서

MVP에서는 **카카오 먼저** 만드는 편이 낫습니다. 이메일 경로는 비밀번호 정책·재설정 메일 발송·토큰 만료까지 딸려 오는데, 카카오는 그 전부를 카카오가 대신해 주기 때문입니다. 이메일/비밀번호는 카카오 계정이 없는 사용자를 위한 보조 경로로 뒤에 붙입니다.

# 12\. 다음 단계

| 단계 | 산출물 | 상태 |
| --- | --- | --- |
| 1\-A | 서비스명 확정 | **미정 — 결정 필요** |
| 1\-B | 서비스 목적·페인포인트·핵심가치·주요기능 (1장) | **확정** (기획자 정리본 반영) |
| 1\-C | 액터 및 액터별 기능 (3장) | **확정** |
| 1\-D | 기능 요구사항 FR\-01\~34 (4장) | 검토 대기 |
| 2\-A | **와이어프레임** — S\-01\~S\-19 로우파이 → S\-11·S\-12·S\-15 하이파이 | **다음 작업** |
| 2\-B | ERD 확정 → Alembic 초기 마이그레이션 | 6장 기반 |
| 2\-C | OpenAPI 명세 초안 (FastAPI 스켈레톤으로 자동 생성) | 7장 기반 |
| 2\-D | 배정 알고리즘 프로토타입 — 더미 데이터로 완전 탐색 검증 | 9\.5·9.7절 기반 |
| 3 | 애플리케이션 개발 (9.8절 순서) | 대기 |
| 4 | 테스트·디버깅 → 1단계로 피드백 반복 | 대기 |

**MVP 범위 제안**

**포함** — 인증(카카오\+이메일) · 팀/팀코드 · 게스트 등록(F13) · 온보딩 설문(F1) · 매니저 정렬(F14) · 일정/RSVP(F4) · 자동 배정 3안(F5) · 묶기 제약(F15) · 배정 설명(F6) · 수동 수정(F7) · 쿼터 기록(F8)

**후순위** — 피어 설문(F9) · 실력/선호 갱신(F10) · 개인 대시보드(F11) · 관리자 콘솔(F12, SQLAdmin으로 대체) · 사전 배치(F16) · 분리 제약 · 로테이션 자동 제안(F17)

**이유:** `F1 → F14 → F5 → F8`이 하나의 데이터 루프를 이루고, 이 루프가 돌아가야 서비스가 성립합니다. 특히 **게스트 등록(F13)은 후순위가 아닙니다** — 게스트 없이는 12\~14명이 모이지 않는 것이 이 동호회의 전제이기 때문입니다.

### 와이어프레임 작업 시 우선순위

1. **S\-12 배정 실행** — 대기 칸 \+ 팀 칸 구조, 묶기 조작, 제약 경고. 이 서비스의 가치가 집중된 화면
2. **S\-11 참석자 현황 · 게스트 등록** — 게스트 추가가 3탭 이내로 끝나야 함
3. **S\-15 쿼터 기록** — 경기 후 7\~10쿼터를 한 화면에서 연속 입력
4. 나머지는 로우파이 박스로 충분

# 13\. 설계 고민 및 다음 단계 고려사항

확정하지 않고 남겨둔 판단들입니다. 개발 중 부딪히면 여기로 돌아옵니다.

## 13\.1 아직 결정하지 못한 것

| \# | 고민 | 선택지 | 현재 기울기 |
| --- | --- | --- | --- |
| Q1 | **서비스명** | 픽앤롤 / 코트메이트 / 밸런스코트 / 신규 | 미정 |
| Q2 | **게스트에게 설문을 시킬 것인가** | ① 매니저가 등급만 지정 ② 게스트용 초간단 설문(4문항·30초) 링크 전송 | ①로 시작. 게스트에게 링크를 보내는 마찰이 실익보다 클 가능성 |
| Q3 | **실력 등급을 매니저에게도 숨길 것인가** | ① 매니저는 수치까지 열람 ② 매니저도 등급만 | ①. 매니저가 결과를 판단하려면 근거가 필요 |
| Q4 | **3팀 이상 지원 시기** | ① v1부터 ② 2팀만 먼저 | ②. 현재 운영이 2팀 고정이고, 3팀은 완전 탐색이 어려워짐 |
| Q5 | **출전 시간 균등을 배정에 반영할 것인가** | ① 쿼터 로테이션에서만 다룸 ② 팀 배정에도 "지난주에 적게 뛴 사람" 가중치 | ①. 목적함수가 복잡해지면 설명이 어려워짐 |
| Q6 | **팀 이름을 고정할 것인가** | ① 블랙/화이트 고정 ② 매니저가 매번 지정 | ①을 기본값으로 두되 수정 가능 |

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

- **배정 알고리즘:** 완전 탐색 결과를 정답 기준으로 두고, 제약이 걸린 모든 경우에 대해 "묶인 사람이 같은 팀인가"를 속성 기반 테스트(property\-based test)로 검증. `hypothesis` 라이브러리가 적합
- **제약 실현가능성 검사:** 실현 불가능한 입력을 의도적으로 만들어 넣고 **실행 전에** 차단되는지 확인. 이 검사가 빠지면 알고리즘이 조용히 제약을 어깁니다
- **마진 계산:** 쿼터 추가 → 수정 → 삭제 순서로 조작한 뒤 지표가 원래 값으로 돌아오는지 확인
- **권한:** 플레이어 토큰으로 매니저 API를 전부 호출해 403이 나오는지 자동 검사
- **실력 모델:** `backend/scripts/simulate_rating.py`를 `tests/test_rating_simulation.py`가 회귀 테스트로 유지. 잔차 모델이 원시 마진보다 못해지거나, 완벽 균형 조건에서 원시 마진 붕괴가 재현되지 않으면 실패
