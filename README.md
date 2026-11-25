# 🏊 HomePool

**Comprehensive swimming pool management integration for Home Assistant.**

HomePool is a hub/meta-integration that orchestrates your existing Home Assistant entities (switches, sensors, cameras) into a coherent pool management system. It doesn't drive hardware directly — it works with whatever you already have.

> ⚠️ **Early development** — This integration is under active development and not yet ready for production use.

## Features

### Intelligent Filtration
- **Daily target calculation** based on season, temperature, UV, rain, and pool cover status
- **Five operation modes**: Off, Timer, Smart, Solar, Smart+Solar
- **Calibrated algorithm** validated against manufacturer specifications

### Salt Chlorinator Management
- **Dual-target system**: filtration demand and chlorine production demand calculated independently
- **Seasonal calendar**: automatic chlorinator toggle by configured months
- **Over-chlorination prevention**: recommended production % for non-self-regulating chlorinators
- **Independent chlorinator control** when connected via separate switch

### Safety
- **Maintenance lock**: manual override that forces pump off
- **Safety shutoff**: automatic stop on flood, overheat, pressure anomaly, or power anomaly
- **Priority hierarchy**: maintenance lock → safety shutoff → pH correction → manual action → automatic mode

### Progressive Capabilities
Connect more sensors, unlock more features. HomePool starts useful with just a pump switch and becomes more powerful as you add pH sensors, temperature probes, solar monitoring, and more.

### Visual Custom Card *(coming soon)*
- SVG rendering of pool and pump room
- CSS animations (water ripples, bubbles, pump rotation)
- Configurable: `display_mode` (pool/pump/pool_and_pump) × `card_size` (small/medium/full)

## Installation

### HACS (recommended)

1. Add this repository as a custom repository in HACS
2. Install "HomePool"
3. Restart Home Assistant
4. Go to Settings → Integrations → Add Integration → HomePool

### Manual

1. Copy `custom_components/homepool/` to your `config/custom_components/` directory
2. Restart Home Assistant
3. Go to Settings → Integrations → Add Integration → HomePool

## Configuration

HomePool uses a multi-step config flow that guides you through:

1. **Identity** — Name your pool
2. **Location** — Geographic coordinates (from HA or manual)
3. **Geometry** — Shape, dimensions, interior layout, volume calculation
4. **Construction** — Type, cover, finish, environment
5. **Filtration** — Pump specs, filter type, skimmers (with optional hardware catalog)
6. **Water Treatment** — Chlorination type, pH targets, salt chlorinator settings
7. **Lighting & Auxiliary** — Light groups, robot cleaner
8. **Entity Connection** — Connect your HA entities to HomePool roles
9. **Notifications** — Optional built-in notification system
10. **Review** — Summary and confirmation

All settings are editable after setup via the options flow.

## Hardware Catalog

HomePool includes a community-contributed catalog of pool equipment (pumps, filters, chlorinators) that pre-fills technical specifications. See [Contributing to the Catalog](docs/contributing-catalog.md).

## Documentation

- [Design Document](docs/design-v1.md) — Complete technical specification
- [Contributing Catalog](docs/contributing-catalog.md) — How to add your equipment
- [Contributing Layouts](docs/contributing-layouts.md) — How to add pool layout variants

## Development

```bash
# Clone the repository
git clone https://github.com/domotk/homepool.git
cd homepool

# Run tests
pip install pytest pyyaml
python -m pytest tests/ -v

# The pool/ module is pure Python (no HA dependencies)
# and can be tested independently
python -m pytest tests/test_filtration_calculator.py -v
python -m pytest tests/test_chlorine_calculator.py -v
```

## License

MIT License — see [LICENSE](LICENSE) for details.

## Reference Hardware

Algorithm calibrated and validated with:
- **Pump**: Astralpool Sena (12.8 m³/h, 0.89 kW)
- **Chlorinator**: Astralpool SEL-E4 55 (35 g/h)
- **pH dosing**: Astralpool BASIC OPK PH (1.1 l/h)
- **Pool**: 30 m³ built-in, rectangular with island, Valencia (Spain)
