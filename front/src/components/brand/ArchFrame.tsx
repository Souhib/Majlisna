import { type ReactNode } from "react"
import { cn } from "@/lib/utils"
import jabreen800 from "@/assets/brand/jabreen-niches.duo.800.webp"
import jabreen1600 from "@/assets/brand/jabreen-niches.duo.1600.webp"

/**
 * ArchFrame: Qandil's pointed arch (sketch section H). A double brass hairline with
 * three lozenge nodes (the apex and both springers), over the Jabreen niches in
 * duotone; the content (the colophon card) is set into the lower part of the arch. The
 * photograph sits BEHIND the card, never behind its text.
 *
 * It is the only arch in the product (with the future share card). Scales with its
 * own width (container query units), up to 560 px.
 *
 * Photo: "Jabreen Castle, Oman - 2024 13" by dconvertini, CC BY-SA 2.0, modified;
 * see src/assets/brand/SOURCES.txt. The credit must appear on the about/credits page.
 *
 * <ArchFrame><Colophon … /></ArchFrame>     (Colophon already wraps itself)
 * <ArchFrame photo={false}>…</ArchFrame>    (a plain deep ground instead of the photo)
 */
export interface ArchFrameProps {
  children: ReactNode
  /** Show the Jabreen photograph inside the arch. Default true. */
  photo?: boolean
  className?: string
}

export function ArchFrame({ children, photo = true, className }: ArchFrameProps) {
  return (
    <div className={cn("arch-stage", className)} data-photo={photo}>
      <div className="arch-photo" aria-hidden="true">
        {photo ? (
          <img
            src={jabreen1600}
            srcSet={`${jabreen800} 800w, ${jabreen1600} 1600w`}
            sizes="(max-width: 760px) 100vw, 560px"
            alt=""
            loading="lazy"
            decoding="async"
          />
        ) : null}
      </div>
      <svg className="arch-head" viewBox="-12 -13 544 263" aria-hidden="true">
        <path className="in" d="M0 250C0 130 120 55 260 0C400 55 520 130 520 250" />
        <path className="out" d="M-11 250C-11 122 114 42 260 -12C406 42 531 122 531 250" />
      </svg>
      <span className="arch-side in" aria-hidden="true" />
      <span className="arch-side out" aria-hidden="true" />
      <span className="arch-node" style={{ left: "-2.115cqw", top: "48.08cqw" }} aria-hidden="true" />
      <span className="arch-node" style={{ left: "102.115cqw", top: "48.08cqw" }} aria-hidden="true" />
      <span className="arch-node" style={{ left: "50cqw", top: "-2.31cqw" }} aria-hidden="true" />
      <div className="arch-inner">{children}</div>
    </div>
  )
}
