# Afrigen 2.0 Page and Route Inventory

## Coverage status (2026-11-14)

This is a repository-level inventory, not a claim that the full redesign is complete.
It was built from Flask route decorators and registrations, all Jinja template files,
inheritance/include declarations, and route-to-template references. A source scan also
identified forms, buttons, Bootstrap controls, fetch/XHR calls, and notification
polling. The detailed interaction, access, subscription, and viewport audit remains
open for pages marked pending below.

| Measure | Current inventory |
|---|---:|
| Registered Flask routes, including Flask's static route | 157 |
| Application-declared route rules | 156 |
| Registered application blueprints | 6 |
| Jinja template files | 69 |
| Page templates (61 layout-extending plus 1 standalone) | 62 |
| Layouts and reusable template fragments | 7 |
| Pages redesigned in this task | 1 (notifications) |
| Pages with targeted automated route/template tests | 1 (notifications) |
| Full automated test suite | 42 passed |
| Pages intentionally retained after completed review | 0 |
| Pages merged | 0 |
| Pages deprecated | 0 |
| Pages verified at all required desktop/mobile widths | 0 |
| Remaining pages pending full review/redesign/testing | 61 |

The notification page has targeted route/API and rendered-page tests. Those tests do
not cover responsive browser rendering, the admin layout, every subscription tier,
or each notification action at all requested viewport sizes. Accordingly it is not
counted as fully viewport-tested.

## Blueprint and inheritance map

| Registration | Prefix | Routes |
|---|---|---:|
| `main` | `/` | 123 |
| `auth` | `/auth` | 7 |
| `api` | `/api/v1` | 2 |
| `campaigns_bp` | `/api/campaigns` | 6 |
| `telegram_bp` | `/telegram` | 5 |
| `movie_studio_bp` | `/movie-studio` | 9 |
| Flask static endpoint | `/static/<path:filename>` | 1 |

`templates/base.html` is the primary public/authenticated shell; it includes the
public navbar or authenticated sidebar, footer, and (for non-embedded authenticated
pages) the notification centre. `templates/admin_base.html` is the admin shell and
now includes the same notification centre. Most page templates extend one of these
shells. `templates/main/founder.html` is a standalone page and remains an explicit
design-system exception awaiting review. The mobile app sidebar is included from
`templates/components/auth_sidebar.html`; its bell and the desktop-header bell are
mutually exclusive at the responsive breakpoint and open the same panel.

Reusable layouts/fragments: `templates/base.html`, `templates/admin_base.html`,
`templates/components/auth_sidebar.html`, `templates/components/public_navbar.html`,
`templates/components/footer.html`,
`templates/components/notification_center.html`, and
`templates/main/_social_publish_modal.html`.

## Page-by-page checklist

For each pending row, the route and template are mapped and the existing page purpose
is summarized, but the page's full control-by-control, empty/error/loading, mobile,
and tier-specific behavior has **not** yet been verified. New-design and mobile cells
are required work, not assertions that those requirements are already met.

