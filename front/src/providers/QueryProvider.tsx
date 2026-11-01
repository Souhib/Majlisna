import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { type ReactNode, useState } from "react"
import { isReportableRequestError, reportError } from "@/lib/report-error"

interface QueryProviderProps {
  children: ReactNode
}

export function QueryProvider({ children }: QueryProviderProps) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        // A failed request reaches the error tracker, unless the server refused it (a 4xx
        // is its verdict, said on the page): lib/report-error.ts.
        queryCache: new QueryCache({
          onError: (error, query) => {
            if (isReportableRequestError(error)) reportError(error, { source: "Query failed", extra: { queryKey: query.queryKey } })
          },
        }),
        mutationCache: new MutationCache({
          onError: (error, _variables, _context, mutation) => {
            if (!isReportableRequestError(error)) return
            reportError(error, { source: "Mutation failed", extra: { mutationKey: mutation.options.mutationKey ?? "unknown" } })
          },
        }),
        defaultOptions: {
          queries: {
            staleTime: 1000 * 60 * 5, // 5 minutes
            gcTime: 1000 * 60 * 30, // 30 minutes
            retry: 1,
            refetchOnWindowFocus: false,
          },
          mutations: {
            retry: 0,
          },
        },
      }),
  )

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
}

export { useQueryClient } from "@tanstack/react-query"
