# HRIS ↔ Module iframe Bridge Protocol

This document is the definitive reference for how the HRIS shell and any embedded
federated module communicate. Read this **before** touching any of:

- `apps/frontend/portal/src/components/ModuleFrame.tsx`
- `apps/frontend/portal/src/components/ModuleAlertBanner.tsx`
- `apps/frontend/portal/src/pages/modules/ModuleWorkspacePage.tsx`
- Any module's `index.js` / `main.ts` (the module-side bridge entry point)

---

## 1. Mental model

```
┌─ HRIS shell (hris.gi-kace.com.gh) ──────────────────────────────┐
│  Navbar  │  Sidebar  │  ModuleWorkspacePage                       │
│                      │  ┌─ ModuleFrame ──────────────────────┐   │
│                      │  │  <iframe src="srms.gi-kace.com.gh">│   │
│                      │  │    SRMS React app runs here         │   │
│                      │  │    (index.js bridge active)         │   │
│                      │  └────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

HRIS owns: navigation, authentication, tab title, search bar, notifications,
theme, scroll position, and the browser URL bar.

The **module** owns: all of its own feature UI (tables, modals, forms, workflows).
It communicates back to HRIS exclusively via `window.parent.postMessage`.

---

## 2. Security model

All `postMessage` calls are origin-restricted:

| Direction | Origin check enforced by |
|---|---|
| Module → HRIS | `ModuleFrame.tsx` — drops any message where `event.origin !== expectedOrigin` |
| HRIS → Module | `index.js` of each module — drops any message where `event.origin !== HRIS_ORIGIN` |

`HRIS_ORIGIN` is set via env var `REACT_APP_HRIS_ORIGIN` in each module. In
production this must be `https://hris.gi-kace.com.gh`. **Never use `'*'` as
the target origin for messages that carry tokens or user data.**

---

## 3. Full message catalogue

### 3.1 Module → HRIS (module sends, HRIS receives)

| `type` | Payload fields | Handled in | What HRIS does |
|---|---|---|---|
| `MODULE_READY` | `moduleId` | `ModuleFrame.tsx` | Calls `relayAuth()` to send the module's auth token |
| `MODULE_SESSION_EXPIRED` | `moduleId` | `ModuleFrame.tsx` | Re-fetches a fresh token and calls `relayAuth()` again silently |
| `MODULE_HEIGHT_CHANGE` | `height: number` | `ModuleFrame.tsx` | Sets iframe `height` style so HRIS scroll bar handles paging |
| `MODULE_ROUTE_CHANGE` | `path: string` | `ModuleFrame.tsx` | Writes `?module_path=…` to the browser URL for back/forward restore |
| `MODULE_TITLE_CHANGE` | `title: string` | `ModuleFrame.tsx` | Sets `document.title` to `"<title> — HRIS"` |
| `MODULE_SEARCH_CONFIG` | `placeholder: string, moduleId` | `ModuleFrame.tsx` → Navbar | Navbar renders a search bar with the given placeholder |
| `MODULE_USER_PROFILE` | `avatarUrl, displayName` | `ModuleFrame.tsx` → Navbar | Navbar avatar/name updated to real module user data |
| `MODULE_NAV_UPDATE` | `navItems` | `ModuleFrame.tsx` → Sidebar | Sidebar renders module sub-navigation items |
| `MODULE_SUMMARY_UPDATE` | `cards: SummaryCard[]` | `ModuleFrame.tsx` → ModuleWorkspacePage | Summary strip above iframe is populated |
| `MODULE_ALERT` | `message, level` | `ModuleFrame.tsx` → ModuleAlertBanner | Fixed-position toast shown at HRIS level |

### 3.2 HRIS → Module (HRIS sends, module receives)