| Page / template | Route and access | Existing functionality / backend dependency | New design, mobile, interactions | Implementation / test / decision |
|---|---|---|---|---|
| Admin campaigns — `templates/admin/campaigns.html` | `GET,POST /admin/campaigns`; admin | Generate and launch promotional campaigns; promo campaign service | Admin design; responsive campaign form/results; inventory every control/state | Review pending; not tested; decision pending |
| Admin newsletter campaigns — `templates/admin/newsletter_campaigns.html` | `GET /admin/newsletter/campaigns`; admin | Newsletter campaign list and lifecycle actions | Admin design; mobile list/actions; audit forms and confirmation states | Review pending; not tested; decision pending |
| Forgot password — `templates/auth/forgot_password.html` | `GET,POST /auth/forgot-password`; public | Request password reset email | Public/auth design; mobile form and delivery/error states | Review pending; not tested; decision pending |
| Login — `templates/auth/login.html` | `GET,POST /auth/login`; public | Password and Google login entry | Public/auth design; mobile form, validation, OAuth and error states | Review pending; not tested; decision pending |
| Registration — `templates/auth/register.html` | `GET,POST /auth/register`; public | Account creation, signup preferences/referral flow | Public/auth design; mobile form, validation and success/error states | Review pending; not tested; decision pending |
| Reset password — `templates/auth/reset_password.html` | `GET,POST /auth/reset-password/<token>`; reset-token holder | Set a new password with token validation | Public/auth design; mobile form and invalid/expired-token state | Review pending; not tested; decision pending |
| Forbidden — `templates/errors/403.html` | Flask 403 handler; any visitor | Permission-denied fallback | Public design; mobile recovery/help navigation | Review pending; not tested; decision pending |
| Not found — `templates/errors/404.html` | Flask 404 handler; any visitor | Not-found fallback | Public design; mobile recovery/navigation | Review pending; not tested; decision pending |
| Server error — `templates/errors/500.html` | Flask 500 handler; any visitor | Server-error fallback | Public design; mobile recovery/retry state | Review pending; not tested; decision pending |
| Admin command center — `templates/main/admin.html` | `GET /admin`; admin | Users, generations, providers, revenue, activity and operations tabs/actions | Admin design; mobile tables/tabs; audit every embedded form/modal/action | Existing 2.0 work present; acceptance review and tests pending |
| Admin credits — `templates/main/admin_credits.html` | `GET,POST /admin/credits`; admin | User lookup, credit grants and ledger history | Admin design; mobile lookup/ledger and form states | Review pending; not tested; decision pending |
| Paystack webhooks — `templates/main/admin_paystack_webhooks.html` | `GET /admin/paystack-webhooks`; admin | Payment webhook log inspection | Admin design; mobile table/filter states | Review pending; not tested; decision pending |
| Admin pricing — `templates/main/admin_pricing.html` | `GET,POST /admin/pricing`; admin | View/update tier pricing | Admin design; mobile pricing form and validation | Existing 2.0 work present; acceptance review and tests pending |
| Provider status — `templates/main/admin_providers.html` | `GET /admin/provider-status`; admin | Provider health/status inspection | Admin design; mobile health/status tables and error states | Review pending; not tested; decision pending |
| Analytics — `templates/main/analytics.html` | `GET /analytics`; authenticated | User analytics and campaign metrics | Application design; mobile charts/tables and empty/loading states | Review pending; not tested; decision pending |
| Afrigen assistant — `templates/main/assistant.html` | `GET /assistant`; authenticated | Assistant UI and chat API; can render embedded | Application design; mobile chat controls, errors and embedded layout | Review pending; not tested; decision pending |
| Automation builder — `templates/main/automation_builder.html` | `GET /automation/build`; authenticated | Workflow construction and save/run interactions | Application design; mobile editor, drawers/forms and validation | Review pending; not tested; decision pending |
| Automation run details — `templates/main/automation_run_details.html` | `GET /automations/<log_id>`; authenticated/owner | Run status and generated assets | Application design; mobile run details/actions and empty/error states | Review pending; not tested; decision pending |
| Automations — `templates/main/automations.html` | `GET /automations`; authenticated | Workflow list, run, delete and API-backed state | Application design; mobile list/actions and tier restrictions | Review pending; not tested; decision pending |
| Blog — `templates/main/blog.html` | `GET /blog`; public | Blog index from blog service | Public design; mobile cards/pagination/empty state | Review pending; not tested; decision pending |
| Blog CMS — `templates/main/blog_admin.html` | `GET /admin/blog`; admin | Draft generation, publishing and editing actions | Admin design; mobile CMS controls, forms and confirmation states | Review pending; not tested; decision pending |
| Blog editor — `templates/main/blog_edit.html` | `GET,POST /admin/blog/edit/<post_id>`; admin | Edit a blog post | Admin design; mobile editor, validation and save/error states | Review pending; not tested; decision pending |
| Blog post — `templates/main/blog_post.html` | `GET /blog/<slug>`; public | Read a published post | Public design; responsive reading/share controls | Review pending; not tested; decision pending |
| Brand dashboard — `templates/main/brand_dashboard.html` | No direct route reference found; template retained | Orphan template; intended brand workspace behavior needs tracing | Review links/callers first; establish responsive intended workflow | Unlinked; review pending; not tested; decision pending |
| Brand Kit — `templates/main/brands.html` | `GET /brands`; authenticated | Brand management plus `/api/brands` create/delete | Application design; mobile brand forms/cards and confirmation states | Review pending; not tested; decision pending |
| Campaign builder — `templates/main/campaign_builder.html` | `GET /campaign/build`; authenticated | Campaign planning/build workflow | Application design; mobile builder/forms and generation states | Review pending; not tested; decision pending |
| Campaign dashboard — `templates/main/campaign_dashboard.html` | `GET /campaign/<campaign_id>`; authenticated/owner | Campaign status/assets and campaign API actions | Application design; mobile dashboard/actions and empty/error states | Review pending; not tested; decision pending |
| Campaigns — `templates/main/campaigns.html` | `GET /campaigns`; authenticated | Campaign listing and campaign API workflow | Application design; mobile list/create and status states | Review pending; not tested; decision pending |
| Connected accounts — `templates/main/connected_accounts.html` | `GET /connected-accounts`; authenticated | Provider connect/callback/disconnect and connection status | Application design; mobile account cards, OAuth/error states | Review pending; not tested; decision pending |
| Contact — `templates/main/contact.html` | `GET,POST /contact`; public | Contact submission | Public design; mobile form, validation and submission state | Review pending; not tested; decision pending |
| Creation workspace — `templates/main/create.html` | `GET /create?mode=video\|image\|voice\|writing`; authenticated | Video/image/voice/writing generation; generation/refinement APIs | Application design; mobile modes/forms, loading/failure/quota/upgrade states | Existing 2.0 work present; acceptance review and tests pending |
| Dashboard — `templates/main/dashboard.html` | `GET /dashboard`; authenticated | Account/creation overview and quick actions | Application design; responsive cards, empty/loading and tier-aware states | Existing 2.0 work present; acceptance review and tests pending |
| Dashboard stub — `templates/main/dashboard_stub.html` | No direct route reference found | Orphan placeholder template; intended functionality needs tracing | Trace references before deciding merge/retain/deprecate; mobile review | Unlinked; review pending; not tested; decision pending |
| Distribution — `templates/main/distribution.html` | `GET /admin/distribution`; admin | Content distribution runs, trigger/retry and run detail | Admin design; mobile tables/actions and failure/retry states | Review pending; not tested; decision pending |
| Help & docs — `templates/main/docs.html` | `GET /docs`; public | Help documentation | Public design; mobile reading and in-page navigation | Review pending; not tested; decision pending |
| Download app — `templates/main/download.html` | `GET /download-app`; public | App/PWA download information | Public design; mobile install/compatibility guidance | Review pending; not tested; decision pending |
| Feedback — `templates/main/feedback.html` | `GET,POST /feedback`; public | Feedback submission | Public design; mobile form and validation/success/error states | Review pending; not tested; decision pending |
| Founder — `templates/main/founder.html` | `GET /founder`; public; standalone HTML | Founder profile/story content | Must adopt/justify new public system; mobile layout and nav need review | Existing standalone retained pending decision; not tested |
| Creation history — `templates/main/history.html` | `GET /history`; authenticated | Owned generations, downloads and social publishing modal | Application design; mobile media cards, modal, filters and empty/error states | Existing 2.0 work present; acceptance review and tests pending |
| Image result — `templates/main/image_result.html` | `GET /result/image`; authenticated | Image result, preview and download actions | Application design; mobile media/actions and failure state | Review pending; not tested; decision pending |
| Public home — `templates/main/index.html` | `GET /`; public/session-aware | Public landing/showcase; signed-in launch links | Public design; responsive showcase/nav and media loading/fallback | Existing 2.0 work present; acceptance review and tests pending |
| Launch waitlist — `templates/main/launch.html` | `GET /launch`; public | Waitlist signup and count endpoint | Public design; mobile signup, validation and success state | Review pending; not tested; decision pending |
| Launch administration — `templates/main/launch_admin.html` | `GET /launch/admin`; admin | Waitlist data/export/newsletter controls | Admin design; mobile tables and export/newsletter actions | Review pending; not tested; decision pending |
| Marketing stub — `templates/main/marketing_stub.html` | No direct route reference found | Orphan placeholder template; intended functionality needs tracing | Trace references before deciding merge/retain/deprecate; mobile review | Unlinked; review pending; not tested; decision pending |
| Movie Studio — `templates/main/movie_studio/index.html` | `GET /movie-studio/`; authenticated, Director entitlement | Project listing/create; tier-gated by entitlement service | Application design; mobile project list and correct upgrade/permission state | Review pending; not tested; decision pending |
| Movie Studio locked — `templates/main/movie_studio/locked.html` | Rendered by movie routes; authenticated, non-Director | Entitlement/upgrade explanation | Application design; mobile permission/upgrade workflow | Review pending; not tested; decision pending |
| Movie project — `templates/main/movie_studio/project.html` | `GET /movie-studio/projects/<project_id>`; authenticated/owner/Director | Treatment, character/scene/shot generation, render status | Application design; mobile production workflow, progress/error/loading states | Review pending; not tested; decision pending |
| Newsletter admin — `templates/main/newsletter_admin.html` | `GET /admin/newsletter`; admin | Generate, edit, approve and send newsletter | Admin design; mobile editor and confirmation/error states | Review pending; not tested; decision pending |
| Notification history — `templates/main/notifications.html` | `GET /notifications`; authenticated, all tiers | Filter/search/paginate, read/unread, mark all, same-origin destinations | Premium application design; dropdown becomes mobile bottom sheet; category, empty/loading/error, keyboard/touch states | Fully redesigned; API/page tests pass; viewport/admin/tier tests pending |
| Offline — `templates/main/offline.html` | `GET /offline`; public/PWA fallback | Offline fallback and recovery link | Public design; small-screen offline/retry guidance | Review pending; not tested; decision pending |
| Privacy — `templates/main/privacy.html` | `GET /privacy`; public | Privacy policy | Public design; mobile reading/accessibility | Review pending; not tested; decision pending |
| Profile — `templates/main/profile.html` | `GET,POST /profile`; authenticated | Profile details/update | Application design; mobile profile form and validation | Review pending; not tested; decision pending |
| Referral — `templates/main/referral.html` | `GET /referral`; authenticated | Referral code/link and usage | Application design; mobile copy/share and empty/error states | Review pending; not tested; decision pending |
| Video result — `templates/main/result.html` | `GET /result/video`; authenticated | Video result, download/share/social publish modal | Application design; mobile playback, modal/actions and failure state | Existing 2.0 work present; acceptance review and tests pending |
| Saved prompts — `templates/main/saved_prompts.html` | `GET /saved-prompts`; authenticated | Saved prompt list; prompt-save API/form | Application design; mobile list/actions and empty state | Review pending; not tested; decision pending |
| Settings — `templates/main/settings.html` | `GET,POST /settings`; authenticated | Account, notification preferences and credentials | Application design; mobile tabs/forms and success/error states | Existing 2.0 work present; acceptance review and tests pending |
| Share — `templates/main/share.html` | `GET /v/<token>`; public token | Shared generation preview | Public design; mobile media and unavailable/expired state | Review pending; not tested; decision pending |
| Terms — `templates/main/terms.html` | `GET /terms`; public | Terms of service | Public design; mobile reading/accessibility | Review pending; not tested; decision pending |
| Unsubscribe — `templates/main/unsubscribe.html` | `GET /unsubscribe/<token>`; token holder | Email unsubscribe confirmation/result | Public design; mobile success/invalid-token states | Review pending; not tested; decision pending |
| Upgrade — `templates/main/upgrade.html` | `GET /upgrade`; public/session-aware, tier-aware | Tier pricing and six payment-initiation paths | Public/app design; mobile plan comparison and correct tier/payment states | Existing 2.0 work present; acceptance review and tests pending |
| Watch ad — `templates/main/watch_ad.html` | `GET /watch-ad/<generation_id>`; authenticated/owner | Ad gate and unlock-download POST; now uses authenticated shell | Application design; mobile gate/form; preserve ad/download workflow | Shell restyled; route/form browser test pending; review decision pending |
| Placeholder — `templates/todo_placeholder.html` | No direct route reference found | Orphan placeholder; intended use needs tracing | Trace references before deciding merge/retain/deprecate; mobile review | Unlinked; review pending; not tested; decision pending |

