# HRIS Module Integration Guide — Any Framework

This guide is written for the team responsible for a **federated module** that
needs to be embedded in the HRIS shell. You do not need to know the HRIS
codebase to follow it. Everything you need to implement lives entirely in
**your own application**.

Applies to: any stack — React, Angular, Vue, Svelte, Next.js, Nuxt,
Laravel + Blade/Alpine, Django + HTMX, vanilla JS/TS, or any other framework.

---

## 0. What the HRIS shell does for you

When HRIS embeds your app:

- It handles login (Keycloak SSO) and gives you a signed token automatically
- It renders the sidebar navigation, top navbar, and notifications
- It manages the browser scroll position and URL bar
- It shows your toasts / alerts natively at the shell level
- It relays theme (dark/light), search queries, and profile requests
- It provides a consistent confirmation dialog for destructive actions

**You only need to respond to events via `window.parent.postMessage`.**

---

## 1. The integration contract at a glance

```
Your app boots
  → send MODULE_READY                     (I'm here, please authenticate me)

HRIS responds
  → HRIS_AUTH_RELAY { token, tenantSlug } (here is your session token)

Your app receives token
  → redirect to your SSO bridge endpoint  (establish your own session)

SSO bridge redirects back to your app
  → send MODULE_READY again               (I'm ready, HRIS ignores duplicate)

While running
  → send MODULE_HEIGHT_CHANGE             (keeps HRIS iframe sized to your content)
  → send MODULE_ROUTE_CHANGE              (keeps HRIS URL bar in sync)
  → send MODULE_SEARCH_CONFIG             (HRIS Navbar shows your search bar)
  → send MODULE_ALERT                     (HRIS shows your toasts natively)
  → send MODULE_PROFILE_CAPABILITY        (HRIS /profile shows a tab for you)
  → receive HRIS_SEARCH_QUERY             (run your search with this string)
  → receive HRIS_NAV_GO                   (navigate your SPA to this path)
  → receive TRIGGER_ACTION                (open a modal by actionId)
  → receive THEME_TOKENS                  (apply dark/light mode CSS vars)
  → receive HRIS_LOGOUT                   (clear your session)
```

---

## 2. Security requirements (non-negotiable)

```
REACT_APP_HRIS_ORIGIN = https://hris.gi-kace.com.gh   (set in your env)
```

**Always validate the sender before processing any message:**

```javascript
window.addEventListener('message', (event) => {
  if (event.origin !== HRIS_ORIGIN) return; // drop everything else
  // … handle event.data
});
```

**Always set a target origin when posting to HRIS:**

```javascript
window.parent.postMessage({ type: 'MODULE_READY' }, HRIS_ORIGIN);
// Never use '*' for messages that carry tokens or sensitive data.
```

---

## 3. Step-by-step implementation

### Step 1 — Detect embedded context

```javascript
const inHris = window.parent !== window;
```

All bridge code runs **only when `inHris === true`**. Your standalone app is
completely unaffected.

---

### Step 2 — Send MODULE_READY and wait for auth

Send `MODULE_READY` as early as possible — before your app's full render if
you can. HRIS will respond with `HRIS_AUTH_RELAY` within ~2 seconds.

```javascript
// Framework-agnostic entry point (index.js / main.ts / app.js)
const HRIS_ORIGIN = process.env.YOUR_ENV_VAR_FOR_HRIS_ORIGIN || 'https://hris.gi-kace.com.gh';
const inHris = window.parent !== window;

if (inHris) {
  window.addEventListener('message', handleHrisMessage);
  window.parent.postMessage({ type: 'MODULE_READY', moduleId: 'your-module-id' }, HRIS_ORIGIN);
}

function handleHrisMessage(event) {
  if (event.origin !== HRIS_ORIGIN) return;
  const { type, token, tenantSlug, path, query, tokens } = event.data || {};

  switch (type) {
    case 'HRIS_AUTH_RELAY':
      // Store tenant context and redirect to your SSO bridge.
      localStorage.setItem('hrisTenantSlug', tenantSlug || '');
      window.location.href = `/api/sso/bridge?token=${encodeURIComponent(token)}&tenant=${encodeURIComponent(tenantSlug || '')}`;
      break;

    case 'HRIS_NAV_GO':
      // Navigate your SPA to `path` without a full reload.
      navigateTo(path); // see §3.5
      break;

    case 'HRIS_SEARCH_QUERY':
      // Run your search feature with this query string.
      runSearch(query || ''); // see §3.6
      break;

    case 'TRIGGER_ACTION':
      // Open a modal or run a feature by ID. see §3.7
      dispatchAction(event.data.actionId);
      break;

    case 'THEME_TOKENS':
      // Apply dark/light mode CSS variables. see §3.8
      applyThemeTokens(tokens || {});
      break;

    case 'HRIS_LOGOUT':
      // Clear your local session.
      localStorage.removeItem('authToken');
      fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin' }).catch(() => {});
      break;

    case 'HRIS_CONFIRM_RESULT':
      // User confirmed or cancelled a destructive action. see §3.9
      handleConfirmResult(event.data.actionId, event.data.confirmed);
      break;
  }
}
```

