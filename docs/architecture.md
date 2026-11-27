# Architecture

How HomePool is put together, for anyone about to change it. The *why* behind
the numbers (turnovers, temperature curve, chlorine demand) is in
[design-v1.md](design-v1.md), in Spanish. What users see is in the
[README](../README.md).

## The shape of it

```
config entry ──► PoolCoordinator (coordinator.py)   one per pool, every 60 s
                   │
                   ├─ reads   Home Assistant states (pump, sensors, weather)
                   ├─ asks    pool/filtration_calculator  → daily target
                   │          pool/chlorine_calculator    → chlorine part
                   │          modes/<mode>                → what the mode wants
                   │          pool/scheduler.arbitrate    → what actually happens
                   │          pool/safety, chlorinator_wanted
                   │          pool/season, tasks, checklists, readings,
                   │          treatment, dosing    → the year, the chores
                   ├─ writes  switch.turn_on/off on the pump and chlorinator
                   ├─ keeps   a Store (.storage/homepool.<entry_id>)
                   └─ fires   homepool_* events, alerts, optional notifications
                   ▲
entities (sensor.py, binary_sensor.py, switch.py, select.py, number.py,
button.py) are thin views over the coordinator; services in __init__.py
call its async_* methods.
```

Two rules hold the design together:

- **`pool/` and `modes/` are pure Python.** No Home Assistant imports, no
  clock, no I/O: everything arrives as plain arguments (minutes of the local
  day, temperatures, flags). That is what lets the calculators and the
  authority ladder be tested on their own and reasoned about whole.
- **Only the coordinator touches Home Assistant**, and only the coordinator
  switches anything.

## One evaluation

`PoolCoordinator._async_update_data`, every `EVALUATION_INTERVAL_S` (60 s):

1. **`_async_rollover`** — counts the time since the last pass under the old
   pump state (`_account`), closes the day at local midnight (splitting a run
   that crosses it), raises `target_missed` if a guaranteed mode fell short,
   and handles the chlorinator season.
2. **`_sample_inputs`** — keeps today's highest air reading and pH samples for
   the trend.
3. **`_async_maybe_recalculate`** — at most once every `RECALC_INTERVAL_MIN`
   (60 min): fetches the forecast, runs `calculate_target`, and **never lets
   the target fall during the day** (`held_at_previous`). The
   `recalculate_schedule` service forces it, up or down.
4. **`_async_control`** — evaluates safety and pH, asks the current mode, then
   `arbitrate()`; sends the pump command if the decision changes the pump, and
   then drives the chlorinator from the result.
5. **`_async_alerts`** — raises and clears alerts on their edges.
6. **`_save`** — debounced write of the Store.

Between passes, `_handle_state_change` reacts to the pump, chlorinator and
sensors at once: accounting, confirming HomePool's own commands, and
detecting changes made from outside.

## The daily target

`pool/filtration_calculator.py::calculate_filtration_target` takes a
`FiltrationInputs` and returns the target with every factor and source, which
the target sensor exposes as attributes.

- Base: **two turnovers** of the pool's volume at the pump's flow.
- Factors: season (by month and hemisphere), temperature
  (`TEMPERATURE_TABLE`, calibrated against a manufacturer's table from 18 °C
  up), UV, rain in the last and next 24 h, cover, and the user's multiplier.
- Limits: `min_minutes` (one turnover, easing to half of one in cold water,
  see `minimum_turnovers`) and `max_minutes` (seven turnovers).
- Temperature source, in `coordinator._temperature_inputs`: water probe →
  highest measured air today or yesterday, capped at the forecast high + 3 °C →
  forecast high → none. Estimated water = air − 2 °C.

The chlorine part (`pool/chlorine_calculator.py`) works out the minutes the
cell must produce to cover the day's demand. The daily target is the larger of
the two (`dominant_component`).

## Modes

`modes/base.py` defines `OperationMode.evaluate(PoolContext) -> PumpDecision`.
A mode answers one question: *should the pump run now to cover today's
target?* It knows nothing about locks, safety or people. `MODE_REGISTRY` in
`modes/__init__.py` lists them: `off`, `timer`, `smart` (a block centred on
solar noon), `solar` (surplus only) and `smart_solar` (surplus, finishing from
the grid before the day ends). `guarantees_target` says whether a short day
raises `target_missed`.

