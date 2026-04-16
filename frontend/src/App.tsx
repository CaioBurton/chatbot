import { useEffect, useRef } from 'react'
import { useSessions } from './hooks/useSessions'
import { useChat } from './hooks/useChat'
import { useTheme } from './hooks/useTheme'
import Sidebar from './components/layout/Sidebar'
import ChatWindow from './components/chat/ChatWindow'

export default function App() {
  const sessions = useSessions()
  const chat = useChat()
  const { theme, toggleTheme } = useTheme()
  const initialized = useRef(false)

  // On first mount: restore the most recent session or create a fresh one.
  // Uses sessions.sessionIds (already loaded from localStorage) — no direct
  // localStorage access needed here.
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

  const handleSend = (text: string) => {
    if (!sessions.currentSessionId) return
    chat.sendMessage(text, sessions.currentSessionId).catch(console.error)
  }

  const handleNewSession = () => {
    sessions.startNewSession().catch(console.error)
  }

  const isDark = theme === 'dark'

  return (
    <div
      style={{
        display: 'flex',
        height: '100vh',
        fontFamily:
          '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
        overflow: 'hidden',
        backgroundColor: isDark ? '#1e1e1e' : '#fff',
        color: isDark ? '#e8e8e8' : '#111',
      }}
    >
      <Sidebar
        summaries={sessions.summaries}
        currentSessionId={sessions.currentSessionId}
        onNewSession={handleNewSession}
        onSelectSession={sessions.switchSession}
        theme={theme}
        toggleTheme={toggleTheme}
      />
      <ChatWindow
        messages={chat.messages}
        streaming={chat.streaming}
        onSend={handleSend}
        onStop={chat.abortStream}
        theme={theme}
      />
    </div>
  )
}

