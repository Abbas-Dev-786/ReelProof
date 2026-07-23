import { ShieldCheck } from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"

export function ProvenanceBanner() {
  return (
    <Card className="overflow-hidden border border-[#e8e3da] bg-[#242238] text-white shadow-xl shadow-[#29253d]/12">
      <CardContent className="relative px-6 py-7 sm:px-8">
        <div className="absolute -right-12 -top-14 size-48 rounded-full bg-[#a88ef6]/30 blur-3xl" />
        <div className="relative grid gap-5 sm:grid-cols-[auto_1fr] sm:items-center">
          <div className="grid size-12 place-items-center rounded-2xl bg-white/10 text-[#ffbd6c]"><ShieldCheck /></div>
          <div>
            <p className="font-medium">Every creative decision is traceable.</p>
            <p className="mt-1 max-w-xl text-sm leading-6 text-white/65">Assets, provider calls, quality passes, and final output are retained with a tamper-evident manifest in Backblaze B2.</p>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
