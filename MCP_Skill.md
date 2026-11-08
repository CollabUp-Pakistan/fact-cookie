---
name: mcp-server-fastmcp
description: Build, test, secure and deploy MCP (Model Context Protocol) servers in Python with FastMCP. Covers installation, tools/resources/prompts, stdio vs streamable HTTP transport, MCP Inspector testing, client configs (Claude, Cursor), FastAPI mounting, authentication (OAuth/JWT), production checklist and common pitfalls. Use this skill whenever the user mentions MCP, Model Context Protocol, FastMCP, an MCP server or connector, "@mcp.tool", exposing tools to Claude/ChatGPT/Cursor/opencode, or building a remote connector with a URL and login, even if they do not say "FastMCP" explicitly. Read this skill instead of web searching for basic MCP/FastMCP usage.
---

# Building MCP Servers with FastMCP (Python)

Sources: Composio's "How to build an MCP server from scratch (2026 guide)" and the official FastMCP docs (gofastmcp.com), compiled 8 Nov 2026. FastMCP changes quickly. For version-specific details (auth classes, import paths, new parameters), check https://gofastmcp.com (it publishes an index at https://gofastmcp.com/llms.txt) before assuming.

---

## 1. What MCP is (the short version)

An MCP server is a JSON-RPC 2.0 process that exposes three primitives to any MCP client:

| Primitive | What it is | FastMCP decorator |
|---|---|---|
| **Tools** | Functions the model can call (may have side effects) | `@mcp.tool` |
| **Resources** | Data the model/client can read, addressed by URI | `@mcp.resource("scheme://path")` |
| **Prompts** | Reusable prompt templates | `@mcp.prompt` |

Transports:
- **stdio**: server runs as a local subprocess of the client. Best for local tools and prototyping.
- **Streamable HTTP**: server is a normal web service at a URL. Required for hosted, multi-user or "add by URL" connectors.
- (Legacy SSE exists; do not choose it for new work.)

### Components

1. **Host**: the app the user talks to (Claude Desktop, Claude Code, Cursor, ChatGPT, opencode).
2. **Client**: created by the host; one dedicated connection per server.
3. **Server**: your code. It exposes tools/resources/prompts and talks to databases, files and APIs.
4. **Data sources / remote services**: what your server actually reads or calls.

The host never talks to your database or API directly. It goes host -> client -> your MCP server -> data source. The server is the integration layer that hides auth, API calls and business logic.

### Why MCP instead of plain function calling or REST
- One shared interface instead of per-vendor glue code.
- Stateful sessions, streaming and progress callbacks.
- Clients discover tools at runtime, so you can add tools without breaking clients.
- Trade-off: one extra hop (agent -> MCP -> API) adds a little latency, and tooling is younger than REST.

---

## 2. Prerequisites and installation

- Python 3.10+ (use a recent version)
- Node.js 18+ (only needed for MCP Inspector, or if building in TypeScript)
- A client for testing: Claude Desktop, Claude Code, or Cursor

```bash
mkdir mcp_servers && cd mcp_servers
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install fastmcp
```

Confirm `(.venv)` shows in the prompt. Pin the version in `requirements.txt` for production (for example `fastmcp==<tested version>`), because FastMCP APIs evolve.

Python vs TypeScript: Python + FastMCP is fastest for prototyping and stdio servers. TypeScript fits HTTP servers on Node-based edge platforms (Cloudflare Workers, Vercel Edge). Our default is Python + FastMCP.

---

## 3. Minimal server (copy-paste starting point)

```python
# server.py
from fastmcp import FastMCP

mcp = FastMCP("Utility Server")

@mcp.tool
def add(a: int, b: int) -> int:
    """Add two integers and return the sum."""
    return a + b

if __name__ == "__main__":
    mcp.run()          # stdio by default
```

Notes:
- Older guides write `@mcp.tool()` with parentheses. Current docs use `@mcp.tool`. Both styles are seen; follow the installed version.
- The function name becomes the tool name; type hints become the input schema; the **docstring becomes the description the model reads**.

