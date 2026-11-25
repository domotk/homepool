# Contributing to the Hardware Catalog

The HomePool hardware catalog (`custom_components/homepool/data/catalog.yaml`) is community-maintained. Adding your equipment helps other users set up HomePool faster.

## How to contribute

1. Fork the repository
2. Edit `custom_components/homepool/data/catalog.yaml`
3. Add your equipment entry under the appropriate section (`pumps`, `filters`, or `salt_chlorinators`)
4. Submit a Pull Request

## Required fields

### Pumps
- `brand` (string) — Manufacturer name
- `model` (string) — Model name/number
- `type` (string) — `fixed` or `variable`
- `nominal_flow_rate` (number) — Flow rate in m³/h

### Salt chlorinators
- `brand`, `model` (string)
- `max_pool_volume_m3` (number) — Maximum recommended pool volume
- `nominal_production_g_h` (number) — Chlorine production in g/h at 100%
- `self_regulating` (boolean) — Has built-in ORP/chlorine sensor
- `min_water_temp_c` (number) — Minimum operating water temperature
- `salt_ideal_g_l` (number) — Ideal salt concentration

## Validation

The catalog is validated at integration startup. Invalid entries are skipped with a warning log.
