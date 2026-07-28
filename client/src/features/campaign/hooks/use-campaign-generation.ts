import { useMutation } from "@tanstack/react-query"
import { createCampaign, startCampaign, uploadProductAsset } from "../api"
import type { RenderMode } from "../types"

type GenerationInput = {
  topic: string
  beatCount: number
  mode: RenderMode
  generateAudio: boolean
  files: File[]
}

export function useCampaignGeneration() {
  return useMutation({
    mutationFn: async ({ topic, beatCount, mode, generateAudio, files }: GenerationInput) => {
      const hasProducts = files.length > 0
      const campaign = await createCampaign(topic, beatCount, mode, !hasProducts, generateAudio)

      if (hasProducts) {
        await Promise.all(files.map((file) => uploadProductAsset(campaign.job_id, file)))
        await startCampaign(campaign.job_id)
      }

      return campaign.job_id
    },
  })
}
