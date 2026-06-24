/**
 * UUID v4 generator that works in both secure (HTTPS/localhost) and
 * non-secure (HTTP + IP) contexts. crypto.randomUUID() is only available
 * in secure contexts; the fallback uses Math.random() which is sufficient
 * for ephemeral UI identifiers.
 */
export function generateUUID(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
    const r = (Math.random() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}
