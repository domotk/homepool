# Contributing to HomePool

HomePool is a community project: built so that anyone with a pool and Home
Assistant can use it, and improved by the people who do. Code, data, testing on
your own pool and plain bug reports are all welcome.

## Ways to help

- **Report how it behaves on your pool.** An issue with your diagnostics file
  (device page → *Download diagnostics*; the location is redacted) is worth
  more than any guess. Say your HomePool version, your mode, and what you
  expected.
- **Add your hardware or your pool's interior.** The pump and chlorinator
  catalogue and the pool layouts are plain YAML: see
  [contributing to the catalogue](docs/contributing-catalog.md) and
  [contributing layouts](docs/contributing-layouts.md).
- **Translate.** Interface text is in `scripts/generate_strings.py`, runtime
  text in `custom_components/homepool/texts.py`; each has an English and a
  Spanish column. A new language is a new column in both.
- **Write code.** Pick an issue, or open one first for anything larger than a
  fix, so we agree on the shape before you build it.

## Getting set up

You need Python 3.13 or 3.14 and git. Home Assistant itself comes with the
test harness.

```bash
git clone https://github.com/domotk/homepool.git && cd homepool
python3.13 -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt
python -m pytest -q
```

To try it in a real Home Assistant, copy `custom_components/homepool` into
your configuration's `custom_components/` and restart. Read
[testing on a real install](docs/testing-on-a-real-install.md) first.

## Before you write code

- [docs/architecture.md](docs/architecture.md) explains how the pieces fit,
  and what must not break: the authority ladder, entity keys, the attributes
  the card reads, the stored state.
- [AGENTS.md](AGENTS.md) has the rules in short form. If you work with an AI
  coding agent, it reads that file; you should too.
- [docs/design-v1.md](docs/design-v1.md) (Spanish) has the reasoning behind
  the algorithm and a section per release on what changed and why.
- `docs/superpowers/specs/` and `docs/superpowers/plans/` hold the design and
  the step-by-step plan of larger releases (0.2 so far), written before the
  code. Read the spec to learn why a 0.2 feature works the way it does. A
  large new feature gets its own spec there, agreed in an issue first.

## Making a change

1. Branch from `main`.
2. Make the change with tests. Pure logic (`pool/`, `modes/`) gets unit tests;
   anything that moves the pump gets a test in `tests/test_control.py`, and a
   new service gets a test that a read-only user is refused
   (`tests/test_services.py`).
3. If you changed interface text, run `python scripts/generate_strings.py` and
   commit its output.
4. `python -m pytest -q` passes.
5. Commit with a conventional prefix (`fix:`, `feat:`, `docs:`, `chore:`,
   `ci:`) and a body that says *why*.
6. Open a pull request. Fill in the template, especially **what is not
   verified on a real Home Assistant**.

CI runs the tests on Python 3.13 and 3.14, hassfest and the HACS checks.
All must pass.

If you find a security problem, do not open an issue: follow
[SECURITY.md](SECURITY.md).

Changes that need the card to follow (a new attribute it should show, a
renamed state) get a matching pull request in
[homepool-card](https://github.com/domotk/homepool-card).

## Releases

A maintainer:

1. Bumps `version` in `custom_components/homepool/manifest.json`.
2. Adds a section to `docs/design-v1.md` recording what changed and why.
3. Merges, then publishes a GitHub release `vX.Y.Z` titled `HomePool X.Y.Z`,
   with notes written for users. HACS offers it from there.
4. Releases the card alongside, with matching numbers, when it changed too.

## Code of conduct

Be kind, assume good faith, and keep discussion about the work. Pools are
for enjoying.
