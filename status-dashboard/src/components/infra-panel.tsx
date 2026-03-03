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
  Database,
  Server,
  Wallet,
  Pickaxe,
  Radio,
  HardDrive,
  Globe,
  ChevronDown,
  ChevronRight,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Loader2,
} from "lucide-react";
import { TerminalView } from "@/components/terminal-view";
import type { ContainerStatus, InfraResponse } from "@/lib/types";
import { truncateAddress } from "@/components/shared/copy-address";

function containerIcon(type: string) {
  switch (type) {
    case "daemon":
      return <Server className="h-4 w-4" />;
    case "wallet":
      return <Wallet className="h-4 w-4" />;
    case "miningWallet":
      return <Pickaxe className="h-4 w-4" />;
    case "oracle":
    case "orderbook":
      return <Radio className="h-4 w-4" />;
    case "evm":
      return <HardDrive className="h-4 w-4" />;
    case "explorer":
      return <Globe className="h-4 w-4" />;
    default:
      return <Database className="h-4 w-4" />;
  }
}

function containerMetric(container: ContainerStatus) {
  if (container.height !== undefined) {
    return (
      <span className="text-xs text-muted-foreground font-mono">
        H: {container.height.toLocaleString()}
      </span>
    );
  }
  if (container.address && container.balance) {
    return (
      <span className="text-xs text-muted-foreground font-mono">
        {truncateAddress(container.address)} | {container.balance.unlocked}
      </span>
    );
  }
  if (container.price !== undefined) {
    return (
      <span className="text-xs text-muted-foreground font-mono">
        ${container.price.toFixed(2)}
      </span>
    );
  }
  if (container.blockNumber !== undefined) {
    return (
      <span className="text-xs text-muted-foreground font-mono">
        Block {container.blockNumber.toLocaleString()}
      </span>
    );
  }
  if (container.health) {
    return (
      <span className="text-xs text-muted-foreground">{container.health}</span>
    );
  }
  return null;
}

function ContainerCard({ container }: { container: ContainerStatus }) {
  const [isOpen, setIsOpen] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [logsLoading, setLogsLoading] = useState(false);

  const fetchLogs = async () => {
    setLogsLoading(true);
    try {
      const response = await fetch(
        `/api/infra/${encodeURIComponent(container.name)}/logs`
      );
      if (response.ok) {
        const data = await response.json();
        setLogs(data.logs || []);
      }
    } catch {
      setLogs(["Failed to fetch logs"]);
    } finally {
      setLogsLoading(false);
    }
  };

  const handleOpenChange = (open: boolean) => {
    setIsOpen(open);
    if (open && logs.length === 0) {
      fetchLogs();
    }
  };

  const isRunning = container.status === "running";
  const hasErrors = isRunning && container.errors && container.errors.length > 0;

  return (
    <Collapsible open={isOpen} onOpenChange={handleOpenChange}>
      <div
        className={`border rounded-lg bg-card ${
          hasErrors
            ? "border-amber-500/30 bg-amber-500/5"
            : isRunning
              ? "border-green-600/30 bg-green-500/5"
              : ""
        }`}
      >
        <CollapsibleTrigger asChild>
          <div className="flex flex-col p-3 cursor-pointer hover:bg-muted/50 transition-colors">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                {containerIcon(container.type)}
                <div>
                  <div className="font-mono font-medium text-sm">
                    {container.name}
                  </div>
                  <div className="flex items-center gap-2">
                    {container.port > 0 && (
                      <span className="text-xs text-muted-foreground font-mono">
                        :{container.port}
                      </span>
                    )}
                    {containerMetric(container)}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {container.mining?.active && (
                  <Badge
                    variant="default"
                    className="bg-amber-500 hover:bg-amber-600"
                  >
                    <Pickaxe className="h-3 w-3 mr-1" />
                    Mining
                  </Badge>
                )}
                {hasErrors && (
                  <Badge
                    variant="default"
                    className="bg-amber-500 hover:bg-amber-600"
                  >
                    <AlertTriangle className="h-3 w-3 mr-1" />
                    errors
                  </Badge>
                )}
                <Badge
                  variant={isRunning ? "default" : "destructive"}
                  className={
                    isRunning && !hasErrors
                      ? "bg-green-600 hover:bg-green-700"
                      : isRunning && hasErrors
                        ? "bg-amber-500 hover:bg-amber-600"
                        : ""
                  }
                >
                  {isRunning && !hasErrors ? (
                    <CheckCircle2 className="h-3 w-3 mr-1" />
                  ) : isRunning && hasErrors ? (
                    <AlertTriangle className="h-3 w-3 mr-1" />
                  ) : (
                    <XCircle className="h-3 w-3 mr-1" />
                  )}
                  {container.status}
                </Badge>
                {isOpen ? (
                  <ChevronDown className="h-4 w-4 text-muted-foreground" />
                ) : (
                  <ChevronRight className="h-4 w-4 text-muted-foreground" />
                )}
              </div>
            </div>
            {/* Error summary when collapsed */}
            {hasErrors && !isOpen && (
              <div className="mt-2 pl-7 space-y-1">
                {container.errors!.slice(0, 2).map((err, i) => (
                  <div
                    key={i}
                    className="text-xs text-amber-600 dark:text-amber-400 font-mono truncate max-w-full"
                  >
                    {err}
                  </div>
                ))}
              </div>
            )}
          </div>
        </CollapsibleTrigger>

        <CollapsibleContent>
          <div className="border-t px-3 py-3 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">
                Last 20 log lines
              </span>
              <Button
                variant="ghost"
                size="sm"
                onClick={fetchLogs}
                disabled={logsLoading}
              >
                <RefreshCw
                  className={`h-3 w-3 ${logsLoading ? "animate-spin" : ""}`}
                />
              </Button>
            </div>
            {logsLoading && logs.length === 0 ? (
              <Skeleton className="h-[100px] w-full rounded-md" />
            ) : (
              <TerminalView logs={logs} maxHeight="200px" />
            )}
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  );
}

export function InfraPanel() {
  const [data, setData] = useState<InfraResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchInfra = useCallback(async () => {
    try {
      const response = await fetch("/api/infra");
      if (!response.ok) throw new Error("Failed to fetch infra");
      const result: InfraResponse = await response.json();
      setData(result);
    } catch (err) {
      console.error("Failed to fetch infra:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchInfra();
    const interval = setInterval(fetchInfra, 10000);
    return () => clearInterval(interval);
  }, [fetchInfra]);

  const containers = data?.containers || [];
  const runningCount = containers.filter((c) => c.status === "running").length;

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Database className="h-5 w-5" />
            <CardTitle className="text-lg">Infrastructure</CardTitle>
          </div>
          <div className="flex items-center gap-2">
            {loading && !data ? (
              <Skeleton className="h-6 w-24" />
            ) : (
              <Badge
                variant={
                  runningCount === containers.length ? "default" : "secondary"
                }
              >
                {runningCount}/{containers.length} running
              </Badge>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={fetchInfra}
              disabled={loading && !data}
            >
              <RefreshCw
                className={`h-4 w-4 ${loading && !data ? "animate-spin" : ""}`}
              />
            </Button>
          </div>
        </div>
        <CardDescription>
          Docker containers — daemons, wallets, oracle, Anvil, Redis, Postgres
        </CardDescription>
      </CardHeader>
      <CardContent>
        {loading && !data ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="space-y-2">
            {containers.map((container) => (
              <ContainerCard key={container.name} container={container} />
            ))}
            {containers.length === 0 && (
              <div className="text-center text-sm text-muted-foreground py-8">
                No containers found. Is Docker running?
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