| `type` | Payload fields | Sent from | What the module does |
|---|---|---|---|
| `HRIS_AUTH_RELAY` | `token, tenantSlug, sub, username, expiresAt` | `ModuleFrame.relayAuth()` | Module redirects to its SSO bridge endpoint to establish its own session |
| `HRIS_NAV_GO` | `path: string` | Sidebar nav click | Module calls `window.history.pushState` + fires `popstate` to navigate without reload |
| `HRIS_SEARCH_QUERY` | `query: string` | Navbar search form | Module invokes `window.__srmsSearch(query)` (or equivalent) to run the search |
| `TRIGGER_ACTION` | `actionId: string` | Sidebar action items | Module dispatches the action (e.g. opens a modal) — see §4 |
| `THEME_TOKENS` | `tokens: Record<string, string>` | `ModuleFrame` on theme change | Module sets CSS variables + toggles `.hris-dark-mode` body class |
| `HRIS_LOGOUT` | — | `ModuleFrame` on session end | Module clears its own localStorage and fires its logout API |

---

## 4. TRIGGER_ACTION — modal dispatch pattern

Because the HRIS sidebar replaces the module's own sidebar, the HRIS sidebar items
that would normally open modals (e.g. "Existing Roles Management") must still reach
the module's React state. The pattern:

```
HRIS Sidebar click
  → dispatchEvent('hris:module-trigger-action-srms', { actionId: 'existing-roles' })
  → ModuleFrame forwards as postMessage TRIGGER_ACTION
  → SRMS index.js receives it
  → SRMS Sidebar.js actionHandlers[actionId]() is called
  → React modal setState fires
```

`actionId` values currently registered in SRMS `Sidebar.js`:

| `actionId` | Effect |
|---|---|
| `profile:view` | Opens the HR profile editor modal |
| `profile:reset-password` | Opens the reset password modal |
| `existing-roles` | Opens the Existing Roles Management modal |
| _(add new ones in SRMS `Sidebar.js` actionHandlers)_ | |

**To add a new action from HRIS:** add the `actionId` to the HRIS `Sidebar.tsx`
sidebar item config. The bridge forwards it automatically — no changes needed in
`ModuleFrame.tsx`.

**To add a new action on the module side:** add `'my-action': () => myHandler()` to
the `actionHandlers` map in `SRMS Sidebar.js`. HRIS picks it up without any change.

---

## 5. Auth relay sequence (step-by-step)

```
1. HRIS shell loads ModuleFrame → renders <iframe src="...">
2. SRMS loads → index.js fires: window.parent.postMessage({ type: 'MODULE_READY' }, HRIS_ORIGIN)
3. ModuleFrame receives MODULE_READY → calls relayAuth():
     a. POST /hris/api/modules/srms/token  (HRIS Core API)
     b. Response: { token, tenantSlug, moduleOrigin, expiresAt }
     c. iframe.postMessage({ type: 'HRIS_AUTH_RELAY', token, tenantSlug, … }, srmsOrigin)
4. SRMS index.js receives HRIS_AUTH_RELAY → redirects to /api/sso/bridge?token=…
5. SRMS backend validates token → creates session → SRMS redirects back to /
6. SRMS sends MODULE_READY again (fresh page load after SSO bridge)
7. ModuleFrame sees MODULE_READY but authRelayedRef.current === true → skips (no loop)
```

**Session expiry (edge case):**
When a SRMS API call returns 401, `request.js` response interceptor sends
`MODULE_SESSION_EXPIRED`. ModuleFrame resets `authRelayedRef` and calls `relayAuth()`
again transparently — the user never sees a login prompt.

---

## 6. Dynamic height — no iframe scrollbar

```
SRMS content changes height (table page change, accordion, modal)
  → ResizeObserver in index.js fires reportHeight()
  → postMessage MODULE_HEIGHT_CHANGE { height: scrollHeight }
  → ModuleFrame sets: <iframe style="height: Npx">
  → HRIS's own overflow-y:auto on <main> provides the scrollbar
  → iframe has overflow:hidden (no inner scrollbar)
```

The key invariant: `html { overflow-y: scroll }` inside the iframe (set by embedded
CSS) makes `scrollHeight` accurate even though visual scrolling is suppressed.

---

## 7. Search bar relay

```
User types in HRIS Navbar search → hits Enter / clicks Search button
  → Navbar dispatches: window.dispatchEvent('hris:module-search-query-srms', { query })
  → ModuleFrame forwards: iframe.postMessage({ type: 'HRIS_SEARCH_QUERY', query }, origin)
  → SRMS index.js receives → calls window.__srmsSearch(query)
  → SearchBar.js: setQuery(query); if (query) setShowModal(true)
```

