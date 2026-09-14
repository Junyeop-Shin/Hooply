/** 라우팅. 설계서 5.3절 흐름 A(온보딩) · B(일정 운영) · C(참여) 를 화면 ID 기준으로 연결한다.
 *
 * 화면은 라우트 단위로 나눠 받는다(lazy). 로그인 화면 하나를 보려고 배정·쿼터 기록 화면까지
 * 내려받을 이유가 없다. 전환 중에는 Spinner 를 보여 준다.
 */
import { Suspense, lazy } from 'react'
import { Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { useIsLoggedIn } from './store/auth'
import { Spinner } from './components/ui'
// 첫 화면(로그인·홈)은 어차피 바로 필요하므로 함께 받는다
import { KakaoCallbackPage, LoginPage, SignupPage } from './pages/auth'
import { HomePage, ProfilePage } from './pages/home'

const page = <T extends Record<string, unknown>, K extends keyof T>(load: () => Promise<T>, name: K) =>
  lazy(() => load().then((m) => ({ default: m[name] as React.ComponentType })))

const ForgotPasswordPage = page(() => import('./pages/password'), 'ForgotPasswordPage')
const ResetPasswordPage = page(() => import('./pages/password'), 'ResetPasswordPage')
const MembersPage = page(() => import('./pages/team'), 'MembersPage')
const TeamCreatePage = page(() => import('./pages/team'), 'TeamCreatePage')
const TeamDetailPage = page(() => import('./pages/team'), 'TeamDetailPage')
const TeamJoinPage = page(() => import('./pages/team'), 'TeamJoinPage')
const QuartersPage = page(() => import('./pages/quarters'), 'QuartersPage')
const VotePage = page(() => import('./pages/vote'), 'VotePage')
const PlayerDetailPage = page(() => import('./pages/player-detail'), 'PlayerDetailPage')
const PastRecordPage = page(() => import('./pages/records'), 'PastRecordPage')
const LeaderboardPage = page(() => import('./pages/leaderboard'), 'LeaderboardPage')
const RankingPage = page(() => import('./pages/ranking'), 'RankingPage')
const AdoptedPage = page(() => import('./pages/assignment'), 'AdoptedPage')
const AssignPage = page(() => import('./pages/assignment'), 'AssignPage')
const RunResultPage = page(() => import('./pages/assignment'), 'RunResultPage')
const SelfRankPage = page(() => import('./pages/survey'), 'SelfRankPage')
const SurveyPage = page(() => import('./pages/survey'), 'SurveyPage')
const EventCreatePage = page(() => import('./pages/events'), 'EventCreatePage')
const EventDetailPage = page(() => import('./pages/events'), 'EventDetailPage')

function RequireAuth() {
  return useIsLoggedIn() ? <Outlet /> : <Navigate to="/login" replace />
}
function GuestOnly() {
  return useIsLoggedIn() ? <Navigate to="/" replace /> : <Outlet />
}

export default function App() {
  return (
    <Suspense fallback={<Spinner />}>
    <Routes>
      <Route path="/auth/kakao/callback" element={<KakaoCallbackPage />} /> {/* 카카오 리다이렉트 (로그인 여부 무관) */}
      <Route path="/password/forgot" element={<ForgotPasswordPage />} />
      <Route path="/password/reset" element={<ResetPasswordPage />} />   {/* 메일 링크 */}
      <Route element={<GuestOnly />}>
        <Route path="/login" element={<LoginPage />} />   {/* S-01 */}
        <Route path="/signup" element={<SignupPage />} /> {/* S-02 */}
      </Route>

      <Route element={<RequireAuth />}>
        <Route path="/" element={<HomePage />} />                        {/* S-04 */}
        <Route path="/survey" element={<SurveyPage />} />                {/* S-03 */}
        <Route path="/teams/new" element={<TeamCreatePage />} />         {/* S-05 */}
        <Route path="/teams/join" element={<TeamJoinPage />} />          {/* S-06 */}
        <Route path="/teams/:teamId" element={<TeamDetailPage />} />     {/* S-07 */}
        <Route path="/teams/:teamId/members" element={<MembersPage />} /> {/* S-08 */}
        <Route path="/teams/:teamId/players/:playerId" element={<PlayerDetailPage />} /> {/* S-08 → 실력 지표 */}
        <Route path="/teams/:teamId/records/new" element={<PastRecordPage />} />       {/* 지난 기록 추가 */}
        <Route path="/teams/:teamId/leaderboard" element={<LeaderboardPage />} />     {/* 팀 리더보드 */}
        <Route path="/teams/:teamId/self-rank" element={<SelfRankPage />} /> {/* 구 E3 — 팀 가입 직후 */}
        <Route path="/teams/:teamId/events/new" element={<EventCreatePage />} /> {/* S-09 */}
        <Route path="/events/:eventId" element={<EventDetailPage />} />       {/* S-10 · S-11 */}
        <Route path="/teams/:teamId/ranking" element={<RankingPage />} />  {/* S-19 */}
        <Route path="/events/:eventId/assign" element={<AssignPage />} />  {/* S-12 */}
        <Route path="/assignments/runs/:runId" element={<RunResultPage />} /> {/* S-13 */}
        <Route path="/events/:eventId/assignment" element={<AdoptedPage />} /> {/* S-14 */}
        <Route path="/events/:eventId/quarters" element={<QuartersPage />} /> {/* S-15 */}
        <Route path="/events/:eventId/vote" element={<VotePage />} />         {/* S-16 */}
        <Route path="/me" element={<ProfilePage />} />                   {/* S-17 */}
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
    </Suspense>
  )
}
