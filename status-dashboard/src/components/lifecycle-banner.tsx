"use client";

import { Activity, Server, Loader2, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import type { LifecycleState } from "@/lib/types";

interface LifecycleBannerProps {
  state: LifecycleState;
}

const BANNER_CONFIG: Record<
  LifecycleState,
  {
    icon: React.ElementType;
    label: string;
    description: string;
    classes: string;
  }
> = {
  running: {
    icon: Activity,
    label: "Running",
    description: "All systems operational — Docker infra + Overmind apps running",
    classes:
      "bg-green-500/10 border-green-500/30 text-green-700 dark:text-green-400",
  },
  "infra-only": {
    icon: Server,
    label: "Infra Only",
    description:
      "Infrastructure only — Docker containers running, Overmind apps not started",
    classes:
      "bg-blue-500/10 border-blue-500/30 text-blue-700 dark:text-blue-400",
  },
  initializing: {
    icon: Loader2,
    label: "Initializing",
    description: "Initializing — Docker containers starting, no checkpoint yet",
    classes:
      "bg-amber-500/10 border-amber-500/30 text-amber-700 dark:text-amber-400",
  },
  stopped: {
    icon: XCircle,
    label: "Stopped",
    description: "Stopped — No infrastructure running",
    classes: "bg-red-500/10 border-red-500/30 text-red-700 dark:text-red-400",
  },
};

export function LifecycleBanner({ state }: LifecycleBannerProps) {
  const config = BANNER_CONFIG[state];
  const Icon = config.icon;
  const isAnimated = state === "initializing";

  return (
    <div
      className={cn(
        "flex items-center gap-3 rounded-lg border px-4 py-3",
        config.classes
      )}
    >
      <Icon
        className={cn("h-5 w-5 shrink-0", isAnimated && "animate-spin")}
      />
      <div className="flex flex-col sm:flex-row sm:items-center sm:gap-2">
        <span className="font-semibold text-sm">{config.label}</span>
        <span className="text-sm opacity-80">{config.description}</span>
      </div>
    </div>
  );
}
