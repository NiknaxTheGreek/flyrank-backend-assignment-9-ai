import { Link, useLocation } from "wouter";
import { Activity, Info, Box } from "lucide-react";
import { cn } from "@/lib/utils";
import { useHealthCheck, getHealthCheckQueryKey } from "@workspace/api-client-react";

export function Layout({ children }: { children: React.ReactNode }) {
  const [location] = useLocation();
  const { data: health } = useHealthCheck({ query: { refetchInterval: 10000, queryKey: getHealthCheckQueryKey() } });

  return (
    <div className="flex h-screen w-full bg-slate-50 font-sans">
      <aside className="w-64 bg-slate-900 text-slate-300 flex flex-col border-r border-slate-800 shrink-0 shadow-xl z-20">
        <div className="h-14 flex items-center px-6 border-b border-slate-800 bg-slate-950 font-medium text-slate-100 tracking-tight gap-2">
           <Box className="w-5 h-5 text-indigo-400" />
           FlyRank Jobs
        </div>
        <nav className="flex-1 py-4 flex flex-col gap-1 px-3">
          <Link href="/" className={cn("flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors", location === "/" ? "bg-indigo-500/10 text-indigo-400" : "hover:bg-slate-800 hover:text-slate-100")}>
            <Activity className="w-4 h-4" />
            Job Queue
          </Link>
          <Link href="/about" className={cn("flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors", location === "/about" ? "bg-indigo-500/10 text-indigo-400" : "hover:bg-slate-800 hover:text-slate-100")}>
            <Info className="w-4 h-4" />
            Architecture
          </Link>
        </nav>
        <div className="p-4 border-t border-slate-800 bg-slate-950 text-xs flex items-center justify-between">
          <span className="flex items-center gap-2">
            <div className={cn("w-2 h-2 rounded-full", health?.status === "ok" ? "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]" : "bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.5)]")} />
            {health?.status === "ok" ? "System Online" : "System Offline"}
          </span>
        </div>
      </aside>
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden bg-slate-50 text-slate-900">
        {children}
      </main>
    </div>
  );
}
