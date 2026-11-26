# Contributing Pool Layouts

Pool layouts describe interior elements (steps, islands, beach entries) for each pool shape. They live in `custom_components/homepool/data/layouts.yaml`.

## How to contribute

1. Fork the repository
2. Edit `layouts.yaml` and add your layout variant under the appropriate shape
3. Optionally, add an SVG template in `data/layout_svgs/`
4. Submit a Pull Request

## Layout structure

```yaml
rectangular:
  - id: my_layout
    name: "Description"
    requires_orientation: short_side
    volume_adjustment: 0.93
    svg_template: "my_layout.svg"
```

## Orientation values

- `false` — No orientation needed
- `corner` — Options: top_left, top_right, bottom_left, bottom_right
- `short_side` — Options: top, bottom
- `long_side` — Options: left, right
- `any_side` — Options: top, right, bottom, left

## Translations

The `name` is the English label in the setup wizard. Add the Spanish one to
`LAYOUT_ES` in `scripts/generate_strings.py`, under the same shape and id, and
run `python scripts/generate_strings.py` to rewrite the translation files. A
test fails if a layout has no label in either language.
