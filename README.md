# HomePool

[![hacs][hacs-badge]][hacs-url]
[![release][release-badge]][release-url]
[![validate][validate-badge]][validate-url]
[![licence][licence-badge]](LICENSE)

Runs a pool's filtration pump and salt chlorinator from the entities you
already have — a smart plug for the pump, a thermometer if there is one, the
grid meter if you have solar — and works out each day how long the water
actually needs to move.

A pool does not need eight hours of filtration every day. In January it needs
two; in a hot August week it needs thirteen. The figure depends on the volume,
the pump's flow, the water temperature, the sun, the rain and whether the pool
was covered. HomePool calculates it every day, runs the pump to meet it, counts
every minute the pump is on no matter who switched it, and tells you what it is
doing and why.

## Why an integration and not a few automations

Because the automations it replaces fail in ways you only notice weeks later:

- **A target that depends on one weather service.** When the service goes
  down, the target goes `unavailable` and the pump does not run at all — for
  days, with full sun.
- **A top-up that crosses midnight.** The counter resets at 00:00, so the hour
  run from 23:00 to 01:00 is half lost, and the next day starts behind.
- **Production mistaken for surplus.** "Panels above 1100 W" is not "spare
  power": a house cooking lunch has no spare power at 1100 W, and the pump ends
  up running on the grid in the middle of the day.
- **A target that changes during the day.** A cloud cools the air, the target
  drops, the pump stops half way, and the day ends short.
- **A pump cycled every few minutes** by a surplus that crosses the threshold
  back and forth — partly because of the pump's own draw.

HomePool keeps its own count in `.storage`, works with or without any of the
sensors it can use, and has one place where every decision about the pump is
made, with the reason written on a sensor.

## How the daily target is worked out

Two turnovers of the pool's volume is the base. That is multiplied by factors
for the season, the water temperature, the UV index, rain in the last and next
24 hours, the cover and your own calibration knob, and kept between one and
seven turnovers in warm water. From 18 °C up the temperature curve is calibrated against a
manufacturer's table: 8 h at 24 °C, 10 h at 26 °C, 13 h above 28 °C. Below
15 °C it falls faster, and the floor eases from one turnover to half of one at
12 °C and below: cold water barely needs moving, and a winter day of a typical
pool lands between one and two hours.

With a salt chlorinator there is a second demand: the hours the cell needs to
produce the chlorine the water uses, which depends on temperature, salt level
and the production setting. The target is the larger of the two — not the sum,
because both happen while the same pump runs.

Every factor, the value it came from and the source of that value are
attributes of `sensor.<pool>_daily_filtration_target`, so you can always see
why today's figure is what it is.

Three rules keep the target honest:

- **No sensor is required.** Without a water thermometer, the air temperature
  stands in for it: the highest your own sensor measured today or yesterday,
  or the forecast's daily high if there is no sensor. With both, the measured
  figure may top the forecast by 3 °C at most, so a sensor in the sun or on a
  heat pump's outdoor unit cannot inflate the target; keep it in the shade
  anyway. Without any of them the factor stays neutral and the target is
  still there. The `min_minutes` and `max_minutes` attributes give the floor
  and ceiling the target is held between.
- **It is recalculated every hour, and during the day it only goes up.** A day's
  demand does not shrink because a cloud passed. When the target is held,
  `held_at_previous` is true and `calculated_minutes` says what the latest
  calculation asked for. `homepool.recalculate_schedule` forces a fresh
  figure, up or down. The forecast used is the entry dated today, so just
  after midnight it is not still yesterday's.
- **A day ends at midnight.** Guaranteed modes finish before it; whatever is
  missing is reported, not carried over into the night.

## Operation modes

| Mode | What it does | Meets the target |
| --- | --- | --- |
| `off` | Nothing. HomePool counts and warns. **The default** — installing it switches nothing, except freeze protection. | No |
| `timer` | Fixed slots, like a mechanical timer. | No |
| `smart` | One block a day, centred on solar noon, finishing before midnight. | Yes |
| `solar` | Only on solar surplus. A cloudy day ends short, and says so. | No |
| `smart_solar` | On surplus first; tops up from the grid as late as possible, before midnight. | Yes |

The solar modes need a surplus sensor, ideally the grid meter. HomePool adds
the pump's own draw back while it runs, so a pump that starts on surplus does
not immediately see none and stop. The surplus has to hold for 5 minutes to
start the pump. Once it runs, a small import is tolerated — up to 400 W by
default, so a kettle or an oven does not stop it — and only 10 minutes of
importing more than that stop it. In practice the pump can keep running on a
small import as the sun drops in the late afternoon; set the tolerance to 0 if
you would rather it never imported at all. The pump also
runs at least 20 minutes and rests at least 10 between starts.

## Who decides

Several things can want the pump on or off at once. One decides, in this order:

1. **Hands off** — an entity of yours (an `input_boolean`, say) that means
   "nobody touches the pump". HomePool never switches it while that is on, and
   keeps counting.
