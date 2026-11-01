import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { answer, httpError, requestsTo, resetFakeApi } from "@/components/notebook/__tests__/fake-api"

/**
 * Account deletion (SEC F14): a password account confirms with its password, a Google
 * account with a fresh Google token, whose `sub` the server compares with the account's.
 * The real generated hooks run over a fake client, and the real `@react-oauth/google`
 * over a stand-in for Google's script (happy-dom never fetches it).
 */
const navigate = vi.fn()
const logout = vi.fn()
vi.mock("@tanstack/react-router", () => ({ useNavigate: () => navigate }))
vi.mock("@/api/client", async () => (await import("@/components/notebook/__tests__/fake-api")).clientModule)
vi.mock("@/providers/AuthProvider", () => ({
  useAuth: () => ({ user: { id: "u1", username: "Yusuf", email: "yusuf@gmail.com" }, logout }),
}))
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }))

const { DeleteAccount } = await import("../DeleteAccount")

const ME = "GET /api/v1/auth/me"
const DELETE = "DELETE /api/v1/users/me/account"
const GSI_SCRIPT = 'script[src^="https://accounts.google.com/gsi/client"]'
const CLIENT_ID = "test-client.apps.googleusercontent.com"

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
const initTokenClient = vi.fn((config: TokenClientConfig) => ({ requestAccessToken: vi.fn(() => googleAnswers(config)) }))

const googleAccount = {
  id: "u1",
  username: "Yusuf",
  email_address: "yusuf@gmail.com",
  auth_provider: "google",
  google_sub: "google-sub-1",
}
const passwordAccount = { ...googleAccount, auth_provider: "email", google_sub: null }

async function renderDeleteAccount() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  await act(async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <DeleteAccount />
      </QueryClientProvider>,
    )
  })
}

async function openDialog() {
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "profile.deleteAccountOpen" }))
  })
  return screen.findByRole("alertdialog")
}

async function confirmWithGoogle(dialog: HTMLElement) {
  const button = await within(dialog).findByRole("button", { name: /^profile\.deleteAccountConfirmWithGoogle/ })
  // the button waits for Google's script
  await waitFor(() => expect(button).not.toHaveAttribute("aria-busy"))
  await act(async () => {
    fireEvent.click(button)
  })
}

