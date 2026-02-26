#!/usr/bin/env node

/**
 * Generate dashboard API documentation from colocated route meta exports.
 *
 * Usage: node status-dashboard/scripts/generate-api-doc.mjs
 * Output: docs/dashboard-api.md
 *
 * Fails with exit code 1 if any route.ts is missing a `meta` export.
 *
 * Note: This script only reads local source files and writes markdown.
 * It does not execute any external commands or use child_process.
 * The `new Function()` call evaluates trusted object literals from our
 * own route files (not user input).
 */

import { readFileSync, writeFileSync, readdirSync, statSync } from "fs";
import { join, relative, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const DASHBOARD_ROOT = join(__dirname, "..");
const API_DIR = join(DASHBOARD_ROOT, "src/app/api");
const OUTPUT = join(DASHBOARD_ROOT, "..", "docs", "dashboard-api.md");

// ---------------------------------------------------------------------------
// 1. Discover route files
// ---------------------------------------------------------------------------

function findRouteFiles(dir) {
  const results = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      results.push(...findRouteFiles(full));
    } else if (entry === "route.ts") {
      results.push(full);
    }
  }
  return results.sort();
}

// ---------------------------------------------------------------------------
// 2. Extract HTTP methods from source
// ---------------------------------------------------------------------------

function extractMethods(source) {
  const methods = [];
  const re = /export\s+(?:async\s+)?function\s+(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)/g;
  let m;
  while ((m = re.exec(source)) !== null) {
    if (!methods.includes(m[1])) methods.push(m[1]);
  }
  return methods;
}

// ---------------------------------------------------------------------------
// 3. Extract meta object from source (no transpiler needed)
//
// Parses the `export const meta: RouteMeta = { ... };` block using
// brace-counting and evaluates the resulting JS object literal.
// This only runs on our own source files — not on external input.
// ---------------------------------------------------------------------------

function extractMeta(source, filePath) {
  const marker = "export const meta";
  const idx = source.indexOf(marker);
  if (idx === -1) return null;

  const braceStart = source.indexOf("{", idx);
  if (braceStart === -1) return null;

  let depth = 0;
  let braceEnd = -1;
  for (let i = braceStart; i < source.length; i++) {
    if (source[i] === "{") depth++;
    else if (source[i] === "}") {
      depth--;
      if (depth === 0) {
        braceEnd = i;
        break;
      }
    }
  }

  if (braceEnd === -1) {
    console.error(`  ERROR: Unbalanced braces in meta for ${filePath}`);
    return null;
  }

  const objectStr = source.slice(braceStart, braceEnd + 1);

  try {
    // Safe: evaluates trusted object literals from our own route files
    const fn = new Function(`return (${objectStr})`);
    return fn();
  } catch (err) {
    console.error(`  ERROR: Failed to parse meta in ${filePath}: ${err.message}`);
    return null;
  }
}

// ---------------------------------------------------------------------------
// 4. Derive route path from filesystem
// ---------------------------------------------------------------------------

function routePath(filePath) {
  const rel = relative(API_DIR, filePath);
  // Remove trailing /route.ts
  let route = "/" + rel.replace(/\/route\.ts$/, "");
  // Convert [param] to :param for display
  route = "/api" + route.replace(/\[([^\]]+)\]/g, ":$1");
  // Clean up trailing slash for root api routes
  if (route === "/api/") route = "/api";
  return route;
}

// ---------------------------------------------------------------------------
// 5. Main
// ---------------------------------------------------------------------------

const routeFiles = findRouteFiles(API_DIR);
console.log(`Found ${routeFiles.length} route files`);

const missing = [];
const routes = [];

for (const file of routeFiles) {
  const source = readFileSync(file, "utf-8");
  const methods = extractMethods(source);
  const meta = extractMeta(source, file);
  const path = routePath(file);
  const relPath = relative(join(DASHBOARD_ROOT, ".."), file);

  if (!meta) {
    missing.push(relPath);
    continue;
  }

  routes.push({ path, methods, meta, relPath });
}

// Fail if any route is missing meta
if (missing.length > 0) {
  console.error(`\nERROR: ${missing.length} route(s) missing meta export:\n`);
  for (const f of missing) {
    console.error(`  - ${f}`);
  }
  console.error(`\nAdd 'export const meta: RouteMeta = { ... }' to each file.`);
  process.exit(1);
}

// ---------------------------------------------------------------------------
// 6. Generate markdown
// ---------------------------------------------------------------------------

const CATEGORY_ORDER = ["Status", "Chain", "Operations", "Testing", "Apps"];

// Group by category
const byCategory = {};
for (const r of routes) {
  const cat = r.meta.category;
  if (!byCategory[cat]) byCategory[cat] = [];
  byCategory[cat].push(r);
}

let md = `<!-- Auto-generated from route meta exports. Do not edit manually. -->
<!-- Regenerate: make docs-dashboard -->

# Dashboard API Reference

Base URL: \`http://localhost:7100\`

`;

// Table of contents
md += `## Contents\n\n`;
for (const cat of CATEGORY_ORDER) {
  if (!byCategory[cat]) continue;
  md += `- [${cat}](#${cat.toLowerCase()})\n`;
  for (const r of byCategory[cat]) {
    const anchor = r.meta.title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/-$/, "");
    md += `  - [${r.meta.title}](#${anchor}) — \`${r.methods.join(", ")} ${r.path}\`\n`;
  }
}
md += `\n---\n\n`;

// Sections
for (const cat of CATEGORY_ORDER) {
  const catRoutes = byCategory[cat];
  if (!catRoutes) continue;

  md += `## ${cat}\n\n`;

  for (const r of catRoutes) {
    const { meta } = r;
    const methodBadges = r.methods.map((m) => `\`${m}\``).join(" ");
    const sseBadge = meta.sse ? " `SSE`" : "";

    md += `### ${meta.title}\n\n`;
    md += `${methodBadges}${sseBadge} \`${r.path}\`\n\n`;
    md += `${meta.description}\n\n`;

    // Request body
    if (meta.request && meta.request.length > 0) {
      md += `**Request body:**\n\n`;
      md += `| Field | Type | Required | Description |\n`;
      md += `|-------|------|----------|-------------|\n`;
      for (const f of meta.request) {
        const req = f.required ? "Yes" : "No";
        md += `| \`${f.name}\` | \`${f.type}\` | ${req} | ${f.description} |\n`;
      }
      md += `\n`;
    }

    // Response
    if (meta.response && meta.response.length > 0) {
      md += `**Response:**\n\n`;
      md += `| Field | Type | Required | Description |\n`;
      md += `|-------|------|----------|-------------|\n`;
      for (const f of meta.response) {
        const req = f.required ? "Yes" : "No";
        md += `| \`${f.name}\` | \`${f.type}\` | ${req} | ${f.description} |\n`;
      }
      md += `\n`;
    } else if (meta.sse) {
      md += `**Response:** SSE stream\n\n`;
    }

    // Curl examples
    const curls = Array.isArray(meta.curl) ? meta.curl : [meta.curl];
    md += `**Example:**\n\n`;
    md += "```bash\n";
    md += curls.join("\n\n");
    md += "\n```\n\n";

    md += `---\n\n`;
  }
}

// Footer
md += `*${routes.length} endpoints documented.*\n`;

writeFileSync(OUTPUT, md, "utf-8");
console.log(`Generated ${OUTPUT} (${routes.length} routes)`);