**Decision rule:** no page is declared intentionally retained, merged, or deprecated
until its route, behavior, links, access rules, and states have been reviewed. The
orphan templates above are deliberately listed rather than silently discarded.

## Route catalog

All six blueprints and four direct application routes were checked. Route patterns
below include every declared Flask rule; route methods are encoded in the route
decorators and should be checked alongside the corresponding handler when auditing
actions. The default Flask static-file route is listed separately.

### `main` blueprint — 123 routes

`/`; `/dashboard`; `/connected-accounts/<provider>/status`; `/generate`;
`/connected-accounts`; `/connected-accounts/<provider>/connect`;
`/connected-accounts/<provider>/callback`; `/connected-accounts/<provider>/connect/token`;
`/connected-accounts/<provider>/disconnect`; `/refine-prompt`; `/refine-image-prompt`;
`/generate-from-image`; `/generate-image`; `/generate-voice`;
`/generation/<int:generation_id>/retry`; `/v/<token>`; `/result/video`; `/result/image`;
`/history`; `/admin/provider-status`; `/admin`;
`/admin/generation/<int:generation_id>/force-refund`;
`/admin/generation/<int:generation_id>/force-retry`;
`/admin/grant-free-video/<int:user_id>`; `/admin/upgrade/<int:user_id>`;
`/admin/credits`; `/admin/pricing`; `/admin/backfill-subscribers`;
`/admin/export/users.csv`; `/admin/export/payments.csv`; `/admin/export/generations.csv`;
`/admin/downgrade/<int:user_id>`; `/admin/ban/<int:user_id>`; `/admin/delete/<int:user_id>`;
`/upgrade`; `/payment/initialize`; `/payment/initialize/annual`;
`/payment/initialize/studio`; `/payment/initialize/studio/annual`;
`/payment/initialize/director`; `/payment/initialize/director/annual`; `/payment/callback`;
`/download/<int:generation_id>`; `/watch-ad/<int:generation_id>`;
`/unlock-download/<int:generation_id>`; `/save-prompt`; `/saved-prompts`; `/referral`;
`/contact`; `/feedback`; `/docs`; `/blog`; `/blog/<slug>`; `/admin/blog`;
`/admin/blog/generate`; `/admin/blog/publish/<int:post_id>`;
`/admin/blog/edit/<int:post_id>`; `/admin/blog/discard/<int:post_id>`;
`/admin/distribution`; `/admin/distribution/trigger/<int:post_id>`;
`/admin/distribution/run/<int:run_id>`;
`/admin/distribution/retry/<int:run_id>/<platform>`; `/analytics`; `/terms`; `/privacy`;
`/founder`; `/launch`; `/launch/subscribe`; `/launch/count`; `/launch/admin`;
`/launch/admin/data`; `/launch/admin/export`; `/launch/admin/newsletter`;
`/admin/newsletter`; `/admin/newsletter/generate`; `/admin/newsletter/save`;
`/admin/newsletter/approve`; `/admin/newsletter/send`; `/unsubscribe/<token>`;
`/cron/newsletter/generate`; `/cron/newsletter/weekly`;
`/f3dd6d35491e4a168ba565d6e14ccffc.txt`; `/payment/webhook`; `/fal/webhook`;
`/admin/paystack-webhooks`; `/admin/newsletter/campaigns`;
`/admin/newsletter/campaigns/new`; `/admin/newsletter/campaigns/<int:id>/launch`;
`/admin/newsletter/campaigns/<int:id>/pause`; `/admin/newsletter/campaigns/<int:id>/delete`;
`/notifications`; `/api/notifications`; `/api/notifications/history`;
`/api/notifications/<int:notif_id>/read`; `/api/notifications/read-all`;
`/admin/notifications/broadcast`; `/admin/campaigns`; `/offline`; `/download-app`;
`/download/video/<int:generation_id>`; `/download/image/<int:generation_id>`; `/create`;
`/brands`; `/api/brands`; `/api/brands/<int:brand_id>`; `/campaigns`; `/automations`;
`/automations/<log_id>`; `/assistant`; `/api/publishing/accounts`;
`/api/publishing/publish`; `/settings`; `/settings/credentials/save`; `/profile`;
`/automation/build`; `/campaign/build`; `/campaign/<campaign_id>`; `/api/copilot`;
`/api/automations`; `/api/automations/run/<workflow_id>`;
`/api/automations/<workflow_id>`; `/api/automations/save`; `/api/campaigns/plan`.

