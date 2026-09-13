import { lazy, Suspense, useEffect, useState } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api, ApiError } from './api'
import type { User } from './types'
import { ErrorState, Loading } from './components/ui'
import { Shell } from './components/Shell'
import { Login } from './pages/Login'
import { Dashboard } from './pages/Dashboard'
import { Schedule } from './pages/Schedule'
import { Roster, PlayerProfile } from './pages/Roster'
import { Teams } from './pages/Teams'
import { Availability } from './pages/Availability'
import { Club } from './pages/Club'
import { MatchPage } from './pages/MatchPage'

const Analytics = lazy(() => import('./pages/Analytics'))

export default function App() {
  const location = useLocation()
  const [online, setOnline] = useState(navigator.onLine)
  const me = useQuery({
    queryKey: ['me'],
    queryFn: async () => {
      try {
        return await api<User>('/auth/me')
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null
        throw e
      }
    },
    retry: false,
  })
  useEffect(() => {
    const update = () => setOnline(navigator.onLine)
    window.addEventListener('online', update)
    window.addEventListener('offline', update)
    return () => {
      window.removeEventListener('online', update)
      window.removeEventListener('offline', update)
    }
  }, [])
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [location.pathname])
  if (me.isPending) return <Loading />
  if (me.error) return <ErrorState error={me.error} />
  if (!me.data) return <Login returnTo={location.pathname !== '/login' ? location.pathname : '/'} />
  const user = me.data
  return (
    <>
      {!online && (
        <div className="offline-banner" role="status">
          You’re offline. Reconnect to see the latest updates and save changes.
        </div>
      )}
      <Shell user={user}>
        <Suspense fallback={<Loading />}>
          <Routes>
            <Route path="/" element={<Dashboard user={user} />} />
            <Route path="/schedule" element={<Schedule user={user} />} />
            <Route path="/matches/:id" element={<MatchPage user={user} />} />
            <Route path="/players" element={<Roster user={user} />} />
            <Route path="/players/:id" element={<PlayerProfile user={user} />} />
            <Route path="/teams" element={<Teams />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/availability" element={<Availability user={user} />} />
            <Route path="/history" element={<Schedule user={user} history />} />
            <Route path="/club" element={<Club user={user} />} />
            <Route path="/login" element={<Navigate to="/" replace />} />
            <Route
              path="*"
              element={
                <div className="empty-state">
                  <h1>Off the pitch?</h1>
                  <p>This page doesn’t exist.</p>
                  <a className="btn btn-primary" href="/">
                    Back to the clubhouse
                  </a>
                </div>
              }
            />
          </Routes>
        </Suspense>
      </Shell>
    </>
  )
}
