import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

interface ConnectionStatusProps {
  connected: boolean
}

export function ConnectionStatus({ connected }: ConnectionStatusProps) {
  const { t } = useTranslation()
  const [showReconnected, setShowReconnected] = useState(false)
  const wasDisconnectedRef = useRef(false)
  const hasConnectedOnceRef = useRef(false)

  useEffect(() => {
    if (connected) {
      if (wasDisconnectedRef.current) {
        // Just reconnected after a disconnection
        wasDisconnectedRef.current = false
        setShowReconnected(true)
        const timer = setTimeout(() => setShowReconnected(false), 3000)
        return () => clearTimeout(timer)
      }
      hasConnectedOnceRef.current = true
    } else if (hasConnectedOnceRef.current) {
      wasDisconnectedRef.current = true
    }
  }, [connected])

  // Only show disconnected banner after we've connected at least once
  if (!connected && hasConnectedOnceRef.current) {
    return (
      <div role="alert" aria-live="assertive" className="fixed top-0 left-0 right-0 z-50 bg-destructive/90 text-destructive-foreground text-center py-1.5 text-xs font-medium animate-slide-down backdrop-blur-sm">
        {t("connection.reconnecting", "Reconnecting...")}
      </div>
    )
  }

  if (showReconnected) {
    return (
      <div role="status" aria-live="polite" className="fixed top-0 left-0 right-0 z-50 bg-primary/90 text-primary-foreground text-center py-1.5 text-xs font-medium animate-slide-down backdrop-blur-sm">
        {t("connection.connected", "Connected!")}
      </div>
    )
  }

  return null
}