---

## 4. Code reference

### 4.1 Tools
```python
from typing import List
import os
from fastmcp import FastMCP

mcp = FastMCP("Files Server")

@mcp.tool
def list_files(directory: str = ".") -> List[str]:
    """List file and folder names in a directory.

    Args:
        directory: Path to list. Defaults to the current directory.

    Returns:
        A list of names, or a single-item list with an error message.
    """
    try:
        return os.listdir(directory)
    except Exception as e:
        return [f"Error: {e}"]

@mcp.tool
def read_file(filename: str) -> str:
    """Read a UTF-8 text file and return its full content.

    Returns the text, or a string starting with 'Error reading file:' on failure.
    """
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {e}"
```

Rules of thumb:
- One clear purpose per tool. Five small tools beat one giant tool.
- Write the docstring for the model: when to use it, what each argument means, what it returns, what errors look like.
- Return clean error messages instead of raising uncaught exceptions.
- Prefer typed returns (str, int, list, dict, Pydantic models) so output schemas are clear.

### 4.2 Resources
```python
@mcp.resource("data://sys-info")
def get_system_info() -> str:
    """Snapshot of the host: OS, time and basic resource usage."""
    import platform
    from datetime import datetime
    return f"OS: {platform.system()} ({platform.machine()})\nTime: {datetime.now():%Y-%m-%d %H:%M:%S}"
```
The string inside `@mcp.resource(...)` is the URI clients use to fetch it. Keep resources read-only. (The Composio sample also imports `psutil` and hardcodes a Windows `C:\` path. Avoid hardcoding OS-specific paths.)

### 4.3 Prompts
```python
@mcp.prompt
def helper_prompt(task: str, context: str = "") -> str:
    """General-purpose prompt for any task, with optional context."""
    text = (f"Task: {task}\n\nWork systematically:\n"
            "1. Break down the problem\n2. Consider multiple solutions\n"
            "3. Explain your reasoning\n4. Give clear, actionable steps")
    if context:
        text += f"\n\nAdditional context: {context}"
    return text
```

### 4.4 Running the server
```python
if __name__ == "__main__":
    # Local (stdio):
    mcp.run()

    # Hosted (streamable HTTP):
    # mcp.run(transport="http", host="0.0.0.0", port=8000)
```
- Composio's guide writes `transport="streamable-http"`. Current FastMCP docs use `transport="http"`. Use the one your installed version accepts.
- Default HTTP endpoint is `http://localhost:8000/mcp/` (custom: `path="/api/mcp/"`).
- You can also use the CLI (`fastmcp run server.py`); check `fastmcp --help` for the installed version.

### 4.5 ASGI app (for uvicorn, gunicorn workers, mounting)
```python
app = mcp.http_app()                 # or mcp.http_app(path="/api/mcp/")
# run:  uvicorn server:app --host 0.0.0.0 --port 8000
```

### 4.6 Testing in code with the FastMCP client
```python
import asyncio
from fastmcp import Client

async def main():
    async with Client(mcp) as client:            # in-memory, no network
        print(await client.list_tools())
        print(await client.call_tool("add", {"a": 2, "b": 3}))

asyncio.run(main())
```
A client can also point at a URL (`Client("http://localhost:8000/mcp/")`) or a script path. Use this for automated tests (pytest + `asyncio`).

---

## 5. Step-by-step workflow

1. **Define the job.** List the 3-8 actions the AI should be able to take. Each becomes a tool.
2. **Set up the environment** (section 2).
3. **Write tools** with strong docstrings and type hints; add resources/prompts only if useful.
4. **Run locally over stdio** and test with MCP Inspector (section 6).
5. **Connect a real client** (section 7) and try prompts that should trigger each tool.
6. **Harden** (section 10): error handling, validation, logging, secrets.
7. **Switch to HTTP** and add authentication (section 8, 9).
8. **Deploy** and expose `/health` (section 10); connect clients by URL.
9. **Version and monitor** tool schemas as you change them.

---

## 6. Testing with MCP Inspector

```bash
npx @modelcontextprotocol/inspector python server.py
```
Open the printed localhost URL, click **Connect**, then call tools, read resources and run prompts directly in the browser without an LLM. Use it to check input schemas, outputs and error responses before involving a model. For an HTTP server, choose the HTTP transport in the Inspector and paste the server URL (for example `http://localhost:8000/mcp/`).

---

## 7. Connecting clients

### 7.1 Cursor / Claude Desktop style config, stdio (local)
Cursor: create `.cursor/mcp.json`:
```json
{
  "mcpServers": {
    "utility_server": {
      "type": "stdio",
      "command": "/full/path/to/.venv/bin/python",
      "args": ["/full/path/to/server.py"]
    }
  }
}
```
Tips:
- Use the full path to the venv's Python (Windows: `.venv\Scripts\python.exe`).
- Quick check: run the same `command` + `args` in a terminal. If it starts, the config is right.
- Cursor Settings -> Tools & MCPs, enable the server, check the Output tab for a "connected" message.
- The client may ask permission before running a tool. Keep that on for anything touching files or secrets.

### 7.2 Remote (HTTP) server by URL
Cursor-style config:
```json
{
  "mcpServers": {
    "my_server": {
      "type": "http",
      "url": "https://mcp.example.com/mcp",
      "headers": {}
    }
  }
}
```
Claude Code:
```bash
claude mcp add --scope user --transport http my_server https://mcp.example.com/mcp
```
Then run `/mcp` in Claude Code to see the server and authenticate if it requires login.

In chat apps (Claude, ChatGPT and others) the user adds a **custom connector** by entering a name and the server URL. If the server requires OAuth, the client shows an auth button, opens the server's login page, and stores the token after approval.

Note: if tool docstrings are poor, a client may fall back to shell/CLI instead of the tool. Fix the descriptions, or add a client rule telling the agent to prefer the MCP tools for that task.

---

## 8. Working flow of a call (what happens at runtime)

1. User asks the host (for example Claude) to do something.
2. Host's MCP client connects to the server and lists tools (`tools/list`).
3. The model chooses a tool and arguments based on the tool descriptions and schemas.
4. Client sends `tools/call`. For HTTP servers the request carries the user's bearer token.
5. Server validates the token, checks permissions and limits, runs the function, and returns structured output.
6. Client passes the result back to the model, which writes the final answer.

Example from the Composio guide: Claude Code is the host; it connects to a Google Sheets MCP server and a Slack MCP server; each server calls its own remote API; responses flow back through the client to the user.

---

## 9. Hosting over HTTP, mounting in FastAPI, and authentication

### 9.1 Standalone HTTP
```python
mcp.run(transport="http", host="0.0.0.0", port=8000)
```

### 9.2 Mount inside an existing FastAPI app
```python
from fastapi import FastAPI
from fastmcp import FastMCP

mcp = FastMCP("API Tools")

@mcp.tool
def query_database(query: str) -> dict:
    """Run a read-only database query."""
    return {"result": "data"}

mcp_app = mcp.http_app()
api = FastAPI(lifespan=mcp_app.lifespan)     # required so the MCP session manager starts

@api.get("/api/status")
def status():
    return {"status": "ok"}

api.mount("/mcp", mcp_app)
# run: uvicorn app:api --host 0.0.0.0 --port 8000
```
- Docs show the MCP endpoint ending up at `http://localhost:8000/mcp/` when mounted at `/mcp`. **Always verify the final URL with Inspector.**
- If the FastAPI app already has its own lifespan (database connections, startup tasks), combine lifespans (FastMCP provides a `combine_lifespans` helper; confirm its import path in the current docs).
- CORS: if the MCP server uses OAuth, do not add app-wide `CORSMiddleware` to the combined app. Mount the API and MCP as separate sub-apps, each with its own middleware.
- Reverse direction: `FastMCP.from_fastapi(app=api)` generates MCP tools from FastAPI routes. Good for quick wrapping, but hand-written tools with good docstrings usually work better for LLMs.
- Custom routes added to the MCP server are **not** covered by its auth. For authenticated REST endpoints, use FastAPI `Depends()` on the FastAPI side.

### 9.3 Authentication (HTTP transport only)
- FastMCP servers default to `auth=None`, meaning anyone who can reach the URL can call the tools. **Always configure auth for remote servers.** Some clients refuse to connect to unauthenticated remote servers.
- stdio inherits the security of the local machine; no auth setup needed.

Options, from least to most responsibility for you:

| Option | Use when |
|---|---|
| **Token validation** (`JWTVerifier` / `TokenVerifier`) | You already have an auth system issuing JWTs; the MCP server only validates tokens |
| **RemoteAuthProvider** (for example WorkOS AuthKit provider) | Your identity provider supports Dynamic Client Registration (DCR); enables the "enter URL -> click auth -> login" flow automatically |
| **OAuthProxy** (for example GitHub provider) | Provider does not support DCR (GitHub, Google, Azure and similar) |
| **Full OAuth server** (`OAuthProvider`) | You need complete control; most work and highest security burden |

JWT example:
```python
from fastmcp import FastMCP
from fastmcp.server.auth.providers.jwt import JWTVerifier

auth = JWTVerifier(
    jwks_uri="https://auth.example.com/.well-known/jwks.json",
    issuer="https://auth.example.com",
    audience="my-mcp-server",
)
mcp = FastMCP(name="Protected Server", auth=auth)
```
WorkOS AuthKit (DCR) example:
```python
from fastmcp.server.auth.providers.workos import AuthKitProvider

auth = AuthKitProvider(
    authkit_domain="https://your-project.authkit.app",
    base_url="https://your-fastmcp-server.com",
)
mcp = FastMCP(name="Enterprise Server", auth=auth)
```
Guidance:
- Production public servers: **OAuth** (so users log in with their account in the browser). Internal/private: bearer tokens or API keys. Do not mix both styles on the same endpoint without a clear reason.
- Map the validated token to your own user record so you can enforce plan limits and log usage per user.
- Optional hardening: `host_origin_protection=True` with `allowed_hosts` and `allowed_origins` passed to `http_app()` or `run()` (or the `FASTMCP_HTTP_*` environment variables).
- Auth APIs are changing quickly. Re-check the official auth pages before implementing.

---

## 10. Production checklist (good practices)

- **Logging**: write to stderr or files only. Never print to stdout on stdio servers (it corrupts the protocol).
- **Error handling**: catch errors in every tool and return a clean message; do not let exceptions drop the connection.
- **Input validation**: type hints (Pydantic) catch most issues; add explicit checks for path traversal, SQL injection and other risky inputs when touching files or databases.
- **Rate limiting / quotas**: tools run whenever the model decides to call them, possibly many times. Limit external API calls and per-user usage.
- **Secrets**: environment variables only. Never hardcode or commit keys.
- **Tool design**: specific, single-purpose tools; descriptions written for the LLM.
- **Schema versioning**: bump the server version when a tool signature changes so clients can adapt. Treat it like API versioning.
- **Health check**: expose `/health` on HTTP servers for load balancers and monitoring.
- **Auth**: required on all production HTTP servers (section 9.3).
- **Always-on hosting**: do not use a host that sleeps when idle for a connector; clients may time out on the first request.
- **Permissions**: keep client confirmation prompts on for tools that read files or change data.
- **Tests**: in-memory FastMCP `Client` tests for each tool, plus a manual Inspector pass before every release.

---

## 11. Common pitfalls and fixes

| Problem | Fix |
|---|---|
| Client can't start stdio server | Use absolute paths to the venv Python and the script; test the command in a terminal |
| Tool never gets called, agent uses shell instead | Improve docstring (when to use, args, returns); add a client rule to prefer MCP tools |
| Server works locally, not by URL | Switch to `transport="http"`, bind `0.0.0.0`, check path (`/mcp/`), firewall and TLS |
| Mounted in FastAPI but sessions fail | Pass `lifespan=mcp_app.lifespan` to FastAPI; combine lifespans if you already have one |
| Wrong URL after mounting | Verify actual endpoint in Inspector (mount path + app path) |
| OAuth login breaks in the browser | Remove app-wide CORS middleware on the OAuth-protected mount; use sub-apps |
| Garbled output / protocol errors on stdio | Something is printing to stdout; log to stderr |
| Code from older blog posts fails | Check decorator style (`@mcp.tool` vs `@mcp.tool()`), transport name (`http` vs `streamable-http`), and auth class names against the installed version |
| Tool takes too long | Offload to background jobs, return a job id and add a status tool; stream progress where supported |

---

## 12. Using managed servers instead of building

If the user only needs common apps (Gmail, Slack, Google Sheets, GitHub and similar), a managed provider can supply pre-built, pre-authenticated MCP tools behind one URL (Composio's hosted endpoint is one example, added to Claude Code with `claude mcp add --scope user --transport http composio https://connect.composio.dev/mcp`). Build your own server when you need custom logic, your own data, per-user billing or tight control. Remember that a hosted third-party server sees the data you send it; review its security and privacy terms.

---

## 13. Template for a custom verification-style connector (FastAPI + FastMCP)

Use this shape when the user wants a remote connector that checks AI answers, with user accounts and usage limits. Replace the placeholder helpers with real implementations.

```python
# app.py
from fastapi import FastAPI
from fastmcp import FastMCP
# from fastmcp.server.auth.providers.jwt import JWTVerifier   # or an OAuth provider

mcp = FastMCP("Answer Verifier")      # add auth=... before going live

@mcp.tool
async def verify_claim(claim: str, context: str = "") -> dict:
    """Check one factual claim (a number, date, name, quote or citation) against live sources.

    Use after an answer contains specific figures or citations.
    Returns: verdict (supported | outdated | contradicted | unverifiable),
    confidence (0-1), source_url, snippet, page_or_section, corrected_text.
    """
    # 1. identify user from the validated token, check plan limits
    # 2. run retrieval + verification (agents/tools)
    # 3. record usage, return structured result
    return {"verdict": "unverifiable", "confidence": 0.0,
            "source_url": None, "snippet": None,
            "page_or_section": None, "corrected_text": None}

@mcp.tool
async def verify_text(text: str) -> dict:
    """Extract every checkable claim from an AI-written answer and verify each one.
    Returns a list of per-claim results plus a corrected version of the text."""
    return {"claims": [], "corrected_text": text}

mcp_app = mcp.http_app()
api = FastAPI(lifespan=mcp_app.lifespan)

@api.get("/health")
def health():
    return {"status": "ok"}

api.mount("/mcp", mcp_app)
```
Design reminders for this kind of connector:
- A connector cannot watch every answer automatically; the model or user must call the tool, so write tool descriptions that say exactly when to call them.
- Same account system for the website login and the connector login, so usage appears in the user's dashboard.
- Return a verdict only with evidence (URL, snippet, page or section); otherwise return `unverifiable`.

---

## 14. Quick command reference

```bash
pip install fastmcp                                   # install
python server.py                                      # run (stdio or http, per run())
uvicorn server:app --host 0.0.0.0 --port 8000         # run ASGI app (http_app)
npx @modelcontextprotocol/inspector python server.py  # test in browser
claude mcp add --scope user --transport http NAME URL # add remote server in Claude Code
```

## 15. Further reading
- Composio guide: https://composio.dev/content/mcp-server-step-by-step-guide-to-building-from-scrtch
- FastMCP docs: https://gofastmcp.com (HTTP deployment, FastAPI integration, authentication)
- MCP Inspector guide: https://modelcontextprotocol.io/docs/tools/inspector
