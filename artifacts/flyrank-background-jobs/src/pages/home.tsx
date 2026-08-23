import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { 
  useListJobs, getListJobsQueryKey,
  useGetJobSummary, getGetJobSummaryQueryKey,
  useCreateJob,
  useGetJob, getGetJobQueryKey,
  useGetJobResult, getGetJobResultQueryKey,
  JobInputFailureMode,
  JobStatus
} from "@workspace/api-client-react";
import { format, formatDistanceToNow } from "date-fns";
import { Loader2, RefreshCw, AlertCircle, CheckCircle2, Clock, PlayCircle, XCircle, Activity } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

function JobForm() {
  const queryClient = useQueryClient();
  const [text, setText] = useState("");
  const [failureMode, setFailureMode] = useState<JobInputFailureMode>("none");
  const [idempotencyKey, setIdempotencyKey] = useState(() => crypto.randomUUID());

  const createJob = useCreateJob({
    request: { headers: { "Idempotency-Key": idempotencyKey } },
    mutation: {
      onSuccess: () => {
        setText("");
        setIdempotencyKey(crypto.randomUUID());
        queryClient.invalidateQueries({ queryKey: getListJobsQueryKey() });
        queryClient.invalidateQueries({ queryKey: getGetJobSummaryQueryKey() });
      }
    }
  });

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!text.trim()) return;
    createJob.mutate({ data: { text, failureMode } });
  };

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4 bg-white p-4 border-b shrink-0">
      <div>
         <Label htmlFor="text" className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1.5 block">Job Payload (Text)</Label>
         <Textarea id="text" value={text} onChange={(e) => setText(e.target.value)} placeholder="Enter text to analyze..." className="font-mono text-sm resize-none h-20 shadow-inner bg-slate-50 focus:bg-white" />
      </div>
      <div className="flex items-end gap-3">
         <div className="flex-1">
            <Label htmlFor="failureMode" className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1.5 block">Test Failure Mode</Label>
            <Select value={failureMode} onValueChange={(val) => setFailureMode(val as JobInputFailureMode)}>
               <SelectTrigger id="failureMode" className="bg-slate-50">
                  <SelectValue />
               </SelectTrigger>
               <SelectContent>
                  <SelectItem value="none">None (Succeed)</SelectItem>
                  <SelectItem value="transient">Transient (Fails once)</SelectItem>
                  <SelectItem value="permanent">Permanent (Always fails)</SelectItem>
               </SelectContent>
            </Select>
         </div>
         <Button type="submit" disabled={createJob.isPending || !text.trim()} className="w-32 bg-indigo-600 hover:bg-indigo-700 text-white font-medium shadow-sm">
            {createJob.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : "Submit Job"}
         </Button>
      </div>
    </form>
  )
}

function StatusIcon({ status, className }: { status: JobStatus, className?: string }) {
  switch (status) {
    case 'pending': return <Clock className={cn("w-4 h-4 text-slate-400", className)} />;
    case 'running': return <PlayCircle className={cn("w-4 h-4 text-indigo-500", className)} />;
    case 'retrying': return <RefreshCw className={cn("w-4 h-4 text-amber-500", className)} />;
    case 'completed': return <CheckCircle2 className={cn("w-4 h-4 text-emerald-500", className)} />;
    case 'failed': return <XCircle className={cn("w-4 h-4 text-rose-500", className)} />;
    default: return <AlertCircle className={cn("w-4 h-4 text-slate-400", className)} />;
  }
}

function QueueList({ onSelect, selectedId }: { onSelect: (id: string) => void, selectedId: string | null }) {
  const { data: jobs, isLoading } = useListJobs({
    query: { refetchInterval: 2000, queryKey: getListJobsQueryKey() }
  });

  if (isLoading) return <div className="p-4 text-sm text-slate-500 flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin" /> Fetching queue...</div>;
  if (!jobs?.length) return <div className="p-4 text-sm text-slate-500 text-center mt-8">Queue is empty.</div>;

  return (
    <div className="flex flex-col divide-y divide-slate-100">
      {jobs.map(job => (
        <button
          key={job.id}
          onClick={() => onSelect(job.id)}
          className={cn(
            "flex items-start gap-3 p-3 text-left transition-all duration-200 border-l-2",
            selectedId === job.id ? "bg-indigo-50/70 border-indigo-500 shadow-sm" : "border-transparent hover:bg-slate-50 hover:border-slate-300"
          )}
        >
          <StatusIcon status={job.status} className="mt-0.5 shrink-0" />
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between gap-2 mb-1">
              <span className="text-xs font-semibold font-mono text-slate-700 truncate">{job.id.split('-')[0]}</span>
              <span className="text-[10px] text-slate-400 whitespace-nowrap font-medium uppercase tracking-wider">{formatDistanceToNow(new Date(job.createdAt))} ago</span>
            </div>
            <p className="text-xs text-slate-600 truncate">{job.textPreview}</p>
          </div>
        </button>
      ))}
    </div>
  );
}

