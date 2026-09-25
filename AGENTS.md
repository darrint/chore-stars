# Agent notes

Household participation PWA. Stars only. A parent payout split is a calculator, not a payment. Do not add payment processing or device-lock features.

## Layout

- `chore_stars/app.py` — routes
- `chore_stars/services.py` — grab, review, ungrab, wall backfill
- `chore_stars/jobs.py` — week, slots, standing, pool
- `chore_stars/seed.py` — templates; advertised capacity may exceed the 100-star purse
- `chore_stars/templates/` — Jinja. Parent desk is `parent.html`; review is `review.html`
- `nix/module.nix` — systemd, postgres, Caddy, 5-minute job timer

## Rules that are easy to break

- The purse stays 100 stars. Advertised template capacity may be higher. `week_advertised_capacity()` is `stars * cap * (7 if day else 1)` and is not capped. Seed updates open-slot stars, deletes extra open slots when a cap drops, and retires `edge-prune-blow` by deactivating it and deleting its open slots.
- Only `role == "resident"` can grab. Kiosk and parent cannot. Dev user Kitchen is a kiosk, not a resident.
- Grab locks `advertised_stars`. Review may award a different amount. Editing an open slot does not change an in-progress lock.
- Award creates a `wall_posts` row. Startup and `/wall` backfill any awarded grab that is missing one.
- Ungrab only releases `status == "active"`. It reopens the slot and does not reverse an award.
- Pool owe is `max(0, awarded_total - star_budget - pool_adjust)`. Positive adjust shrinks owe.
- Clear standing sets `cleared_at` and skips the nightly infraction check unless `parent_marked_miss` is set again. Award calls `mark_present`, which also clears a parent miss.
- Revoke only inserts a `PrivilegeFlag`. Nothing in this app locks a phone.
- Photo forms on the grab page only offer Open camera. Use this shot uploads immediately. Opening the camera again replaces that photo. The picker script is inline in `grab.html` so a stale service worker cannot hide it. Bump `CACHE` in `static/sw.js` when changing cached shell files.
- Do not add comments unless asked.

## Tests

`nix build` runs pytest. Dev login: `CHORES_DEV_AUTH=1`.

## Deploy

The server flake input is `github:darrint/chore-stars`, not this working tree. Local edits do not run until commit, push, `nix flake update chore-stars` in the NixOS config, and a system build. The operator switches; do not `sudo` switch yourself.

OIDC is confidential (no PKCE). The PocketID button appears only when `CHORES_OIDC_CLIENT_ID` and `CHORES_OIDC_CLIENT_SECRET` are in the process environment. Do not commit secrets.
