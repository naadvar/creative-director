import { Link, NavLink, Route, Routes } from 'react-router-dom'
import BrowsePage from './pages/BrowsePage'
import VideoPage from './pages/VideoPage'
import MyReelsPage from './pages/MyReelsPage'
import LandingPage from './pages/LandingPage'
import Disclaimer from './components/Disclaimer'
import Spinner from './components/Spinner'
import { AuthProvider, useAuth, useInstagram } from './hooks/useAuth'

function Logo() {
  return (
    <span className="grid h-7 w-7 place-items-center rounded-lg bg-accent/15 ring-1 ring-accent/40">
      <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor" className="text-accent">
        <path d="M3 1.7v8.6a.6.6 0 0 0 .92.5l6.7-4.3a.6.6 0 0 0 0-1L3.92 1.2A.6.6 0 0 0 3 1.7Z" />
      </svg>
    </span>
  )
}

function navClass({ isActive }: { isActive: boolean }) {
  return `text-sm transition-colors ${isActive ? 'text-text' : 'text-muted hover:text-text'}`
}

function Header() {
  const { logout } = useAuth()
  const { username } = useInstagram()
  return (
    <header className="sticky top-0 z-20 border-b border-border bg-ink/85 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-6 px-5">
        <Link to="/" className="flex items-center gap-2.5">
          <Logo />
          <span className="text-sm font-semibold tracking-tight">Creative Director</span>
        </Link>
        <nav className="flex items-center gap-4">
          <NavLink to="/" end className={navClass}>
            Your Reels
          </NavLink>
          <NavLink to="/browse" className={navClass}>
            Explore
          </NavLink>
        </nav>
        <div className="ml-auto flex items-center gap-3 text-sm">
          {username ? <span className="text-muted">@{username}</span> : null}
          <button
            type="button"
            onClick={() => void logout()}
            className="text-muted transition-colors hover:text-text"
          >
            Sign out
          </button>
        </div>
      </div>
    </header>
  )
}

function AuthedApp() {
  return (
    <div className="flex min-h-screen flex-col">
      <Header />
      <main className="mx-auto w-full max-w-6xl flex-1 px-5 py-7">
        <Routes>
          <Route path="/" element={<MyReelsPage />} />
          <Route path="/browse" element={<BrowsePage />} />
          <Route path="/video/:videoId" element={<VideoPage />} />
          <Route
            path="*"
            element={
              <div className="text-sm text-muted">
                Page not found.{' '}
                <Link to="/" className="text-accent hover:underline">
                  Your Reels
                </Link>
              </div>
            }
          />
        </Routes>
      </main>
      <footer className="border-t border-border">
        <div className="mx-auto max-w-6xl px-5 py-5">
          <Disclaimer />
        </div>
      </footer>
    </div>
  )
}

function Gate() {
  const { user, loading } = useAuth()
  if (loading) {
    return (
      <div className="grid min-h-screen place-items-center">
        <Spinner label="Loading…" />
      </div>
    )
  }
  return user ? <AuthedApp /> : <LandingPage />
}

export default function App() {
  return (
    <AuthProvider>
      <Gate />
    </AuthProvider>
  )
}