function DataPoint({ label, value, className, isMono }: { label: string, value: React.ReactNode, className?: string, isMono?: boolean }) {
  return (
    <div className={cn("bg-slate-50 p-3 rounded-md border border-slate-100", className)}>
      <div className="text-[10px] font-bold tracking-wider uppercase text-slate-400 mb-1">{label}</div>
      <div className={cn("text-sm text-slate-900", isMono && "font-mono text-xs text-slate-700")}>{value}</div>
    </div>
  );
}

function Badge({ status }: { status: JobStatus }) {
  const styles = {
    pending: "bg-slate-100 text-slate-700 border-slate-200",
    running: "bg-indigo-100 text-indigo-700 border-indigo-200",
    retrying: "bg-amber-100 text-amber-700 border-amber-200",
    completed: "bg-emerald-100 text-emerald-700 border-emerald-200",
    failed: "bg-rose-100 text-rose-700 border-rose-200",
  };
  return (
    <span className={cn("px-2.5 py-1 rounded-full text-xs font-semibold tracking-wide uppercase border", styles[status])}>
      {status}
    </span>
  );
}

function JobDetailPanel({ jobId }: { jobId: string }) {
  const { data: job, isLoading } = useGetJob(jobId, {
    query: { refetchInterval: 2000, queryKey: getGetJobQueryKey(jobId) }
  });
  
  const { data: result, isLoading: isLoadingResult } = useGetJobResult(jobId, {
    query: { 
      enabled: job?.status === 'completed',
      queryKey: getGetJobResultQueryKey(jobId) 
    }
  });

  if (isLoading) return <div className="p-8 text-sm text-slate-500 flex flex-col items-center justify-center h-full gap-3"><Loader2 className="w-6 h-6 animate-spin text-indigo-500" /> Inspecting job...</div>;
  if (!job) return <div className="p-8 text-sm text-slate-500 flex justify-center h-full items-center">Job not found.</div>;

  return (
    <div className="flex flex-col h-full bg-white">
      <div className="px-6 py-4 border-b flex items-center justify-between bg-slate-50/50 shadow-sm z-10 shrink-0">
        <div>
          <h2 className="text-lg font-bold flex items-center gap-2 text-slate-900">
            <StatusIcon status={job.status} className="w-5 h-5" />
            Job Inspection
          </h2>
          <p className="text-xs text-slate-500 font-mono mt-1">{job.id}</p>
        </div>
        <Badge status={job.status} />
      </div>
      
      <div className="flex-1 overflow-y-auto p-6 space-y-8">
        <section>
          <h3 className="text-[11px] font-bold uppercase text-slate-400 mb-3 tracking-wider">Lifecycle Events</h3>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <DataPoint label="Created At" value={format(new Date(job.createdAt), "HH:mm:ss.SSS")} isMono />
            <DataPoint label="Started At" value={job.startedAt ? format(new Date(job.startedAt), "HH:mm:ss.SSS") : "--"} isMono />
            <DataPoint label="Completed At" value={job.completedAt ? format(new Date(job.completedAt), "HH:mm:ss.SSS") : "--"} isMono />
            <DataPoint label="Next Run At" value={job.nextRunAt ? format(new Date(job.nextRunAt), "HH:mm:ss.SSS") : "--"} isMono />
          </div>
        </section>

        <section>
          <h3 className="text-[11px] font-bold uppercase text-slate-400 mb-3 tracking-wider">Configuration & State</h3>
          <div className="grid grid-cols-2 gap-3">
            <DataPoint label="Failure Mode" value={job.failureMode} />
            <DataPoint label="Attempts" value={<span className={job.attemptCount > 0 ? "text-amber-600 font-bold" : ""}>{job.attemptCount} / {job.maxAttempts}</span>} />
            <DataPoint label="Idempotency Key" value={job.idempotencyKey} className="col-span-2" isMono />
          </div>
        </section>

        {job.lastError && (
          <section className="animate-in fade-in slide-in-from-bottom-2 duration-300">
            <h3 className="text-[11px] font-bold uppercase text-rose-500 mb-2 tracking-wider flex items-center gap-1.5">
              <AlertCircle className="w-3.5 h-3.5" /> Last Error
            </h3>
            <div className="bg-rose-50/50 text-rose-900 p-4 rounded-md text-xs font-mono whitespace-pre-wrap break-all border border-rose-100 shadow-inner">
              {job.lastError}
            </div>
          </section>
        )}

        {job.status === 'completed' && (
          <section className="animate-in fade-in slide-in-from-bottom-2 duration-300">
            <h3 className="text-[11px] font-bold uppercase text-emerald-600 mb-2 tracking-wider flex items-center gap-1.5">
              <CheckCircle2 className="w-3.5 h-3.5" /> Result Payload
            </h3>
            {isLoadingResult ? (
              <div className="text-sm text-slate-500 flex items-center gap-2 p-4 bg-slate-50 rounded-md border"><Loader2 className="w-4 h-4 animate-spin text-emerald-500" /> Fetching result...</div>
            ) : result ? (
              <pre className="bg-slate-950 text-slate-300 p-5 rounded-md text-xs font-mono overflow-x-auto shadow-inner border border-slate-800">
                {JSON.stringify(result.result, null, 2)}
              </pre>
            ) : (
              <div className="text-sm text-slate-500 p-4 bg-slate-50 rounded-md border text-center">Result unavailable.</div>
            )}
          </section>
        )}

        <section>
          <h3 className="text-[11px] font-bold uppercase text-slate-400 mb-2 tracking-wider">Input Preview</h3>
          <div className="bg-slate-50 p-4 rounded-md text-sm text-slate-700 border border-slate-100 whitespace-pre-wrap shadow-inner font-mono text-xs">
            {job.textPreview}
          </div>
        </section>
      </div>
    </div>
  );
}

