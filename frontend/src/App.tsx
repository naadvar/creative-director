import type { ReactNode } from 'react'
import { Link, NavLink, Route, Routes, useLocation } from 'react-router-dom'
import BrowsePage from './pages/BrowsePage'
import VideoPage from './pages/VideoPage'
import UploadPage from './pages/UploadPage'
import LandingPage from './pages/LandingPage'
import MyUploadsPage from './pages/MyUploadsPage'
import MyDnaPage from './pages/MyDnaPage'
import Disclaimer from './components/Disclaimer'
import Spinner from './components/Spinner'
import EmailGate from './components/EmailGate'
import { AuthProvider, useAuth } from './hooks/useAuth'

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
  const { user, logout } = useAuth()
  return (
    <header className="sticky top-0 z-20 border-b border-border bg-ink/80 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-3 px-4 sm:gap-6 sm:px-5">
        <Link to="/" className="flex shrink-0 items-center gap-2">
          <Logo />
          <span className="hidden text-sm font-semibold tracking-tight sm:inline">
            Creative Director
          </span>
        </Link>
        <nav className="flex items-center gap-3.5 sm:gap-4">
          {user ? (
            <>
              <NavLink to="/analyze" className={navClass}>
                Read
              </NavLink>
              <NavLink to="/my-reads" className={navClass}>
                My reads
              </NavLink>
              <NavLink to="/my-dna" className={navClass}>
                My DNA
              </NavLink>
            </>
          ) : (
            <NavLink to="/analyze" className={navClass}>
              Read a reel
            </NavLink>
          )}
          <NavLink to="/browse" className={navClass}>
            Examples
          </NavLink>
        </nav>
        <div className="ml-auto flex shrink-0 items-center gap-3 text-sm">
          {user ? (
            <>
              {user.email ? (
                <span className="hidden max-w-[12rem] truncate text-muted sm:inline">
                  {user.email}
                </span>
              ) : null}
              <button
                type="button"
                onClick={() => void logout()}
                className="text-muted transition-colors hover:text-text"
              >
                Sign out
              </button>
            </>
          ) : (
            <NavLink to="/my-reads" className="font-medium text-accent hover:opacity-90">
              Sign in
            </NavLink>
          )}
        </div>
      </div>
    </header>
  )
}

/** Route-level gate: render children if signed in, else show the email gate.
 * After sign-in it returns to the page they were trying to reach (so "Sign in" →
 * /my-reads lands on their reads, not a hardcoded page). */
function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) {
    return (
      <div className="grid min-h-[50vh] place-items-center">
        <Spinner label="Loading…" />
      </div>
    )
  }
  if (!user) {
    return (
      <div className="grid min-h-[50vh] place-items-center py-10">
        <EmailGate
          redirectTo={location.pathname}
          heading="Sign in"
          sub="Enter your email — no password. We’ll pull up your reads."
          cta="Sign in"
        />
      </div>
    )
  }
  return <>{children}</>
}

/** Home: logged-out visitors get the marketing landing; signed-in users go
 * straight to the upload flow. */
function Home() {
  const { user, loading } = useAuth()
  if (loading) {
    return (
      <div className="grid min-h-[50vh] place-items-center">
        <Spinner label="Loading…" />
      </div>
    )
  }
  return user ? <UploadPage /> : <LandingPage />
}

function AnimatedRoutes() {
  const location = useLocation()
  return (
    <div key={location.pathname} className="page-in">
      <Routes location={location}>
        <Route path="/" element={<Home />} />
        {/* Public: a creator can pick a file before signing in; the email gate
            is deferred to the "Read my reel" tap (UploadPage handles it). */}
        <Route path="/analyze" element={<UploadPage />} />
        <Route path="/browse" element={<BrowsePage />} />
        <Route
          path="/my-reads"
          element={
            <RequireAuth>
              <MyUploadsPage />
            </RequireAuth>
          }
        />
        <Route
          path="/my-dna"
          element={
            <RequireAuth>
              <MyDnaPage />
            </RequireAuth>
          }
        />
        <Route path="/video/:videoId" element={<VideoPage />} />
        <Route
          path="*"
          element={
            <div className="text-sm text-muted">
              Page not found.{' '}
              <Link to="/" className="text-accent hover:underline">
                Go home
              </Link>
            </div>
          }
        />
      </Routes>
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <div className="flex min-h-screen flex-col">
        <Header />
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-7 sm:px-5">
          <AnimatedRoutes />
        </main>
        <footer className="border-t border-border">
          <div className="mx-auto max-w-6xl px-5 py-5">
            <Disclaimer />
          </div>
        </footer>
      </div>
    </AuthProvider>
  )
}
