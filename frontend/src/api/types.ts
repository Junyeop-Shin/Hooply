/**
 * 백엔드 응답 타입 (설계서 7.2절 공통 스키마 + 7.3절 응답).
 * 나중에 openapi-typescript 로 자동 생성할 예정이며, 지금은 필요한 것만 손으로 옮겼다.
 */

export type Position = 'PG' | 'SG' | 'SF' | 'PF' | 'C'
export const POSITIONS: Position[] = ['PG', 'SG', 'SF', 'PF', 'C']
export type TeamRole = 'MANAGER' | 'PLAYER'
export type TeamStatus = 'PENDING' | 'ACTIVE' | 'ARCHIVED'
export type ApprovalStatus = 'PENDING' | 'APPROVED' | 'REJECTED'
export type SkillGrade = 'A' | 'B' | 'C' | 'D' | 'E'
export type AttendanceStatus = 'ATTEND' | 'ABSENT' | 'PENDING'
export type EventStatus = 'OPEN' | 'CLOSED' | 'DONE' | 'CANCELED'
/** 팀 가입 후 묻는 "이 동호회에서 내 실력 위치" (구 설문 E3) */
export type SelfRankLevel = 'TOP10' | 'TOP30' | 'MID' | 'BOT30' | 'BOT10'
export const SELF_RANK_LABEL: Record<SelfRankLevel, string> = { TOP10: '상위 10%', TOP30: '상위 30%', MID: '중간', BOT30: '하위 30%', BOT10: '하위 10%' }

/** 7.4절 공통 오류 본문 */
export interface ErrorResponse {
  code: string
  message: string
  details: { field?: string | null; reason: string }[]
}

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface UserDetail {
  id: number
  email: string | null
  name: string
  nickname: string | null
  profile_image_url: string | null
  height_cm: number | null
  global_role: 'ADMIN' | 'USER'
  onboarding_completed: boolean
  primary_team_id: number | null
  identities: { provider: 'LOCAL' | 'KAKAO' }[]
  /** 시작 안내: PENDING(팝업) · ACTIVE(체크리스트) · CLOSED · DONE · DECLINED(아무 안내 없음) */
  tutorial_state: TutorialState
  tutorial_path: TutorialPath | null
  tutorial_tips_seen: string[]
}

// --- 시작 안내 (튜토리얼) ---
export type TutorialState = 'PENDING' | 'ACTIVE' | 'CLOSED' | 'DONE' | 'DECLINED'
export type TutorialPath = 'PLAYER' | 'MANAGER'
export interface TutorialStep {
  key: string
  title: string
  /** WAITING = 다른 사람의 행동이 먼저 필요해 아직 할 수 없음 */
  status: 'DONE' | 'TODO' | 'WAITING'
  hint: string
  link: string | null
  action: string | null
}
export interface TutorialView { state: TutorialState; path: TutorialPath | null; tips_seen: string[]; steps: TutorialStep[]; all_done: boolean }
export interface TutorialUpdate { state?: 'ACTIVE' | 'CLOSED' | 'DONE' | 'DECLINED'; path?: TutorialPath; tip_seen?: string }

export interface UserSummary {
  id: number
  name: string
  nickname: string | null
  profile_image_url: string | null
}

export interface TeamMembershipView {
  team_id: number
  team_name: string
  team_code: string
  team_status: TeamStatus
  approval_status: ApprovalStatus
  player_id: number
  role: TeamRole
  member_count: number
}

export interface TeamDetail {
  id: number
  name: string
  description: string | null
  team_code: string
  status: TeamStatus
  approval_status: ApprovalStatus
  min_members: number
  home_court: string | null
  owner: UserSummary
  member_count: number
  my_role: TeamRole | null
  my_player_id: number | null
  created_at: string
}

/** 플레이어에게 내려가는 카드 — 실력은 등급만 (FR-28) */
export interface PlayerCard {
  id: number
  user_id: number | null
  kind: 'MEMBER' | 'GUEST'
  display_name: string
  role: TeamRole
  profile_image_url: string | null
  height_cm: number | null
  skill_grade: SkillGrade | null
  primary_position: Position | null
  playable_positions: Position[]
  attendance_rate: number | null
  skill_confidence: string | null
}

