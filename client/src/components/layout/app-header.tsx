import { CircleAlert, Clapperboard, LoaderCircle, Radio, ShieldCheck } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

export type AppView = "studio" | "verify"
export type ApiConnectionStatus = "checking" | "online" | "offline"

type AppHeaderProps = {
  activeView: AppView
  onViewChange: (view: AppView) => void
  apiStatus: ApiConnectionStatus
}

const apiStatusLabel: Record<ApiConnectionStatus, string> = {
  checking: "Checking API",
  online: "API online",
  offline: "API unavailable",
}

export function AppHeader({ activeView, onViewChange, apiStatus }: AppHeaderProps) {
  return (
    <header className="mb-3 flex min-h-14 items-center justify-between gap-3 rounded-2xl border border-[#e2dfd8] bg-white px-3 shadow-sm sm:px-4">
      <div className="flex min-w-0 items-center gap-3">
        <div className="grid size-9 shrink-0 place-items-center rounded-xl bg-[#202335] text-[#ffbd6c]"><Clapperboard className="size-[18px]" /></div>
        <p className="hidden truncate text-sm font-semibold tracking-tight sm:block sm:text-base">ReelProof</p>
        <nav aria-label="Primary navigation" className="flex items-center gap-1 rounded-lg bg-[#f6f4f0] p-1">
          {(["studio", "verify"] as const).map((view) => <button className={cn("rounded-md px-2.5 py-1.5 text-xs font-medium capitalize transition-colors", activeView === view ? "bg-white text-[#302e38] shadow-sm" : "text-[#77727d] hover:text-[#393640]")} key={view} onClick={() => onViewChange(view)} type="button">{view === "studio" ? "Studio" : "Verify"}</button>)}
        </nav>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <Badge aria-live="polite" title={apiStatusLabel[apiStatus]} variant="outline" className={`h-8 border px-2.5 sm:px-3 ${apiStatus === "online" ? "border-[#bfdfcc] bg-[#f2fbf5] text-[#26784f]" : apiStatus === "offline" ? "border-[#f0ccc4] bg-[#fff6f3] text-[#ad5248]" : "border-[#d9d7d0] bg-[#fafaf8] text-[#66626c]"}`}>
          {apiStatus === "online" ? <Radio className="mr-1.5 size-3.5" /> : apiStatus === "offline" ? <CircleAlert className="mr-1.5 size-3.5" /> : <LoaderCircle className="mr-1.5 size-3.5 animate-spin" />}
          <span>{apiStatusLabel[apiStatus]}</span>
        </Badge>
        <Badge title="Backblaze B2 provenance" variant="outline" className="hidden h-8 border-[#d9d7d0] bg-[#fafaf8] px-3 text-[#565363] sm:inline-flex"><ShieldCheck className="mr-1.5 size-3.5 text-[#24714d]" />B2 provenance</Badge>
      </div>
    </header>
  )
}
