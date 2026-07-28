import { apiRequest, apiUrl } from "@/lib/api-client"
import type { Campaign, CampaignLineage, CampaignPackage, CampaignStartResponse, HealthResponse, ProductAsset, RenderMode, VerifyResult } from "./types"

function campaignPath(jobId: string) {
  return `/campaigns/${encodeURIComponent(jobId)}`
}

export function createCampaign(topic: string, beatCount: number, mode: RenderMode, startImmediately: boolean, generateAudio: boolean) {
  return apiRequest<CampaignStartResponse>("/campaigns", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic, beat_count: beatCount, mode, start_immediately: startImmediately, generate_audio: generateAudio }),
  })
}

export function uploadProductAsset(jobId: string, file: File) {
  const body = new FormData()
  body.append("file", file)
  return apiRequest<ProductAsset>(`${campaignPath(jobId)}/assets`, { method: "POST", body })
}

export function startCampaign(jobId: string) {
  return apiRequest<CampaignStartResponse>(`${campaignPath(jobId)}/start`, { method: "POST" })
}

export function getCampaign(jobId: string) {
  return apiRequest<Campaign>(campaignPath(jobId))
}

export function getCampaignPackage(jobId: string) {
  return apiRequest<CampaignPackage>(`${campaignPath(jobId)}/package`)
}

export function getCampaignLineage(jobId: string) {
  return apiRequest<CampaignLineage>(`${campaignPath(jobId)}/lineage`)
}

export function verifyRun(runId: string) {
  return apiRequest<VerifyResult>(`/verify/${encodeURIComponent(runId)}`)
}

export function getHealth() {
  return apiRequest<HealthResponse>("/health")
}

export function streamUrl(jobId: string) {
  return apiUrl(`${campaignPath(jobId)}/stream`)
}