/** MANAGER / ADMIN 에게만 내려가는 카드 — 수치 포함 */
export interface PlayerCardDetailed extends PlayerCard {
  skill_overall: string | null
  prior_overall: string | null
  skill_axes: Record<string, string | null>
  avg_margin: string | null
  quarters_played: number
  attended_events: number
}

// --- 온보딩 설문 (survey-feature-spec) ---

export type AnswerType = 'STEPPER' | 'ANCHOR_4' | 'MULTI_CHIP' | 'ORDINAL_5' | 'SINGLE_CHOICE' | 'TRIO'

export interface SurveyOption {
  id: number
  code: string
  option_order: number
  label: string
}

export interface SurveyQuestion {
  id: number
  section: string
  code: string
  question_text: string
  answer_type: AnswerType
  display_order: number
  help_text: string | null
  group_label: string | null
  options: SurveyOption[]
}

export interface SurveyTemplate {
  template_id: number
  version: number
  name: string
  questions: SurveyQuestion[]
}

export interface SurveyAnswerIn {
  question_id: number
  selected_option_ids?: number[]
  numeric_value?: number
}

export interface TeamProfileSummary {
  team_id: number
  team_name: string
  player_id: number
  skill_grade: SkillGrade | null
  prior_source: string | null
  skill_confidence: string | null
  self_rank_level: SelfRankLevel | null
  survey_sample_size: number
  quarters_played: number
}

export interface MyProfile {
  onboarding_completed: boolean
  survey_submitted_at: string | null
  height_cm: number | null
  primary_position: Position | null
  playable_positions: Position[]
  teams: TeamProfileSummary[]
}

// --- 일정 · 참석 · 게스트 ---

export interface EventView {
  id: number
  team_id: number
  title: string | null
  event_date: string
  start_time: string | null
  end_time: string | null
  venue: string | null
  rsvp_deadline: string | null
  status: EventStatus
  memo: string | null
  attend_count: number
  my_attendance: AttendanceStatus | null
  rsvp_open: boolean
  my_role: TeamRole | null
  adopted_candidate_id: number | null
  run_count: number
  my_squad_name: string | null
  my_assigned_position: string | null
  quarter_count: number
  /** 피어 투표 (peer-vote-spec) — 종료 시각이 지나면 열림. 응답 현황은 매니저 카드용 */
  survey_open: boolean
  my_survey_submitted: boolean
  survey_responded: number
  survey_total: number
}

export interface EventCreateInput {
  title?: string
  event_date: string
  start_time?: string
  end_time?: string
  venue?: string
  rsvp_deadline?: string
  memo?: string
}

export interface AttendanceView {
  player: PlayerCard
  status: AttendanceStatus
  note: string | null
  responded_at: string | null
  registered_by: number | null
  registered_by_name: string | null
  team_lock_request_player_id: number | null
  team_lock_request_player_name: string | null
  can_edit: boolean
}

export interface AttendanceSummary {
  attend: number
  absent: number
  pending: number
  guest_count: number
  position_counts: Record<Position, number>
  handler_count: number
  bigman_count: number
  warnings: string[]
}

export interface AttendanceList {
  items: AttendanceView[]
  summary: AttendanceSummary
  my_player_id: number | null
}

export interface EventGuestInput {
  display_name: string
  skill_grade?: number | null
  height_cm?: number | null
  preferred_position?: Position | null
  playable_positions?: Position[]
  team_lock_request?: boolean
  existing_player_id?: number
  force_new?: boolean
}

export interface EventGuestUpdate {
  display_name?: string
  skill_grade?: number | null
  height_cm?: number | null
  preferred_position?: Position | null
  playable_positions?: Position[]
  team_lock_request?: boolean
  status?: AttendanceStatus
}

