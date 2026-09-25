# Chore Stars

Household participation board. Stars only. Cash is paid outside the app.

Fiscal week is Thursday–Wednesday, `America/Indiana/Indianapolis`. The purse is 100 stars. Advertised chores may add up to more than that. Parents may award past 100; the extra is an **owe**.

Live site: `https://cs.thompsons.space`.

## Loop

1. A job opens today's slots from templates.
2. A resident grabs one open slot. The grab locks the advertised star value and expires after 45 minutes.
3. They take a before photo, do the work, take an after photo, and submit.
4. A parent reviews the photos and awards, sends back, or rejects.
5. The resident claims awarded stars. Thursday, parents pay cash from claimed stars.

Only residents can grab. One active grab at a time.

## Run

```sh
nix develop
CHORES_DEV_AUTH=1 chore-stars serve
```

Dev auth lists seed users on `/login` (Dad, Mom, Alex, Sam, Riley, Kitchen). Tests run inside `nix build`.

Production is the NixOS module `nixosModules.default` (`services.chore-stars`). Postgres database `chores`, photos in `/var/lib/chores/photos`, Caddy on the configured domain.

## Parent desk

Open **Parent** in the bottom dock. Only a signed-in parent can use it. The line under the title is the week meter: `awarded / 100`, or `awarded / 100 · owe N` when awards plus the pool adjustment exceed the budget.

### Live grabs

Slots someone is holding and has not finished review. Status is `grabbed` (photos in progress) or `submitted` (waiting on you).

**Ungrab** releases that hold and reopens the slot so someone else can take it. It does not award stars. It only works on an active grab. The same button is on the wall. After ungrab the browser goes to the wall.

Use this when a phone was abandoned mid-chore. Do not use it to undo an award; awarded grabs are not in this list.

### Review stream

Submitted work, newest first. Tap a row to open the review page.

The review page shows before and after photos. The star field starts at the value locked when they grabbed. You can type a different number. A note is optional.

- **Award** writes that many stars to their ledger, marks the slot awarded, posts it on the wall, and marks them Present for the week. Awarding past the pool raises **owe**.
- **Send back** returns the grab to them, clears the submit time, and starts a new 45-minute timer. The slot stays theirs. Use this when a photo is missing or the work is not done.
- **Reject** drops the grab and reopens the slot. No stars. Someone else can grab it.

### Standing roster

Each resident this week is **present** (at least one award), **quiet** (none yet), or **infraction** (still at zero after the cutoff, or you marked a miss).

- **Clear** forgives a miss for this week. If they already have an award they stay Present; otherwise they go back to Quiet. The nightly check will not re-mark them until next week.
- **Miss** marks an infraction now, even before the cutoff. A later award clears that flag and marks them Present.
- **Revoke** records a privilege flag for today (games / phone reminder). The app does not lock a device. There is no restore button on the desk.

### Open slot values

Every still-open slot for this week, with its date and sequence. **Set** changes the advertised stars. Grabs already in progress keep the value they locked. Only open slots can be edited here.

### Pool adjust

A signed number added to this week's pool adjustment. **Positive shrinks owe.** Owe is `max(0, awarded − 100 − adjustment)`. Negative adjustment can raise owe without awarding anyone. The change is stored as an adjust event on the parent, not as resident stars.

### Payout split

Type a dollar total and **Split**. Each resident's share is that total times their awarded stars divided by all awarded stars this week. Shares are in cents and add up to the total. If nobody has an award yet, it says so. This does not send money.

### Pair a device

**Make code** prints a 6-digit code that lasts 20 minutes. Redeem it on `/login`. The QR / NFC page is one URL, `https://cs.thompsons.space/board`, not a per-person code.

- **Kiosk** and no person selected creates a new user named Kitchen.
- **Resident phone** or **Parent phone** should have a person selected. The code signs that existing user in on the new device.

## Wall controls

These are not on the desk. On the wall, parents also see:

- **Ungrab** on a live grab (same as the desk).
- **Hide** on an awarded post. Residents and the kiosk stop seeing it. Parents still see it, dimmed, with **Unhide**.
