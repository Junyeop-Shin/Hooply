# 온보딩 설문 기능 구현 스펙

> 기획설계서 v0.3 · 8장(설문 설계) + 6장(데이터 모델) + 7장(API) 발췌·정리
> VS Code의 Claude Code에 이 파일을 통째로 붙여넣거나, 프로젝트에 `docs/survey-spec.md`로 저장한 뒤
> "이 스펙대로 온보딩 설문 기능을 구현해줘"라고 요청하면 됩니다.

---

## 1. 기능 개요

회원가입 직후(S-03) 1회 응답하는 14문항 설문. 목적은 실력 점수를 직접 묻는 게 아니라,
**관찰 가능한 행동 문항으로 클럽 내 상대 순위(prior)를 추정**하는 것.

- 소요 시간: 2~3분 (문항당 8~12초 설계)
- 응답은 1인 1회 제출 (재제출 불가, 수정은 관리자 보정으로만)
- 문항 자체가 버전 관리됨 — 나중에 앵커 재보정(6절)이 있어서 문항/선택지를 히스토리로 남겨야 함

---

## 2. 데이터 모델

기획설계서 6.1절에는 테이블 이름만 나열되어 있어(`survey_templates`, `survey_questions`,
`survey_options`, `survey_responses`, `survey_answers`), 아래 컬럼 설계는 8장의 요구사항을
근거로 이번에 구체화한 내용입니다. 구현 전 검토하세요.

### survey_templates — 설문 버전
| 컬럼 | 타입 | 비고 |
|---|---|---|
| id | BIGSERIAL PK | |
| version | INT | 1부터 증가 |
| is_active | BOOLEAN | 활성 템플릿은 항상 1개만 |
| created_at | TIMESTAMPTZ | |

### survey_questions — 문항
| 컬럼 | 타입 | 비고 |
|---|---|---|
| id | BIGSERIAL PK | |
| template_id | FK → survey_templates.id | |
| section | VARCHAR(1) | `A`~`E` (기본/공격/수비/포지션/성향) |
| code | VARCHAR(4) | `A1`, `B2` 등 — 3절 표의 문항 코드 |
| question_text | TEXT | |
| answer_type | ENUM | `STEPPER` / `ANCHOR_4` / `MULTI_CHIP` / `ORDINAL_5` / `SINGLE_CHOICE` / `TRIO` |
| display_order | SMALLINT | |
| prior_weight | NUMERIC(4,3) NULL | 4.4절 가중치 계산에 쓰이는 항목만 값 존재 |

### survey_options — 선택지
| 컬럼 | 타입 | 비고 |
|---|---|---|
| id | BIGSERIAL PK | |
| question_id | FK → survey_questions.id | |
| option_order | SMALLINT | 앵커 문항은 순서가 곧 등급(0~3) |
| label | TEXT | |
| score_value | NUMERIC(4,2) | 초기엔 균등(0/1/2/3), 6절 재보정으로 갱신됨 |

### survey_responses — 응답 세션 (1인 1회)
| 컬럼 | 타입 | 비고 |
|---|---|---|
| id | BIGSERIAL PK | |
| player_id | FK → players.id | |
| template_id | FK → survey_templates.id | |
| submitted_at | TIMESTAMPTZ | |
| — | — | **UNIQUE (player_id)** — 재제출 방지 |

### survey_answers — 문항별 응답
| 컬럼 | 타입 | 비고 |
|---|---|---|
| id | BIGSERIAL PK | |
| response_id | FK → survey_responses.id ON DELETE CASCADE | |
| question_id | FK → survey_questions.id | |
| selected_option_ids | JSONB | 배열. 단일선택도 길이 1 배열로 통일 |
| numeric_value | NUMERIC NULL | A1(키)처럼 스테퍼 값인 경우만 사용 |
| — | — | **UNIQUE (response_id, question_id)** |

---

## 3. 척도 체계 — 답변 방식은 6종류만 허용

| answer_type | 설명 | 사용처 |
|---|---|---|
| `STEPPER` | 숫자 증감 입력 | A1(키) |
| `ANCHOR_4` | 4단계 행동 앵커 서열형, 선택지 문구 자체가 지식 게이팅 역할 | A2, A3, B3, C1, C2, E1, E2 |
| `MULTI_CHIP` | 다중선택 칩, 선택 개수 자체가 다재다능성 지표 | B1, D1 |
| `ORDINAL_5` | 5택 서열 단일선택 | B2, E3 |
| `SINGLE_CHOICE` | 단일선택 | D2 |
| `TRIO` | 항목별 3택(가능+선호/가능만/불가) 2줄 | D3 |

