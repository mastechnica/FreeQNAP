# AuraView EyeQ Connector App — AuraStore / FreeQNAP

Run this optional connector **directly on the NAS**. It connects outbound to EyeQ
Cloud over certificate-verified HTTPS/WSS on port 443. It needs no Mac, AVE40,
Guessla, inbound NAS port, port forward, Pulse agent or public NAS address. EyeQ
labels the NAS **AuraStore**. Synthia can search its media and request playback in
the signed-in EyeQ browser using the existing Music & media tools.

## Install and check

Download/extract the source-only app from EyeQ → Devices & data → Music & media
connectors. On the NAS, run `sudo sh install.sh`. This requires Python 3 with venv
support and installs the pinned websocket dependency from PyPI. It installs an
optional service; it does not start a connection or create/link user accounts.

Before pairing, check the chosen existing NAS account (username or immutable ID):

```sh
sudo -u freeqnap env PYTHONPATH=/opt/freeqnap/current \
  /opt/auraview-eyeq-connector/venv/bin/python \
  /opt/auraview-eyeq-connector/connector.py --check --owner YOUR_NAS_USERNAME
```

The result reports library availability/counts without contacting Cloud, reading
original bytes, starting scans or printing private paths. A failed library needs
its native permission/storage setup corrected; the connector cannot bypass it.

## Pair one user

1. Sign into the intended **EyeQ Cloud account**. Choose **Devices & data → Music
   & media connectors → Pair AuraStore**. Its single-use code expires in ten minutes.
2. On the NAS, pair that code with the intended existing local NAS username:

   ```sh
   sudo -u freeqnap env PYTHONPATH=/opt/freeqnap/current \
     /opt/auraview-eyeq-connector/venv/bin/python \
     /opt/auraview-eyeq-connector/connector.py \
     --config /var/lib/auraview-eyeq-connector/home.json \
     --pair --owner YOUR_NAS_USERNAME --name 'Home NAS'
   ```

   Enter the code only at the hidden prompt. No Apple password, NAS password,
   Authentik password or API credential is needed in EyeQ. A NAS administrator
   chooses this binding locally; Cloud cannot select or change the NAS user.
3. Start `sudo systemctl enable --now auraview-eyeq-connector@home`.
4. In EyeQ → **Music & media**, choose Home NAS and browse/search. An open player
   browser is required for Synthia playback and must allow playback after a tap.

For another family member, use a separate EyeQ login, NAS username, config basename
and service instance. This app does not merge libraries or grant a family member
administrator access. Existing NAS permissions remain the upper bound.

Optional pairing flags:

- Repeat `--category music`, `--category books`, `--category podcasts`,
  `--category photos`, `--category videos` or `--category folders` to limit the
  connector. If omitted, all six categories are enabled; folders remain empty
  until explicit shares are selected. Known IDs cannot bypass disabled categories.
- Repeat `--share LOCAL_SHARE_NAME` for additional native-authorized media folders.
  This is how already shared movie/TV folders can be browsed without changing the
  NAS media scanner. No volume or filesystem path can be selected remotely.
- `--origin https://YOUR_EYEQ_HOST` supports another EyeQ deployment. Only HTTPS
  origins without credentials, paths, query strings or fragments are accepted.

Changing selected libraries/shares requires a local config edit and restarting
only this connector instance. Stop it first and keep config ownership/mode intact.

## Status, recovery and disconnect

```sh
sudo -u freeqnap /opt/auraview-eyeq-connector/venv/bin/python \
  /opt/auraview-eyeq-connector/connector.py \
  --config /var/lib/auraview-eyeq-connector/home.json --status
sudo systemctl status auraview-eyeq-connector@home
```

A safe sidecar records connecting, online or reconnecting with a timestamp; a
status older than 90 seconds displays stale. Online is written only after Cloud
has accepted the credential and answered its authenticated heartbeat. It means
transport availability, not that every media file can be decoded. `--check` also
works with an existing config and rechecks native library access independently.
Temporary connection loss reconnects with bounded backoff; it never starts a scan,
copy, import, replay or NAS restart. Logs omit credentials and private errors.

Disconnect in EyeQ revokes the pairing and interrupts subsequent stream chunks.
Stop/disable the matching NAS instance to stop reconnection attempts. Remove only
that instance's config/status files when retiring it; never restore or delete NAS
account databases. Existing originals and iCloud downloads remain untouched.

## Media and privacy contract

- Music, audiobooks/readable books, downloaded podcasts, Personal Photos and videos
  use their existing native indexes. Explicit local shares allow additional media
  folder browsing. Names become opaque folder IDs; symlinks/non-media are excluded.
- Catalog pages contain at most 60 items with safe titles, selected metadata,
  artwork availability and pagination. Raw paths, GPS/EXIF, hidden metadata,
  accounts and upstream URLs are not returned. NAS item IDs remain stable.
- Read chunks are at most 256 KiB. Native account permissions, disabled/password
  change state, volume identities and private encrypted-volume ownership are
  checked on every request/chunk. Media categories are checked separately.
- Photo `thumb` requests map to native `thumbnail`; `preview` returns a browser
  compatible image. Readable EPUB/TXT/PDF/DOCX/AZW/AZW3/KPF editions depend on the
  NAS's existing extracted-text support. An extension alone does not prove support.
- Original codecs are streamed without transcoding; client codec/DRM support can
  limit playback. An absent cover, unindexed/locked/offline file or unreadable book
  remains unavailable rather than being downloaded or converted automatically.
- Internet radio and publisher-hosted, unsaved podcast episodes are **not** NAS
  originals and are not proxied by this version. They remain available in the NAS
  and Guessla through their separate existing provider integrations.
- The credential is stored in a private local account config and sent only in the
  first encrypted websocket frame. EyeQ stores its hash. No arbitrary operation,
  URL, path, shell command, storage change or metadata write is available remotely.
- Metadata is returned only on requested browsing/search. Synthia receives bounded
  search metadata; originals stream through EyeQ to its authenticated player, not
  to the language-model provider. No cloud media archive or listening ledger is
  created. Existing NAS preview caching may operate normally.

## Release and validation

Matching sources live in FreeQNAP `apps/auraview-eyeq-connector/` and EyeQ Cloud
`deploy/eyeq/connectors/aurastore/`. Keep source, installer, service, README and tests
identical and rebuild Cloud's source-only download with its `build.py`. No firmware,
keys, pairing configs, recordings or private library data belong in that archive.
See `docs/EYEQ-CLOUD-CONNECTOR.md` in FreeQNAP and Cloud's `docs/MUSIC-MEDIA.md` for
actual acceptance, the Cloud deployment checklist and remaining limits.
