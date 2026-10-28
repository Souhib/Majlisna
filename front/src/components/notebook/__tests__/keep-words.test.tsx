import { fireEvent, render, screen, within } from "@testing-library/react"
import { type ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { NotebookGameWord } from "@/api/generated"
import { ColophonWordList } from "@/components/brand"
import { GameWordsList, KeepWordsAction, KeepWordToggle } from "../KeepWords"
import type { ColophonNotebook } from "../use-colophon-notebook"

const i18nState = vi.hoisted(() => ({ language: "en" }))

// t names its parameters, so an accessible name can be checked for the word it carries
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const params = Object.entries(opts ?? {}).map(([k, v]) => `${k}=${String(v)}`)
      return params.length ? `${key}(${params.join(",")})` : key
    },
    i18n: { language: i18nState.language },
  }),
}))

vi.mock("@tanstack/react-router", () => ({
  Link: ({ to, children, ...rest }: { to: string; children: ReactNode }) => (
    <a href={to} {...rest}>
      {children}
    </a>
  ),
}))

const words: NotebookGameWord[] = [
  { word: "Patience", word_display: "Patience", word_ar: "صبر", word_ar_vocalized: "صَبْر", hint: "Staying steady", kept: false, entry_id: null },
  { word: "Uhud", word_display: "Uhud", word_ar: null, word_ar_vocalized: null, hint: null, kept: true, entry_id: "e2" },
]

function fakeNotebook(over: Partial<ColophonNotebook> = {}): ColophonNotebook {
  const list = over.words ?? words
  return {
    words: list,
    isLoading: false,
    available: list.length > 0,
    allKept: list.length > 0 && list.every((w) => w.kept),
    keepAll: vi.fn(async () => {}),
    keepingAll: false,
    find: (w) => list.find((x) => x.word === w),
    toggle: vi.fn(async () => {}),
    isBusy: () => false,
    ...over,
  }
}

beforeEach(() => {
  i18nState.language = "en"
})

describe("KeepWordToggle", () => {
  it("is a toggle named after the word, pressed once kept", () => {
    // Prepare
    const notebook = fakeNotebook()

    // Act
    render(
      <>
        <KeepWordToggle notebook={notebook} word="Patience" label="Patience" />
        <KeepWordToggle notebook={notebook} word="Uhud" label="Uhud" />
      </>,
    )

    // Assert
    expect(screen.getByRole("button", { name: "notebook.colophon.keepWord(word=Patience)" })).toHaveAttribute("aria-pressed", "false")
    expect(screen.getByRole("button", { name: "notebook.colophon.keepWord(word=Uhud)" })).toHaveAttribute("aria-pressed", "true")
  })

  it("hands the word to the notebook, and ignores a tap while it is busy", () => {
    // Prepare
    const notebook = fakeNotebook()
    const busy = fakeNotebook({ isBusy: () => true })
    const { rerender } = render(<KeepWordToggle notebook={notebook} word="Patience" label="Patience" />)

    // Act
    fireEvent.click(screen.getByRole("button"))
    rerender(<KeepWordToggle notebook={busy} word="Patience" label="Patience" />)
    fireEvent.click(screen.getByRole("button"))

    // Assert
    expect(notebook.toggle).toHaveBeenCalledWith(words[0])
    expect(busy.toggle).not.toHaveBeenCalled()
    expect(screen.getByRole("button")).toHaveAttribute("aria-busy", "true")
  })

  it("renders nothing for a word the notebook does not know, or when keeping is off", () => {
    const { container, rerender } = render(<KeepWordToggle notebook={fakeNotebook()} word="Nope" label="Nope" />)
    expect(container).toBeEmptyDOMElement()
    rerender(<KeepWordToggle notebook={fakeNotebook({ available: false })} word="Patience" label="Patience" />)
    expect(container).toBeEmptyDOMElement()
  })
})

