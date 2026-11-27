# Testing on a real install

Unit tests run on simulated switches that obey instantly. Real relays confirm
late, real sensors sit in the sun, and real households have automations of
their own. Every release so far was shaped by a test like this one. This is how
to run one safely, by hand or with an AI agent that has access to your Home
Assistant.

## Ground rules

- **Start in `off` mode**, next to whatever runs your pump today. In `off`,
  HomePool never switches the pump (except freeze protection, which you can
  leave off for the test). It still calculates, counts and explains, so you can
  compare it with reality before handing it control.
- **Back up** `custom_components/homepool`, the card's file and
  `.storage/homepool*` before replacing them, with the date in the name, so
  you can go back to the previous version.
- **Restart once**, when the person who owns the installation agrees.
- **Report, don't fix.** If something is wrong, write it down with the data.
  Do not edit HomePool's code or configuration on the live system to make it
  pass. That hides exactly what the test is for.
- **An agent follows these rules strictly**. It does not:
  - touch the pump, the chlorinator or the house's automations;
  - change options;
  - restart without asking.
- **Ask before anything that moves the pump or changes the season.** That
  covers:
  - `set_season_state`, and above all `winter_passive`, which keeps the pump
    off and freeze protection with it;
  - the treatment services (`start_treatment`, `advance_treatment`,
    `end_treatment`);
  - `start_cycle`, `stop_cycle`, `force_ph_correction_window`;
  - the buttons that do the same.

  Run a treatment only when the owner is really treating the water.
- **Record only what really happened.** Do not tick a task, a checklist step
  or a reading that was not done or measured. A made-up date or value skews
  the reminders for months.
- **Leave the store alone.** Do not edit `.storage/homepool*` by hand; back it
  up with the rest.

## Installing a version to test

1. Download the release's source (`.../archive/refs/tags/vX.Y.Z.tar.gz`) and
   copy only `custom_components/homepool`. Check that `manifest.json` has the
   version you expect.
2. For the card, take `dist/homepool-card.js` from the same tag in
   homepool-card. Bump the Lovelace resource's `?v=X.Y.Z` so browsers reload
   it.
3. Restart.
4. Call `homepool.recalculate_schedule` once: during a day the target only goes
   up, so without it today keeps the old version's figure until midnight.

## What to look at

| Where | What it tells you |
|---|---|
| `sensor.<pool>_daily_filtration_target` attributes | Every factor and its source, `min_minutes` / `max_minutes`, whether the figure was held |
| `sensor.<pool>_pump_control` | Who is in charge now; `reason`, `reason_key`, `manual_override_by` |
| `sensor.<pool>_filtration_today` against the relay's own history | Whether counting is right (it should agree within a minute) |
| `select.<pool>_season_state` and its `proposal` attribute | The season HomePool believes it is in, and the change it proposes |
| `sensor.<pool>_next_manual_task`: `tasks`, `checklists`, `recent_actions` | What is due, when each task was last done, the open closing or opening list |
| The reading sensors (`free_chlorine`, `ph_manual`, `combined_chlorine`, …) | Each value, its range, and when it was last recorded |
| Diagnostics download | The whole controller state, including the store |
| The log, filtered on `homepool` | Warnings, and at info level each change attributed to a person, an automation or the device |

Things worth catching on camera: midnight (counters reset, the day lands in
`history`, a run crossing it is split, the target uses the new day's forecast),
an automation switching the pump, a switch from the interface, and anything the
card shows that the sensors don't explain. With permission, passive wintering
is worth a few minutes: switch the pump on by hand and time how long HomePool
takes to switch it off again, since a real relay confirms late.

## Reporting

Open an issue, or send it to whoever asked for the test, in this order:

1. A five-line summary: what works, what doesn't, worst first.
2. How the update went.
3. Each check: OK, FAIL or NOT TESTED, with the data.
4. A table of readings over time: time, target, temperature and source,
   minutes counted vs real, control source, `reason_key`.
5. The card: console version line and errors, what it showed.
6. The log lines, verbatim.
7. The diagnostics' `controller` section.

Keep personal details out: town, addresses, names, entity ids that give them
away.