`window.__srmsSearch` is set by `SearchBar.js` on mount and deleted on unmount.
When the search bar is not mounted (user is on a page without it), the fallback
DOM manipulation path in index.js attempts to find the input and simulate a change.

**To add search relay to another module:** the module only needs to receive
`HRIS_SEARCH_QUERY` and call its own search handler. No changes to ModuleFrame.

---

## 8. Toast relay (MODULE_ALERT)

```
SRMS action triggers toast → react-toastify appends DOM node to .Toastify
  → MutationObserver in index.js fires
  → Reads toast text + severity class → postMessage MODULE_ALERT
  → ModuleFrame dispatches hris:module-alert custom event
  → ModuleAlertBanner renders fixed-position notification in HRIS shell
```

The `.Toastify` container is hidden via CSS (`display: none !important`) so users
never see a double notification. The MutationObserver is the only consumer.

---

## 9. Dark mode / theme sync

```
User clicks ☀/🌙 in HRIS Navbar
  → Navbar: setDarkMode(true/false)
  → useEffect → document.documentElement.classList.toggle('dark', darkMode)
  → window.dispatchEvent('hris:theme-change', { darkMode })
  → ModuleFrame receives → postMessage THEME_TOKENS { --hris-theme, --hris-bg, … }
  → SRMS index.js applyThemeTokens() → sets CSS variables on <html>
  → applyThemeTokens() also toggles document.body.classList('hris-dark-mode', isDark)
  → .hris-dark-mode CSS overrides (in embedded style block) recolor SRMS UI
```

---

## 10. Browser back / forward restore

When the user navigates within a module (e.g. clicks a row → detail page), SRMS
sends `MODULE_ROUTE_CHANGE { path }`. ModuleFrame writes:

```
window.history.replaceState(null, '', '/modules/srms/native?module_path=/gi-kace/employees/123')
```

When the user presses Back → HRIS's router navigates back to the workspace URL,
ModuleFrame mounts fresh, and on `relayAuth()` completion reads `?module_path` and
sends `HRIS_NAV_GO { path }` to the iframe with a 400ms delay (so SRMS finishes its
own auth init first). The user lands on the correct internal page.

---

## 11. Adding a new federated module

To integrate a new module (e.g. eAppraisal) into the bridge:

1. **Module side** (`index.js` / `main.ts`):
   - Copy the SRMS `index.js` bridge block pattern (top comment + message handler + embedded CSS).
   - Change `HRIS_ORIGIN` env var and `moduleId: 'eappraisal'` in postMessages.
   - Implement `window.__eappraisalSearch` (or equivalent) for search relay.
   - Add `applyThemeTokens` + `.hris-dark-mode` class toggle.
   - Start `MutationObserver` toast relay on `.Toastify` / module's own toast container.
   - Suppress tour guides: `if (window.parent !== window) return null` in each guide component.

2. **HRIS side** (no code changes needed in most cases):
   - Add `moduleId: 'eappraisal'` to `MODULE_LABELS` in `ModuleFrame.tsx` and `Navbar.tsx`.
   - Add `eappraisal: '/modules/appraisal'` to `MODULE_SUMMARY_PATH` in `Navbar.tsx`.
   - Create `ModuleWorkspacePage` route at `/modules/eappraisal/native`.
   - Add sidebar item that navigates there.
   - Set env var `VITE_MODULE_ORIGIN_EAPPRAISAL=https://eappraisal.gi-kace.com.gh`.

The `ModuleFrame` component handles all message routing generically by `moduleId` —
it does not need to know about any module-specific actions. New `TRIGGER_ACTION`
`actionId` values are purely data-driven from the Sidebar configuration.

---

## 12. Profile capability (MODULE_PROFILE_CAPABILITY)

**The design principle:** HRIS `/profile` is fully data-driven. It never
hard-codes which modules have a profile view or what fields they show. Each
module self-declares its capability on boot and renders its own profile UI
inside the tab iframe — HRIS only owns the chrome.

### Protocol (fully implemented)

