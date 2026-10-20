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

## Setup

Open **Quiet Home → Setup** in the sidebar and pick from your own entities:

- **Light**: one light, light group or switch to toggle from the TV.
- **Scenes**: up to two scenes, such as a movie scene.
- **Heating**: the thermostat for the heating card.
- **Weather**: the weather entity for the forecast card.
- Room title, labels, theme (Automatic, Bento or Gallery) and how often photos change.

Only these entities can be controlled from the TV, and temperatures outside the
thermostat's own minimum and maximum are refused. Sunrise and sunset come from
`sun.sun`. The Checks card shows whether each chosen entity was found.

The add-on's **Configuration** tab holds one option, `tv_key`: a shared secret the
TV sends. Put the same value in the TV build's `hubKey`.

## The TV connection

The TV reads `http://<Green IP address>:8098/`. Give the Green a fixed address in
your router (DHCP reservation) and build the TV package with that address. The
port is meant for your home network only; do not forward it from the internet.
