import { useCallback, useEffect, useState, type FormEvent } from "react"
import { Clapperboard, History, Play, Sparkles } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { CampaignComposer } from "./campaign-composer"
import { CampaignResult } from "./campaign-result"
import { GenerationTray } from "./generation-tray"
import { useCampaignGeneration } from "../hooks/use-campaign-generation"
import { useCampaignLineage, useCampaignPackage } from "../hooks/use-campaign-records"
import { useCampaign, useCampaignStream } from "../hooks/use-campaign-stream"
import { useRunVerification } from "../hooks/use-run-verification"
import type { BeatProgress, GenerationStage, RenderMode } from "../types"
import { createInitialBeats } from "../utils"

type CampaignWorkspaceProps = {
  onOpenVerifier: (runId: string) => void
}

export function CampaignWorkspace({ onOpenVerifier }: CampaignWorkspaceProps) {
  const [topic, setTopic] = useState("")
  const [beatCount, setBeatCount] = useState(5)
  const [mode, setMode] = useState<RenderMode>("slideshow")
  const [generateAudio, setGenerateAudio] = useState(true)
  const [files, setFiles] = useState<File[]>([])
  const [stage, setStage] = useState<GenerationStage>("idle")
  const [jobId, setJobId] = useState<string | null>(null)
  const [beats, setBeats] = useState<BeatProgress[]>(() => createInitialBeats())
  const [error, setError] = useState<string | null>(null)

  const generation = useCampaignGeneration()
  const campaignQuery = useCampaign(jobId)
  const campaignPackageQuery = useCampaignPackage(jobId, campaignQuery.data?.status)
  const campaignLineageQuery = useCampaignLineage(jobId, campaignQuery.data?.status)
  const verification = useRunVerification()

  const updateBeat = useCallback((index: number, update: Partial<BeatProgress>) => {
    setBeats((current) => {
      const existing = current.find((beat) => beat.index === index)
      const next: BeatProgress[] = existing
        ? current.map((beat) => beat.index === index ? { ...beat, ...update } : beat)
        : [...current, { index, label: `Beat ${index + 1}`, state: "working" as const, ...update }]
      return next.sort((a, b) => a.index - b.index)
    })
  }, [])

  const handleStreamFailure = useCallback((message: string) => {
    setError(message)
    setStage("failed")
  }, [])

  useCampaignStream({
    jobId,
    enabled: stage === "generating",
    onBeatUpdate: updateBeat,
    onFailed: handleStreamFailure,
  })

  useEffect(() => {
    const campaign = campaignQuery.data
    if (!campaign) return

    if (campaign.beat_plan) {
      setBeats(campaign.beat_plan.beats.map((beat, index) => {
        const completedBeat = campaign.beats.find((item) => item.index === beat.index)
        return {
          index: beat.index,
          label: beat.caption || `Beat ${index + 1}`,
          state: completedBeat?.passed ? "passed" : "working",
          score: completedBeat?.judge_score ?? undefined,
        }
      }))
    }
    if (campaign.status === "done") setStage("complete")
    if (campaign.status === "failed") handleStreamFailure(campaign.error ?? "Generation failed")
  }, [campaignQuery.data, handleStreamFailure])

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (topic.trim().length < 3) {
      setError("Give your campaign a little more direction before generating.")
      return
    }

    setError(null)
    verification.reset()
    setJobId(null)
    setBeats(createInitialBeats(beatCount))
    setStage(files.length > 0 ? "uploading" : "generating")

    try {
      const nextJobId = await generation.mutateAsync({
        topic: topic.trim(),
        beatCount,
        mode,
        generateAudio,
        files,
      })
      setJobId(nextJobId)
      setStage("generating")
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to start this campaign")
      setStage("failed")
    }
  }

  const handleVerification = async () => {
    if (!campaignQuery.data?.run_id) return
    try {
      await verification.mutateAsync(campaignQuery.data.run_id)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not verify this run")
    }
  }

  const workspaceStatus = stage === "complete"
    ? "Ready to export"
    : stage === "generating" || stage === "uploading"
      ? "Generating"
      : "Draft"

  return (
    <div className="overflow-hidden rounded-2xl border border-[#dfddd7] bg-white shadow-sm lg:grid lg:min-h-[calc(100vh-6.75rem)] lg:grid-cols-[minmax(21rem,0.78fr)_minmax(34rem,1.22fr)]">
      <section className="border-b border-[#e5e2dc] bg-[#faf9f6] lg:max-h-[calc(100vh-6.75rem)] lg:overflow-y-auto lg:border-r lg:border-b-0">
        <div className="p-5 sm:p-7">
          <div className="mb-7 flex items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#77737a]">Campaign brief</p>
              <h1 className="mt-2 text-2xl font-semibold tracking-[-0.035em] text-[#20202b]">Create a reel</h1>
              <p className="mt-2 max-w-md text-sm leading-6 text-[#6e6b75]">Set the message and visual direction. Your working preview stays alongside it.</p>
            </div>
            <div className="grid size-9 shrink-0 place-items-center rounded-lg border border-[#e6e1d7] bg-white text-[#bb6d1d]">
              <Sparkles className="size-4" />
            </div>
          </div>
          <CampaignComposer topic={topic} beatCount={beatCount} mode={mode} generateAudio={generateAudio} files={files} stage={stage} error={error} onTopicChange={setTopic} onBeatCountChange={setBeatCount} onModeChange={setMode} onGenerateAudioChange={setGenerateAudio} onFilesChange={setFiles} onSubmit={handleSubmit} />
        </div>
      </section>

      <section className="min-w-0 bg-white p-5 sm:p-7">
        <div className="mb-6 flex items-center justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#77737a]">Workspace</p>
            <h2 className="mt-2 text-xl font-semibold tracking-[-0.03em] text-[#20202b]">Preview & activity</h2>
          </div>
          <Badge variant="outline" className="h-7 border-[#dedbd4] bg-[#fafaf8] px-2.5 text-[#66626c]">{workspaceStatus}</Badge>
        </div>

        <div className="grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_minmax(19rem,0.85fr)]">
          <div className="min-w-0">
            {campaignQuery.data && stage === "complete" ? (
              <CampaignResult campaign={campaignQuery.data} campaignLineage={campaignLineageQuery.data} campaignLineageError={campaignLineageQuery.error} campaignPackage={campaignPackageQuery.data} campaignPackageError={campaignPackageQuery.error} isCampaignLineageLoading={campaignLineageQuery.isLoading} isCampaignPackageLoading={campaignPackageQuery.isLoading} verification={verification.data} isVerifying={verification.isPending} onVerify={() => void handleVerification()} onOpenVerifier={onOpenVerifier} />
            ) : (
              <div className="flex min-h-[25rem] flex-col justify-between overflow-hidden rounded-xl border border-[#e2dfd8] bg-[#f8f7f4] p-5 sm:p-7">
                <div className="flex items-center justify-between gap-3">
                  <Badge variant="outline" className="border-[#dedbd4] bg-white text-[#625f68]">9:16 {mode === "pov" ? "POV montage" : "slideshow"}</Badge>
                  <Play className="size-4 text-[#938f98]" />
                </div>
                <div className="max-w-sm">
                  <div className="mb-5 grid size-12 place-items-center rounded-xl bg-[#ece9e2] text-[#696570]">
                    <Clapperboard className="size-5" />
                  </div>
                  <h3 className="text-xl font-semibold tracking-[-0.03em] text-[#2a2934]">Your reel will appear here.</h3>
                  <p className="mt-2 text-sm leading-6 text-[#706d76]">Write a brief, add optional product images, then generate a storyboard to begin the review cycle.</p>
                </div>
                <div className="border-t border-[#e4e1db] pt-4 text-xs text-[#77737c]">The final export and its provenance record stay together.</div>
              </div>
            )}
          </div>

          <aside className="min-w-0 rounded-xl border border-[#e2dfd8] bg-[#fcfbf9] p-4 sm:p-5">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-sm font-semibold text-[#33313a]"><History className="size-4 text-[#74707a]" /> Run activity</div>
              <span className="text-xs text-[#827e87]">Current run</span>
            </div>
            <GenerationTray stage={stage} beats={beats} mode={mode} />
          </aside>
        </div>
      </section>
    </div>
  )
}
