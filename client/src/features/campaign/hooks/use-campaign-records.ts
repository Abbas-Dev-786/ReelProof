import { useQuery } from "@tanstack/react-query"
import { getCampaignLineage, getCampaignPackage } from "../api"
import type { CampaignStatus } from "../types"

export const campaignPackageQueryKey = (jobId: string) => ["campaign-package", jobId] as const
export const campaignLineageQueryKey = (jobId: string) => ["campaign-lineage", jobId] as const

function shouldRefresh(status: CampaignStatus | undefined) {
  return status === "pending" || status === "running"
}

export function useCampaignPackage(jobId: string | null, status: CampaignStatus | undefined) {
  return useQuery({
    queryKey: campaignPackageQueryKey(jobId ?? "pending"),
    queryFn: () => getCampaignPackage(jobId!),
    enabled: Boolean(jobId),
    staleTime: 10_000,
    refetchInterval: shouldRefresh(status) ? 5_000 : false,
  })
}

export function useCampaignLineage(jobId: string | null, status: CampaignStatus | undefined) {
  return useQuery({
    queryKey: campaignLineageQueryKey(jobId ?? "pending"),
    queryFn: () => getCampaignLineage(jobId!),
    enabled: Boolean(jobId),
    staleTime: 10_000,
    refetchInterval: shouldRefresh(status) ? 5_000 : false,
  })
}
