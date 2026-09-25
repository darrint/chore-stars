# Chore Stars

Household participation system for adult and young-adult residents.
Stars only. Cash is paid outside the app. Culture goal: everyone shows up.

Fiscal week: **Thursday → Wednesday** (Dad payday), `America/Indiana/Indianapolis`.
Week pool: **100 stars**. Parents may award past 100 and carry an **owe**.

## What it is

A shared board of chore *slots*. Residents grab a slot, prove it with before/after photos, parents award stars, residents claim stars, parents hand out cash from claimed stars on Thursday.

The board, wall, and leaderboards make work visible. Sitting at zero is also visible. Non-participation is an infraction against the house culture, not just a missed payday.

## Loop

1. Nightly job opens today's slots from templates.
2. Resident opens the board (home screen PWA, QR, or NFC — same URL).
3. **Grab** one slot (30–60 min lock, one active grab).
4. Before photo → do the work → after photo → submit.
5. Parent reviews the photo stream and sets awarded stars.
6. Resident **claims** awarded stars. Unclaimed awards keep pinging.
7. Thursday: parents pay cash from claimed stars. Owe means the purse ran hot.

Advertised star value can change while a slot is still open. Grab locks the posted value. Review sets the actual award and may go higher or lower.

## Roles

| Role | Auth | Does |
|---|---|---|
| Parent | PocketID + `parents` | templates, values, review, awards, standing, nags |
| Resident | PocketID + `residents` | grab, photos, claim, wall, boards |
| Kiosk | pairing code → session | kitchen tablet wall / board |

Everyone signs in with PocketID passkeys. After that the PWA keeps a session cookie so QR/NFC taps do not bounce through OIDC. Pairing codes are only for a new phone or the tablet.

## Participation and infractions

Stars measure work. Standing measures showing up.

Each resident has a weekly standing:

- **Present** — at least one awarded slot in the current fiscal week
- **Quiet** — no awarded slot yet this week (yellow after Thursday evening)
- **Infraction** — still at zero awarded stars by a cutoff (default: Saturday evening), or a parent-marked miss

Zero stars is the problem, not a low score. A resident who grabs and finishes stays Present even if parents award 1 star. A resident who never grabs is Quiet, then Infraction.

Effects (app-side only):

- Standing chip on the person, the wall, and the boards
- Push to that resident and to parents
- Parent can flip `privilege_flags.revoked` (games / phone reminder). The app does not lock devices.
- Infraction stays on the week record. It does not expire stars.

Parents can clear or mark a miss by hand (sick day, out of town).

## Screens

**Resident**
- Today board: open / mine / done
- Grab + timer
- Camera: before, after
- My stars: pending, ready to claim, claimed
- Wall + boards
- Standing banner if Quiet or Infraction
- Claim-your-stars banner

**Parent**
- Review stream (before/after)
- Award / reject / send back
- Edit advertised stars on open slots
- Week meter: `76 / 100` or `112 / 100 · owe 12`
- Standing roster (Present / Quiet / Infraction)
- Wall hide
- Templates, QR sheet, devices

## Slots

| Template | Cap |
|---|---|
| Load dishwasher | 2 / day, 3★ |
| Unload dishwasher | 2 / day, 2★ |
| Sweep north | 1 / day |
| Sweep south | 1 / day |
| Vacuum rugs | 1 / day |
| Load laundry | 4 / day |
| Sort and distribute clean laundry | 1 / day, higher default |
| Mow lawn | 1 / week |
| Take out trash | 4 / day |
| Scoop litter | 1 / day, 1★ |
| Change litter | 1 / week, 3★ |
| Edge | 1 / week |
| Blow | 1 / week |
| Outdoor weeding | 1 / week |
| Burn boxes | 1 / week |

Two residents may grab remaining slots of the same template.

## Stars

- Pool counts **awarded** stars, not advertised.
- Award may exceed advertised.
- Award may exceed 100. That is **owe**. Thursday cash should cover it.
- Parents can cut advertised values or post a manual pool adjustment to shrink owe.
- Claimed stars are what payday uses.
- Unclaimed awards stay on the ledger and ping. They do not expire.

## Wall and boards

**Wall** — awarded after-photos, newest first. Name, chore, stars, standing chip. Parent can hide. Before-photos stay in review only.

**Boards** (this fiscal week + all-time)

- Stars claimed
- Stars awarded
- Slots finished
- Streak (days with a claim)
- Standing / misses this week

Quiet and Infraction sit at the bottom on purpose.

## Architecture

One PWA on the NixOS home server. No Expo in v1.

```
Phones / kitchen tablet (PWA)
        HTTPS
Caddy
        → chores app (FastAPI or Django)
PocketID     OIDC, groups parents + residents
Postgres     source of truth
Photos       local disk, thumbs for stream/wall
ntfy + Web Push
systemd timer for slots, grab expiry, nags, Thursday rollover
```

Photos: `/var/lib/chores/photos/{week}/{grab}/{before,after}.jpg`
Auth: PocketID OIDC → session cookie
QR/NFC: same HTTPS URLs (`/board`, optional `/c/dishwasher`)
LAN + Netbird first. PocketID + HTTPS if exposed.

Jobs each day:
- open slots
- expire stale grabs
- standing check (Quiet → Infraction)
- nags: open slots, unclaimed daily/weekly stars, zero-star residents, Thursday owe

## Data

```
users            pocket_id_sub, name, role
devices          user_id, push_endpoint
chore_templates  slug, title, default_stars, caps, period
weeks            thu_start, star_budget, awarded_total, owe_stars
chore_slots      week_id, template_id, slot_date, advertised_stars, status
grabs            slot_id, user_id, timestamps
proofs           grab_id, kind, path
reviews          grab_id, parent_id, awarded_stars, note
star_events      user_id, week_id, kind (award|claim|adjust), amount
standings        user_id, week_id, status, misses, cleared_at
privilege_flags  user_id, day, revoked
wall_posts       grab_id, user_id, published_at, hidden_at
```

## Build order

1. PocketID login, users, templates, slot generator, board
2. Grab, photos, review, pool + owe
3. Claim, Thursday week, wall, boards, standing
4. ntfy / Web Push: undone slots, unclaimed stars, zero-star infractions, owe

Skip rewards store, AI photo judging, native apps until the house is using the loop.
