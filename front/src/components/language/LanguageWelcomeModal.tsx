import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { AnimatePresence, motion, useReducedMotion } from "motion/react"
import { BookOpen, Check, ChevronRight } from "lucide-react"
import { cn } from "@/lib/utils"

const STORAGE_KEY = "ipg-first-visit-complete"

function useFirstVisit() {
  const [isFirstVisit, setIsFirstVisit] = useState(() => {
    if (localStorage.getItem(STORAGE_KEY)) return false
    return true
  })

  const markComplete = useCallback(() => {
    localStorage.setItem(STORAGE_KEY, "true")
    setIsFirstVisit(false)
  }, [])

  return { isFirstVisit, markComplete }
}

const languages = [
  { code: "en", fullName: "English", flag: "\u{1F1EC}\u{1F1E7}", dir: "ltr" },
  { code: "fr", fullName: "Fran\u00E7ais", flag: "\u{1F1EB}\u{1F1F7}", dir: "ltr" },
  { code: "ar", fullName: "\u0627\u0644\u0639\u0631\u0628\u064A\u0629", flag: "\u{1F1E6}\u{1F1EA}", dir: "rtl" },
] as const

type LanguageCode = (typeof languages)[number]["code"]

export function LanguageWelcomeModal() {
  const { i18n } = useTranslation()
  const { isFirstVisit, markComplete } = useFirstVisit()
  const [selected, setSelected] = useState<LanguageCode | null>(null)
  const [ready, setReady] = useState(false)
  const cardRefs = useRef<(HTMLButtonElement | null)[]>([])
  const shouldReduceMotion = useReducedMotion()

  const handleSelect = useCallback(
    (code: LanguageCode) => {
      setSelected(code)
      const lang = languages.find((l) => l.code === code)
      if (!lang) return
      i18n.changeLanguage(code)
      localStorage.setItem("ipg-language", code)
      document.documentElement.dir = lang.dir
      document.documentElement.lang = lang.code

      setTimeout(() => {
        markComplete()
      }, 500)
    },
    [i18n, markComplete],
  )

  const handleSkip = useCallback(() => {
    markComplete()
  }, [markComplete])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent, index: number) => {
      let nextIndex: number | null = null

      if (e.key === "ArrowRight" || e.key === "ArrowDown") {
        e.preventDefault()
        nextIndex = (index + 1) % languages.length
      } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
        e.preventDefault()
        nextIndex = (index - 1 + languages.length) % languages.length
      } else if (e.key === "Enter" || e.key === " ") {
        e.preventDefault()
        handleSelect(languages[index].code)
        return
      }

      if (nextIndex !== null) {
        cardRefs.current[nextIndex]?.focus()
      }
    },
    [handleSelect],
  )

  useEffect(() => {
    if (isFirstVisit) {
      const timer = setTimeout(() => {
        setReady(true)
        cardRefs.current[0]?.focus()
      }, 300)
      return () => clearTimeout(timer)
    }
  }, [isFirstVisit])

  if (!isFirstVisit) return null

  return (
    <AnimatePresence>
      {/* Backdrop */}
      <motion.div
        className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-sm"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.2 }}
      >
        {/* Modal */}
        <motion.div
          className="relative w-full max-w-md mx-4 rounded-2xl border bg-background p-6 shadow-2xl overflow-hidden"
          initial={shouldReduceMotion ? {} : { scale: 0.9, opacity: 0, y: 20 }}
          animate={{ scale: 1, opacity: 1, y: 0 }}
          exit={{ scale: 0.9, opacity: 0, y: 20 }}
          transition={{ type: "spring", stiffness: 300, damping: 24 }}
        >
          {/* Decorative gradient background */}
          <motion.div
            className="pointer-events-none absolute inset-0 overflow-hidden rounded-2xl"
            initial={shouldReduceMotion ? {} : { opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.6 }}
            aria-hidden="true"
          >
            <div
              className="absolute -top-1/3 -left-1/3 h-2/3 w-2/3 rounded-full opacity-15"
              style={{ background: "radial-gradient(circle, var(--primary), transparent 70%)" }}
            />
            <div
              className="absolute -bottom-1/3 -right-1/3 h-2/3 w-2/3 rounded-full opacity-10"
              style={{ background: "radial-gradient(circle, var(--accent), transparent 70%)" }}
            />
          </motion.div>

          {/* Header */}
          <div className="relative text-center mb-5">
            <motion.div
              className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10 text-primary shadow-sm"
              initial={shouldReduceMotion ? {} : { scale: 0, rotate: -180 }}
              animate={{ scale: 1, rotate: 0 }}
              transition={{ type: "spring", stiffness: 260, damping: 20, delay: 0.1 }}
            >
              <BookOpen className="h-7 w-7" />
            </motion.div>

            <motion.p
              className="text-xs font-medium uppercase tracking-widest text-muted-foreground"
              initial={shouldReduceMotion ? {} : { opacity: 0, y: 12 }}
              animate={ready ? { opacity: 1, y: 0 } : {}}
              transition={{ type: "spring", stiffness: 300, damping: 24, delay: 0.2 }}
            >
              Welcome to
            </motion.p>

            <motion.h2
              className="text-2xl font-bold text-primary"
              initial={shouldReduceMotion ? {} : { opacity: 0, y: 12 }}
              animate={ready ? { opacity: 1, y: 0 } : {}}
              transition={{ type: "spring", stiffness: 300, damping: 24, delay: 0.28 }}
            >
              Islamic Party Games
            </motion.h2>

            <motion.p
              className="mt-2 flex items-baseline justify-center gap-2 flex-wrap text-muted-foreground"
              initial={shouldReduceMotion ? {} : { opacity: 0 }}
              animate={ready ? { opacity: 1 } : {}}
              transition={{ duration: 0.3, delay: 0.35 }}
            >
              <span className="text-sm" lang="en">Choose your language</span>
              <span className="opacity-40" aria-hidden="true">·</span>
              <span className="text-base" lang="fr">Choisissez votre langue</span>
              <span className="opacity-40" aria-hidden="true">·</span>
              <span className="text-lg" lang="ar" dir="rtl">اختر لغتك</span>
            </motion.p>
          </div>

          {/* Language cards */}
          <div
            role="radiogroup"
            aria-label="Select language"
            className="relative grid grid-cols-3 gap-3"
          >
            {languages.map((lang, index) => (
              <motion.div
                key={lang.code}
                initial={shouldReduceMotion ? {} : { opacity: 0, y: 24 }}
                animate={ready ? { opacity: 1, y: 0 } : {}}
                transition={{
                  type: "spring",
                  stiffness: 300,
                  damping: 24,
                  delay: 0.4 + index * 0.12,
                }}
              >
                <button
                  ref={(el) => {
                    cardRefs.current[index] = el
                  }}
                  type="button"
                  role="radio"
                  aria-checked={selected === lang.code}
                  tabIndex={selected === lang.code || (!selected && index === 0) ? 0 : -1}
                  onClick={() => handleSelect(lang.code)}
                  onKeyDown={(e) => handleKeyDown(e, index)}
                  className={cn(
                    "group relative flex w-full flex-col items-center gap-2 rounded-2xl border p-4 text-center cursor-pointer transition-all duration-200",
                    "bg-background/60 backdrop-blur-sm border-border/40",
                    "hover:border-primary/50 hover:shadow-lg hover:shadow-primary/5",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                    "active:scale-[0.97]",
                    selected === lang.code && "bg-primary/10 border-primary shadow-[0_0_24px_-6px_var(--primary)]",
                  )}
                >
                  {/* Shimmer sweep on selection */}
                  <AnimatePresence>
                    {selected === lang.code && !shouldReduceMotion && (
                      <motion.div
                        className="pointer-events-none absolute inset-0 overflow-hidden rounded-2xl"
                        initial={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        aria-hidden="true"
                      >
                        <motion.div
                          className="absolute inset-0 bg-gradient-to-r from-transparent via-primary/10 to-transparent"
                          initial={{ x: "-100%" }}
                          animate={{ x: "100%" }}
                          transition={{ duration: 0.6, ease: "easeInOut" }}
                        />
                      </motion.div>
                    )}
                  </AnimatePresence>

                  {/* Checkmark */}
                  <AnimatePresence>
                    {selected === lang.code && (
                      <motion.div
                        className="absolute top-2 end-2 flex h-5 w-5 items-center justify-center rounded-full bg-primary text-primary-foreground"
                        initial={shouldReduceMotion ? {} : { scale: 0 }}
                        animate={{ scale: 1 }}
                        exit={{ scale: 0 }}
                        transition={{ type: "spring", stiffness: 500, damping: 25 }}
                      >
                        <Check className="h-3 w-3" strokeWidth={3} />
                      </motion.div>
                    )}
                  </AnimatePresence>

                  {/* Flag */}
                  <motion.div
                    className="flex h-12 w-12 items-center justify-center rounded-full bg-muted/50"
                    whileHover={shouldReduceMotion ? {} : { scale: 1.1 }}
                    whileTap={shouldReduceMotion ? {} : { scale: 0.9 }}
                    transition={{ type: "spring", stiffness: 400, damping: 15 }}
                  >
                    <span className="text-3xl select-none" aria-hidden="true">
                      {lang.flag}
                    </span>
                  </motion.div>

                  <span lang={lang.code} className={cn("font-medium", lang.code === "ar" ? "text-xl" : "text-base")}>
                    {lang.fullName}
                  </span>
                </button>
              </motion.div>
            ))}
          </div>

          {/* Skip button */}
          <motion.div
            className="mt-4 text-center"
            initial={shouldReduceMotion ? {} : { opacity: 0 }}
            animate={ready ? { opacity: 1 } : {}}
            transition={{ duration: 0.3, delay: 0.65 }}
          >
            <button
              type="button"
              onClick={handleSkip}
              className="inline-flex items-center gap-1.5 rounded-full border border-border/50 px-4 py-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground hover:border-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            >
              Skip
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
          </motion.div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}
