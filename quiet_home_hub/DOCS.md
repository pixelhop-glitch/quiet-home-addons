# Quiet Home Hub

Feeds the Quiet Home TV launcher with photos, living-room controls, weather and
family notes. Open **Quiet Home** in the sidebar to manage photos and notes.

## Photos

Upload from the sidebar page (phones work well through the Home Assistant app).
Choose **Day**, **Night** or **Any time**. Uploads are rotated upright, resized
for a 1080p TV and saved without metadata, so phone location data is removed.

Photos are stored in Home Assistant's media folder at `/media/quiet-home/`
(`day/`, `night/` and `any/`). They appear in the Media browser and are included
in full backups when the media folder is selected. You can also copy JPEGs into
those folders through the Samba share.

## Configuration

| Option | Meaning |
| --- | --- |
| `tv_key` | Shared secret the TV sends. Set one and put the same value in the TV build's `hubKey`. |
| `theme` | Household default: `auto` (Bento by day, Gallery after sunset), `bento` or `gallery`. A choice made on the TV wins. |
| `rotate_minutes` | How often the background photo changes. |
| `room_title` | Heading for the controls card. |
| `light`, `light_label` | One light or light group to toggle, e.g. `light.living_room`. |
| `scenes` | Up to two scenes, e.g. `scene.movie_night`. |
| `climate`, `climate_label` | Thermostat for the heating card, e.g. `climate.heating`. |
| `weather` | Weather entity, e.g. `weather.forecast_home`. |

Only these entities can be controlled from the TV, and temperatures outside the
thermostat's own minimum and maximum are refused. Sunrise and sunset come from
`sun.sun`. The **TV** tab on the sidebar page shows whether each entity was found.

## The TV connection

The TV reads `http://<Green IP address>:8098/`. Give the Green a fixed address in
your router (DHCP reservation) and build the TV package with that address. The
port is meant for your home network only; do not forward it from the internet.