2. **Maintenance lock** — forces it off.
3. **Safety shutoff** — flood in the equipment room, room too hot, filter
   pressure too high, or a pump drawing far more or far less than it should.
   Forces it off.
4. **Freeze protection** — water near 0 °C (or air below zero if there is no
   water probe). Forces it **on**, in every mode including `off`: moving
   water does not freeze in the pipes. Switch it off in the options if HomePool
   must never touch the pump. If something above it keeps the pump off (the
   maintenance lock, say), the freeze alert says so instead of claiming the
   pump is running.
5. **pH correction** — a dosing pump only works with water flowing, so a pH
   that needs correcting runs the pump for a while, capped per day so a faulty
   probe cannot run it all night. Not in `off` mode, and not on a reading that
   cannot be right (outside 5–9, or exactly the same for 24 hours, as from a
   probe left in its cup); a window asked for with `homepool.force_ph_correction_window`
   still runs.
6. **Manual cycle** — started from HomePool's button, switch or service.
7. **Switched from outside** — a person, an automation, a script or the
   device's own button switched the relay. That is respected for two hours
   (configurable) instead of being undone a minute later, and the reason says
   which it was, naming the automation or script. A relay that confirms late
   may report an automation's change as made outside HomePool.
8. **The mode.**

`sensor.<pool>_pump_control` says which of these is in charge right now. Its
`reason` attribute says why, in Home Assistant's language, and `reason_key`
gives the same as a short code that the history keeps.

A relay that ignores a command — some smart plugs reject the first request
after a while idle — gets it again after 20 seconds, up to three times, and
then an alert is raised.

## The salt chlorinator

Three set-ups, three behaviours:

- **The cell has its own switch.** HomePool runs it only with water flowing —
  two minutes after the pump starts, and always off *before* the pump stops —
  and only until today's chlorine is produced, so the pool is not
  over-chlorinated on long filtration days. The cell is also kept off below its
  minimum water temperature.
- **The cell is wired with the pump** and does not regulate itself. HomePool
  cannot switch it, so it recommends the production percentage that would
  produce exactly what the water needs.
- **The cell regulates itself** (ORP or chlorine probe). HomePool only watches.

The season is a list of months (June–September by default in the northern
hemisphere). At its start and end you get an event with what to check, and the
chlorinator follows the calendar unless you tell it not to. With *Chlorinator
in use* off, the cell adds no minutes to the target and low salt is not an
alert; out of season, neither does it.

## Entities

Each pool becomes one device, linked to the device of the pump's relay. Which
entities exist depends on what you connected.

| Entity | What it is |
| --- | --- |
| `sensor.<pool>_daily_filtration_target` | Today's target, in minutes. Every factor and source in its attributes |
| `sensor.<pool>_filtration_today` · `_filtration_left_today` | Minutes run today, and what is left |
| `sensor.<pool>_pump_control` | Who is deciding the pump right now, and why |
| `sensor.<pool>_status` | `ok`, `attention` or `action_required`, with the active alerts |
| `sensor.<pool>_next_manual_task` | Backwash, filter cleaning or probe calibration, whichever is due first |
| `sensor.<pool>_recommended_chlorinator_production` | The production % that matches today's demand |
| `sensor.<pool>_chlorine_production_today` · `_left_today` | Cell running time, with a separate cell switch |
| `sensor.<pool>_salinity` · `_free_chlorine` | From a sensor, or from the last reading you recorded |
| `sensor.<pool>_ph_trend` | Rising, stable or falling over the last three hours |
| `sensor.<pool>_pump_energy_today` · `_pump_cost_today` | With an energy sensor, and a price |
| `binary_sensor.<pool>_daily_target_reached` · `_pump_running` | |
| `binary_sensor.<pool>_safety_shutoff` · `_freeze_protection` · `_pump_power_anomaly` | |
| `binary_sensor.<pool>_ph_out_of_range` · `_ph_correction` · `_filter_needs_cleaning` · `_manual_task_due` | |
| `select.<pool>_operation_mode` | The five modes; the solar ones only with a surplus sensor |
| `switch.<pool>_pump` | The pump through HomePool: a manual cycle that still respects lock and safety |
| `switch.<pool>_maintenance_lock` | |
| `switch.<pool>_chlorinator_in_use` | Whether HomePool counts and runs the chlorinator at all. It does not switch the cell by itself |
| `number.<pool>_filtration_multiplier` | 0.5–2: your calibration knob for the whole target |
| `number.<pool>_solar_surplus_threshold` · `_ph_target` · `_chlorinator_production` | |
| `button.<pool>_start_cycle` · `_stop_cycle` · `_backwash_done` · `_filter_cleaned` · `_salt_added` · `_ph_probe_calibrated` · `_recalculate_target` | |

Entity ids follow Home Assistant's language when the pool is added: in
Spanish the target is `sensor.<pool>_objetivo_de_filtracion_diario`, not
`sensor.<pool>_daily_filtration_target`. The ids above are the English ones;
the card and the services find the entities by themselves either way.

