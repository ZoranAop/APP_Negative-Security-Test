#!/usr/bin/env node
/**
 * XXAI Square Publisher — MCP Server entrypoint.
 *
 * Exposes the knowledge base + python toolkit in this repo via the
 * Model Context Protocol (stdio transport).
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  ListResourcesRequestSchema,
  ReadResourceRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

import { tools, callTool, listDocResources, readDocResource } from "./tools.js";

const server = new Server(
  { name: "xxai-square-publisher", version: "0.2.0" },
  { capabilities: { tools: {}, resources: {} } },
);

// NOTE: we cast the async handler through `any` for compatibility with the
// specific @modelcontextprotocol/sdk version in package.json. The runtime
// contract (name/inputSchema for tools list; content[] for callTool return;
// resources/contents for the resource handlers) is stable across 1.x.

server.setRequestHandler(ListToolsRequestSchema, (async () => ({
  tools: tools.map((t) => ({
    name: t.name,
    description: t.description,
    inputSchema: t.inputSchema,
  })),
})) as any);

server.setRequestHandler(CallToolRequestSchema, (async (req: any) => {
  const { name, arguments: args } = req.params;
  return callTool(name, args ?? {});
}) as any);

server.setRequestHandler(ListResourcesRequestSchema, (async () => ({
  resources: await listDocResources(),
})) as any);

server.setRequestHandler(ReadResourceRequestSchema, (async (req: any) => {
  return readDocResource(req.params.uri);
}) as any);

const transport = new StdioServerTransport();
await server.connect(transport);

// keep process alive on stdio
process.stdin.resume();
