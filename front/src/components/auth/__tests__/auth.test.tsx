import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import type { ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { AuthPage } from "../AuthPage"
import { PasswordInput } from "../PasswordInput"
import { compactErrors, confirmError, currentPasswordError, emailError, newPasswordError, usernameError } from "../validation"
import { Field } from "@/components/ui/field"

// --- router, API and auth stand-ins for the route components -------------------------
const navigate = vi.fn()
const search: { redirect?: string; token?: string } = {}
vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: Record<string, unknown>) => ({ options, useSearch: () => search }),
  useNavigate: () => navigate,
  useSearch: () => search,
  Link: ({ children, to, className }: { children: ReactNode; to: string; className?: string }) => (
    <a href={to} className={className}>
      {children}
    </a>
  ),
}))

const registerMutateAsync = vi.fn()
const loginMutateAsync = vi.fn()
const loginMutate = vi.fn()
const verifyEmail = vi.fn()
vi.mock("@/api/generated", () => ({
  useRegisterApiV1AuthRegisterPost: () => ({ mutateAsync: registerMutateAsync, isPending: false }),
  useLoginApiV1AuthLoginPost: () => ({ mutateAsync: loginMutateAsync, mutate: loginMutate, isPending: false }),
  verifyEmailApiV1AuthVerifyEmailPost: (...args: unknown[]) => verifyEmail(...args),
}))

const login = vi.fn()
vi.mock("@/providers/AuthProvider", () => ({ useAuth: () => ({ login }) }))
vi.mock("@/components/auth/GoogleLoginButton", () => ({ GoogleLoginButton: () => null }))
vi.mock("@/lib/analytics", () => ({ trackEvent: vi.fn() }))

describe("auth validation", () => {
  it("mirrors the server's rules and returns i18n keys", () => {
    expect(emailError("")).toBe("auth.errors.emailRequired")
    expect(emailError("not-an-email")).toBe("auth.errors.emailInvalid")
    expect(emailError(" name@example.com ")).toBeUndefined()
    expect(currentPasswordError("")).toBe("auth.errors.passwordRequired")
    expect(newPasswordError("short")).toBe("auth.passwordTooShort")
    expect(newPasswordError("12345678")).toBeUndefined()
    expect(usernameError("ab")).toBe("auth.errors.usernameLength")
    expect(usernameError("a".repeat(31))).toBe("auth.errors.usernameLength")
    expect(usernameError("two words")).toBe("auth.errors.usernameCharacters")
    expect(usernameError("a@b")).toBe("auth.errors.usernameCharacters")
    expect(usernameError("صهيب")).toBeUndefined()
    expect(confirmError("abcdefgh", "abcdefgx")).toBe("auth.passwordsDoNotMatch")
    expect(compactErrors({ email: undefined, password: "x" })).toEqual({ password: "x" })
  })
})

describe("PasswordInput", () => {
  it("starts hidden and toggles with a named, pressed, non-submit button", () => {
    // Prepare
    render(
      <Field id="password" label="Password">
        <PasswordInput />
      </Field>,
    )
    const input = screen.getByLabelText("Password")
    const toggle = screen.getByRole("button", { name: "auth.showPassword" })

    // Assert: the E2E specs read type=password and address the one submit button
    expect(input).toHaveAttribute("type", "password")
    expect(input).toHaveAttribute("id", "password")
    expect(toggle).toHaveAttribute("type", "button")
    expect(toggle).toHaveAttribute("aria-pressed", "false")

    // Act
    fireEvent.click(toggle)

    // Assert
    expect(input).toHaveAttribute("type", "text")
    expect(toggle).toHaveAttribute("aria-pressed", "true")
  })
})

describe("AuthPage", () => {
  it("titles the panel with the page's one h1 and closes it with the woven foot", () => {
    const { container } = render(
      <AuthPage title="Welcome back" footer={<a href="/auth/register">Register</a>}>
        <form />
      </AuthPage>,
    )
    expect(screen.getByRole("heading", { level: 1, name: "Welcome back" })).toBeInTheDocument()
    expect(screen.getByRole("region", { name: "Welcome back" })).toContainElement(screen.getByRole("link", { name: "Register" }))
    expect(container.querySelectorAll(".sadu-band")).toHaveLength(1)
  })
})

