# Quiet Home Hub

Feeds the Quiet Home TV launcher with photos, living-room controls, weather and
family notes. Open **Quiet Home** in the sidebar to manage photos and notes.

## Photos

Upload from the sidebar page (phones work well through the Home Assistant app).
Choose **Day**, **Night** or **Any time**. Uploads are rotated upright, kept at up
to 4K (3840×2160) and saved without metadata, so phone location data is removed.

### 4K photos in Gallery

The TV draws apps at 1920×1080, but it shows video at full 4K with its own picture
processing. So the hub turns your photos into a 4K slideshow video (one for day, one
for night), which Gallery plays behind the clock, pausing on each photo. Bento and
any TV without the video keep showing normal photos.

- After you add, move or delete photos, the hub rebuilds the video in the
  background. It re-encodes only the photos next to the change, but the first build
  can take a while on a Home Assistant Green (roughly a minute per photo). The TV
  keeps showing the previous video or normal photos until it is ready.
- Photos uploaded before version 0.4.0 were stored at 2560×1440. They still look
  better on the video layer, but upload the original again for full 4K detail.
- The videos are kept in `/media/quiet-home/.video/` and are rebuilt if deleted.

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
