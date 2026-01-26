"use client";

import { useEffect, useRef } from "react";

// ANSI color code to Tailwind class mapping
const ANSI_COLORS: Record<number, string> = {
  30: "text-zinc-600", // black
  31: "text-red-500", // red
  32: "text-green-500", // green
  33: "text-yellow-500", // yellow
  34: "text-blue-500", // blue
  35: "text-purple-500", // magenta
  36: "text-cyan-500", // cyan
  37: "text-zinc-100", // white
  90: "text-zinc-500", // bright black (gray)
  91: "text-red-400", // bright red
  92: "text-green-400", // bright green
  93: "text-yellow-400", // bright yellow
  94: "text-blue-400", // bright blue
  95: "text-purple-400", // bright magenta
  96: "text-cyan-400", // bright cyan
  97: "text-white", // bright white
};

function AnsiLine({ text }: { text: string }) {
  // Parse ANSI escape codes and render with colors
  const parts: { text: string; className?: string }[] = [];
  // Match ANSI escape sequences: \x1b[XXm or \033[XXm
  const ansiRegex = /\x1b\[([0-9;]+)m|\u001b\[([0-9;]+)m/g;

  let lastIndex = 0;
  let currentClass = "";
  let match;

  // Create a copy of the string to work with
  const cleanText = text.replace(/\x1b/g, "\u001b");

  while ((match = ansiRegex.exec(cleanText)) !== null) {
    // Add text before this match
    if (match.index > lastIndex) {
      parts.push({ text: cleanText.slice(lastIndex, match.index), className: currentClass });
    }

    // Parse the ANSI code
    const codes = (match[1] || match[2]).split(";").map(Number);
    for (const code of codes) {
      if (code === 0) {
        currentClass = ""; // Reset
      } else if (code === 1) {
        currentClass += " font-bold";
      } else if (ANSI_COLORS[code]) {
        currentClass = ANSI_COLORS[code];
      }
    }

    lastIndex = match.index + match[0].length;
  }

  // Add remaining text
  if (lastIndex < cleanText.length) {
    parts.push({ text: cleanText.slice(lastIndex), className: currentClass });
  }

  if (parts.length === 0) {
    return <>{text}</>;
  }

  return (
    <>
      {parts.map((part, i) => (
        <span key={i} className={part.className || undefined}>
          {part.text}
        </span>
      ))}
    </>
  );
}

interface TerminalViewProps {
  logs: string[];
  maxHeight?: string;
}

export function TerminalView({ logs, maxHeight = "200px" }: TerminalViewProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Auto-scroll to bottom when logs change
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs]);

  return (
    <div
      ref={scrollRef}
      className="rounded-md border bg-zinc-950 dark:bg-zinc-900 overflow-auto"
      style={{ maxHeight, minHeight: "100px" }}
    >
      <div className="p-3 font-mono text-xs leading-relaxed">
        {logs.length > 0 ? (
          logs.map((line, index) => (
            <div
              key={index}
              className="text-zinc-300 whitespace-pre-wrap break-all hover:bg-zinc-800/50"
            >
              {line ? <AnsiLine text={line} /> : "\u00A0"}
            </div>
          ))
        ) : (
          <div className="text-zinc-500 italic">No output available</div>
        )}
      </div>
    </div>
  );
}
