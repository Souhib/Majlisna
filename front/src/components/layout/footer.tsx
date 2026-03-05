import { Gamepad2 } from "lucide-react"

export function Footer() {
  return (
    <footer className="border-t bg-background py-8">
      <div className="mx-auto max-w-7xl px-4 text-center">
        <div className="flex items-center justify-center gap-2 text-muted-foreground">
          <Gamepad2 className="h-4 w-4" />
          <span className="text-sm">IPG - Islamic Party Games</span>
        </div>
        <p className="mt-2 text-xs text-muted-foreground">
          Play Islamized versions of your favorite party games with friends.
        </p>
      </div>
    </footer>
  )
}