```
Module → HRIS: postMessage {
  type: 'MODULE_PROFILE_CAPABILITY',
  moduleId: 'srms',
  label: 'Staff Profile',        // tab label on /profile
  profilePath: '/hris/profile',  // module route that renders profile-only UI
  actions: [
    { id: 'profile:view',           label: 'View & Edit Profile' },
    { id: 'profile:reset-password', label: 'Reset Password' },
  ]
}
```

`ModuleFrame` receives this and calls `registerCapability()` from
`ModuleCapabilitiesContext` — a session-persisted store keyed by `moduleId`.

### ProfileHubPage (`/profile`) flow

```
1. Fetch GET /modules/catalog → list of active modules for this tenant
2. Render a tab for each active module (label from catalog initially)
3. ModuleCapabilitiesContext updates → tab label/path refined from MODULE_PROFILE_CAPABILITY
4. User clicks a tab → ModuleFrame mounts at profilePath (lazy, stays mounted after)
5. Module renders its own profile editor inside the iframe — HRIS never touches the fields
```

### Adaptive behaviour

| Scenario | Result | HRIS code change? |
|---|---|---|
| New module added to catalog | Tab appears (pending until it sends capability) | None |
| Module sends MODULE_PROFILE_CAPABILITY | Tab label/path refined, green dot shown | None |
| Module redesigns profile UI | iframe shows new design automatically | None |
| Unknown future module X | Sends capability → tab appears | None |
| Module doesn't implement profile | Tab shows "Profile view not available" fallback | None |

### HRIS Identity section (always present, above module tabs)

The top section of `/profile` is HRIS-native and editable:
- **GET /account/profile** → reads user's Keycloak account (name, email, verified status)
- **PATCH /account/profile** → updates firstName, lastName, email in Keycloak
- **POST /account/password** → validates current password, then resets via Keycloak Admin API

Email and password changes propagate to all federated modules automatically because
they all authenticate via the same Keycloak realm.

### Files

| File | Role |
|---|---|
| `apps/frontend/portal/src/pages/ProfileHubPage.tsx` | `/profile` page — identity section + module tabs |
| `apps/frontend/portal/src/contexts/ModuleCapabilitiesContext.tsx` | Stores MODULE_PROFILE_CAPABILITY declarations |
| `apps/frontend/portal/src/api/accountClient.ts` | profile/password API calls |
| `apps/backend/hris-core-api/app/api/account.py` | Keycloak proxy endpoints |
| `<srms>/frontend/src/index.js` | Sends MODULE_PROFILE_CAPABILITY on bootstrap |

---

## 13. Files quick-reference

| File | Role |
|---|---|
| `apps/frontend/portal/src/components/ModuleFrame.tsx` | iFrame host — all HRIS-side bridge logic |
| `apps/frontend/portal/src/components/ModuleAlertBanner.tsx` | Fixed-position toast for module alerts |
| `apps/frontend/portal/src/components/Navbar.tsx` | Search bar, avatar click, theme toggle, back link |
| `apps/frontend/portal/src/components/Sidebar.tsx` | Nav items, user card, TRIGGER_ACTION dispatch |
| `apps/frontend/portal/src/pages/modules/ModuleWorkspacePage.tsx` | Summary strip + ModuleFrame mount |
| `apps/frontend/portal/src/hooks/useModuleToken.ts` | Fetches short-lived module token from HRIS Core API |
| `apps/frontend/portal/src/constants/moduleOrigins.ts` | Maps moduleId → env var origin URL |
| `<srms>/frontend/src/index.js` | SRMS bridge entry: auth relay, CSS injection, all postMessage handlers |
| `<srms>/frontend/src/components/request.js` | Axios instance — 401 interceptor sends MODULE_SESSION_EXPIRED |
| `<srms>/frontend/src/components/pages/SearchBar.js` | Sets `window.__srmsSearch` callback |
| `<srms>/frontend/src/components/pages/ProfileCard.js` | Sets `window.__srmsProfile` callbacks |
| `<srms>/frontend/src/components/pages/Sidebar.js` | TRIGGER_ACTION `actionHandlers` map |
| `<srms>/frontend/src/components/guide/DashboardTourGuide.js` | Returns null when embedded |
| `<srms>/frontend/src/components/guide/TourGuide.js` | Returns null when embedded |