To add a mode:
1. Subclass `OperationMode`.
2. Give each decision a `key`.
3. Add its texts to `texts.REASONS`.
4. Register it in `MODE_REGISTRY`.
5. Add it to `available_modes` if it needs equipment.
6. Add the select option to the strings generator.
7. Write tests.

## Who decides: `pool/scheduler.py::arbitrate`

From most to least authority; the first that applies decides:

| Rung | Source | Pump |
|---|---|---|
| Pump switch unavailable | `unavailable` | left alone |
| Hands-off entity on | `hands_off` | left alone |
| Maintenance lock | `maintenance_lock` | off |
| Passive wintering (`season_state` = `winter_passive`) | `winter_passive` | off, and a pump switched on by hand is switched off again |
| Safety shutoff (flood, hot equipment room, filter pressure, pump power anomaly) | `safety` | off |
| Freeze protection (never in passive wintering) | `freeze_protection` | on, in every mode |
| Water treatment | `treatment` | by phase: on (`filtering`, `mixing`), off (`settling`), `None` (`vacuuming`, the owner's) |
| pH correction window (not in `off`, not on an implausible probe reading, never on a manual pH) | `ph_correction` | on, capped per day |
| Manual cycle | `manual_cycle` | on |
| Changed from outside, for `manual_override_minutes` | `manual_override` | as it was left |
| The mode | `mode` | what the mode says |

Passive wintering sits at the lock's level: with the pipes drained, running the
pump dry can damage it, so only hands-off, above, lets someone run it. A
treatment is decided on its phase key, not on the pump value: in `vacuuming` the
pump is `None`, and the rung still holds the pump for the owner so the relay's
own switch is not read as an outside change. `treatment` is in
`FORCING_SOURCES`, so a pump it started (and `started_by` remembers) is let go
when it ends, and a treatment starts the pump even in `off`, because a person
asked for it.

The minimum run (`MIN_ON_MINUTES`, 20) and rest (`MIN_OFF_MINUTES`, 10) times
apply only to the mode's decisions, wrapped as `min_run` / `min_rest`. When a
forcing reason ends and the mode has no opinion, a pump HomePool started
(`started_by`) is switched off again.

**Changes from outside.** A pump change is HomePool's own if it carries the
context of one of its commands, or matches a command sent within
`OWN_CHANGE_WINDOW_S` (for relays that confirm late). Otherwise it is
attributed by `_changed_by`:
- an automation or script whose `automation_triggered` / `script_started`
  context it carries, or a child of it, recorded by a `@callback` listener;
- a person, if the context has a `user_id`;
- otherwise `external` (a wall switch, the device's button).

## Commands

`_async_command` sends `switch.turn_on/off` under a fresh `Context` remembered
in `_own_contexts`, and tracks it as pending. A relay that does not follow is
retried every `COMMAND_RETRY_S` (20 s), up to `COMMAND_MAX_ATTEMPTS` (3), then
raises `pump_not_responding` or `chlorinator_not_responding`. Before stopping
the pump, HomePool stops the cell and waits for it, but only while the cell's
retries last; then the pump stops anyway.

With a power sensor and a nominal power, a pump drawing far from nominal while
on (above 1.5× or below 0.3×) for `ANOMALY_MINUTES` is a safety shutoff
(`pump_power_anomaly`).

## Season, tasks and treatments (0.2)

Pure modules in `pool/`, driven by the coordinator:

| Module | What it holds |
|---|---|
| `season.py` | `SeasonState`, the calendar (`swimming_months`), `season_proposal()`: what the calendar would propose today, never applied |
| `tasks.py` | The task table: key, action, interval (days or pump hours), when it exists, which states count it |
| `checklists.py` | The step lists `closing`, `opening` and `treatment`, with `only_passive` and `starts_treatment` flags |
| `readings.py` | Kinds, valid values, default ranges, stale ages |
| `treatment.py` | `TreatmentType`, phases and what each wants of the pump |
| `dosing.py` | Shock, clarifier, flocculant and winter product doses, with their inputs |

The coordinator owns the state. The owner confirms season changes
(`async_set_season_state`); `_async_season_proposal` only creates, repeats
weekly and clears a `season_proposal`. Treatment phases that run the pump count
**pump-running time** (so a lock pauses them), `settling` counts clock time
except while freeze protection runs the pump and not across Home Assistant
downtime. Stale readings never set the status to `attention`, and are absent in
passive wintering (salt is never stale while the cell is not in use).

## The chlorinator

`chlorinator_wanted()` turns the cell on only with water flowing for
`CHLORINATOR_FLOW_DELAY_S`, inside its season, with the master switch
*Chlorinator in use* on, the water warm enough, and the day's chlorine not yet
produced. Since 0.2 the season is the season state's
(`PoolCoordinator.cell_in_season`: `swimming`, and `opening` once the cell is in
use; never in wintering), and the same answer decides the chlorine part of the
target and the salt and cell alerts. `chlorinator_active_months` only seeds
`swimming_months` and fires the 0.1 season events. A maintenance lock or safety shutoff blocks
it.

## State that survives a restart

`_to_store` / `async_load` keep the following in one Store per entry:
- today's counters (`elapsed_s`, `chlorine_s`, `ph_correction_s`);
- the target and when it was worked out;
- runtime settings (mode, multiplier, chlorinator in use…);
- maintenance tasks and manual readings, plus `tasks_since`, `task_pump_s`
  (pump seconds per task) and `task_first_seen` (on the first load of 0.2 the
  0.1.4 rows get `tasks_since`; any other row counts from when it first
  appears, so neither an update nor a new probe makes it overdue);
- `winter_entered`, `winter_top_up_from` (a winter product added while closing
  counts for that winter) and `in_season_last`;
- `season_proposal` (with `dismissed_for`), `checklists` (by id), `treatment`
  (type, phase, pump-time and settle counters, when vacuuming was last
  reminded), `backwash_after_treatment`, `treatment_rest_today` (a day spent
  settling or vacuuming misses no target), `closing_needs_pump_notified` and `after_shock_since` (swimming
  stays not advised after a shock);
- a short `history` of closed days;
- `air_max`;
- the pending override, cycle and pH window.

New fields need a default when read. `STORAGE_VERSION` and `CONFIG_VERSION`
change only for incompatible changes, with a migration.

## Entities

Every entity derives from `entity.PoolEntity` with unique id
`<entry_id>_<key>` and `has_entity_name`. Names come from the translations,
ids from Home Assistant's language at creation. Most sensors are a
`PoolSensorDescription` with a `value_fn` and an optional `attrs_fn`. Large
or fast-changing attributes go in `_unrecorded_attributes` so the recorder does
not store them every minute.

## The card's contract

[homepool-card](https://github.com/domotk/homepool-card) finds a pool by its
daily-target sensor and reads:
- `card_attributes()` on it: `pool_entities` (key → entity id, the card's
  index), shape, dimensions, layout, liner colour, volume, the user's linked
  entities and lights;
- the target sensor's factors, `min_minutes` and `max_minutes`;
- the control sensor's state, `reason`, `reason_key` and
  `manual_override_by`. Since 0.2 the state can be `winter_passive` or
  `treatment`; `next_manual_task` gains `checklists`, a dict keyed by list id
  (`closing`, `opening`, `treatment`: several can be open at once). Each list
  is its steps in order, each with `id`, `text`, `done`, `done_at`,
  `starts_treatment` (the treatment the card offers to start, or `null`) and
  `needs_pump`; a treatment's `treatment.dose` step also carries `dose`.

Treat these as a public API: add, don't rename.

## Text and languages

- **Interface text** (wizard, options, entity names, selector options, services,
  exceptions) is written once in `scripts/generate_strings.py` as
  `(english, spanish)` pairs, and the script writes `strings.json`,
  `translations/en.json` and `translations/es.json`. Pool-layout labels take
  their English from `data/layouts.yaml` and their Spanish from `LAYOUT_ES`.
- **Runtime text** (alerts, notifications, reasons) is in `texts.py`, picked
  by `hass.config.language`, English otherwise.

## Events and notifications

Each pool fires these events with its `entry_id` and name:
- `homepool_alert`
- `homepool_safety_shutoff`
- `homepool_target_recalculated`
- `homepool_manual_action_due`
- `homepool_chlorinator_season_start` / `_end`
- `homepool_season_proposal` and `homepool_season_state_changed`
- `homepool_treatment_started`, `homepool_treatment_phase` and
  `homepool_treatment_ended`

Alerts are also binary sensors. `notify_dispatcher.py` is optional: it
forwards alerts to one `notify.*` service, filtered by severity and quiet hours.
Reminders (tasks falling due, a season proposal) pass the severity floor;
one that falls in the quiet hours waits in `pending_reminders` until they end.