### Other registered blueprints and direct rules

- `auth` (`/auth`, 7): `/register`, `/login`, `/logout`, `/google`,
  `/google/callback`, `/forgot-password`, `/reset-password/<token>`.
- `api` (`/api/v1`, 2): `/status`, `/blog/<slug>`.
- `campaigns_bp` (`/api/campaigns`, 6): `/`, `/<int:campaign_id>`,
  `/<int:campaign_id>/retry`, `/<int:campaign_id>/pause`,
  `/<int:campaign_id>/resume`. The blueprint registers `/` for both GET and POST.
- `telegram_bp` (`/telegram`, 5): `/webhook`, `/setup-webhook`, `/webhook-info`,
  `/connect-code`, `/link-status`.
- `movie_studio_bp` (`/movie-studio`, 9): `/`, `/projects/create`,
  `/projects/<int:project_id>`, `/projects/<int:project_id>/treatment`,
  `/projects/<int:project_id>/characters/<int:char_id>/portrait`,
  `/projects/<int:project_id>/scenes/<int:scene_id>/storyboard`,
  `/projects/<int:project_id>/shots/<int:shot_id>/generate`,
  `/projects/<int:project_id>/render`, `/render-jobs/<int:job_id>/status`.
- Direct application routes (4): `/favicon.ico`, `/robots.txt`, `/sitemap.xml`,
  `/ads.txt`. Flask also registers `/static/<path:filename>`.

