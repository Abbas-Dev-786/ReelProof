import { type FormEvent } from "react"
import { ChevronRight, CircleAlert, LoaderCircle, Sparkles } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
import type { GenerationStage, RenderMode } from "../types"
import { ProductImageUpload } from "./product-image-upload"
import { RenderModeSelector } from "./render-mode-selector"

type CampaignComposerProps = {
  topic: string
  beatCount: number
  mode: RenderMode
  generateAudio: boolean
  files: File[]
  stage: GenerationStage
  error: string | null
  onTopicChange: (topic: string) => void
  onBeatCountChange: (count: number) => void
  onModeChange: (mode: RenderMode) => void
  onGenerateAudioChange: (generateAudio: boolean) => void
  onFilesChange: (files: File[]) => void
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
}

export function CampaignComposer({ topic, beatCount, mode, generateAudio, files, stage, error, onTopicChange, onBeatCountChange, onModeChange, onGenerateAudioChange, onFilesChange, onSubmit }: CampaignComposerProps) {
  const isWorking = stage === "uploading" || stage === "generating"

  return (
    <form className="space-y-7" onSubmit={onSubmit}>
      <div className="space-y-2">
        <Label htmlFor="topic" className="text-sm font-medium text-[#393640]">What is this reel about?</Label>
        <Textarea id="topic" value={topic} onChange={(event) => onTopicChange(event.target.value)} placeholder="A quiet morning coffee ritual for people who want less screen time" className="min-h-34 resize-y border-[#d9d6cf] bg-white text-[15px] leading-6 shadow-none focus-visible:border-[#6f5cc5]" disabled={isWorking} />
        <p className="text-xs leading-5 text-[#7d7982]">We’ll develop the hook, visual concepts, post copy, and hashtags from this brief.</p>
      </div>

      <div className="border-y border-[#e4e1db] py-6">
        <p className="mb-4 text-xs font-semibold uppercase tracking-[0.12em] text-[#77737a]">Story settings</p>
        <div className="space-y-5">
          <div className="space-y-2">
            <Label htmlFor="beat-count" className="text-sm font-medium text-[#393640]">Story beats</Label>
            <Input id="beat-count" type="number" min={3} max={8} value={beatCount} onChange={(event) => onBeatCountChange(Math.min(8, Math.max(3, Number(event.target.value) || 3)))} disabled={isWorking} className="h-11 border-[#d9d6cf] bg-white shadow-none" />
          </div>
          <RenderModeSelector value={mode} disabled={isWorking} onChange={onModeChange} />
          <div className="flex items-center justify-between gap-4 rounded-xl border border-[#e2dfd8] bg-white px-4 py-3">
            <div>
              <Label htmlFor="generate-audio" className="text-sm font-medium text-[#393640]">Generate music & voiceover</Label>
              <p className="mt-1 text-xs leading-5 text-[#7d7982]">Turn this off for a faster export without Stability or ElevenLabs audio calls.</p>
            </div>
            <Switch id="generate-audio" checked={generateAudio} disabled={isWorking} onCheckedChange={onGenerateAudioChange} />
          </div>
        </div>
      </div>

      <ProductImageUpload files={files} disabled={isWorking} onFilesChange={onFilesChange} />

      {error && <Alert variant="destructive"><CircleAlert /><AlertTitle>Something needs attention</AlertTitle><AlertDescription>{error}</AlertDescription></Alert>}

      <div className="sticky bottom-0 -mx-5 border-t border-[#e1ded7] bg-[#faf9f6]/95 px-5 pt-5 backdrop-blur sm:-mx-7 sm:px-7">
        <Button type="submit" size="lg" className="h-12 w-full bg-[#242438] text-white shadow-none hover:bg-[#373451]" disabled={isWorking}>
          {isWorking ? <LoaderCircle className="animate-spin" /> : <Sparkles />}
          {stage === "uploading" ? "Preparing product images…" : stage === "generating" ? "Building your storyboard…" : "Generate storyboard"}
          {!isWorking && <ChevronRight />}
        </Button>
      </div>
    </form>
  )
}
