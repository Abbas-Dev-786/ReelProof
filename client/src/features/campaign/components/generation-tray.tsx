import { Check, LoaderCircle, Sparkles } from "lucide-react"
import { Progress, ProgressLabel } from "@/components/ui/progress"
import type { BeatProgress, GenerationStage } from "../types"
import { calculateProgress } from "../utils"

type GenerationTrayProps = {
  stage: GenerationStage
  beats: BeatProgress[]
}

export function GenerationTray({ stage, beats }: GenerationTrayProps) {
  const progress = calculateProgress(stage, beats)

  return (
    <div className="space-y-5">
      <Progress value={progress} className="gap-2 [&_[data-slot=progress-indicator]]:bg-[#7865cd]">
        <ProgressLabel>{stage === "complete" ? "Reel ready" : stage === "idle" ? "Waiting for brief" : "Building story"}</ProgressLabel>
        <span className="ml-auto text-sm tabular-nums text-muted-foreground">{progress}%</span>
      </Progress>
      <div className="space-y-2">
        {beats.map((beat) => <div key={beat.index} className="flex items-center gap-3 rounded-lg border border-[#e6e2db] bg-white px-3 py-3">
          <div className={`grid size-7 shrink-0 place-items-center rounded-full text-xs font-semibold ${beat.state === "passed" ? "bg-[#daf3e5] text-[#22734e]" : beat.state === "retrying" ? "bg-[#fff0da] text-[#b96b14]" : beat.state === "working" ? "bg-[#ede9ff] text-[#6d55cf]" : "bg-[#eeece8] text-[#8b8791]"}`}>
            {beat.state === "passed" ? <Check className="size-3.5" /> : beat.state === "working" ? <LoaderCircle className="size-3.5 animate-spin" /> : beat.index + 1}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">{beat.label}</p>
            <p className="mt-0.5 text-xs text-[#86828c]">{beat.state === "passed" ? "Quality passed" : beat.state === "retrying" ? "Refining from feedback" : beat.state === "working" ? "Generating and judging" : "Queued"}</p>
          </div>
          {beat.score !== undefined && <span className="text-xs font-medium text-[#6d55cf]">{Math.round(beat.score * 100)}%</span>}
        </div>)}
      </div>
      <div className="flex items-start gap-3 border-t border-[#e6e2db] pt-4 text-xs leading-5 text-[#625a7c]">
        <Sparkles className="mt-0.5 size-3.5 shrink-0" />
        <p>Weak frames automatically regenerate with vision-model feedback. Each attempt stays in the provenance chain.</p>
      </div>
    </div>
  )
}
