/**
 * Tool implementations for the XXAI Square Publisher MCP Server.
 *
 * Three families of tools:
 *   - Knowledge:  list_docs / read_doc / search_docs
 *   - Scripts:    list_scripts / read_script
 *   - Actions:    run_post_moments / run_post_video / fetch_opennana / rewrite_caption
 *
 * Action tools shell out to the Python scripts in ../../scripts using the
 * `PYTHON_BIN` env var (default: `py -3` on Windows, `python3` elsewhere).
 */

import { spawn } from "node:child_process";
import { promises as fs } from "node:fs";
import { existsSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

// ---------------------------------------------------------------- paths ----
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
// dist/tools.js → mcp/dist/.. → mcp/ → repo root
const REPO_ROOT = path.resolve(__dirname, "..", "..");
const DOCS_DIR = path.join(REPO_ROOT, "docs");
const SCRIPTS_DIR = path.join(REPO_ROOT, "scripts");

// ---------------------------------------------------------------- helpers --
function pythonBin(): string[] {
  const raw = process.env.PYTHON_BIN
    ?? (process.platform === "win32" ? "py -3" : "python3");
  return raw.split(/\s+/);
}

async function listFiles(dir: string, extFilter?: (p: string) => boolean): Promise<string[]> {
  const out: string[] = [];
  async function walk(d: string) {
    const entries = await fs.readdir(d, { withFileTypes: true });
    for (const e of entries) {
      const full = path.join(d, e.name);
      if (e.isDirectory()) {
        await walk(full);
      } else if (!extFilter || extFilter(full)) {
        out.push(path.relative(REPO_ROOT, full).replaceAll("\\", "/"));
      }
    }
  }
  if (existsSync(dir)) await walk(dir);
  return out.sort();
}

function safeJoin(base: string, rel: string): string {
  const abs = path.resolve(base, rel);
  if (!abs.startsWith(path.resolve(base))) {
    throw new Error(`path escapes base: ${rel}`);
  }
  return abs;
}

interface ToolResult {
  content: Array<{ type: "text"; text: string }>;
  isError?: boolean;
}

function ok(text: string): ToolResult {
  return { content: [{ type: "text", text }] };
}
function err(text: string): ToolResult {
  return { content: [{ type: "text", text }], isError: true };
}

// ---------------------------------------------------------------- subprocess
function runProcess(
  cmd: string,
  args: string[],
  opts: { cwd?: string; timeoutMs?: number; env?: NodeJS.ProcessEnv } = {},
): Promise<{ code: number; stdout: string; stderr: string }> {
  return new Promise((resolve) => {
    const child = spawn(cmd, args, {
      cwd: opts.cwd ?? REPO_ROOT,
      env: { ...process.env, ...(opts.env ?? {}) },
      shell: false,
      windowsHide: true,
    });
    let stdout = "";
    let stderr = "";
    let killed = false;
    const timer = opts.timeoutMs
      ? setTimeout(() => {
          killed = true;
          child.kill("SIGKILL");
        }, opts.timeoutMs)
      : undefined;
    child.stdout.on("data", (d) => (stdout += d.toString("utf8")));
    child.stderr.on("data", (d) => (stderr += d.toString("utf8")));
    child.on("close", (code) => {
      if (timer) clearTimeout(timer);
      resolve({
        code: killed ? 124 : (code ?? -1),
        stdout,
        stderr: killed ? stderr + "\n[timeout, process killed]" : stderr,
      });
    });
    child.on("error", (e) => {
      if (timer) clearTimeout(timer);
      resolve({ code: -1, stdout, stderr: stderr + "\n" + String(e) });
    });
  });
}

async function runPython(
  scriptRel: string,
  args: string[],
  timeoutMs = 5 * 60 * 1000,
): Promise<ToolResult> {
  const bin = pythonBin();
  const script = safeJoin(SCRIPTS_DIR, scriptRel);
  if (!existsSync(script)) return err(`script not found: ${scriptRel}`);
  const cmd = bin[0];
  const finalArgs = [...bin.slice(1), script, ...args];
  const res = await runProcess(cmd, finalArgs, { timeoutMs });
  const text = [
    `$ ${cmd} ${finalArgs.join(" ")}`,
    `[exit ${res.code}]`,
    res.stdout && `--- stdout ---\n${res.stdout.trimEnd()}`,
    res.stderr && `--- stderr ---\n${res.stderr.trimEnd()}`,
  ]
    .filter(Boolean)
    .join("\n");
  return res.code === 0 ? ok(text) : err(text);
}

// =============================================================== tools ====
export const tools = [
  // ----------------------------------------------------- knowledge --------
  {
    name: "list_docs",
    description: "List all Markdown documents under docs/ (relative paths).",
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
  },
  {
    name: "read_doc",
    description: "Read the full content of a docs/*.md file. `path` is relative to repo root (e.g. 'docs/03-post-moments.md').",
    inputSchema: {
      type: "object",
      properties: { path: { type: "string" } },
      required: ["path"],
      additionalProperties: false,
    },
  },
  {
    name: "search_docs",
    description: "Case-insensitive substring search over docs/*.md. Returns matching file + line snippets.",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", minLength: 1 },
        max_results: { type: "integer", minimum: 1, maximum: 200, default: 30 },
      },
      required: ["query"],
      additionalProperties: false,
    },
  },

  // ----------------------------------------------------- scripts ----------
  {
    name: "list_scripts",
    description: "List runnable Python scripts under scripts/ with a one-line summary.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
  },
  {
    name: "read_script",
    description: "Read a script's source. `path` is relative to repo root (e.g. 'scripts/post_moments.py').",
    inputSchema: {
      type: "object",
      properties: { path: { type: "string" } },
      required: ["path"],
      additionalProperties: false,
    },
  },

  // ----------------------------------------------------- actions ----------
  {
    name: "run_post_moments",
    description:
      "Invoke scripts/post_moments.py to batch-post text/image moments. " +
      "Pass the path to an accounts CSV and a materials CSV (see docs/03-post-moments.md). " +
      "Returns stdout/stderr from the Python process.",
    inputSchema: {
      type: "object",
      properties: {
        accounts_csv: { type: "string", description: "Path to accounts CSV (relative to repo root or absolute)." },
        csv: { type: "string", description: "Path to materials CSV." },
        num_accounts: { type: "integer", default: 0, description: "0 = all accounts in CSV; N = random N." },
        num_posts: { type: "integer", default: 0, description: "0 = all materials; M = random M." },
        concurrency: { type: "integer", default: 1, minimum: 1, maximum: 16 },
        delay: { type: "number", default: 2.0, minimum: 0, description: "Seconds between posts when concurrency=1." },
        dry_run: { type: "boolean", default: false, description: "If true, do not actually invoke; just echo the command." },
      },
      required: ["accounts_csv", "csv"],
      additionalProperties: false,
    },
  },
  {
    name: "run_post_video",
    description:
      "Invoke scripts/post_video.py to publish a video moment. " +
      "See docs/06-post-video.md for the media_info contract.",
    inputSchema: {
      type: "object",
      properties: {
        account: { type: "string", description: "Account email or user_id present in accounts_csv." },
        accounts_csv: { type: "string", description: "Path to accounts CSV." },
        video: { type: "string", description: "Local path or URL of the .mp4." },
        cover: { type: "string", description: "Local path or URL of the cover image." },
        caption: { type: "string" },
        visibility: { type: "integer", enum: [0, 1, 2], default: 0 },
        room_id: { type: "string" },
        dry_run: { type: "boolean", default: false },
      },
      required: ["account", "video", "cover", "caption"],
      additionalProperties: false,
    },
  },
  {
    name: "fetch_opennana",
    description:
      "Call scripts/opennana_fetch.py to pull prompt-gallery materials and write a moments CSV. " +
      "Supports theme/model filtering and ad exclusion (see docs/11 / docs/12).",
    inputSchema: {
      type: "object",
      properties: {
        media_type: { type: "string", enum: ["image", "video"], default: "image" },
        page: { type: "integer", default: 1, minimum: 1 },
        pages: { type: "integer", default: 1, minimum: 1, maximum: 30 },
        limit: { type: "integer", default: 10, minimum: 1, maximum: 500 },
        model: { type: "string", description: 'e.g. "ChatGPT", "Nano banana pro"' },
        theme: {
          type: "string",
          enum: ["beauty", "portrait", "sport", "travel", "food", "all"],
          default: "all",
        },
        exclude_ads: { type: "boolean", default: false },
        dedupe_file: { type: "string", description: "JSON of already-used slugs" },
        shuffle_pages: { type: "boolean", default: false },
        output: { type: "string", description: "Destination CSV path." },
      },
      required: ["output"],
      additionalProperties: false,
    },
  },
  {
    name: "fetch_openprompts",
    description:
      "Call scripts/fetch_openprompts.py to pull materials from open-prompts.com and write a moments CSV.",
    inputSchema: {
      type: "object",
      properties: {
        page: { type: "integer", default: 1, minimum: 1 },
        pages: { type: "integer", default: 1, minimum: 1, maximum: 10 },
        limit: { type: "integer", default: 50, minimum: 1, maximum: 500 },
        model: { type: "string" },
        theme: {
          type: "string",
          enum: ["beauty", "portrait", "sport", "travel", "food", "all"],
          default: "all",
        },
        exclude_ads: { type: "boolean", default: false },
        dedupe_file: { type: "string" },
        output: { type: "string" },
      },
      required: ["output"],
      additionalProperties: false,
    },
  },
  {
    name: "fetch_lovimg",
    description:
      "Call scripts/fetch_lovimg.py to pull materials from lovimg.com. lovimg is SSR-only, " +
      "no REST API; the script parses inline JS payloads.",
    inputSchema: {
      type: "object",
      properties: {
        category: { type: "string", default: "people-characters" },
        max_pages: { type: "integer", default: 15, minimum: 1, maximum: 60 },
        limit: { type: "integer", default: 50, minimum: 1, maximum: 500 },
        theme: {
          type: "string",
          enum: ["beauty", "portrait", "sport", "travel", "food", "all"],
          default: "all",
        },
        exclude_ads: { type: "boolean", default: false },
        dedupe_file: { type: "string" },
        output: { type: "string" },
      },
      required: ["output"],
      additionalProperties: false,
    },
  },
  {
    name: "fetch_tophub",
    description:
      "Call scripts/fetch_tophub.py to pull trending topic titles from tophub.today/hot and write a " +
      "text-only moments CSV (image_urls empty). Public source, no login. Pair with " +
      "generate_multilang_captions for EN/繁中/日 output. See docs/14-tophub-source.md.",
    inputSchema: {
      type: "object",
      properties: {
        limit: { type: "integer", default: 100, minimum: 1, maximum: 500 },
        exclude_ads: { type: "boolean", default: false },
        dedupe_file: { type: "string", description: "JSON of already-used topic hashes" },
        output: { type: "string" },
      },
      required: ["output"],
      additionalProperties: false,
    },
  },
  {
    name: "fetch_multi_source",
    description:
      "Call scripts/multi_source_fetch.py to aggregate materials across opennana / open-prompts / lovimg " +
      "with unified theme + ad filters and a shared dedupe list.",
    inputSchema: {
      type: "object",
      properties: {
        sources: { type: "string", default: "opennana,openprompts,lovimg",
                   description: "comma-separated: opennana / openprompts / lovimg / tophub (tophub = text-only)" },
        theme: {
          type: "string",
          enum: ["beauty", "portrait", "sport", "travel", "food", "all"],
          default: "beauty",
        },
        model: { type: "string", description: "optional opennana/openprompts model filter" },
        exclude_ads: { type: "boolean", default: true },
        limit: { type: "integer", default: 100, minimum: 1, maximum: 1000 },
        source_weights: { type: "string",
                          description: 'e.g. "opennana=40,openprompts=40,lovimg=20"' },
        dedupe_file: { type: "string" },
        shuffle: { type: "boolean", default: true },
        opennana_pages: { type: "integer", default: 8, minimum: 1, maximum: 30 },
        openprompts_pages: { type: "integer", default: 3, minimum: 1, maximum: 10 },
        lovimg_max_pages: { type: "integer", default: 15, minimum: 1, maximum: 60 },
        output: { type: "string" },
      },
      required: ["output"],
      additionalProperties: false,
    },
  },
  {
    name: "generate_multilang_captions",
    description:
      "Call scripts/caption_multilang.py to rewrite the `content` column of a moments CSV " +
      "into subject-first captions in one or more languages (en / zh / zh_hant / ja). " +
      "Uses built-in template pool by default; --use-llm invokes LLM_TEXT_* / LLM_* if configured.",
    inputSchema: {
      type: "object",
      properties: {
        input: { type: "string", description: "input CSV path" },
        output: { type: "string", description: "output CSV path" },
        langs: { type: "string", default: "en,zh_hant,ja",
                 description: "comma-separated: en / zh / zh_hant / ja" },
        use_llm: { type: "boolean", default: false },
        use_existing_lang: { type: "boolean", default: false,
                             description: "respect a pre-assigned _lang column (e.g. from plan_lang_ratio)" },
        seed: { type: "integer", default: 20260703 },
      },
      required: ["input", "output"],
      additionalProperties: false,
    },
  },
  {
    name: "plan_lang_ratio",
    description:
      "Call scripts/plan_lang_ratio.py to assign a `_lang` column to a moments CSV by an EXACT ratio " +
      "(e.g. English+Japanese = 80%, Traditional Chinese = 20%). Uses largest-remainder rounding so " +
      "quotas sum to N exactly; rejects Simplified Chinese by default. Pair with " +
      "generate_multilang_captions(use_existing_lang=true). See docs/14 §14.5.",
    inputSchema: {
      type: "object",
      properties: {
        input: { type: "string", description: "input moments CSV" },
        output: { type: "string", description: "output CSV with _lang column" },
        minor_lang: { type: "string", default: "zh_hant",
                      description: "the small-slice language" },
        minor_ratio: { type: "number", default: 0.20, minimum: 0, maximum: 1 },
        major_langs: { type: "string", default: "en,ja",
                       description: "comma list sharing the remaining slice" },
        major_split: { type: "string",
                       description: 'optional fixed split of the WHOLE file, e.g. "en=0.30,ja=0.50"' },
        allow_simplified: { type: "boolean", default: false },
        tolerance: { type: "number", default: 0.02 },
        seed: { type: "integer", default: 20260703 },
      },
      required: ["input", "output"],
      additionalProperties: false,
    },
  },
  {
    name: "run_publish_from_tokens",
    description:
      "Invoke scripts/publish_from_tokens.py: three-phase safe publisher " +
      "(sequential login with 429-backoff → S3 upload cache → parallel publish). " +
      "Recommended for ≥15 accounts. See docs/03 §3.6.",
    inputSchema: {
      type: "object",
      properties: {
        accounts_csv: { type: "string" },
        csv: { type: "string", description: "moments CSV" },
        concurrency: { type: "integer", default: 4, minimum: 1, maximum: 32 },
        login_spacing: { type: "number", default: 2.5, minimum: 0 },
        tokens_in: { type: "string", description: "optional pre-existing tokens JSON to reuse" },
        tokens_out: { type: "string", default: "result/tokens.json" },
        no_persist_tokens: { type: "boolean", default: false },
        output_csv: { type: "string" },
        dry_run: { type: "boolean", default: false,
                   description: "if true, stop after phase 1 (login) and report" },
      },
      required: ["accounts_csv", "csv"],
      additionalProperties: false,
    },
  },
  {
    name: "rewrite_caption",
    description:
      "Rewrite an English prompt / raw description into a first-person Chinese share-style caption, " +
      "following docs/04-content-pipeline.md §4.2. " +
      "This tool does NOT call an LLM itself — it just produces a structured rewrite brief that the " +
      "calling model should fulfil. The LLM agent should then return the rewritten caption to the user.",
    inputSchema: {
      type: "object",
      properties: {
        raw: { type: "string", description: "Original (often English) prompt / title / description." },
        scene_hint: { type: "string", description: "Optional scene hint, e.g. 'beauty fashion shot'." },
      },
      required: ["raw"],
      additionalProperties: false,
    },
  },
] as const;

