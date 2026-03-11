"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import {
  Server,
  Pickaxe,
  DollarSign,
  Wallet,
  Play,
  Square,
  RefreshCw,
  CheckCircle2,
  XCircle,
  Loader2,
  Bookmark,
  Minus,
  Plus,
  ArrowRightLeft,
  ArrowLeftRight,
  BarChart3,
  Send,
  AlertCircle,
} from "lucide-react";
import type { ChainResponse, WalletBalance, AssetType, ReserveInfo } from "@/lib/types";
import { INPUT_CLASS } from "@/lib/styles";

function NodeCard({
  label,
  node,
  loading,
}: {
  label: string;
  node: { height: number | null; synced: boolean } | undefined;
  loading: boolean;
}) {
  if (loading || !node) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <Server className="h-4 w-4" />
            <CardTitle className="text-sm">{label}</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-6 w-full mb-2" />
          <Skeleton className="h-4 w-20" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Server className="h-4 w-4" />
            <CardTitle className="text-sm">{label}</CardTitle>
          </div>
          <Badge
            variant={node.synced ? "default" : "secondary"}
            className={node.synced ? "bg-green-600 hover:bg-green-700" : ""}
          >
            {node.synced ? (
              <CheckCircle2 className="h-3 w-3 mr-1" />
            ) : (
              <XCircle className="h-3 w-3 mr-1" />
            )}
            {node.synced ? "Synced" : "Not Synced"}
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-mono font-bold">
          {node.height !== null ? node.height.toLocaleString() : "--"}
        </div>
        <div className="text-xs text-muted-foreground">Block height</div>
      </CardContent>
    </Card>
  );
}

