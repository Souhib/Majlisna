import { z } from "zod"

/**
 * Turn off Zod's JIT validator compilation.
 *
 * Zod 4 compiles a fast validator with `new Function` when it can, and decides
 * whether it can by *probing*: `util.allowsEval` runs `new Function("")` inside a
 * try/catch. Under an enforced Content-Security-Policy without `'unsafe-eval'` that
 * probe is blocked — Zod catches it and falls back to the interpreted path, so
 * nothing breaks, but the browser records a `script-src`/`eval` violation on every
 * page load. Hunting that down took a while precisely because minification aliases
 * `Function` to a local, so it does not appear in the bundle as `new Function`.
 *
 * Setting `jitless` short-circuits the decision (`const fastEnabled = jit &&
 * allowsEval.value`), so the probe never runs. Same code path Zod would have taken
 * anyway under the policy, minus the violation.
 *
 * **Import this before anything that builds a schema.** `fastEnabled` is computed
 * when a schema is constructed, and the generated API schemas are built at module
 * import time. Getting the order wrong is not dangerous — it just means the probe
 * fires once, which is where we started.
 */
z.config({ jitless: true })
