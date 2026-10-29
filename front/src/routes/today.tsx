import { createFileRoute } from "@tanstack/react-router"
import { DailyWordPage } from "@/components/daily/DailyWordPage"

/** The word of the day (كلمة اليوم). Public: a signed-out visitor sees the number, the theme and hint 1. */
export const Route = createFileRoute("/today")({
  component: DailyWordPage,
})
