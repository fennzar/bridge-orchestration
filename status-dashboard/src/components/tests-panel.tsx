"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Checkbox } from "@/components/ui/checkbox";
import {
  FlaskConical,
  Play,
  Square,
  RefreshCw,
  ChevronDown,
  ChevronRight,
  Loader2,
} from "lucide-react";
import { TerminalView } from "@/components/terminal-view";
import { TestCard, TestStatus } from "@/components/test-card";
import type { TestInfo } from "@/lib/types";

interface TestsState {
  tests: TestInfo[];
  selectedTests: Set<string>;
  runState: "idle" | "running" | "completed";
  currentTest?: string;
  results: Map<string, TestStatus>;
  output: string[];
  startTime?: number;
  endTime?: number;
  runId?: string;
  // Fallback counts from complete event
  completeSummary?: { pass: number; fail: number; skip: number };
}

const LEVEL_DESCRIPTIONS: Record<string, string> = {
  L1: "Infrastructure",
  L2: "Smoke Tests",
  L3: "Component Features",
  L4: "Full Stack E2E",
  L5: "Edge Cases",
};

export function TestsPanel() {
  const [state, setState] = useState<TestsState>({
    tests: [],
    selectedTests: new Set(),
    runState: "idle",
    results: new Map(),
    output: [],
  });

  const [expandedLevels, setExpandedLevels] = useState<Set<string>>(
    new Set(["L1", "L2"])
  );
  const [loading, setLoading] = useState(true);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Fetch available tests
  const fetchTests = useCallback(async () => {
    try {
      setLoading(true);
      const response = await fetch("/api/tests");
      if (!response.ok) throw new Error("Failed to fetch tests");
      const data = await response.json();
      setState((prev) => ({
        ...prev,
        tests: data.tests,
      }));
    } catch (err) {
      console.error("Failed to fetch tests:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTests();
  }, [fetchTests]);

  // Toggle test selection
  const toggleTest = (testId: string, checked: boolean) => {
    setState((prev) => {
      const newSelected = new Set(prev.selectedTests);
      if (checked) {
        newSelected.add(testId);
      } else {
        newSelected.delete(testId);
      }
      return { ...prev, selectedTests: newSelected };
    });
  };

  // Toggle all tests in a level
  const toggleLevel = (level: string, checked: boolean) => {
    setState((prev) => {
      const newSelected = new Set(prev.selectedTests);
      const levelTests = prev.tests.filter((t) => t.level === level);
      for (const test of levelTests) {
        if (checked) {
          newSelected.add(test.id);
        } else {
          newSelected.delete(test.id);
        }
      }
      return { ...prev, selectedTests: newSelected };
    });
  };

  // Check if all tests in a level are selected
  const isLevelSelected = (level: string): boolean => {
    const levelTests = state.tests.filter((t) => t.level === level);
    return levelTests.length > 0 && levelTests.every((t) => state.selectedTests.has(t.id));
  };

  // Check if some tests in a level are selected
  const isLevelPartiallySelected = (level: string): boolean => {
    const levelTests = state.tests.filter((t) => t.level === level);
    const selectedCount = levelTests.filter((t) =>
      state.selectedTests.has(t.id)
    ).length;
    return selectedCount > 0 && selectedCount < levelTests.length;
  };

  // Run tests via SSE
  const runTests = async (testIds?: string[], level?: string) => {
    // Reset state
    setState((prev) => ({
      ...prev,
      runState: "running",
      currentTest: undefined,
      results: new Map(),
      output: [],
      startTime: Date.now(),
      endTime: undefined,
      completeSummary: undefined,
    }));

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const body: { testIds?: string[]; level?: string } = {};
      if (testIds && testIds.length > 0) {
        body.testIds = testIds;
      } else if (level) {
        body.level = level;
      }

      const response = await fetch("/api/tests/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      if (!response.ok || !response.body) {
        throw new Error("Failed to start test run");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Process complete SSE events
        const lines = buffer.split("\n\n");
        buffer = lines.pop() || "";

        for (const chunk of lines) {
          if (!chunk.trim()) continue;

          const eventLines = chunk.split("\n");
          let eventType = "";
          let eventData = "";

          for (const line of eventLines) {
            if (line.startsWith("event: ")) {
              eventType = line.substring(7);
            } else if (line.startsWith("data: ")) {
              eventData = line.substring(6);
            }
          }

          if (eventType && eventData) {
            try {
              const data = JSON.parse(eventData);
              handleSSEEvent(eventType, data);
            } catch {
              // Ignore parse errors
            }
          }
        }
      }
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") {
        // Test run was aborted
        setState((prev) => ({
          ...prev,
          runState: "completed",
          endTime: Date.now(),
          output: [...prev.output, "\n[Aborted by user]"],
        }));
      } else {
        console.error("Test run error:", err);
        setState((prev) => ({
          ...prev,
          runState: "completed",
          endTime: Date.now(),
          output: [
            ...prev.output,
            `\n[Error: ${err instanceof Error ? err.message : "Unknown error"}]`,
          ],
        }));
      }
    } finally {
      abortControllerRef.current = null;
    }
  };

  // Handle SSE events
  const handleSSEEvent = (event: string, data: unknown) => {
    const eventData = data as Record<string, unknown>;

    switch (event) {
      case "start":
        setState((prev) => ({
          ...prev,
          runId: eventData.runId as string,
        }));
        break;

      case "output":
        setState((prev) => ({
          ...prev,
          output: [...prev.output, eventData.line as string],
        }));
        break;

      case "running":
        setState((prev) => ({
          ...prev,
          currentTest: eventData.testId as string,
          results: new Map(prev.results).set(
            eventData.testId as string,
            "running"
          ),
        }));
        break;

      case "result":
        setState((prev) => ({
          ...prev,
          results: new Map(prev.results).set(
            eventData.testId as string,
            eventData.status as TestStatus
          ),
        }));
        break;

      case "complete":
        setState((prev) => ({
          ...prev,
          runState: "completed",
          currentTest: undefined,
          endTime: Date.now(),
          // Store summary counts from event as fallback
          completeSummary: {
            pass: (eventData.pass as number) || 0,
            fail: (eventData.fail as number) || 0,
            skip: (eventData.skip as number) || 0,
          },
        }));
        break;

      case "error":
        setState((prev) => ({
          ...prev,
          runState: "completed",
          endTime: Date.now(),
          output: [...prev.output, `[Error: ${eventData.message}]`],
        }));
        break;
    }
  };

  // Abort running tests
  const abortTests = async () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    if (state.runId) {
      try {
        await fetch("/api/tests/abort", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ runId: state.runId }),
        });
      } catch {
        // Ignore abort errors
      }
    }
  };

  // Calculate results summary (use individual results, fallback to complete event counts)
  const resultsPassCount = Array.from(state.results.values()).filter(
    (s) => s === "pass"
  ).length;
  const resultsFailCount = Array.from(state.results.values()).filter(
    (s) => s === "fail"
  ).length;
  const resultsSkipCount = Array.from(state.results.values()).filter(
    (s) => s === "skip"
  ).length;

  // Use individual results if available, otherwise fallback to complete summary
  const passCount = resultsPassCount || state.completeSummary?.pass || 0;
  const failCount = resultsFailCount || state.completeSummary?.fail || 0;
  const skipCount = resultsSkipCount || state.completeSummary?.skip || 0;

  const duration =
    state.startTime && state.endTime
      ? ((state.endTime - state.startTime) / 1000).toFixed(1)
      : state.startTime
        ? ((Date.now() - state.startTime) / 1000).toFixed(1)
        : null;

  // Group tests by level
  const testsByLevel = state.tests.reduce(
    (acc, test) => {
      if (!acc[test.level]) acc[test.level] = [];
      acc[test.level].push(test);
      return acc;
    },
    {} as Record<string, TestInfo[]>
  );

  // For L5, group by sublevel within the level
  const l5BySublevel = (testsByLevel["L5"] || []).reduce(
    (acc, test) => {
      const sub = test.sublevel || "Other";
      if (!acc[sub]) acc[sub] = [];
      acc[sub].push(test);
      return acc;
    },
    {} as Record<string, TestInfo[]>
  );

  const levels = ["L1", "L2", "L3", "L4", "L5"] as const;

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FlaskConical className="h-5 w-5" />
            <CardTitle className="text-lg">Test Runner</CardTitle>
          </div>
          <div className="flex items-center gap-2">
            {state.runState !== "idle" && (
              <div className="flex items-center gap-4 mr-4 text-sm">
                <span className="text-green-500">Pass: {passCount}</span>
                <span className="text-red-500">Fail: {failCount}</span>
                <span className="text-yellow-500">Skip: {skipCount}</span>
                {duration && (
                  <span className="text-muted-foreground">{duration}s</span>
                )}
              </div>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={fetchTests}
              disabled={loading || state.runState === "running"}
            >
              <RefreshCw
                className={`h-4 w-4 ${loading ? "animate-spin" : ""}`}
              />
            </Button>
          </div>
        </div>
        <CardDescription>
          Run infrastructure, smoke, integration, and edge-case tests
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Run Controls */}
        <div className="flex items-center gap-2 p-3 rounded-lg bg-muted/50">
          <Button
            onClick={() => runTests()}
            disabled={state.runState === "running"}
            size="sm"
          >
            {state.runState === "running" ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Play className="h-4 w-4 mr-2" />
            )}
            Run All L1/L2
          </Button>
          <Button
            onClick={() => runTests(undefined, "L5")}
            disabled={state.runState === "running"}
            variant="secondary"
            size="sm"
          >
            <Play className="h-4 w-4 mr-2" />
            Run L5
          </Button>
          <Button
            onClick={() => runTests(Array.from(state.selectedTests))}
            disabled={
              state.runState === "running" || state.selectedTests.size === 0
            }
            variant="secondary"
            size="sm"
          >
            <Play className="h-4 w-4 mr-2" />
            Run Selected ({state.selectedTests.size})
          </Button>
          {state.runState === "running" && (
            <Button onClick={abortTests} variant="destructive" size="sm">
              <Square className="h-4 w-4 mr-2" />
              Stop
            </Button>
          )}
          <div className="flex-1" />
          <Badge variant="outline">
            {state.tests.length} tests available
          </Badge>
        </div>

        {/* Test Levels */}
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="space-y-2">
            {levels.map((level) => {
              const levelTests = testsByLevel[level] || [];
              if (levelTests.length === 0) return null;

              const isExpanded = expandedLevels.has(level);
              const allSelected = isLevelSelected(level);
              const partiallySelected = isLevelPartiallySelected(level);

              // L5: render with sublevel grouping
              if (level === "L5") {
                const sublevelKeys = Object.keys(l5BySublevel).sort();

                return (
                  <Collapsible
                    key={level}
                    open={isExpanded}
                    onOpenChange={(open) => {
                      setExpandedLevels((prev) => {
                        const next = new Set(prev);
                        if (open) {
                          next.add(level);
                        } else {
                          next.delete(level);
                        }
                        return next;
                      });
                    }}
                  >
                    <div className="border rounded-lg">
                      <CollapsibleTrigger asChild>
                        <div className="flex items-center justify-between p-3 cursor-pointer hover:bg-muted/50 transition-colors">
                          <div className="flex items-center gap-3">
                            <Checkbox
                              checked={allSelected}
                              onCheckedChange={(checked) =>
                                toggleLevel(level, !!checked)
                              }
                              onClick={(e) => e.stopPropagation()}
                              disabled={state.runState === "running"}
                              data-state={
                                partiallySelected
                                  ? "indeterminate"
                                  : undefined
                              }
                            />
                            <div className="flex items-center gap-2">
                              {isExpanded ? (
                                <ChevronDown className="h-4 w-4 text-muted-foreground" />
                              ) : (
                                <ChevronRight className="h-4 w-4 text-muted-foreground" />
                              )}
                              <span className="font-medium">
                                {level}: {LEVEL_DESCRIPTIONS[level]}
                              </span>
                              <Badge variant="outline" className="ml-2">
                                {levelTests.length}
                              </Badge>
                            </div>
                          </div>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation();
                              runTests(undefined, level);
                            }}
                            disabled={state.runState === "running"}
                          >
                            <Play className="h-3 w-3 mr-1" />
                            Run {level}
                          </Button>
                        </div>
                      </CollapsibleTrigger>
                      <CollapsibleContent>
                        <div className="border-t px-3 pb-3 pt-2 space-y-4">
                          {sublevelKeys.map((sublevel) => {
                            const subTests = l5BySublevel[sublevel];
                            return (
                              <div key={sublevel}>
                                <div className="flex items-center gap-2 mb-2">
                                  <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                                    {sublevel}
                                  </span>
                                  <Badge
                                    variant="outline"
                                    className="text-xs"
                                  >
                                    {subTests.length}
                                  </Badge>
                                </div>
                                <div className="space-y-2">
                                  {subTests.map((test) => (
                                    <TestCard
                                      key={test.id}
                                      id={test.id}
                                      name={test.name}
                                      selected={state.selectedTests.has(
                                        test.id
                                      )}
                                      status={
                                        state.results.get(test.id) || "idle"
                                      }
                                      disabled={state.runState === "running"}
                                      onToggle={(checked) =>
                                        toggleTest(test.id, checked)
                                      }
                                      onRun={() => runTests([test.id])}
                                    />
                                  ))}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </CollapsibleContent>
                    </div>
                  </Collapsible>
                );
              }

              // L1-L4: standard rendering
              return (
                <Collapsible
                  key={level}
                  open={isExpanded}
                  onOpenChange={(open) => {
                    setExpandedLevels((prev) => {
                      const next = new Set(prev);
                      if (open) {
                        next.add(level);
                      } else {
                        next.delete(level);
                      }
                      return next;
                    });
                  }}
                >
                  <div className="border rounded-lg">
                    <CollapsibleTrigger asChild>
                      <div className="flex items-center justify-between p-3 cursor-pointer hover:bg-muted/50 transition-colors">
                        <div className="flex items-center gap-3">
                          <Checkbox
                            checked={allSelected}
                            onCheckedChange={(checked) =>
                              toggleLevel(level, !!checked)
                            }
                            onClick={(e) => e.stopPropagation()}
                            disabled={state.runState === "running"}
                            data-state={
                              partiallySelected ? "indeterminate" : undefined
                            }
                          />
                          <div className="flex items-center gap-2">
                            {isExpanded ? (
                              <ChevronDown className="h-4 w-4 text-muted-foreground" />
                            ) : (
                              <ChevronRight className="h-4 w-4 text-muted-foreground" />
                            )}
                            <span className="font-medium">
                              {level}: {LEVEL_DESCRIPTIONS[level]}
                            </span>
                            <Badge variant="outline" className="ml-2">
                              {levelTests.length}
                            </Badge>
                          </div>
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={(e) => {
                            e.stopPropagation();
                            runTests(undefined, level);
                          }}
                          disabled={state.runState === "running"}
                        >
                          <Play className="h-3 w-3 mr-1" />
                          Run {level}
                        </Button>
                      </div>
                    </CollapsibleTrigger>
                    <CollapsibleContent>
                      <div className="border-t px-3 pb-3 pt-2 space-y-2">
                        {levelTests.map((test) => (
                          <TestCard
                            key={test.id}
                            id={test.id}
                            name={test.name}
                            selected={state.selectedTests.has(test.id)}
                            status={state.results.get(test.id) || "idle"}
                            disabled={state.runState === "running"}
                            onToggle={(checked) => toggleTest(test.id, checked)}
                            onRun={() => runTests([test.id])}
                          />
                        ))}
                      </div>
                    </CollapsibleContent>
                  </div>
                </Collapsible>
              );
            })}
          </div>
        )}

        {/* Output Terminal */}
        {state.output.length > 0 && (
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-muted-foreground">
                Test Output
              </span>
              <Button
                variant="ghost"
                size="sm"
                onClick={() =>
                  setState((prev) => ({ ...prev, output: [], results: new Map() }))
                }
                disabled={state.runState === "running"}
              >
                Clear
              </Button>
            </div>
            <TerminalView logs={state.output} maxHeight="400px" />
          </div>
        )}
      </CardContent>
    </Card>
  );
}
