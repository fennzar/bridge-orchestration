"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Terminal,
  ChevronDown,
  ChevronRight,
  RefreshCw,
  RotateCcw,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Loader2,
} from "lucide-react";
import { TerminalView } from "@/components/terminal-view";
import type { AppStatus, AppsResponse } from "@/lib/types";

const APP_GROUPS: Record<string, string> = {
  bridge: "Bridge",
  engine: "Engine",
  dashboard: "Dashboard",
};

function groupLabel(group: string): string {
  return APP_GROUPS[group] || group;
}

function ProcessCard({
  process,
  onRestart,
}: {
  process: AppStatus;
  onRestart: (name: string) => void;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [restarting, setRestarting] = useState(false);

  const isRunning = process.status === "running";
  const isError = process.status === "error";
  const lastLog =
    process.logs.length > 0 ? process.logs[process.logs.length - 1] : null;

  const handleRestart = async () => {
    setRestarting(true);
    try {
      await fetch(`/api/apps/${encodeURIComponent(process.name)}/command`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: "restart" }),
      });
      onRestart(process.name);
    } catch (err) {
      console.error("Restart failed:", err);
    } finally {
      setTimeout(() => setRestarting(false), 2000);
    }
  };

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <div
        className={`border rounded-lg bg-card ${
          isRunning
            ? "border-green-600/30 bg-green-500/5"
            : isError
              ? "border-amber-500/30 bg-amber-500/5"
              : ""
        }`}
      >
        <CollapsibleTrigger asChild>
          <div className="flex flex-col p-3 cursor-pointer hover:bg-muted/50 transition-colors">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Terminal className="h-4 w-4" />
                <div>
                  <div className="font-mono font-medium text-sm">
                    {process.name}
                  </div>
                  {process.port && (
                    <span className="text-xs text-muted-foreground font-mono flex items-center gap-1">
                      :{process.port}
                      {process.health && process.health.portListening !== null && (
                        <span
                          className={`inline-block h-1.5 w-1.5 rounded-full ${
                            process.health.portListening
                              ? "bg-green-500"
                              : "bg-red-500"
                          }`}
                        />
                      )}
                    </span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 px-2"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleRestart();
                  }}
                  disabled={restarting}
                >
                  {restarting ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <RotateCcw className="h-3 w-3" />
                  )}
                </Button>
                <Badge
                  variant={isRunning ? "default" : isError ? "default" : "destructive"}
                  className={
                    isRunning
                      ? "bg-green-600 hover:bg-green-700"
                      : isError
                        ? "bg-amber-500 hover:bg-amber-600"
                        : ""
                  }
                >
                  {isRunning ? (
                    <CheckCircle2 className="h-3 w-3 mr-1" />
                  ) : isError ? (
                    <AlertTriangle className="h-3 w-3 mr-1" />
                  ) : (
                    <XCircle className="h-3 w-3 mr-1" />
                  )}
                  {process.status}
                </Badge>
                {isOpen ? (
                  <ChevronDown className="h-4 w-4 text-muted-foreground" />
                ) : (
                  <ChevronRight className="h-4 w-4 text-muted-foreground" />
                )}
              </div>
            </div>
            {/* Error summary for unhealthy processes */}
            {isError && process.health && !isOpen && (
              <div className="mt-2 pl-7 space-y-1">
                {process.health.portListening === false && process.port && (
                  <div className="text-xs text-amber-600 dark:text-amber-400 font-mono">
                    Port {process.port} not listening
                  </div>
                )}
                {process.health.httpOk === false && (
                  <div className="text-xs text-amber-600 dark:text-amber-400 font-mono">
                    Health check failed
                  </div>
                )}
                {process.health.errors.map((err, i) => (
                  <div
                    key={i}
                    className="text-xs text-amber-600 dark:text-amber-400 font-mono truncate max-w-full"
                  >
                    {err}
                  </div>
                ))}
              </div>
            )}
            {/* Last log line preview when collapsed */}
            {!isOpen && !isError && (
              <div className="mt-2 pl-7">
                {lastLog ? (
                  <div className="inline-block px-2 py-1 rounded bg-zinc-900 dark:bg-zinc-950 text-xs font-mono text-zinc-300 truncate max-w-full">
                    {lastLog}
                  </div>
                ) : (
                  <div className="inline-block px-2 py-1 rounded bg-zinc-900/50 dark:bg-zinc-950/50 text-xs font-mono text-zinc-500 italic">
                    No output
                  </div>
                )}
              </div>
            )}
          </div>
        </CollapsibleTrigger>

        <CollapsibleContent>
          <div className="border-t px-3 py-3">
            <TerminalView logs={process.logs} maxHeight="250px" />
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  );
}

