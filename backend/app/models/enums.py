"""6장 ERD의 VARCHAR 열거값. DB에는 VARCHAR + CHECK 제약으로 저장한다 (native enum 미사용).

설계서 6.2절의 각 테이블은 상태·종류 컬럼을 `VARCHAR(n)` 에 허용값 목록으로 정의한다. PostgreSQL
native ENUM 타입을 쓰지 않는 이유는, 값을 하나 추가할 때마다 `ALTER TYPE ... ADD VALUE` 가 필요하고
트랜잭션 안에서 다루기 까다롭기 때문이다. VARCHAR + CHECK 면 Alembic 마이그레이션에서 CHECK 제약만
갈아 끼우면 된다.

파이썬 쪽은 `StrEnum` 을 쓰므로 `Position.PG == "PG"` 가 성립하고, JSON 직렬화 시 그대로 문자열이
된다. **모든 멤버는 이름과 값을 동일하게 유지해야 한다.** SQLAlchemy `Enum` 은 기본적으로 멤버의
*이름* 을 DB에 저장하므로, 이름 ≠ 값이면 설계서의 허용값 표와 DB 내용이 어긋난다.

각 enum 이 어느 테이블·컬럼에 쓰이는지는 멤버 옆 주석과 해당 모델 파일을 참조한다.
"""

import re
from enum import StrEnum

from sqlalchemy import Enum as SAEnum


def enum_type_name(enum_cls: type[StrEnum]) -> str:
    """StrEnum 클래스 → PostgreSQL 타입 이름. `TeamStatus` → `team_status_enum` (0017 마이그레이션의 ENUMS 키와 같다)."""
    snake = re.sub(r"(?<!^)(?=[A-Z0-9])", "_", enum_cls.__name__).lower()
    return snake.replace("_1_0", "10").replace("_3_0", "30") + "_enum"


def db_enum(enum_cls: type[StrEnum], length: int) -> SAEnum:
    """PostgreSQL ENUM 타입 컬럼 (0017 마이그레이션부터). 타입은 마이그레이션이 만들고, ORM 은 이름으로만 참조한다.

    - native_enum=True    : VARCHAR + CHECK 가 아니라 전용 ENUM 타입. 스키마만 봐도 열거형임이 드러난다
    - create_type=False   : metadata.create_all 이 타입을 만들려 하지 않는다 — 생성·변경은 Alembic 만 한다
    - validate_strings    : 문자열을 직접 바인딩해도 허용값이 아니면 파이썬 단계에서 거부
    값을 추가할 때는 이 클래스와 마이그레이션(`ALTER TYPE ... ADD VALUE`, 트랜잭션 밖)을 함께 바꾼다.
    `length` 는 예전 VARCHAR 길이 — 되돌리기(downgrade) 문서용으로만 남긴다.
    """
    return SAEnum(
        enum_cls,
        native_enum=True,
        create_type=False,
        validate_strings=True,
        name=enum_type_name(enum_cls),
        length=length,
    )


class ApprovalStatus(StrEnum):
    """teams.approval_status — 관리자 승인 (팀 생성 → 관리자 콘솔에서 승인 → 5명 이상이면 ACTIVE)."""

    PENDING = "PENDING"  # 승인 대기. 가입은 되지만 일정 기능이 잠긴다
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"  # 거절. 팀은 남지만 활성화되지 않는다


class ClaimStatus(StrEnum):
    """guest_claims.status — 회원의 게스트 기록 확인 결과."""

    CONFIRMED = "CONFIRMED"  # 내 기록이 맞다 → 병합됨
    DECLINED = "DECLINED"  # 내가 아니다 → 다시 묻지 않는다


class GlobalRole(StrEnum):
    """users.global_role — 전역 권한 (3.1절). 팀 단위 권한은 TeamRole 이 따로 담당한다."""

    ADMIN = "ADMIN"  # 관리자 콘솔(S-18) 접근, 지표 수동 보정 가능. 시스템에서 직접 지정
    USER = "USER"  # 일반 사용자. 팀 안에서의 역할은 players.role 로 결정 (기본값)


class AuthProvider(StrEnum):
    """auth_identities.provider — 로그인 수단 (11.5절)."""

    LOCAL = "LOCAL"  # 이메일 + 비밀번호(bcrypt 해시). provider_uid 에는 email 저장
    KAKAO = "KAKAO"  # 카카오 OAuth. provider_uid 에는 카카오 회원번호 저장