export interface GuestPreset {
  id: number
  display_name: string
  skill_grade: number | null
  height_cm: number | null
  preferred_position: Position | null
  playable_positions: Position[]
  team_lock_request: boolean
  existing_player_id: number | null
  use_count: number
  last_used_at: string
}

export interface GuestSimilar {
  similar: PlayerCard[]
}

export interface LockSuggestion {
  guest: PlayerCard
  target: PlayerCard
  requested_by_user_id: number | null
}

export interface MergeCandidate {
  guest: PlayerCard
  member: PlayerCard
}

export interface Page<T> {
  items: T[]
  meta: { page: number; size: number; total: number; has_next: boolean }
}

// --- 매니저 실력 정렬 (F14) ---

export interface RankingView {
  id: number
  ranked_at: string
  ranked_by: number
  is_active: boolean
  entries: { rank_no: number; player: PlayerCard }[]
}

// --- 팀 배정 (F5 · F15) ---

export type Strategy = 'SKILL' | 'CHEMISTRY' | 'BALANCED'

export interface ConstraintSet {
  lock_groups: number[][]
  separate_groups: number[][]
  pins: { player_id: number; squad_no: number }[]
}

export interface AssignmentRunRequest {
  team_count: number
  strategies: Strategy[]
  constraints: ConstraintSet
}

export interface ValidateResult {
  feasible: boolean
  violations: { code: string; message: string; player_ids: number[]; group_no: number | null }[]
  warnings: string[]
}

export interface SquadView {
  squad_no: number
  squad_name: string
  avg_skill: string | null
  members: PlayerCard[]
  assigned_positions: Record<number, Position | null>
  manual_override_ids: number[]
  avg_height_cm: number | null
}

export interface CandidateView {
  id: number
  strategy: Strategy
  total_score: string | null
  metrics: Record<string, any>
  explanation: string | null
  is_adopted: boolean
  squads: SquadView[]
}

export interface AssignmentRunView {
  id: number
  event_id: number
  team_count: number
  created_at: string
  constraints: ConstraintSet
  candidates: CandidateView[]
  warnings: string[]
}

export interface AdoptedAssignment {
  run_id: number
  candidate_id: number
  strategy: Strategy
  squads: SquadView[]
  explanation: string | null
  my_squad_no: number | null
  my_player_id: number | null
  my_assigned_position: string | null
  adopted_at: string | null
  skill_spread: number | null
  total_score: number | null
}

// --- 경기 기록 (F8) ---

export type Side = 'BLACK' | 'WHITE'

export interface LineupIn {
  player_id: number
  side: Side
  position?: Position | null
}

export interface QuarterIn {
  quarter_no: number
  black_score: number
  white_score: number
  duration_min: number
  lineups: LineupIn[]
}

export interface LineupView {
  player_id: number
  display_name: string
  side: Side
  position: Position | null
  raw_margin: number
  normalized_margin: string
}

export interface QuarterView {
  id: number
  quarter_no: number
  black_score: number
  white_score: number
  duration_min: number
  lineups: LineupView[]
}

export interface QuarterSummary {
  quarter_count: number
  black_total: number
  white_total: number
  black_wins: number
  white_wins: number
  per_player: { player_id: number; display_name: string; side: Side; quarters: number }[]
}

export interface QuarterListView {
  items: QuarterView[]
  summary: QuarterSummary
}

export interface QuarterBulkResult {
  created: number
  updated: number
  deleted: number
}

// --- 피어 투표 (F9 · F10 · F11, peer-vote-spec) ---

