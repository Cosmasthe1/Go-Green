// main.ts — Go Green MCP App entry point
// Supports both Streamable HTTP (for Claude.ai, ChatGPT) and stdio (for Claude Desktop)

import { createMcpExpressApp } from "@modelcontextprotocol/sdk/server/express.js";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import cors from "cors";
import type { Request, Response } from "express";
import { createServer } from "./server.js";

async function startHTTP(factory: () => McpServer): Promise<void> {
  const port = parseInt(process.env.PORT ?? "3001", 10);
  const app  = createMcpExpressApp({ host: "0.0.0.0" });
  app.use(cors());

  app.all("/mcp", async (req: Request, res: Response) => {
    const server    = factory();
    const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined });
    res.on("close", () => { transport.close().catch(()=>{}); server.close().catch(()=>{}); });
    try {
      await server.connect(transport);
      await transport.handleRequest(req, res, req.body);
    } catch (err) {
      console.error("MCP error:", err);
      if (!res.headersSent) res.status(500).json({ jsonrpc:"2.0", error:{code:-32603,message:"Internal error"}, id:null });
    }
  });

  const http = app.listen(port, (err?: Error) => {
    if (err) { console.error(err); process.exit(1); }
    console.log(`\n🌿 Go Green MCP Server`);
    console.log(`   HTTP  → http://localhost:${port}/mcp`);
    console.log(`   Tools → search_rides | book_ride | carbon_portfolio`);
    console.log(`   UI    → ui://gogreen/main (MCP Apps)`);
  });

  const shutdown = () => { http.close(()=>process.exit(0)); };
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
}

async function startStdio(factory: () => McpServer): Promise<void> {
  await factory().connect(new StdioServerTransport());
}

async function main() {
  if (process.argv.includes("--stdio")) {
    await startStdio(createServer);
  } else {
    await startHTTP(createServer);
  }
}

main().catch(e => { console.error(e); process.exit(1); });