HomePool does not copy your sensors into new entities: the pH, temperatures,
pressure and power stay where they are. Their entity ids are listed in the
target sensor's attributes for the card.

## Services

| Service | What it does |
| --- | --- |
| `homepool.start_cycle` | Runs the pump for `duration` minutes (one turnover if left out) |
| `homepool.stop_cycle` | Stops a manual cycle and holds the pump off for the override time |
| `homepool.record_manual_action` | Logs backwash, salt added, probe calibrated, … and resets its reminder. A task never logged counts from when HomePool was installed (or updated to 0.1.4), so press its button the next time you do it |
| `homepool.record_salt_level` · `homepool.record_free_chlorine` | A reading taken by hand, used until a newer one |
| `homepool.recalculate_schedule` | Today's target again, now — the only way it can go down during the day |
| `homepool.force_ph_correction_window` | Runs the pump so the pH doser can work |
| `homepool.reset_daily_counters` | Starts today's count from zero |

All of them take the usual target picker: a pool's device, any of its
entities, an area.

## Events

`homepool_alert` (with `type`, `severity`, `message`), `homepool_safety_shutoff`,
`homepool_target_recalculated`, `homepool_manual_action_due`,
`homepool_chlorinator_season_start` and `homepool_chlorinator_season_end`. They
fire whether or not built-in notifications are on, so automations keep working
either way. The built-in notifications, if you switch them on, go to one
`notify` service with a severity floor and quiet hours. Reminders (a task
falling due, the season changing) ask you to do something, so they are sent
whatever the floor; one that falls in the quiet hours is sent when they end.

## Installation

HACS → three-dot menu → *Custom repositories* → this repository, category
*Integration*. Then install and restart Home Assistant.

Needs Home Assistant 2024.11 or newer.

## Setting it up

Add the integration and answer the questions in order: name and location,
shape and size (it works out the volume and lets you correct it), construction,
pump and filter, water treatment, the chlorinator if it is salt, your entities,
and control and notifications. Pumps and chlorinators in the built-in catalogue
fill in their own figures.

**Only the pump switch is required.** Everything else is optional, and each
sensor you add unlocks something: a water thermometer refines the target, a
power meter enables the anomaly check and the solar modes need a surplus
sensor. Everything can be changed later from the integration's options, one
group at a time.

The mode starts at `off`. Look at the target for a day or two, then pick a mode.

## Diagnostics

The device page offers a download with the configuration (location redacted),
the last decision and its reason, pending commands, the safety state, today's
target with every factor, active alerts and the stored history — everything
needed to work out why a pool behaves as it does.

## The card

[HomePool Card][card] draws the pool from its own shape and size, with the
water moving while the pump runs, and today's progress against the target.

It lives in its own repository because HACS treats a repository as one category
and this one is an integration. The integration is perfectly usable without it:
every figure the card shows is an entity you can put on any dashboard.

## Contributing

HomePool is built to be extended by the people who use it. Start with
[CONTRIBUTING.md](CONTRIBUTING.md); the code is explained in
[docs/architecture.md](docs/architecture.md), and [AGENTS.md](AGENTS.md) is the
short guide that AI coding agents read. To try a version on your own pool,
see [testing on a real install](docs/testing-on-a-real-install.md).

The hardware catalogue (`data/catalog.yaml`) and the pool layouts
(`data/layouts.yaml`) take pull requests: see
[contributing to the catalogue](docs/contributing-catalog.md) and
[contributing layouts](docs/contributing-layouts.md). The reasoning behind the
algorithm is in the [design document](docs/design-v1.md) (Spanish).

The interface text — wizard, options, entity names, services — is written in
`scripts/generate_strings.py`, in English and Spanish, and
`python scripts/generate_strings.py` writes `strings.json` and the
translations from it; don't edit those by hand.

To run the tests:

```bash
pip install -r requirements_test.txt
python -m pytest
```

## Built with

Every push is checked by
[hassfest](https://developers.home-assistant.io/blog/2020/04/16/hassfest/),
Home Assistant's own integration validator, by the
[HACS action](https://github.com/hacs/action), and by the test suite: the
calculators against the manufacturer's table, every mode simulated over whole
days, and the integration itself on a real Home Assistant.

## Licence

MIT. Product names in the catalogue belong to their respective owners.

[card]: https://github.com/domotk/homepool-card
[hacs-badge]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg
[hacs-url]: https://github.com/hacs/integration
[release-badge]: https://img.shields.io/github/v/release/domotk/homepool
[release-url]: https://github.com/domotk/homepool/releases
[validate-badge]: https://github.com/domotk/homepool/actions/workflows/validate.yml/badge.svg
[validate-url]: https://github.com/domotk/homepool/actions/workflows/validate.yml
[licence-badge]: https://img.shields.io/github/license/domotk/homepool
