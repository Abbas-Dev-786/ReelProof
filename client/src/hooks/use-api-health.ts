import { useQuery } from "@tanstack/react-query"
import { getHealth } from "@/features/campaign/api"

export const apiHealthQueryKey = ["api-health"] as const

export function useApiHealth() {
  return useQuery({
    queryKey: apiHealthQueryKey,
    queryFn: getHealth,
    staleTime: 15_000,
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
    retry: false,
  })
}
