import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import type { ReactNode } from "react"
import { toast } from "sonner"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { answer, httpError, requestsTo, resetFakeApi } from "@/components/notebook/__tests__/fake-api"

/**
 * "Change password" for every account: an account with a password confirms with it; a
 * Google-only account (whose stored password is a random value it never saw) chooses one
 * and confirms with Google, after which it signs in with either. The real generated hooks
 * run over a fake client, and the real `@react-oauth/google` over a stand-in for Google's
 * script (happy-dom never fetches it), as in DeleteAccount.test.tsx.
 */
vi.mock("@tanstack/react-router", () => ({
  Link: ({ to, children, ...rest }: { to: string; children: ReactNode }) => (
    <a href={to} {...rest}>
      {children}
    </a>
  ),
}))
vi.mock("@/api/client", async () => (await import("@/components/notebook/__tests__/fake-api")).clientModule)
vi.mock("@/providers/AuthProvider", () => ({
  useAuth: () => ({ user: { id: "u1", username: "Yusuf", email: "yusuf@gmail.com" } }),
}))
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }))

const { ChangePassword } = await import("../ChangePassword")

const ME = "GET /api/v1/auth/me"
const PATCH = "PATCH /api/v1/users/u1/password"
const GSI_SCRIPT = 'script[src^="https://accounts.google.com/gsi/client"]'
const CLIENT_ID = "test-client.apps.googleusercontent.com"
const NEW_PASSWORD = "Chosen-Passw0rd!"

// happy-dom never fetches scripts in tests: let the disabled load read as a success, so
// the provider reports Google's script as loaded (the login tests do the same).
const happyDOM = (window as unknown as { happyDOM?: { settings: { handleDisabledFileLoadingAsSuccess: boolean } } }).happyDOM
if (happyDOM) happyDOM.settings.handleDisabledFileLoadingAsSuccess = true

interface TokenClientConfig {
  client_id: string
  hint?: string
  prompt?: string
  callback: (response: { access_token?: string; error?: string }) => void
  error_callback?: (error: { type: string }) => void
}

/** What Google's popup answers when the token is asked for. */
let googleAnswers: (config: TokenClientConfig) => void = (config) => config.callback({ access_token: "google-token" })
const requestAccessToken = vi.fn()
const initTokenClient = vi.fn((config: TokenClientConfig) => ({
  requestAccessToken: requestAccessToken.mockImplementation(() => googleAnswers(config)),
}))

const googleAccount = {
  id: "u1",
  username: "Yusuf",
  email_address: "yusuf@gmail.com",
  auth_provider: "google",
  google_sub: "google-sub-1",
}
const passwordAccount = { ...googleAccount, auth_provider: "email", google_sub: null }

async function renderChangePassword() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  await act(async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <ChangePassword />
      </QueryClientProvider>,
    )
  })
}

async function openForm() {
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "profile.changePassword" }))
  })
}

async function confirmWithGoogle() {
  const button = await screen.findByRole("button", { name: /^profile\.passwordConfirmWithGoogle/ })
  // the button waits for Google's script
  await waitFor(() => expect(button).not.toHaveAttribute("aria-busy"))
  await act(async () => {
    fireEvent.click(button)
  })
}

