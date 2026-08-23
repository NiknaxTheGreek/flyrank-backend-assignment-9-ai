import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CheckCircle2, RefreshCw, Server, Shield, Zap } from "lucide-react";

export default function About() {
  return (
    <div className="flex flex-col h-full bg-slate-50 overflow-y-auto">
      <div className="max-w-4xl mx-auto w-full p-8 space-y-8">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-slate-900 mb-3">Architecture & Lifecycle</h1>
          <p className="text-slate-600 leading-relaxed max-w-3xl text-lg">
            FlyRank Background Jobs demonstrates a robust, decoupled job processing system using FastAPI and React. 
            The architecture is designed for observability, reliability, and clear separation of concerns between web ingestion and background execution.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Card className="shadow-sm border-slate-200">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-indigo-700">
                <Server className="w-5 h-5" />
                Decoupled Execution
              </CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-slate-600 leading-relaxed">
              Jobs are accepted by a fast API tier and immediately persisted with a `pending` state. A separate asyncio worker loop constantly polls the queue, claiming pending or stalled jobs for execution, ensuring the web tier never blocks on heavy text analysis.
            </CardContent>
          </Card>

          <Card className="shadow-sm border-slate-200">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-amber-700">
                <RefreshCw className="w-5 h-5" />
                Durable Retries
              </CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-slate-600 leading-relaxed">
              Transient failures don't drop jobs. The worker implements exponential backoff and tracks `attemptCount` against `maxAttempts`. If a job fails, it moves to `retrying` with a scheduled `nextRunAt` timestamp. Permanent failures immediately transition to `failed`.
            </CardContent>
          </Card>

          <Card className="shadow-sm border-slate-200">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-emerald-700">
                <Shield className="w-5 h-5" />
                Idempotent Submissions
              </CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-slate-600 leading-relaxed">
              Network instability during submission is handled via client-generated `Idempotency-Key` headers. If a user submits the same payload twice due to a dropped connection, the backend returns the existing job instead of duplicating work.
            </CardContent>
          </Card>

          <Card className="shadow-sm border-slate-200">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-rose-700">
                <Zap className="w-5 h-5" />
                Real-time Observability
              </CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-slate-600 leading-relaxed">
              The frontend continuously polls the unified `/api/jobs/summary` and list endpoints. State transitions (Pending → Running → Completed) reflect instantly, providing immediate developer feedback without needing manual refreshes.
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
