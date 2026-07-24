import { Download, Image, Play } from "lucide-react"
import type { Campaign } from "../types"

type CampaignDeliverablesProps = {
  campaign: Campaign
}

export function CampaignDeliverables({ campaign }: CampaignDeliverablesProps) {
  if (campaign.beats.length === 0) return null

  return (
    <section className="border-t border-[#e9e5de] pt-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <p className="text-sm font-semibold text-[#36333d]">{campaign.mode === "pov" ? "POV clips" : "Photo-mode assets"}</p>
        <span className="text-xs text-[#817c88]">{campaign.beats.length} scenes</span>
      </div>
      <div className="grid grid-cols-3 gap-2">
        {campaign.beats.map((beat) => {
          const assetUrl = beat.captioned_url ?? beat.image_url
          if (campaign.mode === "pov" && beat.video_url) {
            return <a className="group relative aspect-[9/16] overflow-hidden rounded-lg bg-[#20202b] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#6f5cc5]" href={beat.video_url} key={beat.index} rel="noreferrer" target="_blank">
              <video aria-label={`POV clip ${beat.index + 1}`} className="size-full object-cover" muted playsInline preload="metadata" src={beat.video_url} />
              <span className="absolute inset-x-1 bottom-1.5 flex items-center justify-center gap-1 rounded-md bg-black/55 px-1 py-1 text-[10px] font-medium text-white opacity-0 transition-opacity group-hover:opacity-100"><Play className="size-3 fill-current" />Clip {beat.index + 1}</span>
            </a>
          }
          return <a className="group relative aspect-[9/16] overflow-hidden rounded-lg bg-[#edeae5] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#6f5cc5]" href={assetUrl} key={beat.index} rel="noreferrer" target="_blank">
            <img alt={`Download beat ${beat.index + 1}`} className="size-full object-cover transition-transform duration-300 group-hover:scale-105" src={assetUrl} />
            <span className="absolute inset-x-1 bottom-1.5 flex items-center justify-center gap-1 rounded-md bg-black/55 px-1 py-1 text-[10px] font-medium text-white opacity-0 transition-opacity group-hover:opacity-100"><Image className="size-3" />Scene {beat.index + 1}</span>
          </a>
        })}
      </div>
      {campaign.reel_url && <a className="mt-3 inline-flex h-9 w-full items-center justify-center gap-2 rounded-md border border-[#ded8ce] bg-background px-3 text-sm font-medium text-foreground shadow-xs transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50" href={campaign.reel_url} rel="noreferrer" target="_blank"><Download className="size-4" />Download final MP4</a>}
    </section>
  )
}
