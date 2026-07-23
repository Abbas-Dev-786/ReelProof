import { Clapperboard, Play } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import type { Campaign } from "../types"

type CampaignPreviewProps = {
  campaign: Campaign
}

export function CampaignPreview({ campaign }: CampaignPreviewProps) {
  if (campaign.reel_url) {
    return (
      <div className="relative aspect-[9/12] overflow-hidden bg-[#20202b]">
        <video aria-label="Generated reel preview" className="size-full object-cover" controls playsInline preload="metadata" src={campaign.reel_url} />
        <Badge className="absolute left-4 top-4 bg-black/45 text-white hover:bg-black/45">Final reel</Badge>
      </div>
    )
  }

  return (
    <div className="relative aspect-[9/12] overflow-hidden bg-[linear-gradient(160deg,#373153_0%,#6b5ab1_44%,#e69d58_100%)] p-5 text-white">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_75%_17%,rgba(255,255,255,.35),transparent_18%),radial-gradient(circle_at_20%_80%,rgba(255,188,109,.6),transparent_32%)]" />
      <div className="relative flex h-full flex-col justify-between">
        <Badge className="w-fit bg-black/20 text-white hover:bg-black/20">Final reel</Badge>
        <div>
          <span className="mb-4 grid size-10 place-items-center rounded-xl bg-white/15"><Clapperboard className="size-5" /></span>
          <p className="text-3xl font-semibold leading-[1.02] tracking-[-0.04em]">{campaign.beat_plan?.hook ?? "Your reel is ready"}</p>
          <div className="mt-4 flex items-center gap-2 text-sm text-white/80"><Play className="size-4 fill-current" /> 9:16 {campaign.mode === "pov" ? "POV montage" : "slideshow"}</div>
        </div>
      </div>
    </div>
  )
}