export type VoteType = 'PLAY_AGAIN' | 'BEST_PERFORMER'
export type ReasonTag = 'PASS' | 'DEFENSE_HELP' | 'TEMPO' | 'OTHER'
export const REASON_TAGS: { tag: ReasonTag; label: string; opponent: string }[] = [
  { tag: 'PASS', label: '패스가 좋았어요', opponent: '패스가 인상적이었어요' },
  { tag: 'DEFENSE_HELP', label: '수비를 잘 도와줬어요', opponent: '수비가 끈질겨요' },
  { tag: 'TEMPO', label: '템포가 잘 맞았어요', opponent: '같이 하고 싶어요' },
  { tag: 'OTHER', label: '기타', opponent: '기타' },
]
/** 이유 칩 문구 — 상대 팀이었던 사람에게는 "같이 뛰어 보고 싶다"는 맥락으로 바꿔 쓴다 */
export const reasonLabel = (tag: ReasonTag, isSameTeam: boolean | null) => {
  const r = REASON_TAGS.find((x) => x.tag === tag)
  return r ? (isSameTeam === false ? r.opponent : r.label) : tag
}

export interface VoteCandidate {
  player: PlayerCard
  squad_no: number | null
  squad_name: string | null
  is_same_team: boolean | null
}
export interface VoteView {
  target_player_id: number
  vote_type: VoteType
  reason_tag: ReasonTag | null
}
export interface VoteTargets {
  open: boolean
  opens_at: string
  already_submitted: boolean
  my_votes: VoteView[]
  candidates: VoteCandidate[]
}
export interface VoteIn {
  target_player_id: number
  vote_type: VoteType
  reason_tag?: ReasonTag | null
}
export interface ShareMessage {
  text: string
  link: string
  responded: number
  total: number
  open: boolean
  opens_at: string
}
export interface CompatiblePlayer {
  player: PlayerCard
  mutual_play_again: boolean
  voted_me_best: number
  i_voted_best: number
  together_quarters: number
}

// --- 선수 통계 (GET /players/{id}/stats) ---
export interface MarginPoint {
  event_id: number
  event_date: string
  title: string | null
  quarters: number
  avg_normalized_margin: string
  wins: number
  losses: number
}
export interface QuarterRecord {
  event_id: number
  event_date: string
  quarter_no: number
  side: 'BLACK' | 'WHITE'
  my_score: number
  their_score: number
  black_score: number
  white_score: number
  raw_margin: number
  normalized_margin: string
  position: string | null
}
export interface RatingChange {
  source: string
  before_value: string | null
  after_value: string | null
  delta: string | null
  reason: string | null
  created_at: string
}
export interface PlayerStats {
  player: PlayerCard
  events_attended: number
  quarters_played: number
  position_distribution: Record<string, number>
  margin_trend: MarginPoint[]
  recent_quarters: QuarterRecord[]
  // 매니저/ADMIN 에게만
  skill_grade: SkillGrade | null
  skill_overall: string | null
  prior_overall: string | null
  prior_source: string | null
  skill_confidence: string | null
  cumulative_residual: string | null
  skill_axes: Record<string, string | null>
  /** 축별 팀 내 상대 위치. level 이 null 이면 비교 인원 부족 */
  skill_axes_rank: Record<string, { level: 'HIGH' | 'MID' | 'LOW' | null; percentile: number | null; sample: number }>
  manager_rank: { rank_no: number; total: number; ranked_at: string } | null
  play_again_received: number | null
  play_again_mutual: number | null
  history: RatingChange[]
}

// --- 팀 리더보드 ---
// --- 기록 탭: 월간 코트 마진 · 배지 ---
export interface MonthlyMarginEntry {
  rank: number | null
  player: PlayerCard
  avg_margin: string
  total_margin: string
  quarters: number
  wins: number
  eligible: boolean
}
export interface MonthlyMarginView {
  period: string
  total_quarters: number
  threshold_quarters: number
  min_share: number
  items: MonthlyMarginEntry[]
}
export type BadgeGroup = 'START' | 'ACTIVITY' | 'RELATION'
export type BadgeTier = 'BRONZE' | 'SILVER' | 'GOLD'
export interface BadgeView {
  code: string
  group: BadgeGroup
  title: string
  description: string
  threshold: number
  /** 묶음 키 (QUARTERS / ATTEND / VOTES / PLAY_AGAIN). 단일 배지는 null */
  series: string | null
  tier: BadgeTier | null
  progress: number
  earned_at: string | null
}

