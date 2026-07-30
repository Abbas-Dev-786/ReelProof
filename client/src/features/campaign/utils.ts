import type { BeatProgress, GenerationStage } from "./types"

export const createInitialBeats = (beatCount = 3): BeatProgress[] =>
  Array.from({ length: beatCount }, (_, index) => ({
    index,
    label: `Slide ${index + 1}`,
    state: "waiting",
  }))

export const calculateProgress = (stage: GenerationStage, beats: BeatProgress[]) => {
  if (stage === "complete") return 100
  if (stage !== "generating") return 0
  const completed = beats.filter((beat) => beat.state === "passed").length
  return Math.max(12, Math.round((completed / Math.max(beats.length, 1)) * 88))
}
