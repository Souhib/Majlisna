import { Toaster as Sonner, type ToasterProps } from "sonner"
import { useResolvedTheme } from "@/hooks/use-resolved-theme"

/**
 * The app's single toast region, themed for Samar (sonner's colour variables are
 * re-pointed at the tokens in styles/brand.css, "sonner"). A toast is a --surface card
 * with a hairline; errors take an ember hairline and ember-on-tint title, successes a
 * brass one. Behaviour is unchanged from before the redesign (top-center, close button,
 * expanded, at most three): the E2E suite reads `[data-sonner-toast][data-type="error"]`
 * and waits for toasts to clear.
 *
 * Game events are not toasts: achievements wait for the colophon (seals), arrivals
 * belong to the halqa. Toasts are for the outcome of the player's own action.
 *
 * Placement: top centre, just under the sticky nav (never over its controls), in the
 * light actually on screen (a stored choice can differ from the system's).
 */
export function Toaster(props: ToasterProps) {
  const theme = useResolvedTheme()
  return (
    <Sonner
      theme={theme}
      position="top-center"
      offset={{ top: "calc(var(--navh) + 12px)" }}
      mobileOffset={{ top: "calc(var(--navh) + 8px)", left: 16, right: 16 }}
      richColors
      closeButton
      expand
      visibleToasts={3}
      toastOptions={{
        classNames: {
          toast: "samar-toast",
          title: "samar-toast-title",
          description: "samar-toast-description",
        },
      }}
      {...props}
    />
  )
}
