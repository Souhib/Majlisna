import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { type ComponentType, type ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

/**
 * The reset and verification links (SEC F06): the token is read once, kept in memory, and
 * dropped from the address at once, so analytics, the history and a screenshot never hold
 * a usable token. The folder starts with "-" so the router's file scan leaves it alone.
 */
const router = vi.hoisted(() => ({ search: { token: "" } }))
vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: { component: ComponentType }) => ({ options, useSearch: () => router.search }),
  useSearch: () => router.search,
  Link: ({ children, to, className }: { children: ReactNode; to: string; className?: string }) => (
    <a href={to} className={className}>
      {children}
    </a>
  ),
}))

const api = vi.hoisted(() => ({ resetMutate: vi.fn(), resetOptions: {} as { mutation?: { onError?: (e: unknown) => void } }, verifyEmail: vi.fn() }))
vi.mock("@/api/generated", () => ({
  useResetPasswordApiV1AuthResetPasswordPost: (options: typeof api.resetOptions) => {
    api.resetOptions = options
    return { mutate: api.resetMutate, isPending: false }
  },
  verifyEmailApiV1AuthVerifyEmailPost: (...args: unknown[]) => api.verifyEmail(...args),
}))
vi.mock("@/i18n", () => ({ default: { t: (key: string) => key } }))

async function pageOf(path: string): Promise<ComponentType> {
  const { Route } = await import(path)
  return (Route as unknown as { options: { component: ComponentType } }).options.component
}

/** Follow a link from an email: the address the player opened, and what the router read from it. */
function followLink(path: string, token: string) {
  window.history.replaceState({ __TSR_key: "k" }, "", `${path}?token=${token}`)
  router.search = { token }
}

/** What TanStack Router does once the address changes: the page re-renders with the new search. */
function routerReadsTheAddress() {
  router.search = { token: new URLSearchParams(window.location.search).get("token") ?? "" }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe("the reset-password link", () => {
  it("drops the token from the address right away, and the reset still posts it", async () => {
    // Prepare
    followLink("/auth/reset-password", "reset-abc")
    const Page = await pageOf("@/routes/auth/reset-password")

    // Act: the page mounts, then the router re-reads the cleaned address
    const { rerender } = render(<Page />)
    expect(window.location.search).not.toContain("token=")
    expect(window.location.href).not.toContain("reset-abc")
    routerReadsTheAddress()
    rerender(<Page />)
    fireEvent.change(screen.getByLabelText("auth.newPassword"), { target: { value: "NewPass123" } })
    fireEvent.change(screen.getByLabelText("auth.confirmPassword"), { target: { value: "NewPass123" } })
    fireEvent.click(screen.getByRole("button", { name: "auth.saveNewPassword" }))

    // Assert: the form is still there and the token came from memory
    expect(api.resetMutate).toHaveBeenCalledWith({ data: { token: "reset-abc", new_password: "NewPass123" } })
  })

  it("keeps the token for a second try after a failed one", async () => {
    followLink("/auth/reset-password", "reset-def")
    const Page = await pageOf("@/routes/auth/reset-password")
    render(<Page />)
    routerReadsTheAddress()
    fireEvent.change(screen.getByLabelText("auth.newPassword"), { target: { value: "NewPass123" } })
    fireEvent.change(screen.getByLabelText("auth.confirmPassword"), { target: { value: "NewPass123" } })

    // Act: the first try gets no answer
    fireEvent.click(screen.getByRole("button", { name: "auth.saveNewPassword" }))
    act(() => api.resetOptions.mutation?.onError?.(new TypeError("Failed to fetch")))

    // Assert: said in the page's words, never the browser's
    expect(screen.getByTestId("form-error")).toHaveTextContent("errors.network")

    // Act: the second goes
    fireEvent.click(screen.getByRole("button", { name: "auth.saveNewPassword" }))

    // Assert
    expect(api.resetMutate).toHaveBeenCalledTimes(2)
    expect(api.resetMutate).toHaveBeenLastCalledWith({ data: { token: "reset-def", new_password: "NewPass123" } })
  })

  it("still says a link without a token is not valid", async () => {
    window.history.replaceState(null, "", "/auth/reset-password")
    router.search = { token: "" }
    const Page = await pageOf("@/routes/auth/reset-password")

    render(<Page />)

    expect(screen.getByText("auth.invalidOrExpiredToken")).toBeInTheDocument()
  })
})

describe("the verify-email link", () => {
  it("drops the token from the address right away, and posts it once", async () => {
    // Prepare
    followLink("/auth/verify-email", "verify-abc")
    api.verifyEmail.mockResolvedValue({})
    const Page = await pageOf("@/routes/auth/verify-email")

    // Act
    const { rerender } = render(<Page />)
    expect(window.location.search).not.toContain("token=")
    routerReadsTheAddress()
    rerender(<Page />)

    // Assert
    await waitFor(() => expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("auth.emailVerified"))
    expect(api.verifyEmail).toHaveBeenCalledTimes(1)
    expect(api.verifyEmail).toHaveBeenCalledWith({ token: "verify-abc" })
  })

  it("offers to try again when the request got no answer, with the token kept in memory", async () => {
    // Prepare: the address no longer has the token, so a reload could not retry it
    followLink("/auth/verify-email", "verify-def")
    api.verifyEmail.mockRejectedValueOnce(new TypeError("Failed to fetch")).mockResolvedValueOnce({})
    const Page = await pageOf("@/routes/auth/verify-email")
    render(<Page />)
    routerReadsTheAddress()
    const retry = await screen.findByRole("button", { name: "common.retry" })
    expect(screen.getByText("errors.network")).toBeInTheDocument()

    // Act
    fireEvent.click(retry)

    // Assert
    await waitFor(() => expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("auth.emailVerified"))
    expect(api.verifyEmail).toHaveBeenCalledTimes(2)
    expect(api.verifyEmail).toHaveBeenLastCalledWith({ token: "verify-def" })
  })

  it("says a refused link in the page's words, with no retry", async () => {
    followLink("/auth/verify-email", "verify-spent")
    api.verifyEmail.mockRejectedValue({ response: { status: 400, data: { error_key: "errors.api.invalidOrExpiredToken" } } })
    const Page = await pageOf("@/routes/auth/verify-email")

    render(<Page />)

    await waitFor(() => expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("auth.verificationFailed"))
    expect(screen.getByText("auth.invalidOrExpiredToken")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "common.retry" })).not.toBeInTheDocument()
  })
})
