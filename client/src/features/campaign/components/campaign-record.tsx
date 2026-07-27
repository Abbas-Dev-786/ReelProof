import { CircleAlert, ExternalLink, FileCheck2, ImageIcon, LoaderCircle } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { LineageTimeline } from "./lineage-timeline"
import type { Campaign, CampaignLineage, CampaignPackage } from "../types"

type CampaignRecordProps = {
  campaign: Campaign
  campaignPackage: CampaignPackage | undefined
  campaignPackageError: Error | null
  isCampaignPackageLoading: boolean
  campaignLineage: CampaignLineage | undefined
  campaignLineageError: Error | null
  isCampaignLineageLoading: boolean
  verifiedRunId?: string | null
}

function shortValue(value: string | null | undefined) {
  if (!value) return "Not available"
  return value.length > 24 ? `${value.slice(0, 14)}…${value.slice(-8)}` : value
}

function externalHttpUrl(value: string | null | undefined) {
  if (!value) return null
  try {
    const url = new URL(value)
    return url.protocol === "https:" || url.protocol === "http:" ? url.toString() : null
  } catch {
    return null
  }
}

export function CampaignRecord({
  campaign,
  campaignPackage,
  campaignPackageError,
  isCampaignPackageLoading,
  campaignLineage,
  campaignLineageError,
  isCampaignLineageLoading,
  verifiedRunId,
}: CampaignRecordProps) {
  const packageCampaign = campaignPackage?.campaign
  const manifestHash = packageCampaign?.manifest_hash ?? campaign.manifest_hash
  const manifestUrl = externalHttpUrl(packageCampaign?.manifest_uri ?? campaign.manifest_uri)
  const productAssets = campaignPackage?.product_assets ?? []
  const lineage = campaignLineage?.runs ?? campaignPackage?.provenance ?? []
  const showLineageError = Boolean(campaignLineageError && lineage.length === 0)

  return (
    <section aria-labelledby="campaign-record-heading" className="border-t border-[#e9e5de] pt-4">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-[#36333d]" id="campaign-record-heading">Campaign record</h3>
          <p className="mt-1 text-xs leading-5 text-[#817c88]">Package, uploaded products, and retained generation lineage from the API.</p>
        </div>
        <Badge variant="outline" className="border-[#e0dbe9] bg-[#faf9fd] text-[#625b74]">{lineage.length} retained runs</Badge>
      </div>

      {campaignPackageError && !campaignPackage && <Alert className="mb-4" variant="destructive"><CircleAlert /><AlertTitle>Campaign package is unavailable</AlertTitle><AlertDescription>{campaignPackageError.message}</AlertDescription></Alert>}

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-lg border border-[#e6e1da] bg-[#faf9f7] p-3">
          <div className="flex items-center gap-2 text-sm font-medium text-[#423e49]"><FileCheck2 className="size-4 text-[#6856bf]" />Final manifest</div>
          <code className="mt-2 block truncate text-[11px] text-[#716a7b]" title={manifestHash ?? undefined}>{shortValue(manifestHash)}</code>
          {manifestUrl ? <a className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-[#5d49b7] hover:text-[#493898]" href={manifestUrl} rel="noreferrer" target="_blank">Open manifest <ExternalLink className="size-3" /></a> : <p className="mt-2 text-xs text-[#817c88]">Retained with the campaign record</p>}
        </div>

        <div className="rounded-lg border border-[#e6e1da] bg-[#faf9f7] p-3">
          <div className="flex items-center gap-2 text-sm font-medium text-[#423e49]"><ImageIcon className="size-4 text-[#6856bf]" />Input products</div>
          {isCampaignPackageLoading && !campaignPackage ? <p className="mt-2 flex items-center gap-2 text-xs text-[#817c88]"><LoaderCircle className="size-3 animate-spin" />Loading uploaded assets…</p> : productAssets.length === 0 ? <p className="mt-2 text-xs text-[#817c88]">No product images were attached to this campaign.</p> : <ul className="mt-2 space-y-2">
            {productAssets.map((asset) => {
              const assetUrl = externalHttpUrl(asset.asset_url)
              return <li className="flex min-w-0 items-center justify-between gap-2" key={asset.asset_id}>
                <div className="min-w-0"><p className="truncate text-xs font-medium text-[#4d4953]" title={asset.filename}>{asset.filename}</p><code className="block truncate text-[10px] text-[#817c88]" title={asset.sha256 ?? undefined}>{shortValue(asset.sha256)}</code></div>
                {assetUrl && <a aria-label={`Open ${asset.filename}`} className="shrink-0 text-xs font-medium text-[#5d49b7] hover:text-[#493898]" href={assetUrl} rel="noreferrer" target="_blank">Open</a>}
              </li>
            })}
          </ul>}
        </div>
      </div>

      <div className="mt-4 rounded-lg border border-[#e6e1da] p-3">
        <div className="mb-3 flex items-center justify-between gap-3"><div><p className="text-sm font-medium text-[#423e49]">Generation lineage</p><p className="mt-1 text-xs text-[#817c88]">Every stored run is linked to its manifest.</p></div>{isCampaignLineageLoading && lineage.length > 0 && <LoaderCircle className="size-4 animate-spin text-[#817c88]" />}</div>
        {showLineageError ? <Alert variant="destructive"><CircleAlert /><AlertTitle>Lineage is unavailable</AlertTitle><AlertDescription>{campaignLineageError?.message}</AlertDescription></Alert> : isCampaignLineageLoading && lineage.length === 0 ? <p className="flex items-center gap-2 text-sm text-[#76727c]"><LoaderCircle className="size-4 animate-spin" />Loading lineage…</p> : <LineageTimeline lineage={lineage} verifiedRunId={verifiedRunId} />}
      </div>
    </section>
  )
}
