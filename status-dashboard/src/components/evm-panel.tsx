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
import {
  RefreshCw,
  Copy,
  Check,
  AlertCircle,
  Droplets,
} from "lucide-react";
import type { EvmResponse, EvmEnv } from "@/lib/types";

function truncateAddress(addr: string): string {
  if (addr.length <= 14) return addr;
  return `${addr.slice(0, 6)}...${addr.slice(-4)}`;
}

function CopyAddress({ address }: { address: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(address);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <button
      onClick={handleCopy}
      className="inline-flex items-center gap-1 font-mono text-xs hover:text-foreground transition-colors"
      title={address}
    >
      {truncateAddress(address)}
      {copied ? (
        <Check className="h-3 w-3 text-green-500" />
      ) : (
        <Copy className="h-3 w-3 text-muted-foreground" />
      )}
    </button>
  );
}

const ENV_OPTIONS: { value: EvmEnv; label: string }[] = [
  { value: "local", label: "Local (Anvil)" },
  { value: "sepolia", label: "Sepolia" },
  { value: "mainnet", label: "Mainnet" },
];

export function EvmPanel() {
  const [data, setData] = useState<EvmResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [env, setEnv] = useState<EvmEnv>("local");
  const [envInitialized, setEnvInitialized] = useState(false);

  const fetchEvm = useCallback(
    async () => {
      try {
        const response = await fetch(`/api/evm?env=${env}`);
        if (!response.ok) throw new Error("Failed to fetch EVM data");
        const result: EvmResponse = await response.json();
        setData(result);
        // On first load, set env from server auto-detect
        if (!envInitialized) {
          setEnv(result.env);
          setEnvInitialized(true);
        }
      } catch (err) {
        console.error("Failed to fetch EVM:", err);
      } finally {
        setLoading(false);
      }
    },
    [env, envInitialized]
  );

  useEffect(() => {
    fetchEvm();
    const interval = setInterval(() => fetchEvm(), 10000);
    return () => clearInterval(interval);
  }, [fetchEvm]);

  const handleEnvChange = (newEnv: EvmEnv) => {
    setEnv(newEnv);
    setLoading(true);
  };

  const isInitialLoad = loading && !data;
  const inputClass =
    "flex h-8 rounded-md border border-input bg-background px-3 py-1 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 font-mono";

  return (
    <div className="space-y-6">
      {/* Header + Refresh */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">EVM Status</h3>
        <Button
          variant="outline"
          size="sm"
          onClick={() => fetchEvm()}
          disabled={isInitialLoad}
        >
          <RefreshCw
            className={`h-4 w-4 mr-2 ${isInitialLoad ? "animate-spin" : ""}`}
          />
          Refresh
        </Button>
      </div>

      {/* Environment Bar */}
      <Card>
        <CardContent className="pt-4">
          <div className="flex flex-wrap items-center gap-4">
            <div>
              <label className="text-xs text-muted-foreground block mb-1">
                Environment
              </label>
              <select
                value={env}
                onChange={(e) => handleEnvChange(e.target.value as EvmEnv)}
                className={`${inputClass} w-40`}
              >
                {ENV_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
            {isInitialLoad ? (
              <Skeleton className="h-8 w-64" />
            ) : data ? (
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="outline" className="font-mono text-xs">
                  Chain {data.chainId ?? "?"}
                </Badge>
                <Badge variant="outline" className="font-mono text-xs">
                  Block{" "}
                  {data.blockNumber !== null
                    ? data.blockNumber.toLocaleString()
                    : "?"}
                </Badge>
                <span className="text-sm text-muted-foreground">
                  {data.networkName}
                </span>
                <span className="text-xs text-muted-foreground font-mono">
                  {data.rpcUrl}
                </span>
              </div>
            ) : null}
          </div>
          {data?.error && (
            <div className="mt-3 text-sm text-destructive flex items-center gap-1">
              <AlertCircle className="h-4 w-4" />
              {data.error}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Key Accounts */}
      {isInitialLoad ? (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm">Key Accounts</CardTitle>
          </CardHeader>
          <CardContent>
            <Skeleton className="h-16 w-full" />
          </CardContent>
        </Card>
      ) : data && data.accounts.length > 0 ? (
        <div>
          <h4 className="text-sm font-medium text-muted-foreground mb-3">
            Key Accounts
          </h4>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {data.accounts.map((acct) => (
              <Card key={acct.label}>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">{acct.label}</CardTitle>
                </CardHeader>
                <CardContent>
                  <CopyAddress address={acct.address} />
                  <div className="mt-1 text-lg font-mono font-semibold">
                    {acct.ethBalance} ETH
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      ) : null}

      {/* Deployed Tokens */}
      {isInitialLoad ? (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm">Deployed Tokens</CardTitle>
          </CardHeader>
          <CardContent>
            <Skeleton className="h-32 w-full" />
          </CardContent>
        </Card>
      ) : data && data.tokens.length > 0 ? (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm">Deployed Tokens</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b">
                    <th className="text-left py-2 pr-4 text-muted-foreground font-medium">
                      Token
                    </th>
                    <th className="text-left py-2 px-2 text-muted-foreground font-medium">
                      Address
                    </th>
                    <th className="text-right py-2 px-2 text-muted-foreground font-medium">
                      Decimals
                    </th>
                    <th className="text-right py-2 pl-2 text-muted-foreground font-medium">
                      Total Supply
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.tokens.map((t) => (
                    <tr key={t.symbol} className="border-b last:border-0">
                      <td className="py-2 pr-4 font-medium">{t.symbol}</td>
                      <td className="py-2 px-2">
                        <CopyAddress address={t.address} />
                      </td>
                      <td className="text-right py-2 px-2 font-mono text-xs">
                        {t.decimals}
                      </td>
                      <td className="text-right py-2 pl-2 font-mono text-xs">
                        {t.totalSupply}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {/* Core Contracts */}
      {isInitialLoad ? (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm">Core Contracts</CardTitle>
          </CardHeader>
          <CardContent>
            <Skeleton className="h-32 w-full" />
          </CardContent>
        </Card>
      ) : data && data.contracts.length > 0 ? (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm">Core Contracts</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b">
                    <th className="text-left py-2 pr-4 text-muted-foreground font-medium">
                      Contract
                    </th>
                    <th className="text-left py-2 pl-2 text-muted-foreground font-medium">
                      Address
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.contracts.map((c) => (
                    <tr key={c.name} className="border-b last:border-0">
                      <td className="py-2 pr-4 font-medium">{c.name}</td>
                      <td className="py-2 pl-2">
                        <CopyAddress address={c.address} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {/* Liquidity Pools */}
      {isInitialLoad ? (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <Droplets className="h-4 w-4" />
              <CardTitle className="text-sm">Liquidity Pools</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <Skeleton className="h-48 w-full" />
          </CardContent>
        </Card>
      ) : data && data.pools.length > 0 ? (
        <div>
          <h4 className="text-sm font-medium text-muted-foreground mb-3 flex items-center gap-2">
            <Droplets className="h-4 w-4" />
            Liquidity Pools
          </h4>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {data.pools.map((pool) => (
              <Card key={pool.name}>
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-sm">{pool.name}</CardTitle>
                    <Badge variant="outline" className="text-xs font-mono">
                      {(pool.fee / 10000).toFixed(2)}%
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className="space-y-2">
                  {pool.error ? (
                    <div className="text-sm text-destructive flex items-center gap-1">
                      <AlertCircle className="h-3 w-3" />
                      {pool.error}
                    </div>
                  ) : (
                    <>
                      {pool.priceLabel && (
                        <div className="text-lg font-mono font-semibold">
                          {pool.priceLabel}
                        </div>
                      )}
                      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                        <div className="text-muted-foreground">Tick</div>
                        <div className="font-mono text-right">
                          {pool.tick !== null ? pool.tick.toLocaleString() : "--"}
                        </div>
                        <div className="text-muted-foreground">Liquidity</div>
                        <div className="font-mono text-right truncate" title={pool.liquidity ?? ""}>
                          {pool.liquidity ?? "--"}
                        </div>
                        <div className="text-muted-foreground">LP Fee</div>
                        <div className="font-mono text-right">
                          {pool.lpFee !== null
                            ? `${(pool.lpFee / 10000).toFixed(2)}%`
                            : "--"}
                        </div>
                      </div>
                      {pool.poolId && (
                        <div className="text-xs text-muted-foreground font-mono truncate" title={pool.poolId}>
                          {truncateAddress(pool.poolId)}
                        </div>
                      )}
                    </>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