class TeamStatus(StrEnum):
    """teams.status — 팀 활성 상태 (FR-06)."""

    PENDING = "PENDING"  # 생성 직후. 회원이 min_members(기본 5명) 미만이라 일정 기능이 잠김
    ACTIVE = "ACTIVE"  # 회원 5명 이상. 일정 등록·배정 가능
    ARCHIVED = "ARCHIVED"  # 관리자가 강제 비활성화했거나 팀이 해산. 다시 ACTIVE 로 돌리지 않음


class PlayerKind(StrEnum):
    """players.kind — 참가자 종류. `(kind = 'GUEST') = (user_id IS NULL)` CHECK 와 짝을 이룬다."""

    MEMBER = "MEMBER"  # 계정이 있는 회원. user_id NOT NULL. 로그인·설문·투표 주체
    GUEST = "GUEST"  # 계정 없는 게스트(F13). user_id NULL. 기록·배정·투표의 *대상* 만 됨


class TeamRole(StrEnum):
    """players.role — 팀 단위 권한 (3.1절). 같은 사람이 팀마다 다른 역할일 수 있다."""

    MANAGER = "MANAGER"  # 일정·게스트·배정·기록 관리. 팀 생성자에게 자동 부여, 위임 가능
    PLAYER = "PLAYER"  # 일반 팀원. 게스트는 항상 이 값 (서비스 계층에서 고정)


class PlayerStatus(StrEnum):
    """players.status — 팀 소속 상태."""

    ACTIVE = "ACTIVE"  # 현재 소속. 회원 수 집계·배정 대상은 이 상태만
    LEFT = "LEFT"  # 스스로 탈퇴, 또는 게스트→회원 병합으로 비활성화 (merged_into_player_id 참조)
    REMOVED = "REMOVED"  # 매니저가 제외(DELETE /teams/{id}/players/{id}). 행은 soft 로 남김


class Position(StrEnum):
    """농구 포지션 번호 1~5. player_positions / assignment_slots / quarter_lineups 에서 사용."""

    PG = "PG"  # 1번 포인트가드(볼 운반·핸들러). 배정 하드 제약: 팀당 1명 이상 확보
    SG = "SG"  # 2번 슈팅가드
    SF = "SF"  # 3번 스몰포워드
    PF = "PF"  # 4번 파워포워드(빅맨)
    C = "C"  # 5번 센터(골밑·빅맨). 배정 하드 제약: 팀당 1명 이상 확보


class PriorSource(StrEnum):
    """player_profiles.prior_source — 사전 실력값(prior_overall)의 출처 (8.4~8.5절)."""

    SURVEY = "SURVEY"  # 온보딩 설문 응답을 z-score 가중합한 값 (매니저 정렬 결합 포함)
    MANAGER = "MANAGER"  # 게스트 등록 시 매니저가 지정한 등급(1~5)을 분위수로 환산한 값
    DEFAULT = "DEFAULT"  # 아무 정보도 없어 클럽 평균값을 넣은 상태. skill_confidence 0


class SelfRankLevel(StrEnum):
    """player_profiles.self_rank_level — "이 동호회에서 본인의 실력 위치" (구 설문 E3).

    팀 가입 **후** 팀별로 묻는다 (팀을 알아야 상대 위치를 답할 수 있으므로). prior 계산에서
    가중치 0.30 의 self_rank 성분이 된다.
    """

    TOP10 = "TOP10"  # 상위 10%
    TOP30 = "TOP30"  # 상위 30%
    MID = "MID"  # 중간
    BOT30 = "BOT30"  # 하위 30%
    BOT10 = "BOT10"  # 하위 10%


class RatingSource(StrEnum):
    """skill_rating_history.source — 실력 지표가 바뀐 원인."""

    SURVEY = "SURVEY"  # 온보딩 설문 제출로 초기값 생성
    MANAGER_SORT = "MANAGER_SORT"  # 매니저 실력 정렬(F14) 반영
    RESIDUAL = "RESIDUAL"  # 쿼터 저장 시 기대 마진 대비 잔차로 Elo 갱신 (9.2절)
    PEER_VOTE = "PEER_VOTE"  # 경기 후 피어 투표 반영 (가중치 상한 0.3)
    MANAGER_ADJUST = "MANAGER_ADJUST"  # 매니저가 신규 선수 초기값을 1회 보정
    ADMIN_ADJUST = "ADMIN_ADJUST"  # 관리자 콘솔에서 수동 보정 (audit_logs 에도 기록)
    MERGE = "MERGE"  # 게스트→회원 병합으로 기록이 합산되며 값이 바뀜


