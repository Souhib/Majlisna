import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { Lozenge } from "@/components/brand"
import { BusyLozenges } from "@/components/ui/button"

interface ConnectionStatusProps {
  connected: boolean
}

/**
 * The real-time link's state, as a thin strip just under the nav: "Reconnecting…"
 * with the three working lozenges and an ember hairline while the socket is down (the page
 * keeps polling meanwhile), then "Connected again" on a brass hairline for three seconds.
 * Never a coloured fill, never shown before the first connection.
 */
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

  // Under the sticky nav (top: --navh) and below it in the stack (z-40 < the nav's 50):
  // at top 0 over the nav it hid the Menu button and the wordmark at 390 px, while the
  // player most needed a way out.
  const strip =
    "fixed inset-x-0 top-[var(--navh)] z-40 flex min-h-8 items-center justify-center gap-2.5 bg-surface px-4 py-1.5 text-[13.5px] font-medium animate-fade-in"

  // Only show disconnected banner after we've connected at least once
  if (!connected && hasConnectedOnceRef.current) {
    return (
      <div role="alert" aria-live="assertive" className={`${strip} border-b border-ember text-destructive-on-tint`}>
        <BusyLozenges />
        {t("connection.reconnecting")}
      </div>
    )
  }

  if (showReconnected) {
    return (
      <div role="status" aria-live="polite" className={`${strip} border-b border-line-brass-strong text-foreground`}>
        <Lozenge state="brass" size={7} />
        {t("connection.connected")}
      </div>
    )
  }

  return null
}
