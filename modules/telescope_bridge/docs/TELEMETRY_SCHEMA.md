# Telescope Bridge — Schémas de télémétrie (V1)

Tous les samples partagent une **enveloppe commune** + un **bloc spécifique**
au `kind`. Implémentation cible : dataclasses Python dans `schemas/telemetry.py`.

## Enveloppe commune

| Champ | Type | Bornes / Notes |
|---|---|---|
| `device_id` | uuid str | doit appartenir à l'agent |
| `kind` | enum | `mount|camera|focuser|filterwheel|rotator|dome|weather|guider` |
| `ts` | iso8601 UTC | skew toléré ±60 s vs serveur |
| `seq` | int ≥ 0 | numéro de séquence par device (anti-duplicate) |
| `source` | enum | `alpaca|ascom_com|indi|mock` |
| `agent_id` | uuid str | redondant pour audit, vérifié vs JWT |

## kind = mount

| Champ | Type | Bornes |
|---|---|---|
| `ra_hours` | float | 0 ≤ x < 24 |
| `dec_degrees` | float | -90 ≤ x ≤ 90 |
| `alt_degrees` | float\|null | -90..90 (optionnel) |
| `az_degrees` | float\|null | 0..360 |
| `is_tracking` | bool | |
| `tracking_rate` | enum\|null | `sidereal|lunar|solar|king|off` |
| `is_slewing` | bool | |
| `is_parked` | bool | |
| `is_at_home` | bool\|null | |
| `side_of_pier` | enum | `east|west|unknown` |
| `pier_flip_pending` | bool\|null | |
| `firmware_version` | str\|null | ≤ 64 chars |
| `site_lat` | float\|null | **opt-in**, chiffré au repos |
| `site_lon` | float\|null | **opt-in**, chiffré au repos |
| `site_elev_m` | float\|null | |
| `utc_offset_minutes` | int\|null | -780..780 |

## kind = camera

| Champ | Type | Bornes |
|---|---|---|
| `is_connected` | bool | |
| `is_exposing` | bool | |
| `exposure_remaining_s` | float\|null | ≥ 0 |
| `exposure_total_s` | float\|null | ≥ 0 |
| `ccd_temp_c` | float\|null | -100..100 |
| `ccd_target_temp_c` | float\|null | -100..100 |
| `cooler_on` | bool\|null | |
| `cooler_power_pct` | float\|null | 0..100 |
| `binning_x` | int | 1..16 |
| `binning_y` | int | 1..16 |
| `gain` | int\|null | 0..600 |
| `offset` | int\|null | 0..600 |
| `last_image_path` | null | **toujours null en V1**, jamais d'upload image |

## kind = focuser

`position` int (steps), `is_moving` bool, `temp_c` float\|null, `max_step` int.

## kind = filterwheel

`current_slot` int, `slot_count` int, `is_moving` bool,
`filter_names` list[str] (≤ 12).

## kind = rotator

`angle_degrees` float, `is_moving` bool, `target_angle_degrees` float\|null.

## kind = dome

`is_connected` bool, `shutter_state` enum (`open|closed|opening|closing|unknown`),
`is_slewing` bool, `azimuth_degrees` float\|null, `slaved` bool.

## kind = weather

`temperature_c` float\|null, `humidity_pct` float\|null, `pressure_hpa` float\|null,
`wind_speed_kmh` float\|null, `cloud_cover_pct` float\|null,
`sky_brightness_mpsas` float\|null, `safety_state` enum (`safe|unsafe|unknown`).

## kind = guider

`is_guiding` bool, `rms_error_arcsec` float\|null,
`rms_error_ra_arcsec` float\|null, `rms_error_dec_arcsec` float\|null,
`star_snr` float\|null.

## Propriétés EXPLICITEMENT INTERDITES en V1

L'agent doit **refuser** de lire et **refuser** d'envoyer les propriétés suivantes ;
le serveur doit **refuser** de stocker si elles arrivent (`422 schema_invalid`) :

- `slew_target_ra`, `slew_target_dec` (= demande de mouvement implicite)
- `pulse_guide_*`
- `set_*` toute famille
- chemins de fichiers (`last_image_path`, `log_file`)
- `password`, `auth_token`, `api_key` (jamais aucune raison)
- `command_history`, `last_command`
