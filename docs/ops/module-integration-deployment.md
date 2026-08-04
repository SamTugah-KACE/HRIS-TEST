# Module Integration — Deployment Guide

Step-by-step instructions for deploying the HRIS + Module (SRMS) iframe integration
to any environment: local development, staging, or production.

---

## Prerequisites

| Requirement | Version / Notes |
|---|---|
| Docker + Docker Compose | v2.x |
| Node.js | 18+ (for local portal dev) |
| Python | 3.11+ (for HRIS Core API) |
| Git access | Both HRIS-Platform repo and SRMS repo |
| DNS or /etc/hosts | Both domains must resolve |

---

## Part 1 — Environment variables

### 1.1 HRIS Portal (`apps/frontend/portal/.env`)

```env
# The public origin of each federated module.
# ModuleFrame uses these to build iframe src and scope postMessage origins.
VITE_MODULE_ORIGIN_SRMS=https://srms.gi-kace.com.gh
VITE_MODULE_ORIGIN_EAPPRAISAL=https://eappraisal.gi-kace.com.gh
VITE_MODULE_ORIGIN_ELEAVE=https://eleave.gi-kace.com.gh

# HRIS Core API base URL (relative works if served from same origin via nginx)
VITE_API_BASE_URL=/hris/api
```

For local development:

```env
VITE_MODULE_ORIGIN_SRMS=http://localhost:3000
VITE_API_BASE_URL=http://localhost:8000
```

### 1.2 HRIS Core API (`apps/backend/hris-core-api/.env`)

```env
# Module handoff signing secret — must match what each module backend expects.
MODULE_HANDOFF_SECRET=<generate with: python -c "import secrets; print(secrets.token_urlsafe(32))">

# Keycloak settings
KEYCLOAK_URL=https://auth.gi-kace.com.gh
KEYCLOAK_REALM=hris
KEYCLOAK_CLIENT_ID=hris-core-api
KEYCLOAK_CLIENT_SECRET=<from Keycloak admin console>

# Tenant Registry
TENANT_REGISTRY_URL=http://tenant-registry:8001

# Auth mode — MUST be 'keycloak' in production
AUTH_MODE=keycloak
USE_STUB_DATA=false
```

### 1.3 SRMS Frontend (`<srms>/frontend/.env`)

```env
# The HRIS shell origin — index.js strictly validates all incoming postMessages
# against this value. Wrong value = all bridge messages silently dropped.
REACT_APP_HRIS_ORIGIN=https://hris.gi-kace.com.gh

# SRMS API base (relative is fine when served on same host)
REACT_APP_API_URL=/api

# Set to 'production' for console.log suppression in embedded mode
NODE_ENV=production
```

For local development (HRIS on port 5173, SRMS on port 3000):

```env
REACT_APP_HRIS_ORIGIN=http://localhost:5173
REACT_APP_API_URL=http://localhost:8000/api
```

---

## Part 2 — Local development (fastest path)

### Step 1 — Start SRMS (standalone, any terminal)

```bash
cd <path-to-SRMS>/frontend
npm install
npm start          # runs on http://localhost:3000
```

```bash
cd <path-to-SRMS>/Backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Step 2 — Start HRIS stack

```bash
cd <path-to-HRIS-Platform>
python scripts/start_local_stack.py \
  --registry-port 8001 \
  --core-port 8000 \
  --portal-port 5173 \
  --timeout 300
```

Or manually:

```bash
# Terminal 1 — Tenant Registry
cd apps/backend/tenant-registry-service
uvicorn app.main:app --reload --port 8001

# Terminal 2 — HRIS Core API
cd apps/backend/hris-core-api
uvicorn app.main:app --reload --port 8000

# Terminal 3 — Portal
cd apps/frontend/portal
npm run dev        # http://localhost:5173
```

### Step 3 — Verify the bridge

1. Open `http://localhost:5173` → log in.
2. Navigate to Staff Records → you should see SRMS inside the iframe.
3. Open DevTools → Console: you should NOT see SRMS's verbose logs (suppressed in production mode).
4. Open DevTools → Network: verify no cross-origin errors.
5. Try the search bar — type a name, press Enter → SRMS filters in-place.
6. Click your avatar in the top-right → SRMS profile editor modal opens inside the iframe.
7. Toggle dark mode (☀/🌙) → SRMS table and cards darken.
8. Navigate to a specific employee → copy the URL → paste in a new tab → you land on that employee.

---

## Part 3 — Docker Compose deployment