**금지:** 1~10 숫자 척도, "당신의 실력 점수는?" 직접 자기평가, 자유 텍스트 입력.
**5점이 아닌 4단계를 쓰는 이유:** 한국 응답자는 5점 척도에서 중앙집중편향이 강해 방향을 흐린다.

---

## 4. 전체 문항 (14문항)

### 섹션 A — 기본 (3문항)
| 코드 | 문항 | answer_type | 선택지 |
|---|---|---|---|
| A1 | 키 | STEPPER | cm |
| A2 | 농구를 해온 기간 | ANCHOR_4 | 1년 미만 / 1~3년 / 3~7년 / 7년 이상 |
| A3 | 경험한 가장 높은 경기 수준 | ANCHOR_4 | 체육시간·친구들끼리 / 동호회·아마추어 / 학교 대표·클럽팀 / 선수 출신 |

### 섹션 B — 공격 (3문항)
| 코드 | 문항 | answer_type | 선택지 |
|---|---|---|---|
| B1 | 실제 경기에서 자주 쓰는 공격 옵션을 모두 고르세요 | MULTI_CHIP (8개) | 캐치앤슛 3점 / 풀업·미들 점퍼 / 드라이브 후 마무리 / 픽앤롤 핸들러 / 픽앤롤 롤·팝 / 포스트업 / 오프볼 컷인 / 공격 리바운드 풋백 |
| B2 | 경기에서 안정적으로 넣을 수 있는 최대 거리 | ORDINAL_5 | 골밑 레이업 < 페인트존 훅·플로터 < 자유투 라인 < 3점 라인 < 3점 라인 밖 |
| B3 | 볼 운반과 돌파 | ANCHOR_4 | 드리블 돌파를 시도하지 않음 / 가벼운 압박은 벗겨냄 / 하프코트 압박에서도 볼을 운반함 / 풀코트 압박에서도 안정적으로 가져감 |

### 섹션 C — 수비 (2문항)
| 코드 | 문항 | answer_type | 선택지(4단계) |
|---|---|---|---|
| C1 | 상대가 스크린을 걸었을 때 | ANCHOR_4 | ① 스크린이 뭔지 잘 모르거나 그냥 따라간다 ② 피해서 따라가려 하지만 자주 놓친다 ③ 스위치를 부르고 바꿔 막는다 ④ 상황에 따라 스위치·헤지·언더를 구분해서 쓴다 |
| C2 | 동료 매치업이 뚫렸을 때 | ANCHOR_4 | ① 내 사람만 본다 ② 헬프는 가지만 이후 내 자리로 못 돌아온다 ③ 헬프 후 내 매치업으로 복귀한다 ④ 헬프 사이드까지 읽고 미리 로테이션을 돈다 |

### 섹션 D — 포지션 (3문항)
| 코드 | 문항 | answer_type | 선택지 |
|---|---|---|---|
| D1 | 수행 가능한 포지션 | MULTI_CHIP (5개) | PG / SG / SF / PF / C |
| D2 | 가장 선호하는 포지션 | SINGLE_CHOICE | PG / SG / SF / PF / C |
| D3 | 희소 자원 확인 (2줄) | TRIO ×2 | "1번(볼 운반)을 맡을 수 있나요" / "5번(골밑)을 맡을 수 있나요" — 각각: 가능하고 선호함 / 가능하지만 선호하지 않음 / 불가 |

> D3는 D1과 분리한다. 다중선택 안에 섞으면 무심코 전부 체크하는 경향이 있어 별도 문항으로 응답 비용을 만들어야 한다.

### 섹션 E — 성향·상대평가 (3문항)
| 코드 | 문항 | answer_type | 선택지 |
|---|---|---|---|
| E1 | 플레이 성향 | ANCHOR_4 (양극) | 온볼(내가 만들어감) ↔ 오프볼(움직여서 받음) |
| E2 | 체력 | ANCHOR_4 | 1쿼터도 벅참 / 2쿼터 / 3~4쿼터 / 계속 뛰어도 페이스 유지 |
| E3 | 이 동호회에서 본인의 실력 위치 | ORDINAL_5 | 상위 10% / 상위 30% / 중간 / 하위 30% / 하위 10% |

> **E3가 단일 최고 정보량 문항.** 절대 점수보다 상대 위치 판단이 더 정확하고, 겸손 편향이 있어도 모두가 같은 방향으로 편향되므로 순위는 보존된다. UI에서 이 문항이 누락되지 않도록 주의.

---

## 5. 응답 → 사전 실력값(prior) 변환 로직

