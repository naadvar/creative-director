import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react'
import { api } from '../api/client'
import type { AuthUser } from '../api/types'

interface AuthState {
  user: AuthUser | null
  loading: boolean
  refresh: () => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthState | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      const { user } = await api.me()
      setUser(user)
    } catch {
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [])

  const logout = useCallback(async () => {
    await api.logout().catch(() => {})
    setUser(null)
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  return (
    <AuthContext.Provider value={{ user, loading, refresh, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within <AuthProvider>')
  return ctx
}

/** True if the user has a connected Instagram account. */
export function useInstagram(): { connected: boolean; username: string | null } {
  const { user } = useAuth()
  const conn = user?.connections.find((c) => c.platform === 'instagram')
  return { connected: !!conn, username: conn?.username ?? null }
}
