"use client";

import { useEffect, useState, useCallback } from "react";
import { useTheme } from "next-themes";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Separator } from "@/components/ui/separator";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  Activity,
  RefreshCw,
  Clock,
  Moon,
  Sun,
  XCircle,
  Database,
  Terminal,
  Mountain,
  Hexagon,
  FlaskConical,
  LayoutDashboard,
} from "lucide-react";
import { LifecycleBanner } from "@/components/lifecycle-banner";
import { OverviewPanel } from "@/components/overview-panel";
import { InfraPanel } from "@/components/infra-panel";
import { AppsPanel } from "@/components/apps-panel";
import { ZephyrPanel } from "@/components/zephyr-panel";
import { EvmPanel } from "@/components/evm-panel";
import { TestsPanel } from "@/components/tests-panel";
import type { StatusResponse } from "@/lib/types";

function ThemeToggle() {
  const { setTheme, resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  // This pattern is required for SSR hydration with next-themes
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => setMounted(true), []);

  if (!mounted) {
    return (
      <Button variant="outline" size="icon" disabled>
        <Sun className="h-4 w-4" />
      </Button>
    );
  }

  const isDark = resolvedTheme === "dark";

  return (
    <Button
      variant="outline"
      size="icon"
      onClick={() => setTheme(isDark ? "light" : "dark")}
    >
      {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </Button>
  );
}

export function StatusDashboard() {
  const [data, setData] = useState<StatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const fetchStatus = useCallback(async () => {
    try {
      setLoading(true);
      const response = await fetch("/api/status");
      if (!response.ok) throw new Error("Failed to fetch status");
      const result: StatusResponse = await response.json();
      setData(result);
      setError(null);
      setLastRefresh(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(fetchStatus, 10000);
    return () => clearInterval(interval);
  }, [autoRefresh, fetchStatus]);

  const handleRefresh = () => {
    fetchStatus();
  };

  const lifecycleState = data?.lifecycle ?? "stopped";

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Activity className="h-6 w-6" />
            Zephyr Bridge DEVNET Status
          </h1>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Clock className="h-4 w-4" />
            {lastRefresh ? (
              <span>Updated {lastRefresh.toLocaleTimeString()}</span>
            ) : (
              <span>Loading...</span>
            )}
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setAutoRefresh(!autoRefresh)}
          >
            {autoRefresh ? "Auto ON" : "Auto OFF"}
          </Button>
          <Button
            variant="default"
            size="sm"
            onClick={handleRefresh}
            disabled={loading}
          >
            <RefreshCw
              className={`h-4 w-4 mr-2 ${loading ? "animate-spin" : ""}`}
            />
            Refresh
          </Button>
          <ThemeToggle />
        </div>
      </div>

      {/* Lifecycle Banner */}
      <LifecycleBanner state={lifecycleState} />

      {/* Error alert */}
      {error && (
        <Alert variant="destructive">
          <XCircle className="h-4 w-4" />
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Main Tabbed Content */}
      <Tabs defaultValue="overview" className="space-y-4">
        <TabsList>
          <TabsTrigger value="overview">
            <LayoutDashboard className="h-4 w-4 mr-1" />
            Overview
          </TabsTrigger>
          <TabsTrigger value="infra">
            <Database className="h-4 w-4 mr-1" />
            Infrastructure
          </TabsTrigger>
          <TabsTrigger value="apps">
            <Terminal className="h-4 w-4 mr-1" />
            Apps
          </TabsTrigger>
          <TabsTrigger value="chain">
            <Mountain className="h-4 w-4 mr-1" />
            Zephyr
          </TabsTrigger>
          <TabsTrigger value="evm">
            <Hexagon className="h-4 w-4 mr-1" />
            EVM
          </TabsTrigger>
          <TabsTrigger value="tests">
            <FlaskConical className="h-4 w-4 mr-1" />
            Tests
          </TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <OverviewPanel data={data} loading={loading && !data} />
        </TabsContent>

        <TabsContent value="infra">
          <InfraPanel />
        </TabsContent>

        <TabsContent value="apps">
          <AppsPanel />
        </TabsContent>

        <TabsContent value="chain">
          <ZephyrPanel />
        </TabsContent>

        <TabsContent value="evm">
          <EvmPanel />
        </TabsContent>

        <TabsContent value="tests">
          <TestsPanel />
        </TabsContent>
      </Tabs>

      {/* Footer */}
      <Separator />
      <div className="text-center text-sm text-muted-foreground">
        <p>
          Run{" "}
          <code className="bg-muted px-1 py-0.5 rounded">make status</code>{" "}
          for CLI status check
        </p>
      </div>
    </div>
  );
}
