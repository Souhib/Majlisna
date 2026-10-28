import { createFileRoute } from "@tanstack/react-router"
import { GamesFihrist } from "@/components/home/GamesFihrist"
import { HomeHero } from "@/components/home/HomeHero"
import { SupportSection } from "@/components/home/SupportSection"

export const Route = createFileRoute("/")({
  component: HomePage,
})

/**
 * The home (DESIGN.md §9, sketch A/E/F/G then B): the sky and the name on the horizon,
 * the way in (open a room, or join one with its code), the halqa card, the four games,
 * and the two charities.
 */
function HomePage() {
  return (
    <>
      <HomeHero />
      <GamesFihrist />
      <SupportSection />
    </>
  )
}
