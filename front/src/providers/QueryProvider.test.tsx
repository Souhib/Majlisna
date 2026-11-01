import { render, screen, waitFor } from "@testing-library/react"
import { useMutation, useQuery } from "@tanstack/react-query"
import { HTTPError, type NormalizedOptions } from "ky"
import { useEffect } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

/**
 * A failed request reaches the error reporter (FR-9) unless the server refused it: a 4xx is
 * the server's verdict (not found, not allowed, a wrong PIN), said on the page, not a fault.
 */
const reportError = vi.hoisted(() => vi.fn())
vi.mock("@/lib/report-error", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/report-error")>()),
  reportError,
}))

const { QueryProvider } = await import("./QueryProvider")

function httpError(status: number): HTTPError {
  const request = new Request("http://localhost/api/v1/rooms/r1")
  return new HTTPError(new Response(null, { status }), request, {} as NormalizedOptions)
}

function FailingQuery({ error }: { error: unknown }) {
  const query = useQuery({ queryKey: ["rooms", "r1"], queryFn: () => Promise.reject(error), retry: false })
  return <p>{query.isError ? "query failed" : "loading"}</p>
}

function FailingMutation({ error }: { error: unknown }) {
  const mutation = useMutation({ mutationKey: ["rooms", "join"], mutationFn: () => Promise.reject(error) })
  const { mutate } = mutation
  useEffect(() => mutate(), [mutate])
  return <p>{mutation.isError ? "mutation failed" : "pending"}</p>
}

describe("QueryProvider error reporting", () => {
  beforeEach(() => {
    reportError.mockClear()
  })

  it("reports a query that fails with a 500", async () => {
    // Prepare
    const error = httpError(500)

    // Act
    render(
      <QueryProvider>
        <FailingQuery error={error} />
      </QueryProvider>,
    )
    await screen.findByText("query failed")

    // Assert
    expect(reportError).toHaveBeenCalledTimes(1)
    expect(reportError).toHaveBeenCalledWith(error, expect.objectContaining({ extra: { queryKey: ["rooms", "r1"] } }))
  })

  it("does not report a query the server refused with a 404", async () => {
    // Prepare / Act
    render(
      <QueryProvider>
        <FailingQuery error={httpError(404)} />
      </QueryProvider>,
    )
    await screen.findByText("query failed")

    // Assert
    expect(reportError).not.toHaveBeenCalled()
  })

  it("reports a query that failed without an answer from the server (a bug, a blocked request)", async () => {
    // Prepare
    const error = new TypeError("Failed to fetch")

    // Act
    render(
      <QueryProvider>
        <FailingQuery error={error} />
      </QueryProvider>,
    )
    await screen.findByText("query failed")

    // Assert
    expect(reportError).toHaveBeenCalledWith(error, expect.anything())
  })

  it("reports a mutation that fails with a 503 and not one refused with a 409", async () => {
    // Prepare
    const outage = httpError(503)

    // Act
    render(
      <QueryProvider>
        <FailingMutation error={outage} />
        <FailingMutation error={httpError(409)} />
      </QueryProvider>,
    )
    await waitFor(() => expect(screen.getAllByText("mutation failed")).toHaveLength(2))

    // Assert: only the outage
    expect(reportError).toHaveBeenCalledTimes(1)
    expect(reportError).toHaveBeenCalledWith(outage, expect.objectContaining({ extra: { mutationKey: ["rooms", "join"] } }))
  })
})
