import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Navigate, NavLink, Route, Routes } from 'react-router-dom'
import {
  Activity,
  BarChart3,
  Bot,
  BriefcaseBusiness,
  CalendarDays,
  CheckSquare,
  ChevronDown,
  FileText,
  Home,
  LifeBuoy,
  LogOut,
  Menu,
  Moon,
  Search,
  Settings as SettingsIcon,
  ShieldCheck,
  Sun,
  Users,
  Workflow,
  X,
} from 'lucide-react'
import { api, setCsrf, write, ApiError } from './services/api'
import type { Me } from './types'
import { Button } from './components/ui/button'
import { ErrorState, Loading } from './components/shared'
import { Login } from './pages/Login'
import { Dashboard } from './pages/Dashboard'
import { Records } from './pages/Records'
import { Playground } from './pages/Playground'
import { Knowledge } from './pages/Knowledge'
import { Approvals } from './pages/Approvals'
import { Monitoring } from './pages/Monitoring'
import { Settings } from './pages/Settings'

export function App() {
  const client = useQueryClient()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [dark, setDark] = useState(
    () => localStorage.getItem('operations-theme') === 'dark',
  )
  const [error, setError] = useState<unknown>()
  const me = useQuery({
    queryKey: ['me'],
    queryFn: async () => {
      const result = await api<Me>('/auth/me')
      setCsrf(result.csrf_token)
      return result
    },
    retry: false,
  })
  function toggleTheme() {
    const next = !dark
    setDark(next)
    localStorage.setItem('operations-theme', next ? 'dark' : 'light')
  }
  if (me.isPending) return <Loading />
  if (me.error) {
    if (me.error instanceof ApiError && me.error.status === 401)
      return (
        <div className={dark ? 'app-root dark' : 'app-root'}>
          <Login
            onSuccess={() => {
              client.clear()
              void me.refetch()
            }}
          />
        </div>
      )
    return <ErrorState error={me.error} retry={() => void me.refetch()} />
  }
  const user = me.data
  const writable = user.role !== 'viewer'
  const manage = ['owner', 'admin'].includes(user.role)
  const groups = [
    {
      title: 'Overview',
      items: [
        ['/', 'Dashboard', Home],
        ['/analytics', 'Analytics', BarChart3],
      ],
    },
    {
      title: 'Automation',
      items: [
        ['/playground', 'Workflow studio', Workflow],
        ['/runs', 'Runs & workflows', Activity],
        ...(writable ? [['/approvals', 'Approvals', ShieldCheck]] : []),
      ],
    },
    {
      title: 'Operations',
      items: [
        ['/customers', 'Customers', Users],
        ['/tickets', 'Support tickets', LifeBuoy],
        ['/appointments', 'Appointments', CalendarDays],
        ['/tasks', 'Tasks', CheckSquare],
      ],
    },
    {
      title: 'Knowledge',
      items: [
        ['/documents', 'Documents', FileText],
        ['/knowledge', 'Knowledge search', Search],
      ],
    },
    {
      title: 'Administration',
      items: [
        ['/team', 'Team & roles', Users],
        ['/organization', 'Organization', SettingsIcon],
        ['/ai-settings', 'AI settings', Bot],
        ...(manage ? [['/audit', 'Audit logs', ShieldCheck]] : []),
      ],
    },
  ]
  return (
    <div className={`app-root ${dark ? 'dark' : ''}`}>
      <div className="app-shell">
        <aside className={`sidebar ${mobileOpen ? 'mobile-open' : ''}`}>
          <div className="brand">
            <span className="brand-mark">
              <BriefcaseBusiness size={21} />
            </span>
            <div>
              Operations Desk<small>BUSINESS WORKSPACE</small>
            </div>
            <button
              className="mobile-close"
              aria-label="Close navigation"
              onClick={() => setMobileOpen(false)}
            >
              <X size={20} />
            </button>
          </div>
          <div className="organization-switch">
            <span className="org-avatar">
              {user.organization.name.slice(0, 1)}
            </span>
            <div>
              <strong>{user.organization.name}</strong>
              <small>Your organization</small>
            </div>
            <ChevronDown size={16} />
          </div>
          <nav>
            {groups.map((group) => (
              <div className="nav-group" key={group.title}>
                <span>{group.title}</span>
                {group.items.map(([path, label, Icon]) => {
                  const IconComponent = Icon as typeof Home
                  return (
                    <NavLink
                      key={String(path)}
                      to={String(path)}
                      end={path === '/'}
                      onClick={() => setMobileOpen(false)}
                    >
                      <IconComponent size={18} />
                      <span>{String(label)}</span>
                    </NavLink>
                  )
                })}
              </div>
            ))}
          </nav>
          <div className="sidebar-bottom">
            <div className="status-pill">
              <span className="online-dot" />
              Authorized tools · Durable workflows
            </div>
            <div className="user-profile">
              <span className="user-avatar">{user.user.name.slice(0, 1)}</span>
              <div>
                <strong>{user.user.name}</strong>
                <small>{user.role}</small>
              </div>
              <Button
                variant="ghost"
                aria-label="Sign out"
                onClick={() =>
                  void write('/auth/logout', {})
                    .then(() => {
                      setCsrf('')
                      client.clear()
                      void me.refetch()
                    })
                    .catch(setError)
                }
              >
                <LogOut size={17} />
              </Button>
            </div>
          </div>
        </aside>
        <div className="main-shell">
          <header className="topbar">
            <div>
              <button
                className="mobile-menu"
                aria-label="Open navigation"
                onClick={() => setMobileOpen(true)}
              >
                <Menu size={22} />
              </button>
              <span>Workspace</span>
              <span className="topbar-divider">/</span>
              <strong>{user.organization.name}</strong>
            </div>
            <div>
              <span className="workspace-label">{user.role} access</span>
              <Button
                variant="ghost"
                aria-label="Toggle color theme"
                onClick={toggleTheme}
              >
                {dark ? <Sun size={18} /> : <Moon size={18} />}
              </Button>
            </div>
          </header>
          <main>
            {error !== undefined && <ErrorState error={error} />}
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/analytics" element={<Dashboard analytics />} />
              <Route
                path="/playground"
                element={<Playground writable={writable} />}
              />
              <Route
                path="/runs"
                element={<Monitoring writable={writable} />}
              />
              <Route
                path="/runs/:id"
                element={<Monitoring writable={writable} />}
              />
              <Route
                path="/approvals"
                element={
                  writable ? (
                    <Approvals canApprove={manage} />
                  ) : (
                    <Navigate to="/" />
                  )
                }
              />
              {(['customers', 'tickets', 'appointments', 'tasks'] as const).map(
                (kind) => (
                  <Route
                    path={`/${kind}`}
                    key={kind}
                    element={
                      <Records key={kind} kind={kind} writable={writable} />
                    }
                  />
                ),
              )}
              <Route
                path="/documents"
                element={<Knowledge manage={manage} />}
              />
              <Route
                path="/knowledge"
                element={<Knowledge searchOnly manage={manage} />}
              />
              {(['team', 'organization', 'ai-settings'] as const).map(
                (section) => (
                  <Route
                    key={section}
                    path={`/${section}`}
                    element={
                      <Settings
                        key={section}
                        section={section}
                        manage={manage}
                      />
                    }
                  />
                ),
              )}
              <Route
                path="/audit"
                element={
                  manage ? (
                    <Monitoring audit writable={writable} />
                  ) : (
                    <Navigate to="/" />
                  )
                }
              />
              <Route path="*" element={<Navigate to="/" />} />
            </Routes>
          </main>
          <footer>
            Operations Desk{' '}
            <span>Your team’s work, in one place.</span>
          </footer>
        </div>
      </div>
    </div>
  )
}