describe("ChangePassword", () => {
  beforeEach(() => {
    resetFakeApi()
    vi.clearAllMocks()
    googleAnswers = (config) => config.callback({ access_token: "google-token" })
    ;(window as unknown as { google?: unknown }).google = { accounts: { oauth2: { initTokenClient } } }
    vi.stubEnv("VITE_GOOGLE_CLIENT_ID", CLIENT_ID)
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    delete (window as unknown as { google?: unknown }).google
  })

  it("keeps the current password for an account that has one, and never loads Google's script", async () => {
    // Prepare
    answer(ME, () => passwordAccount)
    answer(PATCH, () => passwordAccount)
    await renderChangePassword()
    await openForm()

    // Act
    fireEvent.change(await screen.findByLabelText("profile.currentPasswordLabel"), { target: { value: "my-old-pass" } })
    fireEvent.change(screen.getByLabelText("profile.newPasswordLabel"), { target: { value: NEW_PASSWORD } })
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "common.save" }))
    })

    // Assert
    await waitFor(() => expect(requestsTo(PATCH)).toHaveLength(1))
    expect(requestsTo(PATCH)[0].data).toEqual({ current_password: "my-old-pass", new_password: NEW_PASSWORD })
    expect(toast.success).toHaveBeenCalledWith("profile.passwordChanged")
    expect(screen.queryByRole("button", { name: /passwordConfirmWithGoogle/ })).toBeNull()
    expect(document.querySelector(GSI_SCRIPT)).toBeNull()
  })

  it("says a wrong current password in the password's words, not the login's (review F6)", async () => {
    // Prepare — the server answers the login's 401: "Please check your email and password."
    answer(ME, () => passwordAccount)
    answer(PATCH, () => {
      throw httpError(401, { error: "InvalidCredentialsError", error_key: "errors.api.invalidCredentials" })
    })
    await renderChangePassword()
    await openForm()
    fireEvent.change(await screen.findByLabelText("profile.currentPasswordLabel"), { target: { value: "not-my-pass" } })
    fireEvent.change(screen.getByLabelText("profile.newPasswordLabel"), { target: { value: NEW_PASSWORD } })

    // Act
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "common.save" }))
    })

    // Assert
    expect(await screen.findByText("profile.wrongPassword")).toBeInTheDocument()
    expect(toast.success).not.toHaveBeenCalled()
  })

  it("asks a Google-only account for a new password and Google's confirmation, never a current password", async () => {
    // Prepare
    answer(ME, () => googleAccount)
    answer(PATCH, () => ({ ...googleAccount, auth_provider: "email" }))
    await renderChangePassword()

    // Act
    await openForm()

    // Assert: what the form says, and no current password to type
    expect(await screen.findByText("profile.passwordGoogleIntro")).toBeInTheDocument()
    expect(screen.queryByLabelText("profile.currentPasswordLabel")).toBeNull()

    // Act
    fireEvent.change(screen.getByLabelText("profile.newPasswordLabel"), { target: { value: NEW_PASSWORD } })
    await confirmWithGoogle()

    // Assert: Google was asked for this account, its token sent with the new password
    expect(initTokenClient).toHaveBeenCalledWith(expect.objectContaining({ client_id: CLIENT_ID, hint: "yusuf@gmail.com", prompt: "select_account" }))
    await waitFor(() => expect(requestsTo(PATCH)).toHaveLength(1))
    expect(requestsTo(PATCH)[0].data).toEqual({ google_access_token: "google-token", new_password: NEW_PASSWORD })
    // ...and the page says the password is set
    expect(toast.success).toHaveBeenCalledWith("profile.passwordSet")
  })

  it("asks the account for its password from then on", async () => {
    // Prepare: a Google-only account sets its password
    answer(ME, () => googleAccount)
    answer(PATCH, () => ({ ...googleAccount, auth_provider: "email" }))
    await renderChangePassword()
    await openForm()
    fireEvent.change(await screen.findByLabelText("profile.newPasswordLabel"), { target: { value: NEW_PASSWORD } })
    await confirmWithGoogle()
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("profile.passwordSet"))
    // from now on /auth/me never answers: what the form shows is what the change wrote back
    answer(ME, () => new Promise(() => {}))

    // Act: "Change password" again
    await openForm()

    // Assert: the account has a password now (the answer is the account), Google's script is gone
    expect(await screen.findByLabelText("profile.currentPasswordLabel")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /passwordConfirmWithGoogle/ })).toBeNull()
    await waitFor(() => expect(document.querySelector(GSI_SCRIPT)).toBeNull())
  })

  it("checks the new password before asking Google", async () => {
    // Prepare
    answer(ME, () => googleAccount)
    await renderChangePassword()
    await openForm()
    fireEvent.change(await screen.findByLabelText("profile.newPasswordLabel"), { target: { value: "short" } })

    // Act
    await confirmWithGoogle()

    // Assert
    expect(await screen.findByText("profile.passwordTooShort")).toBeInTheDocument()
    expect(requestAccessToken).not.toHaveBeenCalled()
    expect(requestsTo(PATCH)).toHaveLength(0)
  })

  it("loads Google's script only while the form is open, and reads the account only then", async () => {
    // Prepare
    answer(ME, () => googleAccount)
    await renderChangePassword()

    // Assert: the profile page alone asks Google for nothing (and reads nothing more)
    expect(document.querySelector(GSI_SCRIPT)).toBeNull()
    expect(requestsTo(ME)).toHaveLength(0)

    // Act
    await openForm()
    await screen.findByRole("button", { name: /^profile\.passwordConfirmWithGoogle/ })

    // Assert
    expect(document.querySelectorAll(GSI_SCRIPT)).toHaveLength(1)

    // Act: Cancel
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "common.cancel" }))
    })

    // Assert
    await waitFor(() => expect(document.querySelector(GSI_SCRIPT)).toBeNull())
    expect(requestsTo(PATCH)).toHaveLength(0)
  })

  it("says the server's refusal of another Google account, and keeps the form", async () => {
    // Prepare
    answer(ME, () => googleAccount)
    answer(PATCH, () => {
      throw httpError(403, { error: "GoogleAccountMismatchError", error_key: "errors.api.googleAccountMismatch" })
    })
    await renderChangePassword()
    await openForm()
    fireEvent.change(await screen.findByLabelText("profile.newPasswordLabel"), { target: { value: NEW_PASSWORD } })

    // Act
    await confirmWithGoogle()

    // Assert
    expect(await screen.findByRole("alert")).toHaveTextContent("errors.api.googleAccountMismatch")
    expect(toast.success).not.toHaveBeenCalled()
    expect(screen.getByLabelText("profile.newPasswordLabel")).toBeInTheDocument()
  })

  it("says it when Google refuses, sends nothing, and says nothing when the popup is closed", async () => {
    // Prepare
    answer(ME, () => googleAccount)
    googleAnswers = (config) => config.callback({ error: "access_denied" })
    await renderChangePassword()
    await openForm()
    fireEvent.change(await screen.findByLabelText("profile.newPasswordLabel"), { target: { value: NEW_PASSWORD } })

    // Act
    await confirmWithGoogle()

    // Assert
    expect(await screen.findByRole("alert")).toHaveTextContent("profile.passwordGoogleFailed")
    expect(requestsTo(PATCH)).toHaveLength(0)

    // Act: the player closes Google's window on the next try
    googleAnswers = (config) => config.error_callback?.({ type: "popup_closed" })
    await confirmWithGoogle()

    // Assert: their own choice, not an error
    expect(screen.queryByRole("alert")).toBeNull()
    expect(requestsTo(PATCH)).toHaveLength(0)
  })

  it("offers the emailed link in a build without a Google client id", async () => {
    // Prepare
    vi.stubEnv("VITE_GOOGLE_CLIENT_ID", "")
    answer(ME, () => googleAccount)
    await renderChangePassword()

    // Act
    await openForm()

    // Assert
    expect(await screen.findByText("profile.passwordSetByEmail")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "profile.passwordSetByEmailLink" })).toHaveAttribute("href", "/auth/forgot-password")
    expect(screen.queryByLabelText("profile.currentPasswordLabel")).toBeNull()
    expect(document.querySelector(GSI_SCRIPT)).toBeNull()
  })

  it("says a failed read of the account, with Retry", async () => {
    // Prepare
    answer(ME, () => {
      throw httpError(500, { error_key: "errors.api.internalServer" })
    })
    await renderChangePassword()
    await openForm()

    // Assert
    expect(await screen.findByRole("alert")).toHaveTextContent("errors.api.internalServer")

    // Act
    answer(ME, () => passwordAccount)
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "common.retry" }))
    })

    // Assert
    expect(await screen.findByLabelText("profile.currentPasswordLabel")).toBeInTheDocument()
  })
})