// =============================================================== dispatch =
export async function callTool(name: string, args: Record<string, unknown>): Promise<ToolResult> {
  try {
    switch (name) {
      case "list_docs":
        return ok(JSON.stringify(await listFiles(DOCS_DIR, (p) => p.endsWith(".md")), null, 2));

      case "read_doc": {
        const rel = String(args.path);
        if (!rel.startsWith("docs/")) return err("path must start with 'docs/'");
        const abs = safeJoin(REPO_ROOT, rel);
        return ok(await fs.readFile(abs, "utf8"));
      }

      case "search_docs": {
        const query = String(args.query).toLowerCase();
        const limit = (args.max_results as number) ?? 30;
        const files = await listFiles(DOCS_DIR, (p) => p.endsWith(".md"));
        const hits: string[] = [];
        for (const rel of files) {
          const txt = await fs.readFile(path.join(REPO_ROOT, rel), "utf8");
          const lines = txt.split(/\r?\n/);
          lines.forEach((ln, idx) => {
            if (hits.length >= limit) return;
            if (ln.toLowerCase().includes(query)) {
              hits.push(`${rel}:${idx + 1}: ${ln.trim()}`);
            }
          });
          if (hits.length >= limit) break;
        }
        return ok(hits.length ? hits.join("\n") : `(no matches for ${String(args.query)})`);
      }

      case "list_scripts": {
        const files = await listFiles(SCRIPTS_DIR, (p) => p.endsWith(".py"));
        const lines: string[] = [];
        for (const rel of files) {
          const txt = await fs.readFile(path.join(REPO_ROOT, rel), "utf8");
          const m = txt.match(/^"""([\s\S]*?)"""/m);
          const summary = m
            ? m[1].split("\n").map((l) => l.trim()).filter(Boolean).slice(0, 2).join(" ")
            : "(no docstring)";
          lines.push(`${rel}\n    ${summary}`);
        }
        return ok(lines.join("\n\n"));
      }

      case "read_script": {
        const rel = String(args.path);
        if (!rel.startsWith("scripts/")) return err("path must start with 'scripts/'");
        const abs = safeJoin(REPO_ROOT, rel);
        return ok(await fs.readFile(abs, "utf8"));
      }

      case "run_post_moments": {
        const a = args as Record<string, any>;
        const flags = [
          "--accounts-csv", String(a.accounts_csv),
          "--csv", String(a.csv),
          "--num-accounts", String(a.num_accounts ?? 0),
          "--num-posts", String(a.num_posts ?? 0),
          "--concurrency", String(a.concurrency ?? 1),
          "--delay", String(a.delay ?? 2.0),
        ];
        if (a.dry_run) return ok(`[dry-run] py -3 scripts/post_moments.py ${flags.join(" ")}`);
        return runPython("post_moments.py", flags);
      }

      case "run_post_video": {
        const a = args as Record<string, any>;
        const flags = [
          "--account", String(a.account),
          "--video", String(a.video),
          "--cover", String(a.cover),
          "--caption", String(a.caption),
          "--visibility", String(a.visibility ?? 0),
        ];
        if (a.accounts_csv) flags.push("--accounts-csv", String(a.accounts_csv));
        if (a.room_id) flags.push("--room-id", String(a.room_id));
        if (a.dry_run) return ok(`[dry-run] py -3 scripts/post_video.py ${flags.join(" ")}`);
        return runPython("post_video.py", flags);
      }

      case "fetch_opennana": {
        const a = args as Record<string, any>;
        const flags = [
          "--media-type", String(a.media_type ?? "image"),
          "--page", String(a.page ?? 1),
          "--pages", String(a.pages ?? 1),
          "--limit", String(a.limit ?? 10),
          "--output", String(a.output),
        ];
        if (a.model) flags.push("--model", String(a.model));
        if (a.theme && a.theme !== "all") flags.push("--theme", String(a.theme));
        if (a.exclude_ads) flags.push("--exclude-ads");
        if (a.dedupe_file) flags.push("--dedupe-file", String(a.dedupe_file));
        if (a.shuffle_pages) flags.push("--shuffle-pages");
        return runPython("opennana_fetch.py", flags);
      }

      case "fetch_openprompts": {
        const a = args as Record<string, any>;
        const flags = [
          "--page", String(a.page ?? 1),
          "--pages", String(a.pages ?? 1),
          "--limit", String(a.limit ?? 50),
          "--output", String(a.output),
        ];
        if (a.model) flags.push("--model", String(a.model));
        if (a.theme && a.theme !== "all") flags.push("--theme", String(a.theme));
        if (a.exclude_ads) flags.push("--exclude-ads");
        if (a.dedupe_file) flags.push("--dedupe-file", String(a.dedupe_file));
        return runPython("fetch_openprompts.py", flags);
      }

      case "fetch_lovimg": {
        const a = args as Record<string, any>;
        const flags = [
          "--category", String(a.category ?? "people-characters"),
          "--max-pages", String(a.max_pages ?? 15),
          "--limit", String(a.limit ?? 50),
          "--output", String(a.output),
        ];
        if (a.theme && a.theme !== "all") flags.push("--theme", String(a.theme));
        if (a.exclude_ads) flags.push("--exclude-ads");
        if (a.dedupe_file) flags.push("--dedupe-file", String(a.dedupe_file));
        return runPython("fetch_lovimg.py", flags);
      }

      case "fetch_tophub": {
        const a = args as Record<string, any>;
        const flags = [
          "--limit", String(a.limit ?? 100),
          "--output", String(a.output),
        ];
        if (a.exclude_ads) flags.push("--exclude-ads");
        if (a.dedupe_file) flags.push("--dedupe-file", String(a.dedupe_file));
        return runPython("fetch_tophub.py", flags);
      }

      case "fetch_multi_source": {
        const a = args as Record<string, any>;
        const flags = [
          "--sources", String(a.sources ?? "opennana,openprompts,lovimg"),
          "--theme", String(a.theme ?? "beauty"),
          "--limit", String(a.limit ?? 100),
          "--output", String(a.output),
          "--opennana-pages", String(a.opennana_pages ?? 8),
          "--openprompts-pages", String(a.openprompts_pages ?? 3),
          "--lovimg-max-pages", String(a.lovimg_max_pages ?? 15),
        ];
        if (a.model) flags.push("--model", String(a.model));
        if (a.exclude_ads === false) flags.push("--include-ads");
        // exclude_ads default = true, no flag needed then
        if (a.source_weights) flags.push("--source-weights", String(a.source_weights));
        if (a.dedupe_file) flags.push("--dedupe-file", String(a.dedupe_file));
        if (a.shuffle !== false) flags.push("--shuffle");
        return runPython("multi_source_fetch.py", flags);
      }

      case "generate_multilang_captions": {
        const a = args as Record<string, any>;
        const flags = [
          "--input", String(a.input),
          "--output", String(a.output),
          "--langs", String(a.langs ?? "en,zh_hant,ja"),
          "--seed", String(a.seed ?? 20260703),
        ];
        if (a.use_llm) flags.push("--use-llm");
        if (a.use_existing_lang) flags.push("--use-existing-lang");
        return runPython("caption_multilang.py", flags);
      }

      case "plan_lang_ratio": {
        const a = args as Record<string, any>;
        const flags = [
          "--input", String(a.input),
          "--output", String(a.output),
          "--minor-lang", String(a.minor_lang ?? "zh_hant"),
          "--minor-ratio", String(a.minor_ratio ?? 0.20),
          "--major-langs", String(a.major_langs ?? "en,ja"),
          "--tolerance", String(a.tolerance ?? 0.02),
          "--seed", String(a.seed ?? 20260703),
        ];
        if (a.major_split) flags.push("--major-split", String(a.major_split));
        if (a.allow_simplified) flags.push("--allow-simplified");
        return runPython("plan_lang_ratio.py", flags);
      }

      case "run_publish_from_tokens": {
        const a = args as Record<string, any>;
        const flags = [
          "--accounts-csv", String(a.accounts_csv),
          "--csv", String(a.csv),
          "--concurrency", String(a.concurrency ?? 4),
          "--login-spacing", String(a.login_spacing ?? 2.5),
          "--tokens-out", String(a.tokens_out ?? "result/tokens.json"),
        ];
        if (a.tokens_in) flags.push("--tokens-in", String(a.tokens_in));
        if (a.no_persist_tokens) flags.push("--no-persist-tokens");
        if (a.output_csv) flags.push("--output-csv", String(a.output_csv));
        if (a.dry_run) flags.push("--dry-run");
        return runPython("publish_from_tokens.py", flags, 15 * 60 * 1000);
      }

      case "rewrite_caption": {
        const raw = String((args as any).raw);
        const hint = (args as any).scene_hint ? `\nScene hint: ${(args as any).scene_hint}` : "";
        const brief = [
          "# Caption rewrite brief",
          "",
          "Rewrite the following raw description into a Chinese first-person",
          "share-style social-media caption suitable for XXAI Square moments.",
          "",
          "Rules (from docs/04-content-pipeline.md §4.2):",
          "1. Use first-person voice (e.g. '今日穿搭', '周末打卡了…', '终于拍出来啦').",
          "2. Drop any AI-generation markers: 【AI生图】, Prompt思路：, English prompt body,",
          "   #AI提示词, #NanoBananaPro, etc.",
          "3. Add 2-4 natural Chinese hashtags (#今日穿搭 #居家日常 #国风 …) + 1-3 emoji.",
          "4. Avoid explicit / vulgar content; keep it lifestyle-positive.",
          "5. Output ONLY the final caption text, no preamble.",
          "",
          "## Raw input" + hint,
          "",
          raw,
        ].join("\n");
        return ok(brief);
      }

      default:
        return err(`unknown tool: ${name}`);
    }
  } catch (e: any) {
    return err(`[error] ${e?.message ?? String(e)}`);
  }
}

// =============================================================== resources
export async function listDocResources() {
  const files = await listFiles(DOCS_DIR, (p) => p.endsWith(".md"));
  return files.map((rel) => ({
    uri: `xxai-doc:///${rel}`,
    name: rel,
    mimeType: "text/markdown",
  }));
}

export async function readDocResource(uri: string) {
  const prefix = "xxai-doc:///";
  if (!uri.startsWith(prefix)) {
    throw new Error(`unsupported uri scheme: ${uri}`);
  }
  const rel = uri.slice(prefix.length);
  if (!rel.startsWith("docs/")) {
    throw new Error("only docs/* is exposed as resources");
  }
  const abs = safeJoin(REPO_ROOT, rel);
  const text = await fs.readFile(abs, "utf8");
  return {
    contents: [
      { uri, mimeType: "text/markdown", text },
    ],
  };
}

// silence "unused" warning on Node typings
void statSync;
