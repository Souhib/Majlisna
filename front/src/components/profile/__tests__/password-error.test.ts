import { describe, expect, it, vi } from "vitest"

vi.mock("@/api/client", () => ({
  getApiErrorMessage: (err: { response?: { data?: { error_key?: string } } }) => err.response?.data?.error_key ?? "errors.network",
}))

const { passwordErrorMessage } = await import("../password-error")
const t = ((key: string) => key) as unknown as Parameters<typeof passwordErrorMessage>[1]
const answered = (errorKey: string) => ({ response: { status: 401, data: { error_key: errorKey } } })

describe("passwordErrorMessage", () => {
  it("says a wrong password as a wrong password, never the login's email-and-password line (review F6)", () => {
    expect(passwordErrorMessage(answered("errors.api.invalidCredentials"), t)).toBe("profile.wrongPassword")
  })

  it("leaves every other refusal in the server's words", () => {
    expect(passwordErrorMessage(answered("errors.api.passwordTooLong"), t)).toBe("errors.api.passwordTooLong")
    expect(passwordErrorMessage(new Error("Failed to fetch"), t)).toBe("errors.network")
  })
})