### Non-page routes, APIs and workflows to retain

Generation/refinement: `/generate`, `/refine-prompt`, `/refine-image-prompt`,
`/generate-from-image`, `/generate-image`, `/generate-voice`, and
`/generation/<int:generation_id>/retry`.

Billing: payment initialization variants, `/payment/callback`, `/payment/webhook`,
`/upgrade`, `/unlock-download/<int:generation_id>`, downloads and `/fal/webhook`.

Admin data/actions: generation retry/refund, user tier/credit/ban/delete controls,
CSV exports, pricing, provider health, content/blog/newsletter/distribution controls,
Paystack logs, promo campaigns, and notification broadcast.

Background/integration: newsletter cron endpoints, Telegram webhook/setup/status,
OAuth connected-account routes, publishing APIs, campaign/automation APIs,
Movie Studio generation/render/status endpoints, sitemap, robots, ads, favicon and
IndexNow verification file. These routes do not each have a page template but remain
in the route-retention and regression checklist.

## Notification implementation and validation checklist

- [x] Preserve existing `Notification` records, ownership field and unread-list API
      array response; unread count is supplied as `X-Unread-Count`.
- [x] Keep individual read endpoint owner-scoped; add owner-scoped paginated history
      and idempotent mark-all endpoint.
- [x] Classify existing title/message/type values into display/filter categories;
      no notifications are synthesized and no model migration is required.
