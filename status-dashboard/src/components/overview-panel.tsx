"use client";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Database,
  Terminal,
  Link,
  ExternalLink,
  Pickaxe,
  CheckCircle2,
} from "lucide-react";
import type { StatusResponse } from "@/lib/types";

interface OverviewPanelProps {
  data: StatusResponse | null;
  loading: boolean;
}

function InfraCard({
  data,
  loading,
}: {
  data: StatusResponse | null;
  loading: boolean;
}) {
  if (loading || !data) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <Database className="h-4 w-4" />
            <CardTitle className="text-sm">Infrastructure</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-8 w-full mb-2" />
          <Skeleton className="h-4 w-24" />
        </CardContent>
      </Card>
    );
  }

  const { running, total } = data.infraSummary;
  const allHealthy = running === total;
  const pct = total > 0 ? (running / total) * 100 : 0;

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Database className="h-4 w-4" />
            <CardTitle className="text-sm">Infrastructure</CardTitle>
          </div>
          <Badge
            variant={allHealthy ? "default" : "secondary"}
            className={allHealthy ? "bg-green-600 hover:bg-green-700" : ""}
          >
            {allHealthy ? (
              <CheckCircle2 className="h-3 w-3 mr-1" />
            ) : null}
            {running}/{total} healthy
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <div className="w-full bg-muted rounded-full h-2 mb-2">
          <div
            className={`h-2 rounded-full transition-all ${
              allHealthy ? "bg-green-500" : pct > 50 ? "bg-amber-500" : "bg-red-500"
            }`}
            style={{ width: `${pct}%` }}
          />
        </div>
        <p className="text-xs text-muted-foreground">
          Docker containers
        </p>
      </CardContent>
    </Card>
  );
}

function AppsCard({
  data,
  loading,
}: {
  data: StatusResponse | null;
  loading: boolean;
}) {
  if (loading || !data) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <Terminal className="h-4 w-4" />
            <CardTitle className="text-sm">Applications</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-8 w-full mb-2" />
          <Skeleton className="h-4 w-24" />
        </CardContent>
      </Card>
    );
  }

  const { healthy, total } = data.appsSummary;
  const allHealthy = healthy === total;
  const pct = total > 0 ? (healthy / total) * 100 : 0;

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Terminal className="h-4 w-4" />
            <CardTitle className="text-sm">Applications</CardTitle>
          </div>
          <Badge
            variant={allHealthy ? "default" : "secondary"}
            className={allHealthy ? "bg-green-600 hover:bg-green-700" : ""}
          >
            {allHealthy ? (
              <CheckCircle2 className="h-3 w-3 mr-1" />
            ) : null}
            {healthy}/{total} healthy
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <div className="w-full bg-muted rounded-full h-2 mb-2">
          <div
            className={`h-2 rounded-full transition-all ${
              allHealthy ? "bg-green-500" : pct > 50 ? "bg-amber-500" : "bg-red-500"
            }`}
            style={{ width: `${pct}%` }}
          />
        </div>
        <p className="text-xs text-muted-foreground">
          Overmind processes
        </p>
      </CardContent>
    </Card>
  );
}

function ChainVitalsCard({
  data,
  loading,
}: {
  data: StatusResponse | null;
  loading: boolean;
}) {
  if (loading || !data) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <Link className="h-4 w-4" />
            <CardTitle className="text-sm">Chain Vitals</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-4 w-full mb-2" />
          <Skeleton className="h-4 w-full mb-2" />
          <Skeleton className="h-4 w-3/4" />
        </CardContent>
      </Card>
    );
  }

  const { chain } = data;

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Link className="h-4 w-4" />
            <CardTitle className="text-sm">Chain Vitals</CardTitle>
          </div>
          <Badge
            variant={chain.miningActive ? "default" : "secondary"}
            className={chain.miningActive ? "bg-amber-500 hover:bg-amber-600" : ""}
          >
            <Pickaxe className="h-3 w-3 mr-1" />
            {chain.miningActive ? "Mining" : "Idle"}
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
          <div className="text-muted-foreground">Height</div>
          <div className="font-mono text-right">
            {chain.height !== null ? chain.height.toLocaleString() : "--"}
          </div>

          <div className="text-muted-foreground">Oracle Price</div>
          <div className="font-mono text-right">
            {chain.oraclePrice !== null
              ? `$${chain.oraclePrice.toFixed(2)}`
              : "--"}
          </div>

          <div className="text-muted-foreground">Anvil Block</div>
          <div className="font-mono text-right">
            {chain.anvilBlock !== null
              ? chain.anvilBlock.toLocaleString()
              : "--"}
          </div>

          {chain.checkpoint !== null && (
            <>
              <div className="text-muted-foreground">Checkpoint</div>
              <div className="font-mono text-right">
                block {chain.checkpoint.toLocaleString()}
              </div>
            </>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export function OverviewPanel({ data, loading }: OverviewPanelProps) {
  return (
    <div className="space-y-4">
      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <InfraCard data={data} loading={loading} />
        <AppsCard data={data} loading={loading} />
        <ChainVitalsCard data={data} loading={loading} />
      </div>

      {/* Quick Links */}
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" size="sm" asChild>
          <a
            href="http://localhost:7050"
            target="_blank"
            rel="noopener noreferrer"
          >
            <ExternalLink className="h-4 w-4 mr-2" />
            Bridge UI (:7050)
          </a>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <a
            href="http://localhost:7000"
            target="_blank"
            rel="noopener noreferrer"
          >
            <ExternalLink className="h-4 w-4 mr-2" />
            Engine (:7000)
          </a>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <a
            href="http://localhost:7050/admin"
            target="_blank"
            rel="noopener noreferrer"
          >
            <ExternalLink className="h-4 w-4 mr-2" />
            Bridge Admin
          </a>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <a
            href="http://localhost:4000"
            target="_blank"
            rel="noopener noreferrer"
          >
            <ExternalLink className="h-4 w-4 mr-2" />
            Explorer (:4000)
          </a>
        </Button>
      </div>
    </div>
  );
}
