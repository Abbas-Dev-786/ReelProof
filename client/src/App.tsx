import { useState } from "react"
import "./App.css"
import { AppHeader, type ApiConnectionStatus, type AppView } from "@/components/layout/app-header"
import { CampaignWorkspace } from "@/features/campaign/components/campaign-workspace"
import { VerificationWorkspace } from "@/features/verification/components/verification-workspace"
import { useApiHealth } from "@/hooks/use-api-health"

function App() {
  const [activeView, setActiveView] = useState<AppView>("studio")
  const [verificationRunId, setVerificationRunId] = useState<string | null>(null)
  const apiHealth = useApiHealth()
  const apiStatus: ApiConnectionStatus = apiHealth.isError ? "offline" : apiHealth.isSuccess && apiHealth.data.status === "ok" ? "online" : "checking"

  const openVerifier = (runId: string) => {
    setVerificationRunId(runId)
    setActiveView("verify")
  }

  return (
    <main className="min-h-screen bg-[#f4f3f0] text-[#1b1d2a]">
      <div className="mx-auto max-w-[1600px] px-3 py-3 sm:px-5 sm:py-5">
        <AppHeader activeView={activeView} apiStatus={apiStatus} onViewChange={setActiveView} />
        {activeView === "studio" ? <CampaignWorkspace onOpenVerifier={openVerifier} /> : <VerificationWorkspace initialRunId={verificationRunId} onBackToStudio={() => setActiveView("studio")} />}
      </div>
    </main>
  )
}

export default App