- [x] One visible bell per breakpoint/layout; desktop and mobile triggers share one
      accessible panel. Admin and regular authenticated shells are included.
- [x] Desktop anchored dropdown and responsive mobile bottom sheet; close, Escape,
      touch-sized targets, unread badge, filters, mark-all, timestamps and history link.
- [x] Dedicated history page with all/read/unread, categories, bounded search,
      20-item pagination, empty/loading/error states and same-origin destinations.
- [x] Dynamic notification copy is inserted as text, not HTML; external destinations
      are not treated as in-app navigation.
- [x] Targeted API/page test passes for ownership, category/status filters, individual
      read, mark-all and rendered page.
- [x] Signed-in Director-tier page empty state, one visible bell and panel sizing
      checked in the browser at 320, 360, 390, 430, 768, 1280 and 1440 CSS pixels.
      The mobile panel fits available viewport width and the desktop panel remains
      bounded and right-anchored.
- [ ] Browser-check desktop and admin headers, dropdown, focus behavior and panel.
- [ ] Browser-check normal-tier users, populated categories/actions, 2xx/5xx failures,
      refresh persistence, and admin layout behavior at all viewport breakpoints.
- [ ] Verify all tiers, normal/admin sessions, empty/error states and page-refresh
      persistence in browser tests.
- [ ] Verify notification destinations and all category mappings against real records.

## Complete page-by-page implementation checklist

- [x] Discover every registered route, blueprint and current Jinja template.
- [x] Record orphan/unlinked templates and standalone layouts.
- [ ] Review each page's rendered controls, forms, modals, dropdowns, fetch/AJAX,
      loading/error/empty states, access checks, navigation destinations and tiers.
- [ ] Decide for every page: fully redesign, intentionally retain with justification,
      merge with behavior preserved, or deprecate with justification and confirmation.
- [ ] Redesign and test all public pages and auth flows.
- [ ] Redesign and test all authenticated pages, subscription-specific access states,
      and upgrade paths.
- [ ] Redesign and test all admin pages, tables, tabs, forms and actions.
- [ ] Test mobile navigation and each page at 320, 360, 390 and 430px plus desktop.
- [ ] Compare the final registered route/template inventory to this baseline and close
      every pending item before claiming completion.