describe("KeepWordsAction", () => {
  it("is the brass button while a word is left to keep", () => {
    // Prepare
    const notebook = fakeNotebook()
    render(<KeepWordsAction notebook={notebook} />)

    // Act
    fireEvent.click(screen.getByRole("button", { name: "notebook.colophon.keep" }))

    // Assert
    expect(notebook.keepAll).toHaveBeenCalledOnce()
    expect(screen.getByRole("button", { name: "notebook.colophon.keep" })).toHaveClass("bg-primary")
  })

  it("becomes a link to the notebook once every word is kept", () => {
    render(<KeepWordsAction notebook={fakeNotebook({ words: [{ ...words[0], kept: true, entry_id: "e1" }] })} />)
    expect(screen.getByRole("link", { name: "notebook.colophon.kept" })).toHaveAttribute("href", "/notebook")
    expect(screen.queryByRole("button")).not.toBeInTheDocument()
  })

  it("says it is working while the words are kept", () => {
    render(<KeepWordsAction notebook={fakeNotebook({ keepingAll: true })} />)
    expect(screen.getByRole("button", { name: /notebook\.colophon\.keep/ })).toHaveAttribute("aria-busy", "true")
  })

  it("is not there without the words (spectator, MCQ, refused read)", () => {
    const { container } = render(<KeepWordsAction notebook={fakeNotebook({ words: [], available: false })} />)
    expect(container).toBeEmptyDOMElement()
  })
})

describe("GameWordsList", () => {
  it("lists Arabic (vocalised first), the word, the meaning and the toggle", () => {
    // Act
    render(<GameWordsList notebook={fakeNotebook()} />)

    // Assert
    const [patience, uhud] = screen.getAllByRole("listitem")
    expect(within(patience).getByText("صَبْر")).toHaveAttribute("lang", "ar")
    expect(within(patience).getByText("Patience")).toBeInTheDocument()
    expect(within(patience).getByText("Staying steady")).toHaveAttribute("dir", "auto")
    expect(within(patience).getByRole("button", { name: "notebook.colophon.keepWord(word=Patience)" })).toBeInTheDocument()
    expect(within(uhud).getByText("Uhud")).toBeInTheDocument()
  })

  it("never transliterates in the Arabic UI, and names the toggle in Arabic", () => {
    // Prepare
    i18nState.language = "ar"

    // Act
    render(<GameWordsList notebook={fakeNotebook()} />)

    // Assert
    const [patience, uhud] = screen.getAllByRole("listitem")
    expect(within(patience).queryByText("Patience")).not.toBeInTheDocument()
    expect(within(patience).getByRole("button", { name: "notebook.colophon.keepWord(word=صَبْر)" })).toBeInTheDocument()
    // a word with no Arabic form still shows what there is
    expect(within(uhud).getByText("Uhud")).toBeInTheDocument()
  })

  it("is bare warp while loading, and says so", () => {
    render(<GameWordsList notebook={fakeNotebook({ words: undefined, available: false, isLoading: true })} />)
    expect(screen.getByRole("status")).toHaveTextContent("notebook.colophon.loadingWords")
    expect(screen.queryByRole("listitem")).not.toBeInTheDocument()
  })
})

describe("ColophonWordList", () => {
  it("sets an optional control at the end of a row, and lays out rows without one as before", () => {
    // Act
    render(
      <ColophonWordList
        words={[
          { word: "صبر", translit: "Ṣabr", meaning: "Patience", action: <button type="button">keep</button> },
          { word: "حلم", translit: "Ḥilm", meaning: "Forbearance" },
        ]}
      />,
    )

    // Assert
    const [withAction, without] = screen.getAllByRole("listitem")
    expect(within(withAction).getByRole("button", { name: "keep" })).toBeInTheDocument()
    expect(withAction.className).toContain("grid-cols-[auto_minmax(0,1fr)_auto]")
    expect(without.className).toContain("grid-cols-[auto_1fr]")
    expect(within(without).queryByRole("button")).not.toBeInTheDocument()
  })
})