describe("DeleteAccount", () => {
  beforeEach(() => {
    resetFakeApi()
    vi.clearAllMocks()
    googleAnswers = (config) => config.callback({ access_token: "google-token" })
    ;(window as unknown as { google?: unknown }).google = { accounts: { oauth2: { initTokenClient } } }
    vi.stubEnv("VITE_GOOGLE_CLIENT_ID", CLIENT_ID)
    answer(DELETE, () => undefined)
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    delete (window as unknown as { google?: unknown }).google
  })

  it("asks a Google account's owner for a Google token, and sends it instead of a password", async () => {
    // Prepare
    answer(ME, () => googleAccount)
    await renderDeleteAccount()

    // Act
    const dialog = await openDialog()

    // Assert: no password to type, Google's confirmation said instead
    expect(await within(dialog).findByText("profile.deleteAccountWarningGoogle")).toBeInTheDocument()
    expect(within(dialog).queryByLabelText("profile.password")).toBeNull()

    // Act
    await confirmWithGoogle(dialog)

    // Assert: Google was asked for this account (the address as the hint), the token was sent
    expect(initTokenClient).toHaveBeenCalledWith(expect.objectContaining({ client_id: CLIENT_ID, hint: "yusuf@gmail.com" }))
    await waitFor(() => expect(requestsTo(DELETE)).toHaveLength(1))
    expect(requestsTo(DELETE)[0].data).toEqual({ google_access_token: "google-token" })
    await waitFor(() => expect(logout).toHaveBeenCalledTimes(1))
    expect(navigate).toHaveBeenCalledWith({ to: "/" })
  })

  it("loads Google's script only once the dialog is open, and drops it when it closes", async () => {
    // Prepare
    answer(ME, () => googleAccount)
    await renderDeleteAccount()

    // Assert: the profile page alone asks Google for nothing (and reads nothing more)
    expect(document.querySelector(GSI_SCRIPT)).toBeNull()
    expect(requestsTo(ME)).toHaveLength(0)

    // Act
    const dialog = await openDialog()
    await within(dialog).findByRole("button", { name: /^profile\.deleteAccountConfirmWithGoogle/ })

    // Assert
    expect(document.querySelectorAll(GSI_SCRIPT)).toHaveLength(1)

    // Act: Cancel
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: "common.cancel" }))
    })

    // Assert
    await waitFor(() => expect(document.querySelector(GSI_SCRIPT)).toBeNull())
    expect(requestsTo(DELETE)).toHaveLength(0)
  })

  it("keeps the password field for an account with a password, and never loads Google's script", async () => {
    // Prepare
    answer(ME, () => passwordAccount)
    await renderDeleteAccount()
    const dialog = await openDialog()

    // Act
    const field = await within(dialog).findByLabelText("profile.password")
    fireEvent.change(field, { target: { value: "my-secret-pass" } })
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: "profile.deleteAccountConfirm" }))
    })

    // Assert
    await waitFor(() => expect(requestsTo(DELETE)).toHaveLength(1))
    expect(requestsTo(DELETE)[0].data).toEqual({ password: "my-secret-pass" })
    expect(within(dialog).queryByRole("button", { name: /deleteAccountConfirmWithGoogle/ })).toBeNull()
    expect(document.querySelector(GSI_SCRIPT)).toBeNull()
    await waitFor(() => expect(logout).toHaveBeenCalledTimes(1))
  })

  it("says a wrong password in the password's words, not the login's (review F6)", async () => {
    // Prepare — the server answers the login's 401: "Please check your email and password."
    answer(ME, () => passwordAccount)
    answer(DELETE, () => {
      throw httpError(401, { error: "InvalidCredentialsError", error_key: "errors.api.invalidCredentials" })
    })
    await renderDeleteAccount()
    const dialog = await openDialog()
    fireEvent.change(await within(dialog).findByLabelText("profile.password"), { target: { value: "not-my-pass" } })

    // Act
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: "profile.deleteAccountConfirm" }))
    })

    // Assert — there is no email in this form
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("profile.wrongPassword")
    expect(within(dialog).getByRole("alert")).not.toHaveTextContent("errors.api.invalidCredentials")
    expect(logout).not.toHaveBeenCalled()
  })

  it("says the server's refusal of another Google account, and keeps the account", async () => {
    // Prepare: the token belongs to another Google account
    answer(ME, () => googleAccount)
    answer(DELETE, () => {
      throw httpError(403, { error: "GoogleAccountMismatchError", error_key: "errors.api.googleAccountMismatch" })
    })
    await renderDeleteAccount()
    const dialog = await openDialog()

    // Act
    await confirmWithGoogle(dialog)

    // Assert: said in the dialog, translated through its error key
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("errors.api.googleAccountMismatch")
    expect(logout).not.toHaveBeenCalled()
    expect(navigate).not.toHaveBeenCalled()
    expect(screen.getByRole("alertdialog")).toBeInTheDocument()
  })

  it("says it when Google refuses, sends nothing, and says nothing when the popup is closed", async () => {
    // Prepare
    answer(ME, () => googleAccount)
    googleAnswers = (config) => config.callback({ error: "access_denied" })
    await renderDeleteAccount()
    const dialog = await openDialog()

    // Act
    await confirmWithGoogle(dialog)

    // Assert
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("profile.deleteAccountGoogleFailed")
    expect(requestsTo(DELETE)).toHaveLength(0)

    // Act: the player closes Google's window on the next try
    googleAnswers = (config) => config.error_callback?.({ type: "popup_closed" })
    await confirmWithGoogle(dialog)

    // Assert: their own choice, not an error
    expect(within(dialog).queryByRole("alert")).toBeNull()
    expect(requestsTo(DELETE)).toHaveLength(0)
  })

  it("falls back to the password in a build without a Google client id", async () => {
    // Prepare
    vi.stubEnv("VITE_GOOGLE_CLIENT_ID", "")
    answer(ME, () => googleAccount)
    await renderDeleteAccount()

    // Act
    const dialog = await openDialog()

    // Assert
    expect(await within(dialog).findByLabelText("profile.password")).toBeInTheDocument()
    expect(document.querySelector(GSI_SCRIPT)).toBeNull()
  })

  it("says a failed read of the account in the dialog, with Retry", async () => {
    // Prepare
    answer(ME, () => {
      throw httpError(500, { error_key: "errors.api.internalServer" })
    })
    await renderDeleteAccount()
    const dialog = await openDialog()

    // Assert
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("errors.api.internalServer")
    expect(within(dialog).queryByLabelText("profile.password")).toBeNull()

    // Act
    answer(ME, () => passwordAccount)
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: "common.retry" }))
    })

    // Assert
    expect(await within(dialog).findByLabelText("profile.password")).toBeInTheDocument()
  })
})
