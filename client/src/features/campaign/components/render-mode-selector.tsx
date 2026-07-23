import { Image, LockKeyhole, PlaySquare } from "lucide-react"
import { cn } from "@/lib/utils"
import type { RenderMode } from "../types"

type RenderModeSelectorProps = {
  value: RenderMode
  disabled: boolean
  onChange: (mode: RenderMode) => void
}

const modeOptions: Array<{
  value: RenderMode
  title: string
  description: string
  icon: typeof Image
  available: boolean
}> = [
  { value: "slideshow", title: "Slideshow", description: "Captioned stills with motion and music", icon: Image, available: true },
  { value: "pov", title: "POV montage", description: "Animated scenes, rendered asynchronously", icon: PlaySquare, available: false },
]

export function RenderModeSelector({ value, disabled, onChange }: RenderModeSelectorProps) {
  return (
    <fieldset className="space-y-3" disabled={disabled}>
      <div className="flex items-center justify-between gap-3">
        <legend className="text-sm font-medium text-[#393640]">Render mode</legend>
        <span className="text-xs text-[#85828f]">9:16 vertical</span>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {modeOptions.map((option) => {
          const Icon = option.icon
          const isSelected = option.value === value
          return (
            <button
              aria-pressed={isSelected}
              className={cn(
                "relative flex min-h-28 flex-col rounded-xl border p-4 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#6f5cc5]/40",
                isSelected ? "border-[#7865cd] bg-[#f7f5ff]" : "border-[#dfdcd5] bg-white hover:border-[#b7afd9]",
                !option.available && "cursor-not-allowed opacity-65 hover:border-[#dfdcd5]",
              )}
              disabled={disabled || !option.available}
              key={option.value}
              onClick={() => onChange(option.value)}
              type="button"
            >
              <span className={cn("mb-3 grid size-8 place-items-center rounded-lg", isSelected ? "bg-[#e8e2ff] text-[#654fc4]" : "bg-[#f1efea] text-[#736f79]")}><Icon className="size-4" /></span>
              <span className="text-sm font-semibold text-[#35323d]">{option.title}</span>
              <span className="mt-1 text-xs leading-4 text-[#7e7a84]">{option.description}</span>
              {!option.available && <span className="absolute right-3 top-3 inline-flex items-center gap-1 rounded-full bg-[#f0ede8] px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-[#736e79]"><LockKeyhole className="size-2.5" />Soon</span>}
            </button>
          )
        })}
      </div>
      <p className="text-xs leading-5 text-[#7d7982]">POV montage is queued for the next release; slideshow is the proven live-render path.</p>
    </fieldset>
  )
}
