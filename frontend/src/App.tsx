import { useEffect, useRef, useState } from 'react'
import { useSessions } from './hooks/useSessions'
import { useChat } from './hooks/useChat'
import { useAuth } from './hooks/useAuth'
import Sidebar from './components/layout/Sidebar'
import ChatWindow from './components/chat/ChatWindow'
import LoginPage from './components/admin/LoginPage'
import AdminPanel from './components/admin/AdminPanel'

type View = 'chat' | 'admin-login' | 'admin'

export default function App() {
  const sessions = useSessions()
  const chat = useChat()
  // Single source of truth for auth state — login/logout from child
  // components receive these stable callbacks as props so they all mutate
  // the same useState instance rather than isolated copies.
  const auth = useAuth()
  const initialized = useRef(false)

  const [view, setView] = useState<View>('chat')

  // On first mount: restore the most recent session or create a fresh one.
  useEffect(() => {
    if (initialized.current) return
    initialized.current = true

    if (sessions.sessionIds.length === 0) {
      sessions.startNewSession().catch(console.error)
    } else {
      sessions.setCurrentSessionId(sessions.sessionIds[0])
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Load (or clear) history whenever the active session changes
  useEffect(() => {
    if (!sessions.currentSessionId) return
    chat.clearMessages()
    chat.loadHistory(sessions.currentSessionId).catch(console.error)
  }, [sessions.currentSessionId]) // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-logout when any authFetch receives a 401 (expired / revoked token).
  // auth.logout is stable (useCallback in useAuth) so this effect runs once.
  useEffect(() => {
    const handleAuthError = () => {
      auth.logout()
      setView('admin-login')
    }
    window.addEventListener('propesqi:auth-error', handleAuthError)
    return () => window.removeEventListener('propesqi:auth-error', handleAuthError)
  }, [auth.logout])

  const handleDeleteSession = (id: string) => {
    sessions.removeSession(id).then(() => {
      // If we just deleted the active session, start a fresh one
      if (id === sessions.currentSessionId) {
        sessions.startNewSession().catch(console.error)
      }
    }).catch(console.error)
  }

  const handleSend = (text: string) => {
    if (!sessions.currentSessionId) return
    chat.sendMessage(text, sessions.currentSessionId).catch(console.error)
  }

  const handleNewSession = () => {
    sessions.startNewSession().catch(console.error)
  }

  const handleAdminClick = () => {
    setView(auth.isAdmin ? 'admin' : 'admin-login')
  }

  // ------------------------------------------------------------------ //
  // Render non-chat views                                               //
  // ------------------------------------------------------------------ //

  if (view === 'admin-login') {
    return (
      <LoginPage
        login={auth.login}
        onSuccess={() => setView('admin')}
      />
    )
  }

  if (view === 'admin') {
    if (!auth.isAdmin) {
      // Token expired or cleared — send back to login
      return <LoginPage login={auth.login} onSuccess={() => setView('admin')} />
    }
    return <AdminPanel logout={auth.logout} onBack={() => setView('chat')} />
  }

  return (
    <div
      className="flex h-screen overflow-hidden bg-white dark:bg-[#1e1e1e] text-[#111] dark:text-[#e8e8e8]"
      style={{ fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif' }}
    >
      <Sidebar
        summaries={sessions.summaries}
        currentSessionId={sessions.currentSessionId}
        onNewSession={handleNewSession}
        onSelectSession={sessions.switchSession}
        onDeleteSession={handleDeleteSession}
        onAdminClick={handleAdminClick}
      />
      <ChatWindow
        messages={chat.messages}
        streaming={chat.streaming}
        onSend={handleSend}
        onStop={chat.abortStream}
      />
    </div>
  )
}
