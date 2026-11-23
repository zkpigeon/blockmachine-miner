# Blockmachine Miner

- [How it works](#how-it-works)
- [How you are paid](#how-you-are-paid)
- [How routing works](#how-routing-works)
- [Getting started](#getting-started)
- [Pricing](#pricing)
- [TLS options](#tls-options)
- [Manual setup](#manual-setup-without-install-script)
- [Architecture](#architecture)
- [Secret rotation](#secret-rotation-zero-downtime)
- [Configuration](#configuration)
- [Day-to-day operations](#day-to-day-operations)
- [CLI reference](#cli-reference)
- [Troubleshooting](#troubleshooting)

## How it works

```
Customer → Gateway → Your Node
                ↓
         Logs & Verification
                ↓
         Validators score you
                ↓
         Emissions paid per CU served
```

1. You run your own node for your chosen chain, fronted by our nginx gateway that authenticates requests from the Blockmachine network
2. The protocol gateway routes customer RPC requests among eligible nodes by their live routing score (see [How routing works](#how-routing-works))
3. Validators read gateway logs, verify correctness, and submit weights on-chain each epoch (~72 minutes)
4. Each chain's share of the miner pool goes to its busiest eligible nodes, split by CU served (see [How you are paid](#how-you-are-paid))

## How you are paid

Miners receive 41% of subnet 19 alpha emissions each epoch (7,200 blocks, about 24 hours).
Under Bittensor's emission split, validators receive 41% and the subnet owner 18%. Customer
payments are a separate flow.

- The miner pool is divided equally across the chains currently included in scoring.
- On each chain, **90%** goes to the **five eligible UIDs that served the most CU on archive
  requests** in the epoch, shared in proportion to that CU. A UID outside the top five gets no
  part of this portion.
- The other **10%** goes to the **ten UIDs eligible for the full-node tier that served the most
  CU on non-archive requests**, shared in proportion to that CU.
- A UID that is not eligible for a tier, or that served no CU in that tier's requests, receives
  no share of it.
- Validators turn each UID's dollar target into allocation weight using payout CU valued at
  the bid. The bid changes how many payout CU represent that target; it does not change the
  target's dollar value. Weights are shares of the miner pool, so a UID receives its share of
  the 41%, not a guaranteed dollar amount.

Eligibility lets a node take part. It does not guarantee traffic or income.

## How routing works

Among eligible nodes on a chain, the gateway routes requests by each node's **live routing
score**. A higher score makes a node more likely to receive requests, and so to serve more CU.
It does not guarantee traffic or override eligibility.

```
score = S × R^1.5 × L × Lr × P × T
```

- **S, success rate:** falls as errors rise, reaching its 5% floor at 4.75% errors.
- **R, reliability:** a day counts as good when at least 95% of its requests succeed. Only the
  last three days count; R reaches full value after three good days.
- **L, latency:** the rolling-hour p95. Full marks at or below 20 ms for archive nodes and
  1 ms for full nodes, zero at 1,000 ms. In between,
  `L = 1 − ((p95 − minimum) ÷ (1,000 ms − minimum))^0.3`. If the current hour has fewer than
  100 requests, the last hour with enough requests is used.
- **Lr, 15-second latency:** the same curve applied to the p95 of replies from the last 15
  seconds, so a sudden slowdown lowers routing within seconds. Replies are capped at
  1,000 ms, and a request still unanswered after one second counts as 1,000 ms. With fewer
  than 20 replies in the window, Lr stays at 1. Lr changes a node's routing share, and so how
  much CU it serves; it does not change the payout formula or eligibility.
- **P, price:** the peer-group median bid divided by your bid, capped at 3; a zero bid scores
  zero. The accepted bid is currently fixed at $0.50 per million CU, so P does not
  distinguish nodes.
- **T, slow responses:** the rolling-hour p99 compared with the higher of the chain's median
  p99 and 100 ms. At or below that baseline T is 1; twice the baseline gives 0.5, with a 5%
  floor.

Your live score, its factors, your eligibility and payout estimates are public on the
[miner performance page](https://blockmachine.io/miners). The full explanation is on the
[incentive mechanism page](https://blockmachine.io/incentive-mechanism).

## Getting started

**You bring the node.** Provisioning, syncing, disk sizing and snapshots are your
responsibility — we provide the gateway that fronts your node and the CLI that registers and
manages it. Your node must meet the eligibility requirements for its chain and declared type.

### Install the Blockmachine CLI

The CLI requires Python 3.10+ and can run anywhere — your laptop, a management server, or on the miner node itself. It's the control panel for registering nodes, managing secrets, and setting prices across your fleet without SSH-ing into each machine.

```bash
pip install blockmachine
```

### Testnet vs Mainnet

The install script asks whether you're running on testnet or mainnet. For testnet, all `bm` CLI commands require the `--testnet` flag:

```bash
bm --testnet miner login
bm --testnet miner add --endpoint wss://... --alias my-node --secret '...' --price 0.01
```

For mainnet (the default), use `bm` without the flag. The install script prints the correct commands for whichever network you choose.

**Testnet requirement:** You need a Bittensor hotkey registered as a miner on **netuid 417** (the Blockmachine testnet subnet). Register your hotkey before running the install script:

```bash
btcli subnet register --netuid 417 --subtensor.network test
```

### Authenticate

```bash
bm miner login              # mainnet
bm --testnet miner login    # testnet
```

This uses a device authorization flow: the CLI displays a URL and code, then polls until you approve in a browser. The browser does not need to be on the same machine — you can run `bm miner login` on a headless server and open the URL on your phone or laptop. If a browser is available locally, it opens automatically.

### On your server

SSH into your server and run the install script:

```bash
bash <(curl -sSL https://blockmachine.io/miner/install.sh)
```

The script will:
- Install git and Docker if missing
- Clone this repository (or update it if re-running)
- Ask which chain your node serves
- Ask whether you have a domain name or are using an IP address
- Set up TLS (auto-renewing Let's Encrypt for domains, or self-signed for IPs)
- Generate a bearer token secret
- Start the gateway, pointed at your node's RPC port
- Print the registration commands to run from your local machine

At the end you'll see output like:

```
========================================
 Miner is running!
========================================

  Endpoint: wss://203.0.113.50
  Chain:    tao
  Alias:    tao-203-0-113-50
  Secret:   stored in /root/blockmachine-miner/.env

Now run these commands on your local machine:

  bm miner login                    # or: bm --testnet miner login
  bm miner add --endpoint wss://203.0.113.50 --alias tao-203-0-113-50 --secret '<secret from .env>' --price <usd-per-cu>
```

### Register the node

Using the CLI (wherever you installed it), register your node with the secret from the server's `.env` file (`SECRET_V1`):

```bash
bm miner add \
  --endpoint wss://203.0.113.50 \
  --alias my-node \
  --secret '<SECRET_V1 from your server .env>' \
  --price 0.01

# For testnet, prefix with --testnet:
bm --testnet miner add \
  --endpoint wss://203.0.113.50 \
  --alias my-node \
  --secret '<SECRET_V1 from your server .env>' \
  --price 0.01
```

Or run `bm miner add` with no flags for interactive prompts.

`bm miner add --region us-east` registers the node for the US East region (default `eu`). Each region's registration is separate, with its own node id, secret and eligibility. Pass `--region us-east` to `rm`, `update`, `secret ...` and `show` to act on the US East registration. US East is not serving traffic yet and does not earn yet; this will be announced.

**What happens during registration:**
- The CLI connects to the registry and creates your node entry
- For IP-based endpoints, the CLI fetches and pins your TLS certificate fingerprint (so the gateway can verify your identity via cert pinning)
- For domain endpoints, standard CA verification is used (no pinning needed)
- Your secret is hashed and stored — the gateway uses it to authenticate when routing requests to you
- Your price bid is recorded for the next epoch

### Verify and receive traffic

Once your node is synced and the gateway is up, the network starts routing traffic to you.
Verify everything is working:

```bash
bm miner test <alias>              # Test TLS, health, and authenticated RPC
bm miner show                      # Check status and last seen timestamp
```

`bm miner test` runs three checks: TLS handshake on port 443, health endpoint on port 80, and an authenticated `system_health` RPC call. You can also test before registering with `bm miner test --endpoint <url> --secret '<secret>'`.

Once traffic is flowing, check your node's performance:

```bash
bm miner metrics [alias]           # Quality score, latency, success rate
```

### Prometheus metrics

Each miner exposes authenticated Prometheus metrics through the same HTTPS gateway:

```bash
curl -fsS \
  -H "Authorization: Bearer <SECRET_V1 from your server .env>" \
  https://203.0.113.50/metrics
```

Prometheus scrape example:

```yaml
scrape_configs:
  - job_name: blockmachine-miners
    metrics_path: /metrics
    scheme: https
    authorization:
      type: Bearer
      credentials: <SECRET_V1 from your server .env>
    static_configs:
      - targets:
          - 203.0.113.50
```

Metrics are operator telemetry for visibility and alerting. They are authenticated and useful for debugging sync, peer, disk, TLS, and version rollout issues, but they are not proof that a miner is honestly serving work.

The endpoint includes Blockmachine-curated health metrics, host CPU/memory/load, TLS certificate expiry, and the live deployed git SHA, and appends your chain client's native Prometheus output where the gateway can reach it.

## Pricing

You set a price in USD per Compute Unit (CU). A CU represents the normalized computational cost of serving a specific RPC method. Different methods cost different amounts of CU (a simple balance query costs less than a transaction trace).

Price is one factor in the routing score (see [How routing works](#how-routing-works)). The accepted bid is currently fixed at $0.50 per million CU, so price does not currently distinguish nodes. Only successful responses (HTTP 200 with a JSON-RPC `result`) count as CU served.

Set or update your price:

```bash
bm miner price set --price 0.01    # USD per CU, effective next epoch
bm miner price show                # Current price
bm miner price history             # Price history
```

## TLS options

### Auto-renewing Let's Encrypt (recommended for domains)

Select "Let's Encrypt" during install. A certbot container handles issuance and auto-renewal every 12 hours. Requires a domain name with a DNS A record pointing to your server, and port 80 reachable for the ACME challenge.

### Self-signed (default for IP-only)

Generated automatically during install. Valid for 10 years. The CLI pins the certificate fingerprint during `bm miner add` so the gateway can verify your identity. No renewal needed.

### Bring your own

Place `cert.pem` and `key.pem` in the `ssl/` directory before running the install script. Select "no" when prompted about Let's Encrypt.

## Manual setup (without install script)

If you prefer to set things up yourself:

```bash
git clone https://github.com/taostat/blockmachine-miner.git
cd blockmachine-miner

# Generate a secret
SECRET=$(openssl rand -base64 32 | tr -d '=/+' | head -c 43)

# Create .env
cp .env.example .env
# Edit .env: set SECRET_V1=$SECRET, set DOMAIN if using Let's Encrypt

# Generate self-signed cert (skip if using Let's Encrypt or BYO cert)
IP=$(curl -s ifconfig.me)
mkdir -p ssl
openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
  -keyout ssl/key.pem -out ssl/cert.pem \
  -subj "/CN=$IP" -addext "subjectAltName=IP:$IP"

# Start the gateway stack, pointed at your node's RPC port:
docker compose up -d

# For Let's Encrypt, add the TLS overlay:
# docker compose -f docker-compose.yml -f docker-compose.tls.yml up -d
```

Then register from your local machine:

```bash
bm miner login
bm miner add --endpoint wss://$IP --alias my-node --secret "$SECRET" --price 0.01

# For testnet:
bm --testnet miner login
bm --testnet miner add --endpoint wss://$IP --alias my-node --secret "$SECRET" --price 0.01
```

## Architecture

```
┌──────────────────────────────────────────────┐
│  Your Server                                 │
│                                              │
│  ┌──────────┐      ┌───────────────────┐     │
│  │  nginx   │ :443 │  your chain node  │     │
│  │ gateway  │─────▶│  (yours to run)   │     │
│  │          │ :9944│                   │     │
│  └──────────┘      └───────────────────┘     │
│    │ :80 (health + ACME)    │ :30333 (p2p)   │
│    │                        │                │
│    │ /metrics               │                │
│    ▼                        │                │
│  ┌──────────┐      ┌────────┴─────────┐      │
│  │ metrics  │─────▶│ node RPC + data  │      │
│  │          │─────▶│ native :9615     │      │
│  │          │─────▶│ host /proc       │      │
│  └──────────┘      └──────────────────┘      │
│                                              │
│  ┌──────────┐                                │
│  │ certbot  │ (optional)                     │
│  └──────────┘                                │
└──────────────────────────────────────────────┘
```

- **nginx gateway** — Terminates TLS, authenticates requests via bearer token, proxies WebSocket and HTTP RPC to the chain node. Supports dual secrets for zero-downtime rotation. The eth gateway template routes by the `Upgrade` header so a single 443 endpoint serves both JSON-RPC and `eth_subscribe`.
- **chain node** — yours: any accepted client for your chain, meeting the eligibility requirements for its declared type.
- **metrics** — Exposes `/metrics` internally; nginx publishes it at `https://<endpoint>/metrics` with the same bearer auth as RPC.
- **certbot** — Optional. Auto-renews Let's Encrypt certificates. Only used with domain-based setups.

## Secret rotation (zero downtime)

Rotate your bearer token without dropping any traffic:

1. **Set the new secret as `next` in the registry:**
   ```bash
   bm miner secret set --secret '<new-secret>'
   ```

2. **Add the new secret to your server and restart the gateway:**
   ```bash
   # Edit .env: set SECRET_V2=<new-secret>
   docker compose up -d gateway
   ```
   The gateway now accepts both the old and new secret.

3. **Promote the new secret to `active`:**
   ```bash
   bm miner secret promote
   ```
   The gateway now sends requests using the new secret.

4. **Remove the old secret from your server:**
   ```bash
   # Edit .env: move SECRET_V2 value to SECRET_V1, clear SECRET_V2
   docker compose up -d gateway
   ```

## Configuration

Environment variables in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_V1` | (required) | Primary bearer token |
| `SECRET_V2` | (empty) | Secondary token for zero-downtime rotation |
| `DOMAIN` | (empty) | Domain for Let's Encrypt auto-renewal |
| `CHAIN` | `tao` | Chain selection |
| `METRICS_PORT` | `9100` | Internal metrics exporter port |
| `SSL_CERT_PATH` | `/etc/nginx/ssl/cert.pem` | TLS certificate path in container |
| `SSL_KEY_PATH` | `/etc/nginx/ssl/key.pem` | TLS key path in container |
| `BM_MINER_GIT_SHA` | `unknown` | Deployed repository commit exposed in metrics |
| `BM_MINER_GIT_BRANCH` | `unknown` | Deployed repository branch exposed in metrics |

Chain-specific:

| Variable | Default | Used by | Description |
|----------|---------|---------|-------------|
| `BACKEND_PORT` | `9944` | tao | Your node's RPC port |
| `BACKEND_HTTP_PORT` | `8545` | EVM chains | Your node's HTTP JSON-RPC port |
| `BACKEND_WS_PORT` | `8546` | EVM chains | Your node's WebSocket port |

## Day-to-day operations

### Monitoring

```bash
bm miner show                      # Node status, endpoint, last seen
bm miner ls                        # List all your nodes
bm miner metrics [alias]           # Quality score, latency, success rate
docker compose logs -f              # Container logs
curl -sf http://localhost/health    # Gateway health check
curl -fsS -H "Authorization: Bearer $SECRET_V1" https://<endpoint>/metrics
```

### Updating

Pull the latest gateway config and images, then restart:

```bash
cd /root/blockmachine-miner && git pull && docker compose pull && docker compose up -d
```

Or re-run the install script — it updates the repo automatically:

```bash
bash <(curl -sSL https://blockmachine.io/miner/install.sh)
```

### Stopping

```bash
docker compose down
```

## CLI reference

All commands below default to mainnet. Add `--testnet` after `bm` for testnet: `bm --testnet miner ...`

```bash
# Authentication
bm miner login                         # Authenticate with miner scopes
bm miner status                        # Check auth status
bm miner logout                        # Clear stored tokens

# Node management
bm miner add                           # Register a node (interactive)
bm miner use <alias>                   # Set active node for commands
bm miner ls                            # List all nodes
bm miner show [alias]                  # Show node details
bm miner update [alias] --endpoint ... # Change endpoint or alias
bm miner rm [alias]                    # Remove a node

# Secrets
bm miner secret set [alias]            # Set bearer token secret
bm miner secret show [alias]           # Show secret metadata
bm miner secret promote [alias]        # Promote next secret to active

# Testing & metrics
bm miner test <alias>                  # Test TLS, health, and auth RPC
bm miner test --endpoint <url> --secret '<secret>'  # Test before registering
bm miner metrics [alias]              # Quality score, latency, success rate

# Pricing
bm miner price set [alias] --price ... # Set price per compute unit
bm miner price show [alias]            # Show current price
bm miner price history [alias]         # Show price history

```

When `[alias]` is omitted, the active node (set via `bm miner use`) is used.

## Troubleshooting

**Port 80 or 443 in use:** Stop the process using the port (`sudo lsof -i :443`) and try again.

**Gateway unhealthy:** Your node may still be syncing — check your node's own logs.

**Authentication errors:** Run `bm miner login` to re-authenticate, then `bm miner secret show` to verify your secret is registered.

**Node not receiving traffic:** Check `bm miner show` — status should be `active`. If `pending`, the gateway hasn't connected yet (node may still be syncing). If `unreachable`, the gateway can't reach your endpoint — check firewall rules and that ports 443 is open.

**TLS errors (self-signed):** The gateway uses certificate pinning to verify your identity. If you regenerate your certificate, you need to re-register your node (`bm miner rm` then `bm miner add`) so the new fingerprint is captured.

**TLS errors (Let's Encrypt):** Check `docker compose logs certbot`. Ensure your domain's DNS A record points to your server and port 80 is reachable for the ACME challenge.

**Firewall setup:** If using `ufw`, allow the required ports:

```bash
sudo ufw allow 80/tcp && sudo ufw allow 443/tcp
```
