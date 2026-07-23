import { apiRequest, apiUrl } from "@/lib/api-client"
import type { Campaign, CampaignStatus, ProductAsset, RenderMode, VerifyResult } from "./types"

export function createCampaign(topic: string, beatCount: number, mode: RenderMode, startImmediately: boolean) {
  return apiRequest<{ job_id: string; status: CampaignStatus }>("/campaigns", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic, beat_count: beatCount, mode, start_immediately: startImmediately }),
  })
}

export function uploadProductAsset(jobId: string, file: File) {
  const body = new FormData()
  body.append("file", file)
  return apiRequest<ProductAsset>(`/campaigns/${jobId}/assets`, { method: "POST", body })
}

export function startCampaign(jobId: string) {
  return apiRequest<{ job_id: string; status: CampaignStatus }>(`/campaigns/${jobId}/start`, { method: "POST" })
}

export function getCampaign(jobId: string) {
  return apiRequest<Campaign>(`/campaigns/${jobId}`)
}

export function verifyRun(runId: string) {
  return apiRequest<VerifyResult>(`/verify/${runId}`)
}

export function streamUrl(jobId: string) {
  return apiUrl(`/campaigns/${jobId}/stream`)
}