---

### Step 3 — Your SSO bridge endpoint

HRIS posts a short-lived signed JWT to your bridge. Your backend validates it
and creates a native session for the user. Typical pattern:

```
GET/POST /api/sso/bridge?token=<hris_token>&tenant=<slug>
  → validate token signature (shared secret or HRIS public key)
  → extract sub, username, tenant_id
  → create or update local user record
  → issue your native session cookie or token
  → redirect back to / (or the requested path)
```

The bridge is called once per HRIS auth relay. After the redirect, your app
sends `MODULE_READY` again — HRIS ignores it (duplicate guard is in place).

**SRMS reference:** `Backend/app/api/auth.py` → `/api/sso/bridge` endpoint.

---

### Step 4 — Handle 401 → request token refresh

When your API returns a 401, send `MODULE_SESSION_EXPIRED`. HRIS will
silently fetch a new token and relay it via `HRIS_AUTH_RELAY`, restarting
the bridge without any user-visible prompt.

```javascript
// In your HTTP client interceptor (axios, fetch wrapper, etc.)
onResponseError(error) {
  if (error.status === 401 && inHris) {
    window.parent.postMessage({ type: 'MODULE_SESSION_EXPIRED', moduleId: 'your-module-id' }, HRIS_ORIGIN);
  }
  return Promise.reject(error);
}
```

---

### Step 5 — Report content height (no iframe scrollbar)

HRIS sizes the iframe to exactly fit your content. Use a `ResizeObserver`:

```javascript
let lastHeight = 0;
const reportHeight = () => {
  const h = Math.max(document.documentElement.scrollHeight, document.body.scrollHeight);
  if (h > 0 && Math.abs(h - lastHeight) > 4) {
    lastHeight = h;
    window.parent.postMessage({ type: 'MODULE_HEIGHT_CHANGE', height: h }, HRIS_ORIGIN);
  }
};
new ResizeObserver(reportHeight).observe(document.body);

// Required: suppress the iframe's own scrollbar while keeping scrollHeight accurate.
document.documentElement.style.cssText += `
  overflow-y: scroll !important;
  scrollbar-width: none !important;
`;
const style = document.createElement('style');
style.textContent = 'html::-webkit-scrollbar { display: none !important; }';
document.head.appendChild(style);
```

---

### Step 5b — Sync browser URL (MODULE_ROUTE_CHANGE)

When your router changes the current page, notify HRIS so the browser's
address bar reflects the module-internal path (used for browser back/forward):

```javascript
// React Router
useEffect(() => {
  if (!inHris) return;
  window.parent.postMessage({ type: 'MODULE_ROUTE_CHANGE', path: location.pathname }, HRIS_ORIGIN);
}, [location.pathname]);

// Angular Router
this.router.events.pipe(filter(e => e instanceof NavigationEnd)).subscribe(e => {
  if (!inHris) return;
  window.parent.postMessage({ type: 'MODULE_ROUTE_CHANGE', path: e.urlAfterRedirects }, HRIS_ORIGIN);
});

// Vue Router
router.afterEach((to) => {
  if (!inHris) return;
  window.parent.postMessage({ type: 'MODULE_ROUTE_CHANGE', path: to.fullPath }, HRIS_ORIGIN);
});

// Vanilla / HTMX — listen for popstate / History API calls
window.addEventListener('popstate', () => {
  if (!inHris) return;
  window.parent.postMessage({ type: 'MODULE_ROUTE_CHANGE', path: location.pathname }, HRIS_ORIGIN);
});
```