### Step 1 — Build images

```bash
# HRIS portal
docker build -t hris-portal:latest apps/frontend/portal/

# HRIS Core API
docker build -t hris-core-api:latest apps/backend/hris-core-api/

# SRMS frontend (in SRMS repo)
docker build -t srms-frontend:latest <path-to-SRMS>/frontend/

# SRMS backend (in SRMS repo)
docker build -t srms-backend:latest <path-to-SRMS>/Backend/
```

### Step 2 — Configure `docker-compose.yml`

Key services and their env vars:

```yaml
services:
  hris-portal:
    image: hris-portal:latest
    environment:
      VITE_MODULE_ORIGIN_SRMS: "https://srms.gi-kace.com.gh"
      VITE_API_BASE_URL: "/hris/api"

  hris-core-api:
    image: hris-core-api:latest
    environment:
      AUTH_MODE: "keycloak"
      USE_STUB_DATA: "false"
      MODULE_HANDOFF_SECRET: "${MODULE_HANDOFF_SECRET}"
      KEYCLOAK_URL: "https://auth.gi-kace.com.gh"
      TENANT_REGISTRY_URL: "http://tenant-registry:8001"

  srms-frontend:
    image: srms-frontend:latest
    environment:
      REACT_APP_HRIS_ORIGIN: "https://hris.gi-kace.com.gh"
      NODE_ENV: "production"

  nginx:
    image: nginx:alpine
    volumes:
      - ./infra/nginx/hris-platform.conf:/etc/nginx/conf.d/default.conf
    ports:
      - "80:80"
      - "443:443"
```

### Step 3 — nginx configuration

The nginx config routes sub-paths to each module. The key headers for iframe embedding:

```nginx
# Inside the /srms/ location block:
add_header X-Frame-Options "SAMEORIGIN" always;
add_header Content-Security-Policy "frame-ancestors 'self' https://hris.gi-kace.com.gh" always;

# Cookie sharing (same parent domain):
# Ensure SRMS sets cookies with: Domain=.gi-kace.com.gh; SameSite=None; Secure
```

Full nginx config is at `infra/nginx/hris-platform.conf`.

### Step 4 — Start the stack

```bash
docker compose up -d

# Check all services are healthy:
docker compose ps

# Tail logs:
docker compose logs -f hris-core-api
docker compose logs -f srms-frontend
```

---

## Part 4 — Production (VM / bare metal)

### Step 1 — Provision infrastructure

Minimum VMs (can be consolidated on a single large VM for small orgs):

| VM | Services | Minimum specs |
|---|---|---|
| `hris-vm` | HRIS portal, HRIS Core API, Tenant Registry, nginx | 4 vCPU, 8 GB RAM |
| `srms-vm` | SRMS frontend, SRMS backend, SRMS PostgreSQL | 2 vCPU, 4 GB RAM |
| `auth-vm` | Keycloak, Keycloak PostgreSQL | 2 vCPU, 4 GB RAM |

### Step 2 — TLS certificates