function SummaryMetrics() {
  const { data: summary } = useGetJobSummary({
    query: { refetchInterval: 2000, queryKey: getGetJobSummaryQueryKey() }
  });

  const metrics = [
    { label: "Total", value: summary?.total ?? "-", icon: Activity, color: "text-slate-600" },
    { label: "Pending", value: summary?.pending ?? "-", icon: Clock, color: "text-slate-500" },
    { label: "Running", value: summary?.running ?? "-", icon: PlayCircle, color: "text-indigo-500" },
    { label: "Retrying", value: summary?.retrying ?? "-", icon: RefreshCw, color: "text-amber-500" },
    { label: "Completed", value: summary?.completed ?? "-", icon: CheckCircle2, color: "text-emerald-500" },
    { label: "Failed", value: summary?.failed ?? "-", icon: XCircle, color: "text-rose-500" },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-0 border-b shrink-0 bg-white shadow-sm z-10 divide-x divide-slate-100">
      {metrics.map(m => (
        <div key={m.label} className="p-4 flex flex-col items-center justify-center text-center gap-1.5 transition-colors hover:bg-slate-50/50">
          <div className="flex items-center gap-1.5 mb-1">
            <m.icon className={cn("w-3.5 h-3.5", m.color)} />
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{m.label}</span>
          </div>
          <span className="text-2xl font-black font-mono text-slate-900 tracking-tight">{m.value}</span>
        </div>
      ))}
    </div>
  );
}

export default function Home() {
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);

  return (
    <div className="flex flex-col h-full bg-slate-100">
      <SummaryMetrics />
      <div className="flex-1 flex overflow-hidden">
        <div className="w-1/3 flex flex-col min-w-[320px] max-w-md border-r bg-slate-50 z-10 shadow-[4px_0_12px_-6px_rgba(0,0,0,0.1)]">
          <JobForm />
          <div className="flex-1 relative">
             <div className="absolute inset-0 overflow-y-auto bg-white">
               <QueueList onSelect={setSelectedJobId} selectedId={selectedJobId} />
             </div>
          </div>
        </div>
        <div className="flex-1 overflow-hidden relative bg-slate-100/50">
          {selectedJobId ? (
            <JobDetailPanel jobId={selectedJobId} />
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-slate-400 gap-4">
              <Activity className="w-16 h-16 text-slate-200 stroke-[1.5]" />
              <p className="text-sm font-medium">Select a job from the queue to view inspection details.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