---

### Step 5c — Sync tab title (MODULE_TITLE_CHANGE)

```javascript
// Call this whenever your page title changes
function syncTitle(title) {
  if (!inHris) return;
  window.parent.postMessage({ type: 'MODULE_TITLE_CHANGE', title }, HRIS_ORIGIN);
}
```

---

### Step 6 — Register a search bar (MODULE_SEARCH_CONFIG)

After your app mounts, tell HRIS to show a search bar in its Navbar:

```javascript
window.parent.postMessage({
  type: 'MODULE_SEARCH_CONFIG',
  moduleId: 'your-module-id',
  placeholder: 'Search employees by name, ID…',
}, HRIS_ORIGIN);
```

Then handle `HRIS_SEARCH_QUERY` from the message handler (see §3 above):

```javascript
function runSearch(query) {
  // React: call setState on your search component
  if (window.__yourModuleSearch) {
    window.__yourModuleSearch(query);
    return;
  }
  // Fallback: DOM manipulation for pages without the search component mounted.
  const input = document.querySelector('[data-hris-search-input]');
  if (input) {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
    setter?.call(input, query);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  }
}
```

**Best practice:** in your search component, set a global callback on mount:

```javascript
// React
useEffect(() => {
  window.__yourModuleSearch = (q) => { setQuery(q); if (q) openResults(); };
  return () => { delete window.__yourModuleSearch; };
}, []);

// Angular / Vue: same pattern in ngOnInit / onMounted lifecycle hook
```

---

### Step 7 — Handle TRIGGER_ACTION (sidebar → modal dispatch)

HRIS sidebar items can trigger modals or features inside your app by `actionId`:

```javascript
const ACTION_HANDLERS = {
  'profile:view':           () => openProfileModal(),
  'profile:reset-password': () => openPasswordModal(),
  'existing-roles':         () => openRolesModal(),
  // Add new actions here — HRIS picks them up automatically.
};

function dispatchAction(actionId) {
  const handler = ACTION_HANDLERS[actionId];
  if (handler) handler();
}
```

Declare your available actions in `MODULE_PROFILE_CAPABILITY` (see §9) so HRIS
knows which ones exist for the avatar-click shortcut.

---

### Step 8 — Dark/light theme (THEME_TOKENS)

```javascript
function applyThemeTokens(tokens) {
  // 1. Set CSS variables on <html> for any component using them.
  Object.entries(tokens).forEach(([key, value]) => {
    document.documentElement.style.setProperty(key, value);
  });

  // 2. Toggle a body class so your existing CSS can also react.
  const isDark = tokens['--hris-theme'] === 'dark';
  document.body.classList.toggle('your-dark-class', isDark);

  // Angular: update your ThemeService
  // Vue: update a reactive ref used by your theme composable
  // Django + Alpine: set Alpine.$store.theme.dark = isDark
}
```

Available token variables from HRIS:

| Variable | Light | Dark |
|---|---|---|
| `--hris-theme` | `'light'` | `'dark'` |
| `--hris-bg` | `#f9fafb` | `#111827` |
| `--hris-surface` | `#ffffff` | `#1f2937` |
| `--hris-text` | `#111827` | `#f9fafb` |
| `--hris-border` | `#e5e7eb` | `#374151` |
| `--hris-brand` | `#3b82f6` | `#3b82f6` |

---

### Step 9 — Declare profile capability (MODULE_PROFILE_CAPABILITY)

This is what makes HRIS `/profile` show a tab for your module automatically —
even if HRIS was deployed before your module existed.

```javascript
// Send after your app finishes bootstrapping (after auth)
window.parent.postMessage({
  type: 'MODULE_PROFILE_CAPABILITY',
  moduleId: 'your-module-id',
  label: 'Your Module Profile',      // tab label on HRIS /profile
  profilePath: '/hris/profile',      // your route that renders profile-only UI
  actions: [
    { id: 'profile:view',           label: 'View & Edit Profile' },
    { id: 'profile:reset-password', label: 'Reset Password' },
    // Add any profile-related actions your module supports
  ],
}, HRIS_ORIGIN);
```

Your `/hris/profile` route should render **only** the profile editor — no
sidebar, no navbar (already hidden by embedded CSS). A full-page profile form.

