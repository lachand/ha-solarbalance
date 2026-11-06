# solarbalance-card

Custom Lovelace card for [SolarBalance](https://github.com/solarbalance/ha-solarbalance).

Displays a real-time energy-flow diagram (solar, grid, batteries, home) with the current HEMS mode, live measures and battery level, in the **Signature** design shared with the full-page panel.

The drawing code lives in `custom_components/solarbalance/www/panel/` and is imported here (single source); the Signature tokens, fonts and `panel.css` are loaded from the integration's static path `/solarbalance_card/`, so the card expects the integration to be installed.

## Installation

### Manual (recommandé pendant le développement)

1. Build the card:

   ```bash
   cd frontend/solarbalance-card
   npm install
   npm run build
   ```

   The compiled bundle is written to `custom_components/solarbalance/www/solarbalance-card.js`.

2. Add the resource in HA (Settings → Dashboards → Resources, or `configuration.yaml`):

   ```yaml
   lovelace:
     resources:
       - url: /local/community/solarbalance/solarbalance-card.js
         type: module
   ```

   Or if served from the integration's `www/` folder:

   ```yaml
   lovelace:
     resources:
       - url: /hacsfiles/solarbalance/solarbalance-card.js
         type: module
   ```

   The integration already registers the card and serves `vendor/` and `panel/` under `/solarbalance_card/`; a manual resource is only needed if you copy the bundle elsewhere, in which case copy those two folders next to it.

3. Add the card to a dashboard:
   ```yaml
   type: custom:solarbalance-card
   title: Tableau de bord solaire
   ```

## Configuration

| Option                 | Default                                 | Description                          |
| ---------------------- | --------------------------------------- | ------------------------------------ |
| `title`                | `"SolarBalance"`                        | Card title                           |
| `contrast`             | `false`                                 | High-contrast (AAA) theme            |
| `mode_entity`          | `sensor.solarbalance_mode`              | HEMS mode entity                     |
| `strategy_entity`      | `sensor.solarbalance_dominant_strategy` | Dominant strategy entity             |
| `grid_power_entity`    | `sensor.solarbalance_grid_power`        | Grid power (W, positive = import)    |
| `pv_power_entity`      | `sensor.solarbalance_pv_power`          | PV power (W, always positive)        |
| `battery_power_entity` | `sensor.solarbalance_battery_power`     | Battery power (W, positive = charge) |
| `battery_soc_entity`   | `sensor.solarbalance_battery_soc_avg`   | Battery SoC average (%)              |

## Development

```bash
npm install
npm run dev      # Vite dev mode (hot-reload)
npm run typecheck
npm run lint
npm run build    # Production build → ../../custom_components/solarbalance/www/
```
