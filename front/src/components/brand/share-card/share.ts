/**
 * Can this browser hand a PNG to the system's share sheet? `navigator.canShare` is asked
 * about a file of the card's own kind (an empty PNG), synchronously, so the decision is
 * taken inside the player's tap: where the answer is no, the tap copies the line at
 * once, as Share always did, and no card is drawn at all.
 */
export function canShareFiles(nav: Navigator | undefined = typeof navigator !== "undefined" ? navigator : undefined): boolean {
  if (!nav || typeof nav.share !== "function" || typeof nav.canShare !== "function" || typeof File === "undefined") return false
  try {
    return nav.canShare({ files: [new File([], "card.png", { type: "image/png" })] })
  } catch {
    return false
  }
}

/** The name of a DOMException (or any error), "" for anything else. */
export function errorName(err: unknown): string {
  return err && typeof err === "object" && "name" in err ? String((err as { name: unknown }).name) : ""
}
