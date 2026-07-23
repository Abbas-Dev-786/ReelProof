import { Clapperboard, ShieldCheck } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

export type AppView = "studio" | "verify"

type AppHeaderProps = {
  activeView: AppView
  onViewChange: (view: AppView) => void
}

export function AppHeader({ activeView, onViewChange }: AppHeaderProps) {
  return (
    <header className="mb-3 flex min-h-14 items-center justify-between gap-3 rounded-2xl border border-[#e2dfd8] bg-white px-3 shadow-sm sm:px-4">
      <div className="flex min-w-0 items-center gap-3">
        <div className="grid size-9 shrink-0 place-items-center rounded-xl bg-[#202335] text-[#ffbd6c]"><Clapperboard className="size-[18px]" /></div>
        <p className="hidden truncate text-sm font-semibold tracking-tight sm:block sm:text-base">ReelProof</p>
        <nav aria-label="Primary navigation" className="flex items-center gap-1 rounded-lg bg-[#f6f4f0] p-1">
          {(["studio", "verify"] as const).map((view) => <button className={cn("rounded-md px-2.5 py-1.5 text-xs font-medium capitalize transition-colors", activeView === view ? "bg-white text-[#302e38] shadow-sm" : "text-[#77727d] hover:text-[#393640]")} key={view} onClick={() => onViewChange(view)} type="button">{view === "studio" ? "Studio" : "Verify"}</button>)}
        </nav>
      </div>
      <Badge variant="outline" className="h-8 shrink-0 border-[#d9d7d0] bg-[#fafaf8] px-2.5 text-[#565363] sm:px-3"><ShieldCheck className="mr-1.5 size-3.5 text-[#24714d]" /><span className="hidden sm:inline">B2 provenance</span><span className="sm:hidden">Verified</span></Badge>
    </header>
  )
}
