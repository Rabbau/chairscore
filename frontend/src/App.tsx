import { Navigate, Route, Routes } from 'react-router-dom'

import { Layout } from './components/Layout'
import { HomePage } from './pages/HomePage'
import { CompetitionPage } from './pages/CompetitionPage'
import { MatchPage } from './pages/MatchPage'
import { TeamPage } from './pages/TeamPage'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<HomePage />} />
        <Route path="competitions/:code" element={<CompetitionPage />} />
        <Route path="matches/:id" element={<MatchPage />} />
        <Route path="teams/:id" element={<TeamPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