describe("RegisterPage", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    search.redirect = "/rooms/join?code=ABCDE&pin=1234"
  })

  async function renderRegister() {
    const { Route } = await import("@/routes/auth/register")
    const Page = (Route as unknown as { options: { component: () => ReactNode } }).options.component
    render(<Page />)
  }

  function fill(username: string, email: string, password: string) {
    fireEvent.change(document.getElementById("username") as HTMLInputElement, { target: { value: username } })
    fireEvent.change(document.getElementById("email") as HTMLInputElement, { target: { value: email } })
    fireEvent.change(document.getElementById("password") as HTMLInputElement, { target: { value: password } })
  }

  it("names what to fix in each field and sends nothing", async () => {
    // Prepare
    await renderRegister()

    // Act
    fireEvent.click(screen.getByRole("button", { name: "auth.register" }))

    // Assert
    const alerts = screen.getAllByRole("alert").map((a) => a.textContent)
    expect(alerts).toEqual(["auth.errors.usernameLength", "auth.errors.emailRequired", "auth.passwordTooShort"])
    expect(document.activeElement).toBe(document.getElementById("username"))
    expect(registerMutateAsync).not.toHaveBeenCalled()
    expect(document.getElementById("password")).toHaveAttribute("minlength", "8")
  })

  it("logs in with the new credentials, because /register returns no tokens", async () => {
    // Prepare
    registerMutateAsync.mockResolvedValue({ id: "u1", username: "maryam", email_address: "m@example.com" })
    loginMutateAsync.mockResolvedValue({
      access_token: "access",
      refresh_token: "refresh",
      expires_in: 900,
      user: { id: "u1", username: "maryam", email: "m@example.com" },
    })
    await renderRegister()
    fill("maryam", "m@example.com", "TestPass123!")

    // Act
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "auth.register" }))
    })

    // Assert
    expect(registerMutateAsync).toHaveBeenCalledWith({ data: { username: "maryam", email_address: "m@example.com", password: "TestPass123!" } })
    expect(loginMutateAsync).toHaveBeenCalledWith({ data: { email: "m@example.com", password: "TestPass123!" } })
    expect(login).toHaveBeenCalledWith("access", "refresh", 900, { id: "u1", username: "maryam", email: "m@example.com" })
    expect(navigate).toHaveBeenCalledWith({ href: "/rooms/join?code=ABCDE&pin=1234" })
  })

  it("keeps the player on the page with a way to log in when the automatic log-in fails", async () => {
    // Prepare
    registerMutateAsync.mockResolvedValue({ id: "u1" })
    loginMutateAsync.mockRejectedValue(new Error("Verify your email first"))
    await renderRegister()
    fill("maryam", "m@example.com", "TestPass123!")

    // Act
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "auth.register" }))
    })

    // Assert
    expect(login).not.toHaveBeenCalled()
    expect(navigate).not.toHaveBeenCalled()
    expect(screen.getByRole("status")).toHaveTextContent("auth.accountCreated")
    expect(screen.getByRole("status")).toHaveTextContent("Verify your email first")
  })

  it("shows the server's refusal in the form-error alert the E2E specs read", async () => {
    // Prepare
    registerMutateAsync.mockRejectedValue(new Error("This email is already registered"))
    await renderRegister()
    fill("maryam", "m@example.com", "TestPass123!")

    // Act
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "auth.register" }))
    })

    // Assert
    expect(screen.getByTestId("form-error")).toHaveTextContent("This email is already registered")
    expect(loginMutateAsync).not.toHaveBeenCalled()
  })
})

describe("LoginPage", () => {
  it("checks the fields before calling the API", async () => {
    // Prepare
    vi.clearAllMocks()
    search.redirect = undefined
    const { Route } = await import("@/routes/auth/login")
    const Page = (Route as unknown as { options: { component: () => ReactNode } }).options.component
    render(<Page />)

    // Act: an address without a domain
    fireEvent.change(document.getElementById("email") as HTMLInputElement, { target: { value: "not-an-email" } })
    fireEvent.click(screen.getByRole("button", { name: "auth.login" }))

    // Assert
    expect(screen.getAllByRole("alert").map((a) => a.textContent)).toEqual(["auth.errors.emailInvalid", "auth.errors.passwordRequired"])
    expect(loginMutate).not.toHaveBeenCalled()

    // Act: fixed
    fireEvent.change(document.getElementById("email") as HTMLInputElement, { target: { value: "m@example.com" } })
    fireEvent.change(document.getElementById("password") as HTMLInputElement, { target: { value: "secret" } })
    fireEvent.click(screen.getByRole("button", { name: "auth.login" }))

    // Assert
    expect(screen.queryAllByRole("alert")).toHaveLength(0)
    expect(loginMutate).toHaveBeenCalledWith({ data: { email: "m@example.com", password: "secret" } })
  })

  it("tabs from the email to the password before reaching 'Forgot password?'", async () => {
    // Prepare
    search.redirect = undefined
    const { Route } = await import("@/routes/auth/login")
    const Page = (Route as unknown as { options: { component: () => ReactNode } }).options.component
    render(<Page />)

    // Act: the document's tab order (no positive tabindex anywhere, so DOM order)
    const focusable = Array.from(document.querySelectorAll<HTMLElement>("a[href], input, button")).filter((el) => el.tabIndex >= 0)
    const order = focusable.map((el) => el.id || el.getAttribute("href") || "")

    // Assert
    expect(order.indexOf("email")).toBeLessThan(order.indexOf("password"))
    expect(order.indexOf("password")).toBeLessThan(order.indexOf("/auth/forgot-password"))
    expect(document.querySelector("[tabindex]:not([tabindex='0']):not([tabindex='-1'])")).toBeNull()
  })
})

describe("VerifyEmailPage", () => {
  it("posts its token once, however often it re-renders", async () => {
    // Prepare
    vi.clearAllMocks()
    search.token = "tok-1"
    verifyEmail.mockResolvedValue({})
    const { Route } = await import("@/routes/auth/verify-email")
    const Page = (Route as unknown as { options: { component: () => ReactNode } }).options.component

    // Act
    const { rerender } = render(<Page />)
    rerender(<Page />)

    // Assert
    await waitFor(() => expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("auth.emailVerified"))
    expect(verifyEmail).toHaveBeenCalledTimes(1)
    expect(verifyEmail).toHaveBeenCalledWith({ token: "tok-1" })
  })
})