설문 제출 시 서버에서 즉시 계산해 `player_profiles.prior_overall`에 저장.
**절대값은 의미 없고 클럽(팀) 내 z-score 상대 위치만 사용.**

```
prior_z = 0.30 × z(E3 자기 백분위)
        + 0.20 × z(A2 구력, A3 경기 수준)
        + 0.20 × z(B2 슛 거리, B1 옵션 개수)
        + 0.15 × z(B3 볼 운반)
        + 0.15 × z(C1, C2 수비 이해도)
```

z-score는 **같은 팀(team_id) 내 응답자들 사이에서만** 계산한다 (전체 서비스 기준 아님).
신규 팀이라 표본이 너무 적으면(예: 5명 미만) 클럽 평균 0으로 시작하고 표본이 쌓이는 대로 재계산.

세부 축(표시·포지션 매칭용, `player_profiles`의 6축 컬럼에 매핑):
```
슛      ← B2, B1(캐치앤슛·풀업)
볼핸들링 ← B3, B1(픽앤롤 핸들러)
패스     ← B1(픽앤롤 핸들러·롤팝 조합), E1
수비     ← C1, C2
골밑     ← A1(키), B1(포스트업·롤·풋백), D3
체력     ← E2
```

`player_profiles.prior_source = 'SURVEY'`로 기록. 이후 매니저 정렬이 생기면
`prior_final_z = 0.5 × prior_survey_z + 0.5 × manager_rank_z`로 재계산 (별도 기능, F14 — 이번 스코프 아님).

---

## 6. 앵커 재보정 (선택 — 나중 스코프)

4단계 앵커의 배점은 초기엔 균등(0/1/2/3)으로 둔다. 이건 `survey_options.score_value`
필드로 이미 구조가 있으므로, 지금 구현 범위에서는 **하드코딩 값을 그대로 쓰고
재보정 배치 로직은 만들지 않아도 된다.** (분기 1회 배치로 나중에 추가)

---

## 7. API 명세

| Method | Path | 설명 | 응답 |
|---|---|---|---|
| GET | `/surveys/onboarding` | 활성 설문(`is_active=true`) 문항·선택지 전체 조회 | `200 SurveyTemplate { template_id, questions: [{ id, section, code, question_text, answer_type, options: [...] }] }` |
| POST | `/surveys/onboarding/responses` | 응답 제출 → prior 계산 → 프로필 생성 | `201 PlayerProfile` · `409 ALREADY_SUBMITTED` (survey_responses UNIQUE 위반 시) |
| GET | `/me/profile` | 제출 후 내 프로필 조회 (확인용) | `200 PlayerCard` |

**POST body 예시**
```json
{
  "answers": [
    { "question_id": 1, "numeric_value": 178 },
    { "question_id": 2, "selected_option_ids": [3] },
    { "question_id": 6, "selected_option_ids": [1, 4, 7] }
  ]
}
```
MULTI_CHIP은 배열 길이 ≥1, 그 외 타입은 길이 1로 검증. `numeric_value`와
`selected_option_ids`는 문항의 `answer_type`에 따라 둘 중 하나만 채워야 함(둘 다 비면 400).

---

## 8. 화면 요구사항 (S-03)

- 진행률 바 (14문항 기준 몇 번째인지)
- 문항 카드 1개씩 표시, **이전/다음** 버튼으로 이동
- 필수 응답 — 다음 버튼은 현재 문항 응답 전까지 비활성
- 마지막 문항 다음은 [제출하기]로 텍스트 변경
- 제출 즉시 서버가 prior 계산 → 성공 시 홈(S-04) 또는 팀 가입 흐름으로 이동
- 이미 제출한 사용자가 이 화면에 재진입하면 즉시 리다이렉트 (재응답 UI 자체를 노출하지 않음)

---

## 9. 구현 순서 제안

1. `survey_templates` / `survey_questions` / `survey_options` 시드 데이터 — 위 4절 표 그대로 마이그레이션 시드로 넣기 (문항·선택지는 코드가 아니라 데이터라서 하드코딩보다 시드가 맞음)
2. `GET /surveys/onboarding` — 시드 데이터 조회 API
3. `survey_responses` / `survey_answers` 저장 + UNIQUE 제약으로 재제출 차단
4. prior 계산 로직 (5절 공식) — 별도 함수/서비스로 분리해두면 나중에 매니저 정렬과 합칠 때 재사용 가능
5. S-03 화면 연동
6. (스코프 아님, 메모만) 6절 앵커 재보정, 8.5절 매니저 정렬과의 결합