export function AppsPanel() {
  const [data, setData] = useState<AppsResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchApps = useCallback(async () => {
    try {
      const response = await fetch("/api/apps");
      if (!response.ok) throw new Error("Failed to fetch apps");
      const result: AppsResponse = await response.json();
      setData(result);
    } catch (err) {
      console.error("Failed to fetch apps:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchApps();
    const interval = setInterval(fetchApps, 15000);
    return () => clearInterval(interval);
  }, [fetchApps]);

  const processes = data?.processes || [];
  const runningCount = processes.filter((p) => p.status === "running").length;

  // Group processes by their group field
  const grouped = processes.reduce(
    (acc, proc) => {
      const group = proc.group || "other";
      if (!acc[group]) acc[group] = [];
      acc[group].push(proc);
      return acc;
    },
    {} as Record<string, AppStatus[]>
  );

  const groupOrder = ["bridge", "engine", "dashboard"];

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Terminal className="h-5 w-5" />
            <CardTitle className="text-lg">Applications</CardTitle>
          </div>
          <div className="flex items-center gap-2">
            {loading && !data ? (
              <Skeleton className="h-6 w-24" />
            ) : (
              <Badge
                variant={
                  runningCount === processes.length && processes.length > 0
                    ? "default"
                    : "secondary"
                }
              >
                {runningCount}/{processes.length} running
              </Badge>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={fetchApps}
              disabled={loading && !data}
            >
              <RefreshCw
                className={`h-4 w-4 ${loading && !data ? "animate-spin" : ""}`}
              />
            </Button>
          </div>
        </div>
        <CardDescription>
          Overmind processes — bridge, engine, dashboard
        </CardDescription>
      </CardHeader>
      <CardContent>
        {loading && !data ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="space-y-6">
            {groupOrder.map((group) => {
              const procs = grouped[group];
              if (!procs || procs.length === 0) return null;

              return (
                <div key={group}>
                  <h4 className="text-sm font-medium text-muted-foreground mb-3">
                    {groupLabel(group)}
                  </h4>
                  <div className="space-y-2">
                    {procs.map((proc) => (
                      <ProcessCard
                        key={proc.name}
                        process={proc}
                        onRestart={() => {
                          // Re-fetch after a short delay to pick up new status
                          setTimeout(fetchApps, 3000);
                        }}
                      />
                    ))}
                  </div>
                </div>
              );
            })}
            {/* Catch any ungrouped processes */}
            {Object.entries(grouped)
              .filter(([g]) => !groupOrder.includes(g))
              .map(([group, procs]) => (
                <div key={group}>
                  <h4 className="text-sm font-medium text-muted-foreground mb-3">
                    {groupLabel(group)}
                  </h4>
                  <div className="space-y-2">
                    {procs.map((proc) => (
                      <ProcessCard
                        key={proc.name}
                        process={proc}
                        onRestart={() => {
                          setTimeout(fetchApps, 3000);
                        }}
                      />
                    ))}
                  </div>
                </div>
              ))}
            {processes.length === 0 && (
              <div className="text-center text-sm text-muted-foreground py-8">
                No Overmind processes found. Run{" "}
                <code className="bg-muted px-1 py-0.5 rounded">
                  make dev-apps
                </code>{" "}
                to start.
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