function MiningControls({
  mining,
  loading,
  onAction,
}: {
  mining: { active: boolean; threads?: number; speed?: number } | undefined;
  loading: boolean;
  onAction: (action: string, params?: Record<string, unknown>) => Promise<void>;
}) {
  const [threads, setThreads] = useState(1);
  const [actionLoading, setActionLoading] = useState(false);

  const isActive = mining?.active ?? false;

  const handleAction = async (action: string) => {
    setActionLoading(true);
    try {
      if (action === "start") {
        await onAction("start", { threads });
      } else {
        await onAction("stop");
      }
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <Pickaxe className="h-4 w-4" />
            <CardTitle className="text-sm">Mining Controls</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-10 w-full" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Pickaxe className="h-4 w-4" />
            <CardTitle className="text-sm">Mining Controls</CardTitle>
          </div>
          <Badge
            variant={isActive ? "default" : "secondary"}
            className={isActive ? "bg-amber-500 hover:bg-amber-600" : ""}
          >
            <Pickaxe className="h-3 w-3 mr-1" />
            {isActive ? "Mining" : "Idle"}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {isActive ? (
          <div className="space-y-3">
            <div className="flex items-center gap-4 text-sm">
              {mining?.threads && (
                <span className="text-muted-foreground">
                  Threads: <span className="font-mono">{mining.threads}</span>
                </span>
              )}
              {mining?.speed !== undefined && mining.speed > 0 && (
                <span className="text-muted-foreground">
                  Speed: <span className="font-mono">{mining.speed.toFixed(1)}</span> H/s
                </span>
              )}
            </div>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => handleAction("stop")}
              disabled={actionLoading}
            >
              {actionLoading ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Square className="h-4 w-4 mr-2" />
              )}
              Stop Mining
            </Button>
          </div>
        ) : (
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1">
              <span className="text-sm text-muted-foreground">Threads:</span>
              <Button
                variant="outline"
                size="icon-xs"
                onClick={() => setThreads(Math.max(1, threads - 1))}
                disabled={threads <= 1}
              >
                <Minus className="h-3 w-3" />
              </Button>
              <span className="font-mono text-sm w-6 text-center">
                {threads}
              </span>
              <Button
                variant="outline"
                size="icon-xs"
                onClick={() => setThreads(Math.min(4, threads + 1))}
                disabled={threads >= 4}
              >
                <Plus className="h-3 w-3" />
              </Button>
            </div>
            <Button
              size="sm"
              className="bg-amber-500 hover:bg-amber-600"
              onClick={() => handleAction("start")}
              disabled={actionLoading}
            >
              {actionLoading ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Play className="h-4 w-4 mr-2" />
              )}
              Start Mining
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function CheckpointCard({
  checkpoint,
  loading,
}: {
  checkpoint: { current: number | null; saved: number | null } | undefined;
  loading: boolean;
}) {
  if (loading || !checkpoint) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <Bookmark className="h-4 w-4" />
            <CardTitle className="text-sm">Checkpoint</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-6 w-full mb-2" />
          <Skeleton className="h-4 w-32" />
        </CardContent>
      </Card>
    );
  }

  const blocksSince =
    checkpoint.current !== null && checkpoint.saved !== null
      ? checkpoint.current - checkpoint.saved
      : null;

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <Bookmark className="h-4 w-4" />
          <CardTitle className="text-sm">Checkpoint</CardTitle>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
          <div className="text-muted-foreground">Current Height</div>
          <div className="font-mono text-right">
            {checkpoint.current !== null
              ? checkpoint.current.toLocaleString()
              : "--"}
          </div>
          <div className="text-muted-foreground">Checkpoint</div>
          <div className="font-mono text-right">
            {checkpoint.saved !== null
              ? checkpoint.saved.toLocaleString()
              : "--"}
          </div>
          {blocksSince !== null && (
            <>
              <div className="text-muted-foreground">Blocks Since</div>
              <div className="font-mono text-right">
                {blocksSince.toLocaleString()}
              </div>
            </>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function OracleSection({
  oracle,
  loading,
  onSetPrice,
  onSetScenario,
  onSetMode,
}: {
  oracle: ChainResponse["oracle"] | undefined;
  loading: boolean;
  onSetPrice: (price: string) => Promise<void>;
  onSetScenario: (scenario: string) => Promise<void>;
  onSetMode: (mode: "manual" | "mirror") => Promise<void>;
}) {
  const [priceInput, setPriceInput] = useState("");
  const [settingPrice, setSettingPrice] = useState(false);
  const [settingScenario, setSettingScenario] = useState<string | null>(null);
  const [settingMode, setSettingMode] = useState(false);

  const isMirror = oracle?.mode === "mirror";

  const handleSetPrice = async () => {
    if (!priceInput.trim()) return;
    setSettingPrice(true);
    try {
      await onSetPrice(priceInput.trim());
      setPriceInput("");
    } finally {
      setSettingPrice(false);
    }
  };

  const handleSetScenario = async (scenario: string) => {
    setSettingScenario(scenario);
    try {
      await onSetScenario(scenario);
    } finally {
      setSettingScenario(null);
    }
  };

  const handleSetMode = async (mode: "manual" | "mirror") => {
    setSettingMode(true);
    try {
      await onSetMode(mode);
    } finally {
      setSettingMode(false);
    }
  };

  const scenarios = [
    { id: "normal", label: "Normal", color: "bg-green-600 hover:bg-green-700" },
    { id: "defensive", label: "Defensive", color: "bg-amber-500 hover:bg-amber-600" },
    { id: "crisis", label: "Crisis", color: "bg-red-600 hover:bg-red-700" },
    { id: "recovery", label: "Recovery", color: "bg-blue-600 hover:bg-blue-700" },
  ];

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <DollarSign className="h-4 w-4" />
            <CardTitle className="text-sm">Oracle Price</CardTitle>
            {!loading && isMirror && (
              <Badge className="bg-blue-600 hover:bg-blue-700 text-xs">
                Mirror
              </Badge>
            )}
          </div>
          {!loading && oracle && (
            <span className="text-2xl font-mono font-bold">
              {oracle.price !== null ? `$${oracle.price.toFixed(2)}` : "--"}
            </span>
          )}
          {loading && <Skeleton className="h-8 w-20" />}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Mode Toggle */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Mode:</span>
          <div className="flex gap-1">
            <Button
              variant={!isMirror ? "default" : "outline"}
              size="sm"
              onClick={() => handleSetMode("manual")}
              disabled={settingMode || !isMirror}
            >
              {settingMode && !isMirror ? (
                <Loader2 className="h-3 w-3 mr-1 animate-spin" />
              ) : null}
              Manual
            </Button>
            <Button
              variant={isMirror ? "default" : "outline"}
              size="sm"
              onClick={() => handleSetMode("mirror")}
              disabled={settingMode || isMirror}
            >
              {settingMode && isMirror ? (
                <Loader2 className="h-3 w-3 mr-1 animate-spin" />
              ) : null}
              Mirror
            </Button>
          </div>
        </div>

        {/* Mirror info */}
        {isMirror && (
          <div className="text-xs text-muted-foreground space-y-1 bg-blue-500/10 rounded-md px-3 py-2">
            <div>Syncing from mainnet oracle</div>
            {oracle.mirrorSpot !== undefined && (
              <div>Mainnet spot: <span className="font-mono">${oracle.mirrorSpot.toFixed(4)}</span></div>
            )}
            {oracle.mirrorLastFetch && (
              <div>Last fetch: <span className="font-mono">{oracle.mirrorLastFetch}</span></div>
            )}
          </div>
        )}

        {/* Manual controls — disabled in mirror mode */}
        <div className="flex items-center gap-2">
          <input
            type="text"
            placeholder="e.g. 2.50"
            value={priceInput}
            onChange={(e) => setPriceInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSetPrice();
            }}
            disabled={isMirror}
            className="flex h-8 rounded-md border border-input bg-background px-3 py-1 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 w-28 font-mono disabled:opacity-50 disabled:cursor-not-allowed"
          />
          <Button
            size="sm"
            onClick={handleSetPrice}
            disabled={settingPrice || !priceInput.trim() || isMirror}
          >
            {settingPrice ? (
              <Loader2 className="h-4 w-4 mr-1 animate-spin" />
            ) : null}
            Set Price
          </Button>
        </div>
        <Separator />
        <div>
          <span className="text-xs text-muted-foreground mb-2 block">
            Scenario Presets
          </span>
          <div className="flex flex-wrap gap-2">
            {scenarios.map((s) => (
              <Button
                key={s.id}
                size="sm"
                className={s.color}
                onClick={() => handleSetScenario(s.id)}
                disabled={settingScenario !== null || isMirror}
              >
                {settingScenario === s.id ? (
                  <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                ) : null}
                {s.label}
              </Button>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function WalletBalancesSection({
  wallets,
  loading,
}: {
  wallets: WalletBalance[];
  loading: boolean;
}) {
  if (loading) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <Wallet className="h-4 w-4" />
            <CardTitle className="text-sm">Wallet Balances</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-24 w-full" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <Wallet className="h-4 w-4" />
          <CardTitle className="text-sm">Wallet Balances</CardTitle>
        </div>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b">
                <th className="text-left py-2 pr-4 text-muted-foreground font-medium">
                  Wallet
                </th>
                <th className="text-right py-2 px-2 text-muted-foreground font-medium font-mono">
                  ZPH
                </th>
                <th className="text-right py-2 px-2 text-muted-foreground font-medium font-mono">
                  ZSD
                </th>
                <th className="text-right py-2 px-2 text-muted-foreground font-medium font-mono">
                  ZRS
                </th>
                <th className="text-right py-2 pl-2 text-muted-foreground font-medium font-mono">
                  ZYS
                </th>
              </tr>
            </thead>
            <tbody>
              {wallets.map((w) => (
                <tr key={w.name} className="border-b last:border-0">
                  <td className="py-2 pr-4 font-medium capitalize">
                    <div className="flex items-center gap-2">
                      {w.name}
                      {w.error && (
                        <span className="text-xs text-destructive flex items-center gap-1">
                          <AlertCircle className="h-3 w-3" />
                          {w.error}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="text-right py-2 px-2 font-mono text-xs">
                    {w.balances.ZPH}
                  </td>
                  <td className="text-right py-2 px-2 font-mono text-xs">
                    {w.balances.ZSD}
                  </td>
                  <td className="text-right py-2 px-2 font-mono text-xs">
                    {w.balances.ZRS}
                  </td>
                  <td className="text-right py-2 pl-2 font-mono text-xs">
                    {w.balances.ZYS}
                  </td>
                </tr>
              ))}
              {wallets.length === 0 && (
                <tr>
                  <td
                    colSpan={5}
                    className="py-4 text-center text-muted-foreground"
                  >
                    No wallet data available
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

const ASSETS: AssetType[] = ["ZPH", "ZSD", "ZRS", "ZYS"];
const WALLET_NAMES = ["gov", "miner", "test", "bridge", "engine"];

const VALID_CONVERSION_TARGETS: Record<string, AssetType[]> = {
  ZPH: ["ZSD", "ZRS"],
  ZSD: ["ZPH", "ZYS"],
  ZRS: ["ZPH"],
  ZYS: ["ZSD"],
};

function TransferSection({ onComplete }: { onComplete: () => void }) {
  const [mode, setMode] = useState<"send" | "convert">("send");
  const [fromWallet, setFromWallet] = useState("gov");
  const [toWallet, setToWallet] = useState("test");
  const [customAddress, setCustomAddress] = useState("");
  const [amount, setAmount] = useState("");
  const [sourceAsset, setSourceAsset] = useState<AssetType>("ZPH");
  const [destAsset, setDestAsset] = useState<AssetType>("ZPH");
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);

  // For convert mode, keep destAsset valid when sourceAsset changes
  const validTargets = VALID_CONVERSION_TARGETS[sourceAsset] || [];

  const handleSourceChange = (asset: AssetType) => {
    setSourceAsset(asset);
    if (mode === "convert") {
      const targets = VALID_CONVERSION_TARGETS[asset] || [];
      if (!targets.includes(destAsset)) {
        setDestAsset(targets[0] || "ZPH");
      }
    }
  };

  const handleSubmit = async () => {
    const parsedAmount = parseFloat(amount);
    if (!parsedAmount || parsedAmount <= 0) {
      setFeedback({ type: "error", message: "Enter a valid amount" });
      return;
    }

    setSubmitting(true);
    setFeedback(null);

    try {
      const body =
        mode === "send"
          ? {
              fromWallet,
              ...(toWallet === "custom"
                ? { toAddress: customAddress.trim() }
                : { toWallet }),
              amount: parsedAmount,
              sourceAsset,
              destAsset: sourceAsset,
            }
          : { fromWallet, toWallet: fromWallet, amount: parsedAmount, sourceAsset, destAsset };

      const response = await fetch("/api/chain/transfer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const result = await response.json();

      if (result.success) {
        const txInfo = result.txHash ? ` (tx: ${result.txHash.slice(0, 16)}...)` : "";
        const dest = toWallet === "custom" ? customAddress.trim().slice(0, 8) + "..." : toWallet;
        setFeedback({
          type: "success",
          message: mode === "send"
            ? `Sent ${parsedAmount} ${sourceAsset}: ${fromWallet} -> ${dest}${txInfo}`
            : `Converted ${parsedAmount} ${sourceAsset} -> ${destAsset}${txInfo}`,
        });
        setAmount("");
        setTimeout(onComplete, 2000);
      } else {
        setFeedback({ type: "error", message: result.error || "Transfer failed" });
      }
    } catch (err) {
      setFeedback({ type: "error", message: err instanceof Error ? err.message : "Network error" });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ArrowRightLeft className="h-4 w-4" />
            <CardTitle className="text-sm">Transfer Controls</CardTitle>
          </div>
          <div className="flex gap-1">
            <Button
              variant={mode === "send" ? "default" : "outline"}
              size="sm"
              onClick={() => { setMode("send"); setFeedback(null); }}
            >
              <Send className="h-3 w-3 mr-1" />
              Send
            </Button>
            <Button
              variant={mode === "convert" ? "default" : "outline"}
              size="sm"
              onClick={() => { setMode("convert"); setFeedback(null); }}
            >
              <ArrowLeftRight className="h-3 w-3 mr-1" />
              Convert
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {mode === "send" ? (
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label className="text-xs text-muted-foreground block mb-1">From</label>
              <select
                value={fromWallet}
                onChange={(e) => setFromWallet(e.target.value)}
                className={`${INPUT_CLASS} w-24`}
              >
                {WALLET_NAMES.map((w) => (
                  <option key={w} value={w}>{w}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs text-muted-foreground block mb-1">To</label>
              <select
                value={toWallet}
                onChange={(e) => setToWallet(e.target.value)}
                className={`${INPUT_CLASS} w-24`}
              >
                {WALLET_NAMES.filter((w) => w !== fromWallet).map((w) => (
                  <option key={w} value={w}>{w}</option>
                ))}
                <option value="custom">custom</option>
              </select>
            </div>
            {toWallet === "custom" && (
              <div>
                <label className="text-xs text-muted-foreground block mb-1">Address</label>
                <input
                  type="text"
                  placeholder="Zephyr address..."
                  value={customAddress}
                  onChange={(e) => setCustomAddress(e.target.value)}
                  className={`${INPUT_CLASS} w-48`}
                />
              </div>
            )}
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Amount</label>
              <input
                type="text"
                placeholder="0.00"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") handleSubmit(); }}
                className={`${INPUT_CLASS} w-28`}
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Asset</label>
              <select
                value={sourceAsset}
                onChange={(e) => setSourceAsset(e.target.value as AssetType)}
                className={`${INPUT_CLASS} w-20`}
              >
                {ASSETS.map((a) => (
                  <option key={a} value={a}>{a}</option>
                ))}
              </select>
            </div>
            <Button
              size="sm"
              onClick={handleSubmit}
              disabled={submitting || !amount.trim() || (toWallet === "custom" && !customAddress.trim())}
            >
              {submitting ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Send className="h-4 w-4 mr-1" />}
              Send
            </Button>
          </div>
        ) : (
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Wallet</label>
              <select
                value={fromWallet}
                onChange={(e) => setFromWallet(e.target.value)}
                className={`${INPUT_CLASS} w-24`}
              >
                {WALLET_NAMES.map((w) => (
                  <option key={w} value={w}>{w}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Amount</label>
              <input
                type="text"
                placeholder="0.00"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") handleSubmit(); }}
                className={`${INPUT_CLASS} w-28`}
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground block mb-1">From</label>
              <select
                value={sourceAsset}
                onChange={(e) => handleSourceChange(e.target.value as AssetType)}
                className={`${INPUT_CLASS} w-20`}
              >
                {ASSETS.map((a) => (
                  <option key={a} value={a}>{a}</option>
                ))}
              </select>
            </div>
            <span className="text-muted-foreground pb-1">-&gt;</span>
            <div>
              <label className="text-xs text-muted-foreground block mb-1">To</label>
              <select
                value={destAsset}
                onChange={(e) => setDestAsset(e.target.value as AssetType)}
                className={`${INPUT_CLASS} w-20`}
              >
                {validTargets.map((a) => (
                  <option key={a} value={a}>{a}</option>
                ))}
              </select>
            </div>
            <Button
              size="sm"
              onClick={handleSubmit}
              disabled={submitting || !amount.trim() || validTargets.length === 0}
            >
              {submitting ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <ArrowLeftRight className="h-4 w-4 mr-1" />}
              Convert
            </Button>
          </div>
        )}

        {feedback && (
          <div
            className={`text-sm px-3 py-2 rounded-md ${
              feedback.type === "success"
                ? "bg-green-500/10 text-green-600 dark:text-green-400"
                : "bg-destructive/10 text-destructive"
            }`}
          >
            {feedback.message}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// --- Number formatting ---

function fmtNum(n: number, decimals = 2): string {
  return n.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function fmtUsd(n: number, decimals = 4): string {
  return `$${fmtNum(n, decimals)}`;
}

// --- Network State sub-components ---

function RateCell({
  label,
  value,
  ma,
  unit,
  usdValue,
  usdMa,
}: {
  label: string;
  value: number;
  ma?: number;
  unit?: string;
  usdValue?: number;
  usdMa?: number;
}) {
  const fmtVal = unit ? `${fmtNum(value, 4)} ${unit}` : fmtUsd(value);
  const fmtMa = ma !== undefined
    ? unit ? `${fmtNum(ma, 4)} ${unit}` : fmtUsd(ma)
    : null;

  return (
    <div>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-lg font-mono font-semibold">{fmtVal}</div>
      {fmtMa && (
        <div className="text-xs text-muted-foreground font-mono">
          MA {fmtMa}
        </div>
      )}
      {usdValue !== undefined && (
        <div className="text-xs text-muted-foreground font-mono">
          {fmtUsd(usdValue)}{usdMa !== undefined ? ` (MA ${fmtUsd(usdMa)})` : ""}
        </div>
      )}
    </div>
  );
}

function CircStat({ label, value }: { label: string; value: number }) {
  return (
    <div className="bg-muted/50 rounded-md px-3 py-2">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-lg font-mono font-semibold">{fmtNum(value, 2)}</div>
    </div>
  );
}

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-mono">{value}</span>
    </div>
  );
}

function NetworkStateSection({
  reserve,
  loading,
}: {
  reserve: ReserveInfo | undefined;
  loading: boolean;
}) {
  if (loading) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <BarChart3 className="h-4 w-4" />
            <CardTitle className="text-sm">Network State</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-48 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (!reserve) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <BarChart3 className="h-4 w-4" />
            <CardTitle className="text-sm">Network State</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            No reserve data available
          </p>
        </CardContent>
      </Card>
    );
  }

  const rr = parseFloat(reserve.reserveRatio);
  const rrColor =
    rr >= 8
      ? "text-green-500"
      : rr >= 4
        ? "text-amber-500"
        : "text-red-500";

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <BarChart3 className="h-4 w-4" />
            <CardTitle className="text-sm">Network State</CardTitle>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="font-mono text-xs">
              HF v{reserve.hfVersion}
            </Badge>
            <Badge variant="outline" className="font-mono text-xs">
              Height {reserve.height.toLocaleString()}
            </Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Reserve Ratio + Asset Rates */}
        <div className="flex items-baseline gap-6">
          <div className="shrink-0">
            <div className="text-xs text-muted-foreground mb-1">
              Reserve Ratio
            </div>
            <div className={`text-3xl font-mono font-bold ${rrColor}`}>
              {parseFloat(reserve.reserveRatio).toFixed(4)}x
            </div>
            <div className="text-xs text-muted-foreground font-mono">
              MA {parseFloat(reserve.reserveRatioMa).toFixed(4)}x
            </div>
          </div>
          <Separator orientation="vertical" className="h-14 mx-2" />
          <div className="grid grid-cols-2 md:grid-cols-4 gap-x-6 gap-y-3 flex-1">
            <RateCell
              label="ZPH Spot"
              value={reserve.spot}
              ma={reserve.movingAverage}
            />
            <RateCell
              label="ZSD Rate"
              value={reserve.stableRate}
              ma={reserve.stableRateMa}
              unit="ZPH"
              usdValue={reserve.stableRate * reserve.spot}
              usdMa={reserve.stableRateMa * reserve.movingAverage}
            />
            <RateCell
              label="ZRS Rate"
              value={reserve.reserveRate}
              ma={reserve.reserveRateMa}
              unit="ZPH"
              usdValue={reserve.reserveRate * reserve.spot}
              usdMa={reserve.reserveRateMa * reserve.movingAverage}
            />
            <RateCell
              label="ZYS Price"
              value={reserve.yieldPrice}
              unit="ZSD"
              usdValue={reserve.yieldPrice * reserve.stableRate * reserve.spot}
            />
          </div>
        </div>

        <Separator />

        {/* Circulation */}
        <div>
          <div className="text-xs text-muted-foreground mb-2">
            Circulation
          </div>
          <div className="grid grid-cols-3 gap-4">
            <CircStat label="ZSD" value={reserve.numStables} />
            <CircStat label="ZRS" value={reserve.numReserves} />
            <CircStat label="ZYS" value={reserve.numZyield} />
          </div>
        </div>

        <Separator />

        {/* Reserve Backing */}
        <div>
          <div className="text-xs text-muted-foreground mb-2">
            Reserve Backing
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-x-8 gap-y-1 text-sm">
            <StatRow label="Assets" value={fmtNum(reserve.assets)} />
            <StatRow label="Assets MA" value={fmtNum(reserve.assetsMa)} />
            <StatRow label="Liabilities" value={fmtNum(reserve.liabilities)} />
            <StatRow label="Equity" value={fmtNum(reserve.equity)} />
            <StatRow label="Equity MA" value={fmtNum(reserve.equityMa)} />
            <StatRow label="ZPH Reserve" value={fmtNum(reserve.zephReserve)} />
            <StatRow
              label="ZYS Reserve"
              value={fmtNum(reserve.zyieldReserve)}
            />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export function ZephyrPanel() {
  const [data, setData] = useState<ChainResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchChain = useCallback(async () => {
    try {
      const response = await fetch("/api/chain");
      if (!response.ok) throw new Error("Failed to fetch chain data");
      const result: ChainResponse = await response.json();
      setData(result);
    } catch (err) {
      console.error("Failed to fetch chain:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchChain();
    const interval = setInterval(fetchChain, 10000);
    return () => clearInterval(interval);
  }, [fetchChain]);

  const handleMiningAction = async (
    action: string,
    params?: Record<string, unknown>
  ) => {
    try {
      await fetch("/api/chain/mining", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, ...params }),
      });
      setTimeout(fetchChain, 1500);
    } catch (err) {
      console.error("Mining action failed:", err);
    }
  };

  const handleSetPrice = async (price: string) => {
    try {
      await fetch("/api/chain/oracle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ price }),
      });
      setTimeout(fetchChain, 1000);
    } catch (err) {
      console.error("Set price failed:", err);
    }
  };

  const handleSetScenario = async (scenario: string) => {
    try {
      await fetch("/api/chain/scenario", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scenario }),
      });
      setTimeout(fetchChain, 1500);
    } catch (err) {
      console.error("Set scenario failed:", err);
    }
  };

  const handleSetMode = async (mode: "manual" | "mirror") => {
    try {
      await fetch("/api/chain/oracle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "set-mode", mode }),
      });
      setTimeout(fetchChain, 1000);
    } catch (err) {
      console.error("Set mode failed:", err);
    }
  };

  const isInitialLoad = loading && !data;

  return (
    <div className="space-y-6">
      {/* Header with refresh */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Zephyr Status</h3>
        <Button
          variant="outline"
          size="sm"
          onClick={fetchChain}
          disabled={isInitialLoad}
        >
          <RefreshCw
            className={`h-4 w-4 mr-2 ${isInitialLoad ? "animate-spin" : ""}`}
          />
          Refresh
        </Button>
      </div>

      {/* Network State — major panel at top */}
      <NetworkStateSection
        reserve={data?.reserve}
        loading={isInitialLoad}
      />

      {/* Node Status */}
      <div>
        <h4 className="text-sm font-medium text-muted-foreground mb-3">
          Node Status
        </h4>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <NodeCard
            label="Node 1 (Primary)"
            node={data?.nodes.node1}
            loading={isInitialLoad}
          />
          <NodeCard
            label="Node 2 (Mining)"
            node={data?.nodes.node2}
            loading={isInitialLoad}
          />
        </div>
      </div>

      {/* Mining + Checkpoint */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <MiningControls
          mining={data?.mining}
          loading={isInitialLoad}
          onAction={handleMiningAction}
        />
        <CheckpointCard
          checkpoint={data?.checkpoint}
          loading={isInitialLoad}
        />
      </div>

      {/* Oracle Price */}
      <OracleSection
        oracle={data?.oracle}
        loading={isInitialLoad}
        onSetPrice={handleSetPrice}
        onSetScenario={handleSetScenario}
        onSetMode={handleSetMode}
      />

      {/* Wallet Balances */}
      <WalletBalancesSection
        wallets={data?.wallets || []}
        loading={isInitialLoad}
      />

      {/* Transfer Controls */}
      <TransferSection onComplete={fetchChain} />
    </div>
  );
}
