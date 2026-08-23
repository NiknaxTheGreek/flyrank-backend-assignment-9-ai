import { AlertCircle } from "lucide-react";

export default function NotFound() {
  return (
    <div className="flex w-full h-full items-center justify-center bg-slate-50 text-slate-900">
      <div className="flex flex-col items-center gap-4 text-center">
        <AlertCircle className="w-12 h-12 text-rose-500" />
        <h1 className="text-2xl font-bold">404 - Page Not Found</h1>
        <p className="text-slate-500">The page you are looking for does not exist.</p>
      </div>
    </div>
  );
}