export type LeaderboardMetric = 'attendance' | 'quarters' | 'residual'
export interface LeaderboardEntry {
  rank: number
  player: PlayerCard
  value: string
  detail: string
}

/** 오늘 날짜 YYYY-MM-DD (기기 로컬 기준). toISOString 은 UTC 라 새벽에는 하루 전 날짜가 나오므로 쓰지 않는다 */
export const localISODate = (d: Date = new Date()) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

// --- 게스트 기록 본인 확인 (GET /me/guest-claims, POST /players/{id}:claim) ---
export interface GuestClaimView {
  guest: PlayerCard
  team_id: number
  team_name: string
  member_player_id: number
  events_attended: number
  quarters_played: number
  last_event_date: string | null
}

// --- 전술 (docs/07 F20 · F21) ---

export type Defense = 'man' | 'zone' | 'any'
export type TacticRole = 'ball_handler' | 'screener_roll' | 'screener_pop' | 'shooter' | 'cutter' | 'post' | 'spacer'
export type PlayActionType = 'move' | 'dribble' | 'pass' | 'screen' | 'cut' | 'handoff' | 'shot'

/** 코트 좌표 0~1. x 왼쪽→오른쪽, y 베이스라인→하프라인 */
export interface CourtPoint { x: number; y: number }

export interface PlayAction {
  type: PlayActionType
  slot: number
  to: CourtPoint | null
  target: number | null
}

export interface PlayStep { caption: string; actions: PlayAction[] }

export interface Play {
  key: string
  name: string
  summary: string
  defense: Defense
  start: CourtPoint[]
  ball: number
  roles: TacticRole[]
  steps: PlayStep[]
}

export interface PresetList { presets_version: number; items: Play[] }

export interface SlotPlayer { player_id: number; display_name: string }

/** 자리 하나. score·속성·교체 후보는 매니저에게만 채워진다 */
export interface SlotLineup {
  slot: number
  role: TacticRole
  player_id: number
  display_name: string
  backups: SlotPlayer[] // 예비: 같은 전술판 5명 중 이 역할도 맞는 사람
  score: number | null
  matched_attrs: string[]
  missing_attrs: string[]
  alt_player_id: number | null
  alt_display_name: string | null
}

export interface PlayLineup {
  play_key: string
  name: string
  summary: string
  defense: Defense
  fit: number
  manual: boolean // 매니저가 자리를 바꿔 저장한 배치
  slots: SlotLineup[]
}

export interface SquadRecommendation { squad_no: number; squad_name: string; member_count: number; items: PlayLineup[] }
export interface TacticRecommendation {
  event_id: number
  zone: boolean
  fit_min: number
  presets_version: number
  can_edit: boolean
  my_squad_no: number | null
  squads: SquadRecommendation[]
}

export interface SquadMember { player_id: number; display_name: string; is_guest: boolean }
export interface SquadBoard { squad_no: number; squad_name: string; members: SquadMember[]; lineup: PlayLineup | null }

export interface EventPlayView {
  play_key: string
  play: Play
  can_edit: boolean
  my_squad_no: number | null
  squads: SquadBoard[]
}

// --- AI 배정 설명 (docs/07 F19) ---

/** 체인 A (매니저용). fallback 이면 AI 문장 대신 text(기존 규칙 설명) */
export interface AiExplanation {
  summary: string
  key_players: string[] // 활약이 기대되는 선수
  chemistry: string[] // 호흡이 좋을 조합
  gaps: string[] // 부족한 역할
  watch_point: string
  fallback: boolean
  text: string | null
  cached: boolean
}

/** 체인 B (팀원용) — 내 것만 */
export interface AiMessage {
  in_assignment: boolean
  why_position: string
  role: string
  partner: string
  fallback: boolean
  text: string | null
}

/** 체인 C — 한 팀의 추천 전술 설명. fallback 이면 reason 이 규칙 문장 */
export interface AiTacticItem { play_key: string; reason: string; key_roles: string[]; caution: string }
export interface AiTactics { squad_no: number; one_liner: string; items: AiTacticItem[]; fallback: boolean; cached: boolean }