class AnswerType(StrEnum):
    """survey_questions.answer_type — 설문 척도 종류 (8.2절, 설문 설계). 프론트 위젯 선택 기준.

    이 6종 외의 척도(1~10 숫자, 직접 자기평가, 자유 텍스트)는 설계상 금지다.
    """

    STEPPER = "STEPPER"  # 숫자 증감 입력 (A1 키). option 없이 numeric_value 로 응답
    ANCHOR_4 = "ANCHOR_4"  # 4단계 행동 앵커 서열형 (A2, A3, B3, C1, C2, E1, E2). 문구 자체가 지식 게이팅
    MULTI_CHIP = "MULTI_CHIP"  # 다중선택 칩 (B1 공격 옵션, D1 가능 포지션). 선택 개수가 다재다능성 지표
    ORDINAL_5 = "ORDINAL_5"  # 5택 서열 단일선택 (B2 슛 거리, E3 자기 백분위)
    SINGLE_CHOICE = "SINGLE_CHOICE"  # 단일선택 (D2 선호 포지션)
    TRIO = "TRIO"  # 항목별 3택 — 가능+선호 / 가능만 / 불가 (D3A 1번, D3B 5번)


class EventStatus(StrEnum):
    """events.status — 일정 생명주기."""

    OPEN = "OPEN"  # 등록됨. 참석 응답(RSVP) 받는 중
    CLOSED = "CLOSED"  # 응답 마감. 배정·기록 입력 단계
    DONE = "DONE"  # 경기 종료. 쿼터 기록 완료, 피어 설문 진행
    CANCELED = "CANCELED"  # 취소. 배정·기록 불가


class AttendanceStatus(StrEnum):
    """event_attendances.status — 참석 응답."""

    ATTEND = "ATTEND"  # 참석. 배정 대상 (팀 수 × 5 이상이어야 배정 실행 가능)
    ABSENT = "ABSENT"  # 불참
    PENDING = "PENDING"  # 미응답 (기본값). 홈 화면에 미응답 배지로 표시


class ConstraintType(StrEnum):
    """assignment_constraints.type — 회차별 배정 제약 (9.6절)."""

    LOCK = "LOCK"  # 같은 group_no 끼리 반드시 같은 팀 (슈퍼노드로 축약). 1순위 기능
    SEPARATE = "SEPARATE"  # 같은 group_no 끼리 반드시 다른 팀. 2순위
    PIN = "PIN"  # squad_no 로 지정한 팀에 사전 배치 (F16). 2순위


class Strategy(StrEnum):
    """assignment_candidates.strategy — 후보안 3종 (9.5절 가중치 표). POSITION 은 의도적으로 없음."""

    SKILL = "SKILL"  # 실력 우선: w_skill 0.70
    CHEMISTRY = "CHEMISTRY"  # 친화도 우선: w_pref 0.40 (선호 조합 중심)
    BALANCED = "BALANCED"  # 종합: w_skill 0.45 / w_position 0.25


class Side(StrEnum):
    """quarter_lineups.side — 그 쿼터에 어느 팀으로 뛰었는가. 기본 팀명이 블랙/화이트다 (Q6)."""

    BLACK = "BLACK"  # quarters.black_score 쪽 팀 (squad_no 1)
    WHITE = "WHITE"  # quarters.white_score 쪽 팀 (squad_no 2)


class VoteType(StrEnum):
    """post_game_votes.vote_type — 경기 후 피어 설문 항목 (F9)."""

    BEST_PERFORMER = "BEST_PERFORMER"  # "오늘 잘한 사람" — 표시 전용. 실력 산출에는 절대 입력하지 않는다 (피어 투표 설계)
    PLAY_AGAIN = "PLAY_AGAIN"  # "다음에 같이 뛰고 싶은 사람" — 선호 조합(pref_score)의 원천


class ReasonTag(StrEnum):
    """post_game_votes.reason_tag — "또 뛰고 싶은 사람" 을 고른 이유 (피어 투표 설계). PLAY_AGAIN 에만, 선택 사항."""

    PASS = "PASS"  # 패스가 좋았어요
    DEFENSE_HELP = "DEFENSE_HELP"  # 수비를 잘 도와줬어요
    TEMPO = "TEMPO"  # 템포가 잘 맞았어요
    OTHER = "OTHER"  # 기타


class TargetSide(StrEnum):
    """post_game_votes.target_side — 지목 대상이 응답자와 같은 팀이었는지 (확정 배정으로 서버가 계산, 없으면 NULL)."""

    SAME_TEAM = "SAME_TEAM"  # 같은 팀에서 고른 사람
    OPPONENT = "OPPONENT"  # 상대 팀에서 고른 사람
