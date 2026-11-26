# AGENTS.md

Guidance for AI coding agents (Claude Code, Codex, Cursor, Copilot and the
like) and for the people driving them. Humans should start with
[CONTRIBUTING.md](CONTRIBUTING.md); everything here applies to them too.

## What this is

HomePool is a Home Assistant custom integration, installed through HACS, that
runs a pool's pump and salt chlorinator: it works out a daily filtration target
and decides, minute by minute, whether the pump runs. Its companion Lovelace
card lives in a separate repository,
[domotk/homepool-card](https://github.com/domotk/homepool-card), and reads the
attributes this integration exposes.

Read [docs/architecture.md](docs/architecture.md) before changing behaviour. The
original design, with the reasoning behind every number, is
[docs/design-v1.md](docs/design-v1.md) (Spanish); its last sections record what
each release changed and why.

## Commands

```bash
python3.13 -m venv .venv && . .venv/bin/activate   # 3.13 or 3.14
pip install -r requirements_test.txt               # pulls a matching Home Assistant
python -m pytest -q                                 # the whole suite, about two seconds
python scripts/generate_strings.py                  # after changing any interface text
```

CI (`.github/workflows/validate.yml`) runs the tests on Python 3.13 and 3.14
(each with the newest Home Assistant it can install), plus `hassfest` and the
HACS validation. Run the tests before every commit; you cannot run hassfest
locally without Docker, so read its output on the pull request.

## Layout

| Path | What it holds |
|---|---|
| `custom_components/homepool/coordinator.py` | The runtime: one `PoolCoordinator` per pool, evaluated every 60 s |
| `custom_components/homepool/pool/` | Pure logic, no Home Assistant imports: target and chlorine calculators, authority ladder (`scheduler.py`), safety, geometry, layouts, hardware catalogue |
| `custom_components/homepool/modes/` | Operation modes, pure: each answers only *should the pump run now to cover the target?* |
| `custom_components/homepool/{sensor,binary_sensor,switch,select,number,button}.py` | Entities: thin views over the coordinator |
| `custom_components/homepool/config_flow.py` | Setup wizard and options menu |
| `custom_components/homepool/__init__.py` | Entry setup and the `homepool.*` services |
| `custom_components/homepool/texts.py` | Text composed at runtime (alerts, reasons), English and Spanish |
| `custom_components/homepool/data/` | `catalog.yaml` (pumps, chlorinators) and `layouts.yaml` (pool interiors): community data |
| `scripts/generate_strings.py` | The source of all interface text; writes `strings.json` and `translations/` |
| `scripts/draw_icon.py` | Draws `brand/icon.png` and `icon@2x.png` (needs Pillow) |
| `tests/` | pytest with `pytest-homeassistant-custom-component`; `helpers.py` sets up a pool |

## Rules that are easy to break

**Behaviour**

- **The authority ladder is the safety model.** `pool/scheduler.py::arbitrate`
  decides in a fixed order: pump unavailable, hands-off, maintenance lock,
  safety shutoff, freeze protection, pH correction, manual cycle, a change
  made outside HomePool, then the mode. A new feature that moves the pump
  finds its rung there; it never switches the pump from anywhere else.
- **In `off` mode HomePool never starts the pump on its own**, except for
  freeze protection; only what a person asks for (a manual cycle, a forced pH
  window) runs it. Users rely on that when testing it next to their own
  automations. Keep it so.
- **During a day the target only goes up** (`_async_maybe_recalculate`);
  `homepool.recalculate_schedule` is the only way down. A day ends at local
  midnight, and time is never carried over.
- **Every pump decision carries a stable `key`**, and its text lives in
  `texts.REASONS` in *both* languages. `reason_key` is recorded in history;
  `reason` is not. Never rename a key: history and automations use them.

**Compatibility**

- **Entity unique ids are `<entry_id>_<key>`.** Renaming a key orphans the
  entity on every install. Entity *names* may change; keys may not.
- **The card reads attributes by name**: `card_attributes()`, the control
  sensor's `reason`, `reason_key` and `manual_override_by`, the target sensor's
  factors and limits. Renaming or removing one breaks the card; add instead,
  and change the card in its own repository.
- **The store** (`async_load` / `_to_store`) must read anything an older
  version wrote. Add fields with a default; bump `STORAGE_VERSION` and migrate
  only when a field changes meaning. The config entry version works the same
  way (`CONFIG_VERSION`, `async_migrate_entry`).
- **No runtime Python requirements** (`manifest.json` `requirements: []`),
  and `pool/` and `modes/` stay free of Home Assistant imports so they can be
  tested and reasoned about alone.

**Text**

- **Never edit `strings.json` or `translations/*.json` by hand.** Edit
  `scripts/generate_strings.py` and run it; a test checks every layout has a
  label in each language.
- Runtime text goes in `texts.py`, in English and Spanish. A new language is
  a new column in both places.

**Home Assistant**

- hassfest is stricter than Home Assistant: for example, `services.yaml` may
  not put a `device` filter on a `target` (the entity filter already lets the
  picker offer the pool's device).
- Name other integrations' events as strings (`"automation_triggered"`) rather
  than importing their modules, so HomePool does not load them.
- Listeners that must run before other code reacts are `@callback` methods.
  A lambda handed to `hass.bus.async_listen` runs in the executor, later.

## Tests

- `tests/helpers.py::setup_pool(hass, **overrides)` creates a pool on
  `input_boolean` switches; `SwitchRouter` makes `switch.turn_on/off` drive
  them. Use the `freezer` fixture and `tick()` in `test_control.py` to move
  time.
- `input_boolean` writes state instantly under the caller's context. Real
  relays confirm late and under a fresh context; say so when a test can only
  cover the instant case.
- A service call that carries a `user_id` needs a real user
  (`await hass.auth.async_create_user(...)`).
- Entity ids follow Home Assistant's language at creation. To test Spanish
  text, set `hass.config.language` *after* `setup_pool`.
- Pure calculators have their own tests (`test_filtration_calculator.py`,
  `test_chlorine_calculator.py`); `test_simulation.py` runs whole days.

## Working on it

- One branch and pull request per change; conventional prefixes in commit
  titles (`fix:`, `feat:`, `docs:`, `chore:`, `ci:`).
- In the pull request, say what you tested and what is **not** verified on a
  real Home Assistant. Being honest about that is how this project works.
- Testing on a live installation follows
  [docs/testing-on-a-real-install.md](docs/testing-on-a-real-install.md). An
  agent with access to someone's Home Assistant follows its rules strictly:
  it reports problems, it does not fix them in place.
- Releases are cut by a maintainer: see
  [CONTRIBUTING.md](CONTRIBUTING.md#releases).
