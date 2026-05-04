import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const root = process.cwd();
const requiredRoutes = [
  "app/page.tsx",
  "app/calendar/page.tsx",
  "app/opportunities/page.tsx",
  "app/review/page.tsx",
  "app/drafts/page.tsx",
  "app/wishlist/page.tsx",
  "app/tour-assemblies/page.tsx",
  "app/tour-legs/page.tsx",
  "app/business-cases/page.tsx",
];
const requiredComponents = ["components/action-notice.tsx", "components/purpose-button.tsx"];
const requiredApiRoutes = ["app/api/roadshow/[...path]/route.ts"];
const requiredStartCopy = [
  "Seminar Manager Start",
  "One next seminar action",
  "What blocks seminar management",
  "No data yet",
  "Run real source sync",
  "Source status",
];
const bannedProductionCopy = [
  "Demo data loaded",
  "synthetic",
  "local-only",
  "Load local KOF demo data",
  "localhost",
  "dev server",
  "developer",
];
const bannedCopy = [
  "One-Click Draft",
  "Run external ingest",
  "Propose tour leg",
  "View dossier",
  "Record source audit",
  "Source Health",
  "Seminar Admin",
  "Morning Sweep",
  "Run real sweep",
  "Roadshow Cockpit",
  "Operating queue",
  "Next best action",
];
const bannedImplementation = ["calendar/overlay?rebuild=true"];
const bannedGenericActionLabels = ["Review", "Open", "Check", "Resolve"];
const mojibake = [/\u00c2/, /\u00e2\u20ac/, /[\u201c\u201d\u2014\u00b7]/];

function fail(message) {
  console.error(`Smoke check failed: ${message}`);
  process.exitCode = 1;
}

function walk(dir) {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    if (entry === ".next" || entry === "node_modules") {
      return [];
    }
    if (statSync(path).isDirectory()) {
      return walk(path);
    }
    return [path];
  });
}

for (const route of requiredRoutes) {
  const path = join(root, route);
  if (!existsSync(path)) {
    fail(`missing required route ${route}`);
  }
}

for (const component of requiredComponents) {
  const path = join(root, component);
  if (!existsSync(path)) {
    fail(`missing required shared component ${component}`);
  }
}

for (const route of requiredApiRoutes) {
  const path = join(root, route);
  if (!existsSync(path)) {
    fail(`missing required API route ${route}`);
  }
}

const home = [
  readFileSync(join(root, "app/page.tsx"), "utf8"),
  readFileSync(join(root, "components/morning-sweep-button.tsx"), "utf8"),
  readFileSync(join(root, "lib/action-labels.ts"), "utf8"),
].join("\n");
for (const phrase of requiredStartCopy) {
  if (!home.includes(phrase)) {
    fail(`guided start page is missing "${phrase}"`);
  }
}
const primaryActionCount = (readFileSync(join(root, "app/page.tsx"), "utf8").match(/data-primary-action="true"/g) ?? []).length;
if (primaryActionCount !== 1) {
  fail(`guided start page must expose exactly one primary action, found ${primaryActionCount}`);
}

const actionLabelFile = readFileSync(join(root, "lib/action-labels.ts"), "utf8");
const apiClientFile = readFileSync(join(root, "lib/api.ts"), "utf8");
if (apiClientFile.includes("NEXT_PUBLIC_ROADSHOW_API_ACCESS_TOKEN") || apiClientFile.includes("NEXT_PUBLIC_API_ACCESS_TOKEN")) {
  fail("frontend API client must not expose backend API tokens through NEXT_PUBLIC variables");
}
if (!apiClientFile.includes('"/api/roadshow"')) {
  fail("frontend API client must default to the same-origin Roadshow proxy");
}
const labelValues = [...actionLabelFile.matchAll(/:\s*"([^"]+)"/g)].map((match) => match[1]);
const allowedDuplicateLabels = [...actionLabelFile.matchAll(/ALLOWED_DUPLICATE_ACTION_LABELS\s*=\s*\[([^\]]*)\]/gs)]
  .flatMap((match) => [...match[1].matchAll(/"([^"]+)"/g)].map((labelMatch) => labelMatch[1]));
const seenLabels = new Map();
for (const label of labelValues) {
  seenLabels.set(label, (seenLabels.get(label) ?? 0) + 1);
}
for (const [label, count] of seenLabels) {
  if (count > 1 && !allowedDuplicateLabels.includes(label)) {
    fail(`central action label "${label}" is duplicated ${count} times without being explicitly allowed`);
  }
}
for (const label of labelValues) {
  if (bannedGenericActionLabels.includes(label)) {
    fail(`central action label "${label}" is too generic`);
  }
}

for (const route of requiredRoutes) {
  const content = readFileSync(join(root, route), "utf8");
  if (!content.includes('export const dynamic = "force-dynamic"')) {
    fail(`${route} must be dynamic so builds do not depend on a live API`);
  }
}

for (const file of walk(join(root, "app")).concat(walk(join(root, "components")), walk(join(root, "lib")))) {
  const content = readFileSync(file, "utf8");
  const relativePath = relative(root, file);
  for (const pattern of mojibake) {
    if (pattern.test(content)) {
      fail(`${relativePath} contains mojibake or non-ASCII punctuation matched by ${pattern}`);
    }
  }
  for (const phrase of bannedCopy) {
    if (content.includes(phrase)) {
      fail(`${relativePath} still contains vague legacy action label "${phrase}"`);
    }
  }
  for (const phrase of bannedProductionCopy) {
    if (content.includes(phrase)) {
      fail(`${relativePath} still contains production-blocked copy "${phrase}"`);
    }
  }
  for (const phrase of bannedImplementation) {
    if (content.includes(phrase)) {
      fail(`${relativePath} still performs hidden page-load rebuild via "${phrase}"`);
    }
  }
  if (/\.(tsx|ts)$/.test(file)) {
    if (content.includes("Planner caution:")) {
      fail(`${relativePath} still renders passive planner caution copy`);
    }
    if (content.includes("source-error")) {
      fail(`${relativePath} still renders a passive source-error instead of ActionNotice or PurposeButton errorText`);
    }
    for (const label of bannedGenericActionLabels) {
      const exactText = new RegExp(`>\\s*${label}\\s*<`);
      const exactProp = new RegExp(`label=\\{?["']${label}["']\\}?`);
      if (exactText.test(content) || exactProp.test(content)) {
        fail(`${relativePath} contains generic action label "${label}" without an object`);
      }
    }
    const purposeMatches = [...content.matchAll(/<PurposeButton[\s\S]*?\/>/g)];
    for (const match of purposeMatches) {
      const snippet = match[0];
      if (!snippet.includes("helperText=") && !snippet.includes("resultText=") && !snippet.includes("disabledReason=")) {
        fail(`${relativePath} has a PurposeButton without helperText, resultText, or disabledReason context`);
      }
    }
  }
}

if (!process.exitCode) {
  console.log("Smoke check passed: guided start, actionable warnings, action labels, dynamic pages, and text hygiene look good.");
}
