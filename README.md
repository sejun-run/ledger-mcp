# ledger

Requirements & decision ledger for AI-collaboration tasks. Records who said what,
what was decided and why, and what is still unverified. `report()` gives a
Q&A-ready summary.

Tools: `log`, `update`, `show`, `report`, `reset`.
State: JSON at `$LEDGER_PATH` (default `./ledger.json`, i.e. the workspace).

## Run

```sh
uvx --from git+https://github.com/sejun-run/ledger-mcp ledger-mcp   # stdio, ledger.json in cwd
ledger-mcp --http                                                       # streamable HTTP on :8000
```

## Client configs

Replace `/home/sejun/projects/ledger-mcp` with the actual checkout path.
Set `LEDGER_PATH` to a file inside the task workspace so the ledger ships with the submission.

### Codex CLI (`~/.codex/config.toml`)

```toml
[mcp_servers.ledger]
command = "uv"
args = ["run", "--directory", "/home/sejun/projects/ledger-mcp", "ledger-mcp"]
env = { LEDGER_PATH = "./ledger.json" }
```

### Claude Code (`.mcp.json` in the task repo)

```json
{
  "mcpServers": {
    "ledger": {
      "command": "uv",
      "args": ["run", "--directory", "/home/sejun/projects/ledger-mcp", "ledger-mcp"],
      "env": { "LEDGER_PATH": "./ledger.json" }
    }
  }
}
```

### VS Code / Copilot (`.vscode/mcp.json`)

```json
{
  "servers": {
    "ledger": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--directory", "/home/sejun/projects/ledger-mcp", "ledger-mcp"],
      "env": { "LEDGER_PATH": "${workspaceFolder}/ledger.json" }
    }
  }
}
```

## Remote (streamable HTTP)

Use when Codex runs somewhere other than the machine holding this repo
(hosted sandbox, web environment). Start the server, expose it, point Codex at the URL.

```sh
PORT=8000 LEDGER_PATH=./ledger.json uv run ledger-mcp --http   # serves http://0.0.0.0:8000/mcp
cloudflared tunnel --url http://localhost:8000                 # prints a random https://*.trycloudflare.com URL
codex mcp add ledger --url https://<random>.trycloudflare.com/mcp
```

```toml
[mcp_servers.ledger]
url = "https://<random>.trycloudflare.com/mcp"
```

The ledger file then lives on this machine, not in the task workspace. Paste `report()` output
into the submission so the trail is still visible.

## Offline

`uv sync` once with network; afterwards `uv run` starts from the local `.venv`.

## Deployed on ampere

```sh
# on ampere (~/ledger-mcp)
docker build -t ledger .
docker run -d --name ledger --restart unless-stopped -p 8000:8000 \
  -v ledger-data:/data -e LEDGER_TOKEN=$(cat .ledger-token) ledger
```

Token is in `.ledger-token` (git-ignored). Codex entry `ledger-remote` in `~/.codex/config.toml`
Token is optional: omit `-e LEDGER_TOKEN` to run open (current ampere setup).

Blocker: OCI VCN security list only allows TCP 22. Add an ingress rule for TCP 8000 from 0.0.0.0/0,
then `codex mcp` enable `ledger-remote`. Fallback without opening a port: run a cloudflared quick
tunnel next to the container and use the printed URL instead.

## Domain: https://ledger.sejun.run/<PREFIX>/mcp

Gateway (amd-gateway) nginx terminates TLS with the existing `*.sejun.run` cert and proxies to
ampere over the private VCN (<AMPERE_PRIVATE_IP>:8000). Server block: `deploy/ledger.sejun.run.conf`,
appended to `/srv/snappycal-gateway/repo/server/llm_app_api/deploy/nginx/api.sejun.run.conf`.
DNS: Cloudflare A record `ledger` -> <GATEWAY_PUBLIC_IP>.