Use Certbot (Let's Encrypt) or your org's CA:

```bash
certbot certonly --nginx -d hris.gi-kace.com.gh
certbot certonly --nginx -d srms.gi-kace.com.gh
certbot certonly --nginx -d auth.gi-kace.com.gh
```

### Step 3 — Deploy SRMS frontend build

```bash
# In SRMS frontend repo:
REACT_APP_HRIS_ORIGIN=https://hris.gi-kace.com.gh \
REACT_APP_API_URL=/api \
NODE_ENV=production \
npm run build

# Copy build output to SRMS nginx www root:
rsync -avz build/ srms-vm:/var/www/srms/
```

**Important:** Every time `index.js` (the bridge entry) changes, rebuild and redeploy
SRMS frontend. The HRIS portal does not need rebuilding for SRMS-side-only changes.

### Step 4 — Deploy HRIS portal build

```bash
cd apps/frontend/portal
VITE_MODULE_ORIGIN_SRMS=https://srms.gi-kace.com.gh \
VITE_API_BASE_URL=/hris/api \
npm run build

rsync -avz dist/ hris-vm:/var/www/hris/
```

### Step 5 — Systemd service for HRIS Core API

```ini
# /etc/systemd/system/hris-core-api.service
[Unit]
Description=HRIS Core API
After=network.target

[Service]
User=hris
WorkingDirectory=/opt/hris/apps/backend/hris-core-api
EnvironmentFile=/opt/hris/.env.production
ExecStart=/opt/hris/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
systemctl enable hris-core-api
systemctl start hris-core-api
```

### Step 6 — Health checks

```bash
# HRIS Core API
curl https://hris.gi-kace.com.gh/hris/api/health

# SRMS backend
curl https://srms.gi-kace.com.gh/api/health

# Tenant Registry
curl https://hris.gi-kace.com.gh/registry/api/health

# Keycloak
curl https://auth.gi-kace.com.gh/health/ready
```

---

## Part 5 — Post-deployment verification checklist

Run these manually after every production deployment:

- [ ] Log in at `https://hris.gi-kace.com.gh` → redirects to Keycloak → returns to HRIS dashboard
- [ ] Staff Records link → SRMS loads inside iframe, no login prompt, shows correct user
- [ ] SRMS sidebar / header NOT visible (hidden by embedded CSS)
- [ ] HRIS Navbar search bar appears (MODULE_SEARCH_CONFIG received)
- [ ] Type a search → SRMS filters results in-place
- [ ] Toggle dark mode → SRMS UI darkens (MODULE_THEME_TOKENS applied)
- [ ] Perform an action that triggers a toast in SRMS → ModuleAlertBanner shows in HRIS top-right
- [ ] Navigate to a staff member detail page → copy URL → open in new tab → lands on same page
- [ ] Click your avatar (top-right) → SRMS profile editor opens inside iframe
- [ ] Log out → HRIS clears session, SRMS localStorage cleared (HRIS_LOGOUT received)
- [ ] Wait for module token to expire (default: 15 min) → SRMS automatically re-authenticates (MODULE_SESSION_EXPIRED flow)

---

## Part 6 — Troubleshooting

### iframe shows blank / error state

1. Check browser Console for `Refused to frame` CSP errors.
   - Fix: add HRIS origin to SRMS nginx `Content-Security-Policy: frame-ancestors`.
2. Check `X-Frame-Options` header from SRMS: must be `SAMEORIGIN` or absent.
3. Verify `REACT_APP_HRIS_ORIGIN` in SRMS matches exactly (including protocol, no trailing slash).

### Search bar not working

1. Open DevTools in the HRIS tab → Console → check for `[SRMS] HRIS_SEARCH_QUERY received`.
2. If not received: check `expectedOriginRef` in ModuleFrame — it must match SRMS's actual origin.
3. If received but no results: SRMS's `window.__srmsSearch` may not be mounted. SearchBar must
   be visible on the current SRMS route. Pages without SearchBar fall back to DOM manipulation.

### Toast notifications not appearing

1. Verify `.Toastify` container exists in SRMS DOM (react-toastify must be mounted).
2. Check MutationObserver is attached: `startToastRelay()` retries every 600ms for up to ~5s.
   If SRMS takes longer to mount, increase the retry timeout in SRMS `index.js`.
3. Verify `MODULE_ALERT` is received in ModuleFrame: add a temporary `console.log` in
   the `MODULE_ALERT` case of the switch statement.

### Module session keeps expiring

- Default module token TTL is set in HRIS Core API (`MODULE_TOKEN_TTL_MINUTES`).
  Increase it if users report frequent invisible re-auths causing brief UI freezes.
- Check `request.js` response interceptor is sending `MODULE_SESSION_EXPIRED` (line ~315).
  If it's not, the 401 silently fails and the user sees stale data.

### Dark mode not applying to module

1. `THEME_TOKENS` must be received after dark mode toggle (check in DevTools → Messages tab
   on the iframe).
2. `applyThemeTokens()` in SRMS `index.js` must toggle `.hris-dark-mode` on `document.body`.
3. The `.hris-dark-mode` CSS overrides in the embedded style block must target the right selectors.
   Use DevTools to inspect the SRMS iframe's DOM and add new selectors as needed.

---

## Part 7 — Rollback procedure

### HRIS portal only

```bash
# Re-deploy previous build from dist backup
rsync -avz /var/www/hris-backup-YYYYMMDD/ hris-vm:/var/www/hris/
```

### SRMS frontend only (bridge changes)

```bash
# Re-deploy previous SRMS build
rsync -avz /var/www/srms-backup-YYYYMMDD/ srms-vm:/var/www/srms/
# No HRIS rebuild needed — the bridge is entirely in SRMS index.js
```

### Both (coordinated)

Follow the HRIS → SRMS order to avoid a window where one side has the new protocol
but the other doesn't. Both sides are backward-compatible within the same major version.
