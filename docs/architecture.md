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
| Safety shutoff (flood, hot equipment room, filter pressure, pump power anomaly) | `safety` | off |
| Freeze protection | `freeze_protection` | on, in every mode |
| pH correction window | `ph_correction` | on, capped per day |
| Manual cycle | `manual_cycle` | on |
| Changed from outside, for `manual_override_minutes` | `manual_override` | as it was left |
| The mode | `mode` | what the mode says |

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

## The chlorinator

`chlorinator_wanted()` turns the cell on only with water flowing for
`CHLORINATOR_FLOW_DELAY_S`, inside its season (`chlorinator_active_months`,
toggled automatically at season start and end if `chlorinator_auto_toggle`),
with the master switch *Chlorinator in use* on, the water warm enough, and the
day's chlorine not yet produced. A maintenance lock or safety shutoff blocks
it.

## State that survives a restart

`_to_store` / `async_load` keep the following in one Store per entry:
- today's counters (`elapsed_s`, `chlorine_s`, `ph_correction_s`);
- the target and when it was worked out;
- runtime settings (mode, multiplier, chlorinator in use…);
- maintenance tasks and manual readings;
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
  `manual_override_by`.

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

Alerts are also binary sensors. `notify_dispatcher.py` is optional: it
forwards alerts to one `notify.*` service, filtered by severity and quiet hours.
