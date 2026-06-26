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
      "Call scripts/opennana_fetch.py to pull prompt-gallery materials and write a moments CSV.",
    inputSchema: {
      type: "object",
      properties: {
        media_type: { type: "string", enum: ["image", "video"], default: "image" },
        page: { type: "integer", default: 1, minimum: 1 },
        pages: { type: "integer", default: 1, minimum: 1, maximum: 20 },
        limit: { type: "integer", default: 10, minimum: 1, maximum: 200 },
        output: { type: "string", description: "Destination CSV path." },
      },
      required: ["output"],
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
        return runPython("opennana_fetch.py", flags);
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
