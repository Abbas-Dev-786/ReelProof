import { CheckCircle2, GitBranch, ShieldCheck } from "lucide-react"
import type { LineageEntry } from "../types"

type LineageTimelineProps = {
  lineage: LineageEntry[]
  compact?: boolean
  verifiedRunId?: string | null
}

function shortHash(hash: string) {
  return hash.length > 16 ? `${hash.slice(0, 10)}…${hash.slice(-6)}` : hash
}

function formattedDate(value: string | null | undefined) {
  if (!value) return "Stored with the run"
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? "Stored with the run" : date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })
}

export function LineageTimeline({ lineage, compact = false, verifiedRunId }: LineageTimelineProps) {
  if (lineage.length === 0) {
    return <p className="text-sm leading-6 text-[#76727c]">Lineage will appear once the first generation run has been stored.</p>
  }

  const chronologicalLineage = [...lineage].sort((left, right) => {
    const leftTimestamp = left.created_at ? Date.parse(left.created_at) : Number.NaN
    const rightTimestamp = right.created_at ? Date.parse(right.created_at) : Number.NaN
    if (Number.isNaN(leftTimestamp) || Number.isNaN(rightTimestamp)) return 0
    return leftTimestamp - rightTimestamp
  })

  return (
    <ol className="space-y-0">
      {chronologicalLineage.map((entry, index) => (
        <li className="relative flex gap-3 pb-5 last:pb-0" key={entry.run_id}>
          {index < chronologicalLineage.length - 1 && <span aria-hidden="true" className="absolute left-[13px] top-7 h-[calc(100%-1.2rem)] w-px bg-[#ded9e8]" />}
          <span className="relative z-10 grid size-7 shrink-0 place-items-center rounded-full bg-[#eeeaff] text-[#6954c6]">
            {index === chronologicalLineage.length - 1 ? <ShieldCheck className="size-3.5" /> : <GitBranch className="size-3.5" />}
          </span>
          <div className="min-w-0 pt-0.5">
            <p className="text-sm font-medium text-[#383541]">{entry.parent_run_id ? "Refined generation" : "Initial generation"}{entry.run_id === verifiedRunId && <span className="ml-2 inline-flex items-center gap-1 text-xs font-medium text-[#278052]"><CheckCircle2 className="size-3" />Integrity checked</span>}</p>
            {!compact && <p className="mt-1 text-xs leading-5 text-[#77727d]">{formattedDate(entry.created_at)}</p>}
            <code className="mt-1 block max-w-full truncate text-[11px] text-[#756f83]" title={entry.manifest_hash}>{shortHash(entry.manifest_hash)}</code>
          </div>
        </li>
      ))}
    </ol>
  )
}
