export type RenderMode = "slideshow" | "pov"

export type CampaignStatus = "pending" | "running" | "done" | "failed"

export type HealthResponse = {
  status: string
}

export type CampaignStartResponse = {
  job_id: string
  status: CampaignStatus
}

export type BeatState = "waiting" | "working" | "passed" | "retrying"

export type Beat = {
  index: number
  concept: string
  caption: string
  vo?: string | null
}

export type Campaign = {
  job_id: string
  topic: string
  mode: RenderMode
  status: CampaignStatus
  generate_audio: boolean
  beat_plan?: {
    hook: string
    beats: Beat[]
    suggested_caption: string
    hashtags: string[]
  } | null
  beats: Array<{
    index: number
    image_url: string
    video_url?: string | null
    captioned_url?: string | null
    judge_score?: number | null
    judge_iterations: number
    passed: boolean
  }>
  reel_url?: string | null
  music_url?: string | null
  suggested_caption?: string | null
  hashtags: string[]
  manifest_hash?: string | null
  manifest_uri?: string | null
  run_id?: string | null
  total_cost_usd?: number | null
  error?: string | null
}

export type LineageEntry = {
  run_id: string
  manifest_hash: string
  manifest_uri?: string | null
  parent_run_id?: string | null
  created_at?: string | null
}

export type ProductAsset = {
  asset_id: string
  filename: string
  media_type: string
  asset_url: string
  sha256?: string | null
  run_id: string
  manifest_hash: string
  manifest_uri?: string | null
}

export type CampaignPackage = {
  job_id: string
  campaign: Campaign
  product_assets: ProductAsset[]
  provenance: LineageEntry[]
}

export type CampaignLineage = {
  job_id: string
  runs: LineageEntry[]
}

export type VerifyResult = {
  run_id: string
  verified: boolean
  manifest_hash?: string | null
  manifest_uri?: string | null
  provider?: string | null
  model?: string | null
  created_at?: string | null
  lineage: LineageEntry[]
  error?: string | null
}

export type GenerationStage = "idle" | "uploading" | "generating" | "complete" | "failed"

export type BeatProgress = {
  index: number
  label: string
  state: BeatState
  score?: number
}
