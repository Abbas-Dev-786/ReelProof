import { useEffect } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { getCampaign, streamUrl } from "../api"
import type { BeatProgress } from "../types"

type StreamOptions = {
  jobId: string | null
  enabled: boolean
  onBeatUpdate: (index: number, update: Partial<BeatProgress>) => void
  onFailed: (message: string) => void
}

type StreamEventType = "beat.started" | "beat.judged" | "beat.checkpointed" | "beat.resuming" | "beat.resumed" | "beat.completed" | "engine.completed" | "engine.failed"

type StreamEventPayload = {
  type: StreamEventType
  beat_index?: number
  passed?: boolean
  score?: number
  error?: string
}

function parseStreamEvent(message: string): StreamEventPayload {
  return JSON.parse(message) as StreamEventPayload
}

export const campaignQueryKey = (jobId: string) => ["campaign", jobId] as const

export function useCampaign(jobId: string | null) {
  return useQuery({
    queryKey: campaignQueryKey(jobId ?? "pending"),
    queryFn: () => getCampaign(jobId!),
    enabled: Boolean(jobId),
    staleTime: 10_000,
  })
}

export function useCampaignStream({ jobId, enabled, onBeatUpdate, onFailed }: StreamOptions) {
  const queryClient = useQueryClient()

  useEffect(() => {
    if (!jobId || !enabled) return

    const source = new EventSource(streamUrl(jobId))
    const refreshCampaign = () => queryClient.invalidateQueries({ queryKey: campaignQueryKey(jobId) })

    source.onmessage = (event) => {
      try {
        const payload = parseStreamEvent(event.data)
        const index = payload.beat_index ?? -1

        if (payload.type === "beat.started") onBeatUpdate(index, { state: "working" })
        if (payload.type === "beat.checkpointed" || payload.type === "beat.resuming") onBeatUpdate(index, { state: "working" })
        if (payload.type === "beat.judged") {
          onBeatUpdate(index, {
            state: payload.passed ? "passed" : "retrying",
            score: payload.score,
          })
        }
        if (payload.type === "beat.completed") onBeatUpdate(index, { state: "passed" })
        if (payload.type === "engine.completed") {
          source.close()
          void refreshCampaign()
        }
        if (payload.type === "engine.failed") {
          source.close()
          onFailed(payload.error ?? "Generation failed")
          void refreshCampaign()
        }
      } catch {
        onFailed("The generation stream returned an invalid update.")
      }
    }

    source.addEventListener("done", () => {
      source.close()
      void refreshCampaign()
    })
    source.onerror = () => {
      // EventSource reconnects and supplies Last-Event-ID automatically.
      // The server replays durable SQLite events after that cursor.
      void refreshCampaign()
    }

    return () => source.close()
  }, [enabled, jobId, onBeatUpdate, onFailed, queryClient])
}
