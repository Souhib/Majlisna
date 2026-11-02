import { useGoogleLogin, useGoogleOAuth } from "@react-oauth/google"

/**
 * `UserView.auth_provider` of a Google-only account (the backend's AUTH_PROVIDER_GOOGLE): its
 * stored password is a random value its owner never saw, so what the account confirms, it
 * confirms with Google. Once it sets a password it reads "email" (and still signs in with Google).
 */
export const GOOGLE_PROVIDER = "google"

/** Google's window closed by the player: their own choice, not an error to say. */
const GOOGLE_POPUP_CLOSED = "popup_closed"

/**
 * "Confirm with Google": asks Google for a fresh access token for the account's address
 * (`hint`), with the account chooser shown (`prompt: "select_account"`), so the act is
 * confirmed by a choice the player makes, never by a silent token. The server checks the
 * token's account against this one (`errors.api.googleAccountMismatch` otherwise).
 *
 * Runs under `WithGoogleOAuth` (Google's hooks need the provider). `ask` opens Google's popup:
 * call it from a click or a submit. `ready` waits for Google's script. A closed popup calls
 * neither callback.
 */
export function useGoogleConfirmation({ email, onToken, onRefused }: { email?: string; onToken: (accessToken: string) => void; onRefused: () => void }) {
  const { scriptLoadedSuccessfully } = useGoogleOAuth()
  const askGoogle = useGoogleLogin({
    hint: email,
    prompt: "select_account",
    onSuccess: (response) => onToken(response.access_token),
    onError: () => onRefused(),
    onNonOAuthError: (nonOAuthError) => {
      if (nonOAuthError.type !== GOOGLE_POPUP_CLOSED) onRefused()
    },
  })
  return { ask: () => askGoogle(), ready: scriptLoadedSuccessfully }
}
