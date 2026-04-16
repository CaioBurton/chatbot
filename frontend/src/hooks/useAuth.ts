import { useCallback, useState } from 'react'
import { loginApi } from '../lib/api'

const ACCESS_TOKEN_KEY = 'propesqi_access_token'
const REFRESH_TOKEN_KEY = 'propesqi_refresh_token'

function readToken(): string | null {
  try {
    return localStorage.getItem(ACCESS_TOKEN_KEY)
  } catch {
    return null
  }
}

function decodeJwtPayload(token: string): Record<string, unknown> {
  try {
    const parts = token.split('.')
    if (parts.length !== 3) return {}
    // Base64url → standard base64 padding
    const b64 = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    const padded = b64 + '=='.slice(0, (4 - (b64.length % 4)) % 4)
    const payload = JSON.parse(atob(padded)) as Record<string, unknown>
    // Reject expired tokens so client-side guards reflect real access state
    if (typeof payload.exp === 'number' && payload.exp * 1000 < Date.now()) {
      return {}
    }
    return payload
  } catch {
    return {}
  }
}

export function useAuth() {
  const [token, setToken] = useState<string | null>(readToken)

  const isAuthenticated = token !== null

  const payload = token ? decodeJwtPayload(token) : {}
  const isAdmin =
    payload.role === 'admin' || payload.role === 'superadmin'

  // useCallback ensures login/logout are stable references so callers can
  // safely include them in useEffect dependency arrays without causing
  // infinite re-registration loops.
  const login = useCallback(async (email: string, password: string): Promise<void> => {
    const response = await loginApi(email, password)
    try {
      localStorage.setItem(ACCESS_TOKEN_KEY, response.access_token)
      localStorage.setItem(REFRESH_TOKEN_KEY, response.refresh_token)
    } catch {
      // Storage unavailable — token kept only in memory for this session
    }
    setToken(response.access_token)
  }, [])

  const logout = useCallback(() => {
    try {
      localStorage.removeItem(ACCESS_TOKEN_KEY)
      localStorage.removeItem(REFRESH_TOKEN_KEY)
    } catch {
      // ignore
    }
    setToken(null)
  }, [])

  return { isAuthenticated, isAdmin, login, logout }
}

