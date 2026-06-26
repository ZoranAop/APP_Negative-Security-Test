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
  { name: "xxai-square-publisher", version: "0.1.0" },
  { capabilities: { tools: {}, resources: {} } },
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: tools.map((t) => ({
    name: t.name,
    description: t.description,
    inputSchema: t.inputSchema,
  })),
}));

server.setRequestHandler(CallToolRequestSchema, async (req) => {
  const { name, arguments: args } = req.params;
  return callTool(name, args ?? {});
});

server.setRequestHandler(ListResourcesRequestSchema, async () => ({
  resources: await listDocResources(),
}));

server.setRequestHandler(ReadResourceRequestSchema, async (req) => {
  return readDocResource(req.params.uri);
});

const transport = new StdioServerTransport();
await server.connect(transport);

// keep process alive on stdio
process.stdin.resume();
