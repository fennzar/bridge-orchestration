"use client";

import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Loader2,
  Play,
  Circle,
} from "lucide-react";

export type TestStatus = "idle" | "running" | "pass" | "fail" | "skip";

interface TestCardProps {
  id: string;
  name: string;
  selected: boolean;
  status: TestStatus;
  disabled?: boolean;
  onToggle: (checked: boolean) => void;
  onRun: () => void;
}

function StatusBadge({ status }: { status: TestStatus }) {
  switch (status) {
    case "running":
      return (
        <Badge variant="secondary" className="bg-blue-500/20 text-blue-400">
          <Loader2 className="h-3 w-3 mr-1 animate-spin" />
          Running
        </Badge>
      );
    case "pass":
      return (
        <Badge variant="default" className="bg-green-600 hover:bg-green-700">
          <CheckCircle2 className="h-3 w-3 mr-1" />
          Pass
        </Badge>
      );
    case "fail":
      return (
        <Badge variant="destructive">
          <XCircle className="h-3 w-3 mr-1" />
          Fail
        </Badge>
      );
    case "skip":
      return (
        <Badge variant="secondary" className="bg-yellow-500/20 text-yellow-400">
          <AlertTriangle className="h-3 w-3 mr-1" />
          Skip
        </Badge>
      );
    default:
      return (
        <Badge variant="outline" className="text-muted-foreground">
          <Circle className="h-3 w-3 mr-1" />
          Idle
        </Badge>
      );
  }
}

export function TestCard({
  id,
  name,
  selected,
  status,
  disabled,
  onToggle,
  onRun,
}: TestCardProps) {
  const isRunning = status === "running";

  return (
    <div
      className={`flex items-center justify-between p-3 rounded-lg transition-colors ${
        status === "pass"
          ? "bg-green-500/5 border border-green-500/20"
          : status === "fail"
            ? "bg-red-500/5 border border-red-500/20"
            : status === "running"
              ? "bg-blue-500/5 border border-blue-500/20"
              : "bg-muted/50 border border-transparent"
      }`}
    >
      <div className="flex items-center gap-3">
        <Checkbox
          id={`test-${id}`}
          checked={selected}
          onCheckedChange={onToggle}
          disabled={disabled || isRunning}
        />
        <label
          htmlFor={`test-${id}`}
          className="flex items-center gap-2 cursor-pointer"
        >
          <span className="font-mono text-sm text-muted-foreground">{id}</span>
          <span className="font-medium text-sm">{name}</span>
        </label>
      </div>
      <div className="flex items-center gap-2">
        <StatusBadge status={status} />
        <Button
          variant="ghost"
          size="sm"
          onClick={onRun}
          disabled={disabled || isRunning}
          className="h-7 px-2"
        >
          <Play className="h-3 w-3" />
        </Button>
      </div>
    </div>
  );
}
