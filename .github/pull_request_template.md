## What and why

<!-- What changes for a pool owner, and the reason. Link the issue. -->

## How it was tested

- [ ] `python -m pytest -q` passes
- [ ] Interface text changed → ran `python scripts/generate_strings.py`
- [ ] New pump decisions have a `key` and texts in every language in `texts.py`

**Not verified on a real Home Assistant:**
<!-- Be specific: real relays, real sensors, midnight, a particular mode. "Nothing" is a fine answer if it was tested live. -->

## Compatibility

- [ ] No entity key renamed or removed
- [ ] No attribute the card reads renamed or removed
- [ ] Stored state from the previous version still loads

<!-- Needs a card change? Link the homepool-card pull request. -->
