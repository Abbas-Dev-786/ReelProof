import { BadgeCheck, LoaderCircle, ShieldCheck } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { CampaignDeliverables } from "./campaign-deliverables"
import { CampaignPreview } from "./campaign-preview"
import { CampaignRecord } from "./campaign-record"
import { LineageTimeline } from "./lineage-timeline"
import type { Campaign, CampaignLineage, CampaignPackage, VerifyResult } from "../types"

type CampaignResultProps = {
  campaign: Campaign
  verification: VerifyResult | undefined
  isVerifying: boolean
  campaignPackage: CampaignPackage | undefined
  campaignPackageError: Error | null
  isCampaignPackageLoading: boolean
  campaignLineage: CampaignLineage | undefined
  campaignLineageError: Error | null
  isCampaignLineageLoading: boolean
  onVerify: () => void
  onOpenVerifier: (runId: string) => void
}

export function CampaignResult({
  campaign,
  verification,
  isVerifying,
  campaignPackage,
  campaignPackageError,
  isCampaignPackageLoading,
  campaignLineage,
  campaignLineageError,
  isCampaignLineageLoading,
  onVerify,
  onOpenVerifier,
}: CampaignResultProps) {
  return (
    <Card className="overflow-hidden border border-[#e2dfd8] bg-white shadow-none">
      <CampaignPreview campaign={campaign} />
      <CardContent className="space-y-4 pt-5">
        <div>
          <Badge variant="outline" className="border-[#e1ddd5] bg-[#faf9f7] text-[#5e5967]">Ready to publish</Badge>
          <p className="mt-3 text-sm font-medium leading-6 text-[#34313b]">{campaign.suggested_caption ?? "Ready to publish"}</p>
          <p className="mt-1 text-xs leading-5 text-[#85828f]">{campaign.hashtags.map((tag) => `#${tag.replace(/^#/, "")}`).join(" ")}</p>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <Button onClick={onVerify} disabled={isVerifying || !campaign.run_id} variant="outline" className="border-[#ded8ce]">{isVerifying ? <LoaderCircle className="animate-spin" /> : <BadgeCheck />}Check integrity</Button>
          <Button disabled={!campaign.run_id} onClick={() => campaign.run_id && onOpenVerifier(campaign.run_id)} className="bg-[#7561d9] hover:bg-[#6550c5]"><ShieldCheck />View provenance</Button>
        </div>
        {verification && <div className={`rounded-lg border p-3 ${verification.verified ? "border-[#bfe7cf] bg-[#f0fbf4]" : "border-[#f3d1c8] bg-[#fff4f1]"}`}>
          <div className="flex items-center gap-2 text-sm font-medium"><ShieldCheck className={`size-4 ${verification.verified ? "text-[#2d8b5d]" : "text-[#bd5c51]"}`} />{verification.verified ? "Manifest verified" : "Verification needs review"}</div>
          <p className="mt-1 break-all text-[11px] leading-4 text-[#777482]">{verification.manifest_hash ?? campaign.manifest_hash}</p>
          {verification.lineage.length > 0 && <div className="mt-4 border-t border-[#cfe7d8] pt-3"><LineageTimeline compact lineage={verification.lineage} verifiedRunId={verification.verified ? verification.run_id : undefined} /></div>}
        </div>}
        <CampaignDeliverables campaign={campaign} />
        <CampaignRecord campaign={campaign} campaignLineage={campaignLineage} campaignLineageError={campaignLineageError} campaignPackage={campaignPackage} campaignPackageError={campaignPackageError} isCampaignLineageLoading={isCampaignLineageLoading} isCampaignPackageLoading={isCampaignPackageLoading} verifiedRunId={verification?.verified ? verification.run_id : undefined} />
      </CardContent>
    </Card>
  )
}
