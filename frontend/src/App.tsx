import type { ReactNode } from 'react'
import { Link, NavLink, Navigate, Route, Routes, useLocation, useParams } from 'react-router-dom'
import BrowsePage from './pages/BrowsePage'
import VideoPage from './pages/VideoPage'
import UploadPage from './pages/UploadPage'
import LandingPage from './pages/LandingPage'
import MyUploadsPage from './pages/MyUploadsPage'
import MyDnaPage from './pages/MyDnaPage'
import PrivacyPage from './pages/PrivacyPage'
import Disclaimer from './components/Disclaimer'
import Spinner from './components/Spinner'
import EmailGate from './components/EmailGate'
import { isNativeApp } from './api/client'
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
        <nav className="hidden items-center gap-3.5 sm:flex sm:gap-4">
          {user ? (
            <>
              <NavLink to="/analyze" className={navClass}>
                New
              </NavLink>
              <NavLink to="/my-reads" className={navClass}>
                Library
              </NavLink>
              <NavLink to="/my-dna" className={navClass}>
                Growth
              </NavLink>
            </>
          ) : (
            <NavLink to="/analyze" className={navClass}>
              New
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

function TabIcon({ d }: { d: string }) {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={d} />
    </svg>
  )
}

const TAB_ICONS = {
  read: 'M12 15V4m0 0L8 8m4-4 4 4M5 15v3a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-3',
  reads: 'M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z',
  dna: 'M7 4c0 4 10 6 10 10M17 4c0 4-10 6-10 10M7 20c0-2 10-4 10-8',
  examples: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM10.5 8.5l5 3.5-5 3.5z',
}

function BottomTab({ to, label, icon }: { to: string; label: string; icon: keyof typeof TAB_ICONS }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `flex flex-1 flex-col items-center justify-center gap-0.5 py-2 text-[10px] font-medium transition-colors active:bg-surface ${
          isActive ? 'text-accent' : 'text-muted'
        }`
      }
    >
      <TabIcon d={TAB_ICONS[icon]} />
      {label}
    </NavLink>
  )
}

/** Native-style bottom tab bar — the primary navigation on phones (the top header
 * nav is hidden below sm). Hidden on desktop, which keeps the top nav. */
function BottomNav() {
  const { user } = useAuth()
  const native = isNativeApp()
  // Logged-out native = just the sign-in screen, no tab bar.
  if (native && !user) return null
  return (
    <nav
      className="fixed inset-x-0 bottom-0 z-30 flex border-t border-border bg-ink/95 backdrop-blur-md sm:hidden"
      style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
    >
      {/* Upload (New) is sign-in-gated in the native app — the app is sign-in-first,
          so it only appears once you're logged in. On web it stays public (the
          conversion funnel: try-before-you-sign-in, gate deferred to submit). */}
      {!native || user ? <BottomTab to="/analyze" label="New" icon="read" /> : null}
      {user ? (
        <>
          <BottomTab to="/my-reads" label="Library" icon="reads" />
          <BottomTab to="/my-dna" label="Growth" icon="dna" />
        </>
      ) : null}
      {/* Examples shows the example CORPUS (third-party reels). Web only — the native
          app deliberately surfaces NO third-party content (App Store IP cleanliness),
          so it's your-own-reels only. */}
      {!native ? <BottomTab to="/browse" label="Examples" icon="examples" /> : null}
    </nav>
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

/** Home: signed-in users go straight to the upload flow. Logged-out, the first
 * screen is platform-aware — the native app opens to a clean passwordless
 * sign-in (an app shouldn't open to a marketing scroll), while the web keeps the
 * value-prop landing (it converts visitors and reassures an App Store reviewer's
 * logged-out web visit). After sign-in, native lands on the upload flow. */
function Home() {
  const { user, loading } = useAuth()
  if (loading) {
    return (
      <div className="grid min-h-[50vh] place-items-center">
        <Spinner label="Loading…" />
      </div>
    )
  }
  if (user) return <UploadPage />
  if (isNativeApp()) {
    return (
      <div className="grid min-h-[60vh] place-items-center">
        <EmailGate
          heading="Sign in"
          sub="Enter your email — no password. We’ll save your reads."
          cta="Sign in"
          redirectTo="/analyze"
        />
      </div>
    )
  }
  return <LandingPage />
}

/** /analyze — the upload flow. Public on web (pick a file first, email gate
 * deferred to the "Read my reel" tap = the conversion funnel). In the native app
 * it's sign-in-gated: the app is sign-in-first, so you can't reach upload until
 * you're logged in (matches the hidden "New" tab when logged out). */
function AnalyzeRoute() {
  const { user, loading } = useAuth()
  if (isNativeApp() && !user) {
    if (loading) {
      return (
        <div className="grid min-h-[50vh] place-items-center">
          <Spinner label="Loading…" />
        </div>
      )
    }
    return (
      <div className="grid min-h-[60vh] place-items-center">
        <EmailGate
          heading="Sign in"
          sub="Enter your email — no password. We’ll save your reads."
          cta="Sign in"
          redirectTo="/analyze"
        />
      </div>
    )
  }
  return <UploadPage />
}

/** On the native app, only the creator's OWN uploads (up_*) are viewable — never a
 * corpus reel (third-party content). Anything else redirects home. */
function NativeVideoGate() {
  const { videoId } = useParams<{ videoId: string }>()
  if (!videoId || !videoId.startsWith('up')) return <Navigate to="/" replace />
  return <VideoPage />
}

function AnimatedRoutes() {
  const location = useLocation()
  return (
    <div key={location.pathname} className="page-in">
      <Routes location={location}>
        <Route path="/" element={<Home />} />
        {/* Web: public (deferred gate). Native app: sign-in-gated (see AnalyzeRoute). */}
        <Route path="/analyze" element={<AnalyzeRoute />} />
        {/* Examples corpus = third-party reels. Web only; the native app redirects
            away so it surfaces no third-party content (App Store IP cleanliness). */}
        <Route
          path="/browse"
          element={isNativeApp() ? <Navigate to="/" replace /> : <BrowsePage />}
        />
        <Route path="/video/:videoId" element={isNativeApp() ? <NativeVideoGate /> : <VideoPage />} />
        <Route path="/privacy" element={<PrivacyPage />} />
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
        {/* pb-24 on mobile clears the fixed bottom tab bar. */}
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 pt-7 pb-24 sm:px-5 sm:py-7">
          <AnimatedRoutes />
        </main>
        <footer className="hidden border-t border-border sm:block">
          <div className="mx-auto max-w-6xl space-y-2 px-5 py-5">
            <Disclaimer />
            <Link to="/privacy" className="text-xs text-muted underline-offset-2 hover:text-text hover:underline">
              Privacy
            </Link>
          </div>
        </footer>
        <BottomNav />
      </div>
    </AuthProvider>
  )
}
