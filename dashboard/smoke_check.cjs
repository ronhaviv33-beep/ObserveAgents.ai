#!/usr/bin/env node
/**
 * Smoke check: scan App.jsx for React hooks called at module scope.
 *
 * Hooks called outside a component function cause:
 *   TypeError: Cannot read properties of null (reading 'useEffect')
 * in production builds — the page renders blank.
 *
 * Heuristic: after the file is parsed into function-depth segments,
 * any useEffect/useState/useMemo/useCallback/useRef at depth 0
 * (top-level module scope) is illegal.
 */
const fs = require("fs");
const path = require("path");

const filePath = path.join(__dirname, "src", "App.jsx");
const src = fs.readFileSync(filePath, "utf8");
const lines = src.split("\n");

const HOOKS = /\b(useEffect|useState|useMemo|useCallback|useRef)\s*\(/;

let depth = 0;          // JS brace depth
let inTemplateLiteral = false;
let violations = [];

for (let i = 0; i < lines.length; i++) {
  const line = lines[i];

  // Count backticks to track template literals (very rough, good enough)
  const backticks = (line.match(/`/g) || []).length;
  if (backticks % 2 !== 0) inTemplateLiteral = !inTemplateLiteral;

  if (!inTemplateLiteral) {
    depth += (line.match(/\{/g) || []).length;
    depth -= (line.match(/\}/g) || []).length;
  }

  // depth <= 0 means module scope
  if (depth <= 0 && HOOKS.test(line) && !line.trimStart().startsWith("//")) {
    violations.push({ line: i + 1, depth, text: line.trimEnd() });
  }
}

if (violations.length === 0) {
  console.log("✓ App.jsx smoke check passed — no module-scope hook calls detected.");
  process.exit(0);
} else {
  console.error("✗ App.jsx smoke check FAILED — React hooks at module scope:");
  for (const v of violations) {
    console.error(`  Line ${v.line} (depth=${v.depth}): ${v.text}`);
  }
  process.exit(1);
}
