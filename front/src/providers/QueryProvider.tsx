import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { type ReactNode, useState } from "react"

interface QueryProviderProps {
  children: ReactNode
}

export function QueryProvider({ children }: QueryProviderProps) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        queryCache: new QueryCache({
          onError: (error, query) => {
            console.error(`Query failed [${JSON.stringify(query.queryKey)}]:`, error)
          },
        }),
        mutationCache: new MutationCache({
          onError: (error, _variables, _context, mutation) => {
            console.error(
              `Mutation failed [${mutation.options.mutationKey ? JSON.stringify(mutation.options.mutationKey) : "unknown"}]:`,
              error,
            )
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
