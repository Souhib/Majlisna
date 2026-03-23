import * as Popover from "@radix-ui/react-popover"
import { Info } from "lucide-react"
import { memo, useCallback, useEffect, useRef } from "react"
import { cn } from "@/lib/utils"

interface HintButtonProps {
  hint: string | null
  onView?: () => void
  className?: string
}

export const HintButton = memo(function HintButton({ hint, onView, className }: HintButtonProps) {
  const hasNotified = useRef(false)

  useEffect(() => {
    hasNotified.current = false
  }, [hint])

  const handleOpenChange = useCallback(
    (open: boolean) => {
      if (open && !hasNotified.current && onView) {
        hasNotified.current = true
        onView()
      }
    },
    [onView],
  )

  if (!hint) return null

  return (
    <Popover.Root onOpenChange={handleOpenChange}>
      <Popover.Trigger asChild>
        <button
          type="button"
          className={cn(
            "inline-flex items-center justify-center rounded-full p-1.5 text-muted-foreground hover:text-primary hover:bg-glow transition-all duration-200 hover:scale-110",
            className,
          )}
          aria-label="Show explanation"
        >
          <Info className="h-4 w-4" />
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          className="z-50 max-w-xs glass rounded-2xl p-4 text-sm text-popover-foreground shadow-xl animate-scale-in"
          sideOffset={5}
          align="center"
        >
          {hint}
          <Popover.Arrow className="fill-[var(--surface)]" />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
})
