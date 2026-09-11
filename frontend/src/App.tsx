/** 라우팅. 설계서 5.3절 흐름 A(온보딩) · B(모임 운영) · C(참여) 를 화면 ID 기준으로 연결한다. */
import { Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { useIsLoggedIn } from './store/auth'
import { KakaoCallbackPage, LoginPage, SignupPage } from './pages/auth'
import { ForgotPasswordPage, ResetPasswordPage } from './pages/password'
import { HomePage, ProfilePage } from './pages/home'
import { MembersPage, TeamCreatePage, TeamDetailPage, TeamJoinPage } from './pages/team'
import { QuartersPage } from './pages/quarters'
import { VotePage } from './pages/vote'
import { PlayerDetailPage } from './pages/player-detail'
import { PastRecordPage } from './pages/records'
import { LeaderboardPage } from './pages/leaderboard'
import { RankingPage } from './pages/ranking'
import { AdoptedPage, AssignPage, RunResultPage } from './pages/assignment'
import { SelfRankPage, SurveyPage } from './pages/survey'
import { EventCreatePage, EventDetailPage } from './pages/events'

function RequireAuth() {
  return useIsLoggedIn() ? <Outlet /> : <Navigate to="/login" replace />
}
function GuestOnly() {
  return useIsLoggedIn() ? <Navigate to="/" replace /> : <Outlet />
}

export default function App() {
  return (
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
  )
}