---

### Step 10 — Request a native confirm dialog (MODULE_CONFIRM_ACTION)

Before a destructive operation (delete, archive, bulk action), request a
native HRIS confirm dialog instead of showing your own. The result comes back
as `HRIS_CONFIRM_RESULT` in your message handler (see §3).

```javascript
function confirmDelete(recordId) {
  window.parent.postMessage({
    type: 'MODULE_CONFIRM_ACTION',
    actionId: `delete-${recordId}`,        // unique per action instance
    title: 'Delete employee record?',
    message: 'This action cannot be undone. The employee will be permanently removed.',
    confirmLabel: 'Delete',
    danger: true,
  }, HRIS_ORIGIN);
}

// In your message handler:
function handleConfirmResult(actionId, confirmed) {
  if (actionId.startsWith('delete-') && confirmed) {
    const recordId = actionId.replace('delete-', '');
    deleteRecord(recordId);
  }
}
```

---

### Step 11 — Relay toasts to HRIS (MODULE_ALERT)

HRIS hides your module's own toast container (to avoid double notifications)
and re-displays them natively in its shell. You have two options:

**Option A: Direct relay (best — call this wherever you'd normally show a toast)**

```javascript
function notify(message, level = 'info') {
  if (inHris) {
    window.parent.postMessage({ type: 'MODULE_ALERT', message, level }, HRIS_ORIGIN);
    return;
  }
  // Fall through to your native toast library when running standalone.
  yourToastLib.show(message, { type: level });
}
// level: 'info' | 'success' | 'warning' | 'error'
```

**Option B: MutationObserver on your toast container (good when you can't change toast call sites)**

```javascript
// Reference the SRMS implementation in index.js startToastRelay() for the full pattern.
// This watches for DOM insertions into your toast container and relays each toast text.
```

---

### Step 12 — Report user profile (MODULE_USER_PROFILE)

After authentication, send the logged-in user's avatar and name to HRIS so
its Navbar shows the real photo instead of the initials placeholder:

```javascript
window.parent.postMessage({
  type: 'MODULE_USER_PROFILE',
  avatarUrl: user.profilePictureUrl ?? null,
  displayName: `${user.firstName} ${user.lastName}`.trim() || user.username,
}, HRIS_ORIGIN);
```

---

### Step 13 — Report runtime errors (MODULE_RUNTIME_ERROR)

Attach a global error handler so HRIS can surface unexpected crashes in its
`ModuleAlertBanner` without the operator needing to open DevTools:

```javascript
window.onerror = (message, source, lineno) => {
  window.parent.postMessage({
    type: 'MODULE_RUNTIME_ERROR',
    message: `${String(message)} (${String(source ?? '').split('/').pop()}:${lineno ?? '?'})`,
  }, HRIS_ORIGIN);
  return false;
};
window.onunhandledrejection = (event) => {
  window.parent.postMessage({
    type: 'MODULE_RUNTIME_ERROR',
    message: `Unhandled promise rejection: ${String(event.reason?.message ?? event.reason ?? 'unknown')}`,
  }, HRIS_ORIGIN);
};
```

---

### Step 14 — Hide your own navigation chrome

When embedded, HRIS provides the sidebar, header, and footer. Your module's
own nav should be hidden. The simplest approach: add a CSS class to `<body>`
on boot, then hide via CSS.

```javascript
if (inHris) document.body.classList.add('hris-embedded');
```

```css
/* In your global stylesheet */
.hris-embedded .your-sidebar,
.hris-embedded .your-header,
.hris-embedded .your-footer,
.hris-embedded .your-topbar { display: none !important; }

/* Remove sidebar offset from main content */
.hris-embedded .your-main-content { margin-left: 0 !important; }
```

```html
<!-- Angular: in AppComponent template -->
<app-sidebar *ngIf="!inHris"></app-sidebar>
<app-header *ngIf="!inHris"></app-header>
<router-outlet></router-outlet>
```

```vue
<!-- Vue: in App.vue -->
<AppSidebar v-if="!inHris" />
<RouterView />
```

```python
# Django: in your base template
{% if not request.headers.get('Sec-Fetch-Dest') == 'iframe' %}
  {# This check is unreliable; prefer the JS class approach above #}
{% endif %}
```

---

### Step 15 — Suppress tour guides / onboarding overlays

If your app has a product tour (Shepherd, Intro.js, Joyride, etc.), suppress
it when embedded — the tour steps reference your own nav which is hidden.

```javascript
// React (component-level guard)
if (window.parent !== window) return null;  // before any tour render

// Angular
ngOnInit() {
  if (window.parent !== window) return;
  this.startTour();
}

// Vanilla JS
if (window.parent === window) startTour();
```

CSS safety net (catches any tour library):
```css
.hris-embedded .__floater,
.hris-embedded .shepherd-element,
.hris-embedded .introjs-overlay,
.hris-embedded .react-joyride__overlay { display: none !important; }
```

---

## 4. Framework-specific bootstrap templates

### React / Next.js (CRA / Vite)

```javascript
// src/index.js or src/main.jsx
const HRIS_ORIGIN = process.env.REACT_APP_HRIS_ORIGIN || 'https://hris.gi-kace.com.gh';
const inHris = window.parent !== window;

if (inHris) {
  applyEmbeddedSetup();   // inject CSS, set body class, start height reporter
  window.addEventListener('message', handleHrisMessage);
  if (!isSsoBridgeCallback()) {
    window.parent.postMessage({ type: 'MODULE_READY', moduleId: 'your-id' }, HRIS_ORIGIN);
  }
}

// Then render your React app normally.
ReactDOM.createRoot(document.getElementById('root')).render(<App />);
```

### Angular

```typescript
// src/main.ts
const HRIS_ORIGIN = environment.hrisOrigin || 'https://hris.gi-kace.com.gh';
const inHris = window.parent !== window;

if (inHris) {
  applyEmbeddedCss();   // inject <style> tag with embedded overrides
  document.body.classList.add('hris-embedded');
  window.addEventListener('message', handleHrisMessage);
  window.parent.postMessage({ type: 'MODULE_READY', moduleId: 'your-id' }, HRIS_ORIGIN);
}

platformBrowserDynamic().bootstrapModule(AppModule);

// In AppModule, provide an HrisService that wraps handleHrisMessage and exposes
// observables for HRIS_NAV_GO, HRIS_SEARCH_QUERY, TRIGGER_ACTION, THEME_TOKENS.
// Components subscribe to these instead of listening to window.addEventListener.
```

### Vue 3 / Nuxt

```javascript
// src/main.js or plugins/hris-bridge.client.js (Nuxt)
const HRIS_ORIGIN = import.meta.env.VITE_HRIS_ORIGIN || 'https://hris.gi-kace.com.gh';
const inHris = window.parent !== window;

export const hrisBridge = reactive({ inHris, query: '', theme: 'light' });

if (inHris) {
  applyEmbeddedCss();
  document.body.classList.add('hris-embedded');
  window.addEventListener('message', (event) => {
    if (event.origin !== HRIS_ORIGIN) return;
    const { type, ...rest } = event.data || {};
    if (type === 'HRIS_SEARCH_QUERY') hrisBridge.query = rest.query || '';
    if (type === 'THEME_TOKENS') applyThemeTokens(rest.tokens);
    // etc.
  });
  window.parent.postMessage({ type: 'MODULE_READY', moduleId: 'your-id' }, HRIS_ORIGIN);
}

// Inject hrisBridge as an app-level provide:
app.provide('hrisBridge', hrisBridge);
```

### Svelte / SvelteKit

```javascript
// src/app.html or src/routes/+layout.svelte <script context="module">
// src/lib/hris.js
export const HRIS_ORIGIN = import.meta.env.PUBLIC_HRIS_ORIGIN || 'https://hris.gi-kace.com.gh';
export const inHris = typeof window !== 'undefined' && window.parent !== window;

export const hrisEvents = writable({ type: null });

if (inHris) {
  applyEmbeddedCss();
  document.body.classList.add('hris-embedded');
  window.addEventListener('message', (e) => {
    if (e.origin !== HRIS_ORIGIN) return;
    hrisEvents.set(e.data);   // components subscribe via derived stores
  });
  window.parent.postMessage({ type: 'MODULE_READY', moduleId: 'your-id' }, HRIS_ORIGIN);
}
```

### Laravel + Blade + Alpine.js

```javascript
// resources/js/app.js  (or a dedicated hris-bridge.js loaded in blade layout)
const HRIS_ORIGIN = window.HRIS_ORIGIN || 'https://hris.gi-kace.com.gh';
const inHris = window.parent !== window;

window.hrisBridge = { inHris };

if (inHris) {
  applyEmbeddedCss();
  document.body.classList.add('hris-embedded');
  window.addEventListener('message', (e) => {
    if (e.origin !== HRIS_ORIGIN) return;
    // Dispatch a custom DOM event — Alpine components listen with x-on:
    document.dispatchEvent(new CustomEvent('hris-message', { detail: e.data }));
  });
  window.parent.postMessage({ type: 'MODULE_READY', moduleId: 'your-id' }, HRIS_ORIGIN);
}
```

```blade
{{-- In your base layout, pass the origin from a config/env value --}}
<script>window.HRIS_ORIGIN = "{{ config('hris.origin') }}";</script>
```

```html
<!-- Alpine component that reacts to HRIS messages -->
<div x-data="{ searchQuery: '' }"
     @hris-message.document="if ($event.detail.type === 'HRIS_SEARCH_QUERY') searchQuery = $event.detail.query">
  <input type="text" :value="searchQuery" x-model="searchQuery" @input="doSearch(searchQuery)" />
</div>
```

### Django + HTMX

```python
# In your view or middleware, detect iframe context:
def is_embedded(request):
    # Reliable only via JS; set a cookie in the bridge JS and read it here.
    return request.COOKIES.get('hris_embedded') == '1'
```

```javascript
// static/js/hris-bridge.js (loaded in base template)
if (window.parent !== window) {
  document.cookie = 'hris_embedded=1; path=/; SameSite=None; Secure';
  // proceed with bridge setup…
}
```

```html
<!-- In base.html: hide Django nav when embedded -->
{% if not request.COOKIES.hris_embedded %}
  {% include "partials/nav.html" %}
{% endif %}
```

HTMX + MODULE_HEIGHT_CHANGE:
```javascript
// After every HTMX swap (content changes height), report to HRIS
document.addEventListener('htmx:afterSwap', reportHeight);
```

---

## 5. Required HTTP headers (server / nginx)

Your app's server must allow HRIS to frame it:

```nginx
# nginx.conf — inside your server block
add_header X-Frame-Options "SAMEORIGIN" always;
add_header Content-Security-Policy
  "frame-ancestors 'self' https://hris.gi-kace.com.gh" always;
```

```python
# Django settings.py
X_FRAME_OPTIONS = 'SAMEORIGIN'
CSP_FRAME_ANCESTORS = ("'self'", "https://hris.gi-kace.com.gh")
```

```php
// Laravel: in a middleware or kernel boot
header("X-Frame-Options: SAMEORIGIN");
header("Content-Security-Policy: frame-ancestors 'self' https://hris.gi-kace.com.gh");
```

```java
// Spring Boot
http.headers().frameOptions().sameOrigin();
// Add CSP via WebSecurityConfigurerAdapter or SecurityFilterChain
```

---

## 6. Your `/hris/profile` route

When HRIS `/profile` shows a tab for your module, it embeds you at the
`profilePath` you declared in `MODULE_PROFILE_CAPABILITY` (default: `/hris/profile`).

This route should render **only** your profile UI — form fields, avatar upload,
personal details — with no surrounding navigation. The embedded CSS already
hides your sidebar and header, so you just need a plain page.

```javascript
// React: a dedicated route
{ path: '/hris/profile', element: <ProfileEditorPage embedded /> }

// Angular: a route with a guard that skips the usual shell
{ path: 'hris/profile', component: ProfileEditorComponent }
// In AppComponent: <router-outlet *ngIf="!inHris"> ... nav ... </router-outlet>

// Vue: same pattern
{ path: '/hris/profile', component: ProfileEditorView }

// Laravel: a named route
Route::get('/hris/profile', [ProfileController::class, 'embedded'])->name('hris.profile');
// The `embedded` method returns a Blade view without the nav partials.
```

---

## 7. Environment variables checklist

| Variable | Where set | Value |
|---|---|---|
| `REACT_APP_HRIS_ORIGIN` / `VITE_HRIS_ORIGIN` / `HRIS_ORIGIN` | Your module's `.env` | `https://hris.gi-kace.com.gh` |
| Your module's origin | HRIS `.env` as `VITE_MODULE_ORIGIN_YOURMODULE` | `https://yourmodule.gi-kace.com.gh` |
| Module ID | Agree with the HRIS team | `your-module-id` (lowercase, no spaces) |

---

## 8. Integration checklist (complete before handover to HRIS team)

- [ ] `MODULE_READY` sent on app boot (before React/Angular/Vue renders)
- [ ] `HRIS_AUTH_RELAY` received and SSO bridge redirects user in
- [ ] `MODULE_SESSION_EXPIRED` sent on any 401 response
- [ ] `MODULE_HEIGHT_CHANGE` sent via ResizeObserver; iframe scrollbar hidden
- [ ] `MODULE_ROUTE_CHANGE` sent on every SPA navigation
- [ ] `MODULE_SEARCH_CONFIG` sent after mount; `HRIS_SEARCH_QUERY` handled
- [ ] `MODULE_USER_PROFILE` sent after authentication (avatar + name)
- [ ] `MODULE_PROFILE_CAPABILITY` sent after mount; `/hris/profile` route exists
- [ ] `MODULE_ALERT` sent instead of (or alongside) native toasts
- [ ] `MODULE_RUNTIME_ERROR` wired via `window.onerror`
- [ ] `TRIGGER_ACTION` handler dispatches to correct modal/feature
- [ ] `THEME_TOKENS` applied to CSS variables + body class toggle
- [ ] `HRIS_LOGOUT` clears local session
- [ ] `HRIS_NAV_GO` navigates SPA without full reload
- [ ] Your sidebar/header/footer hidden via `.hris-embedded` CSS class
- [ ] Tour guides / onboarding overlays suppressed when embedded
- [ ] `X-Frame-Options: SAMEORIGIN` + `Content-Security-Policy: frame-ancestors` headers set
- [ ] `REACT_APP_HRIS_ORIGIN` / equivalent env var set in both dev and production
- [ ] Tested: dark mode toggle in HRIS → module recolours correctly
- [ ] Tested: search in HRIS Navbar → results appear in module
- [ ] Tested: print → module content prints without nav clutter
- [ ] Tested: mobile — no double scrollbar, touch scroll works in HRIS shell

---

## 9. HRIS team: adding a new module to the shell

When a new module is ready for integration, the HRIS team needs to do
**very little** because the protocol is generic. The only HRIS changes:

1. Add `VITE_MODULE_ORIGIN_NEWMODULE=https://newmodule.gi-kace.com.gh` to `apps/frontend/portal/.env`
2. Add `newmodule` to `getModuleOrigin()` in `apps/frontend/portal/src/constants/moduleOrigins.ts`
3. Add a sidebar nav item pointing to `/modules/newmodule/native`
4. Add the module to the tenant catalog in the Tenant Registry database

`ModuleFrame`, `ModuleCapabilitiesContext`, `ProfileHubPage`, and all bridge
handlers work generically for any `moduleId`. No other HRIS code changes.

---

## 10. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Refused to frame` in console | Missing CSP/X-Frame-Options headers | Add headers (see §5) |
| Blank iframe, no MODULE_READY | Module JS failed to load | Check browser console inside iframe |
| Search bar doesn't appear | `MODULE_SEARCH_CONFIG` not sent or wrong origin | Verify HRIS_ORIGIN env var |
| Search doesn't filter | `HRIS_SEARCH_QUERY` received but handler not wired | Implement `runSearch()` (see §6) |
| 401 loop | MODULE_SESSION_EXPIRED sent but HRIS_AUTH_RELAY not re-triggering | Check expectedOriginRef in ModuleFrame |
| Dark mode doesn't apply | `applyThemeTokens` not toggling body class | Add body class toggle (see §8) |
| Profile tab not appearing | MODULE_PROFILE_CAPABILITY not sent after bootstrap | Check timing — send after auth, not on load |
| Modal doesn't open on avatar click | TRIGGER_ACTION handler not registered | Implement `dispatchAction()` (see §7) |
| Iframe has scrollbar | ResizeObserver not running or scrollbar CSS missing | Check Step 5 (overflow-y: scroll) |
| Toasts show twice | MODULE_ALERT sent but `.Toastify` not hidden via CSS | Hide your toast container when embedded |
| Runtime errors not surfaced | `window.onerror` not wired | Add Step 13 |
