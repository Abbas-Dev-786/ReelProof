import { useEffect, useState, type FormEvent } from "react"
import { ArrowLeft, CircleAlert, FileCheck2, ShieldCheck } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { LineageTimeline } from "@/features/campaign/components/lineage-timeline"
import { useRunVerification } from "@/features/campaign/hooks/use-run-verification"

type VerificationWorkspaceProps = {
  initialRunId: string | null
  onBackToStudio: () => void
}

function displayTimestamp(value: string | null | undefined) {
  if (!value) return "Not recorded"
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })
}

export function VerificationWorkspace({ initialRunId, onBackToStudio }: VerificationWorkspaceProps) {
  const [runId, setRunId] = useState(initialRunId ?? "")
  const verification = useRunVerification()
  const result = verification.data

  useEffect(() => {
    if (initialRunId) setRunId(initialRunId)
  }, [initialRunId])

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const normalizedRunId = runId.trim()
    if (normalizedRunId) void verification.mutateAsync(normalizedRunId)
  }

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
        <div>
          <Badge className="bg-[#ede9ff] text-[#5d48c6] hover:bg-[#ede9ff]">Public verification</Badge>
          <h1 className="mt-3 text-3xl font-semibold tracking-[-0.045em] text-[#242238] sm:text-4xl">Verify a creative record.</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-[#6c6874]">Look up a run to confirm its manifest and inspect the linked generation attempts retained in Backblaze B2.</p>
        </div>
        <Button onClick={onBackToStudio} variant="outline" className="border-[#dfdad2]"><ArrowLeft />Back to studio</Button>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(19rem,.7fr)_minmax(0,1.3fr)]">
        <Card className="h-fit border-[#e2dfd8] shadow-sm">
          <CardHeader className="pb-3"><CardTitle className="text-base">Run lookup</CardTitle></CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={handleSubmit}>
              <div className="space-y-2">
                <Label htmlFor="run-id">Run ID</Label>
                <Input autoComplete="off" id="run-id" onChange={(event) => setRunId(event.target.value)} placeholder="Paste a generation run ID" value={runId} />
                <p className="text-xs leading-5 text-[#817c87]">A run ID is included with each ReelProof export and provenance record.</p>
              </div>
              <Button className="w-full bg-[#242438] hover:bg-[#373451]" disabled={!runId.trim() || verification.isPending} type="submit"><ShieldCheck />{verification.isPending ? "Checking manifest…" : "Verify record"}</Button>
            </form>
            {verification.isError && <Alert className="mt-4" variant="destructive"><CircleAlert /><AlertTitle>We couldn’t verify that run</AlertTitle><AlertDescription>{verification.error instanceof Error ? verification.error.message : "Please check the run ID and try again."}</AlertDescription></Alert>}
          </CardContent>
        </Card>

        <Card className="min-h-[27rem] border-[#e2dfd8] shadow-sm">
          {!result ? <CardContent className="flex min-h-[27rem] flex-col justify-center p-7">
            <span className="mb-5 grid size-12 place-items-center rounded-2xl bg-[#f0edf9] text-[#6954c6]"><FileCheck2 className="size-6" /></span>
            <h2 className="text-xl font-semibold tracking-[-0.03em] text-[#302d38]">Manifest details will appear here.</h2>
            <p className="mt-2 max-w-md text-sm leading-6 text-[#716d77]">Verification checks the canonical manifest hash and reports the full retained lineage for the supplied run.</p>
          </CardContent> : <CardContent className="p-6 sm:p-7">
            <div className={`flex items-start gap-4 rounded-xl border p-4 ${result.verified ? "border-[#bfe7cf] bg-[#f0fbf4]" : "border-[#f3d1c8] bg-[#fff4f1]"}`}>
              <span className={`grid size-10 shrink-0 place-items-center rounded-full ${result.verified ? "bg-[#d8f2e3] text-[#26784f]" : "bg-[#f8dbd4] text-[#af5048]"}`}><ShieldCheck className="size-5" /></span>
              <div>
                <p className="font-semibold text-[#34313a]">{result.verified ? "Manifest integrity confirmed" : "Manifest needs review"}</p>
                <p className="mt-1 text-sm leading-5 text-[#666f71]">{result.verified ? "The recorded manifest hash matches the preserved generation record." : (result.error ?? "The preserved record could not be validated.")}</p>
              </div>
            </div>

            <dl className="mt-6 grid gap-4 border-y border-[#e8e4dd] py-5 sm:grid-cols-2">
              <div><dt className="text-xs font-semibold uppercase tracking-[0.1em] text-[#817b88]">Provider</dt><dd className="mt-1 text-sm font-medium text-[#403c47]">{result.provider ?? "Recorded in manifest"}</dd></div>
              <div><dt className="text-xs font-semibold uppercase tracking-[0.1em] text-[#817b88]">Model</dt><dd className="mt-1 text-sm font-medium text-[#403c47]">{result.model ?? "Recorded in manifest"}</dd></div>
              <div><dt className="text-xs font-semibold uppercase tracking-[0.1em] text-[#817b88]">Stored</dt><dd className="mt-1 text-sm font-medium text-[#403c47]">{displayTimestamp(result.created_at)}</dd></div>
              <div><dt className="text-xs font-semibold uppercase tracking-[0.1em] text-[#817b88]">Manifest hash</dt><dd className="mt-1 break-all font-mono text-xs text-[#595362]">{result.manifest_hash ?? "Not available"}</dd></div>
            </dl>

            <section className="mt-6">
              <div className="mb-4 flex items-center justify-between gap-3"><div><h2 className="text-base font-semibold text-[#37333d]">Generation lineage</h2><p className="mt-1 text-xs leading-5 text-[#817b87]">Every refinement remains linked to the final verified run.</p></div><Badge variant="outline" className="border-[#e0dbe9] bg-[#faf9fd] text-[#625b74]">{result.lineage.length} attempts</Badge></div>
              <LineageTimeline lineage={result.lineage} verifiedRunId={result.verified ? result.run_id : undefined} />
            </section>
          </CardContent>}
        </Card>
      </div>
    </div>
  )
}
