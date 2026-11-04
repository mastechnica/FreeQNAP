## Navigation update — 4 November 2026

The main menu now keeps everyday collections and operations prominent. **Settings** groups System & access, Connections, and Protection & help; Network, AI agent access, VPN & gateway, Dynamic DNS, Backup & restore, and the local installation guide live there. **Storage & RAID** contains Volumes & encryption and RAID & recovery. Old links still work. **My Radio** has Music, Books, Podcasts and Internet Radio, with a persistent player and separate private collection storage. See [My Radio](MY-RADIO.md), [guided recovery](INTERRUPTED-RAID-RECOVERY.md), and [front-button capability limits](FRONT-BUTTON.md).

# Dashboard usability review

The dashboard uses action labels rather than implementation steps: Restart, Shut down, Save network settings, Create storage, Restore files, and Eject safely. The ellipsis means another screen follows. Existing exact-identity checks, typed destructive confirmations and review expiry remain enforced. Power dialogs explain the connection interruption before the final confirmation.

The review covered the source for Overview, Storage, Shares, Files, Backup, Media, USB, Network, Dynamic DNS, VPN, Downloads, RAID recovery, Health/notifications, Activity and Settings. Terms such as storage volume and backup destination replace pool/repository where useful. Technical identifiers stay available for disk safety and diagnosis. This is an iterative wording/workflow review, not proof that every service has passed real-client acceptance.

Downloads has a live summary, status filters and one card per job with graphical progress, transferred bytes, speed and a calculated ETA. Unknown total sizes have no fabricated percentage/ETA. Pause or Resume reflects the job state; removal states that files remain on disk. Destination/limits are expanded for first setup and collapsed once configured. Existing URL/torrent forms and durable engine behavior are unchanged. No downloads or torrents are started by a visual test.

Verification: JavaScript syntax, 12 desktop/location/download/PWA tests, and live Settings/Downloads inspection. No restart, shutdown, network configuration, notification replay or user credential change is part of this UX pass. Live transfer and torrent performance remain separate acceptance work.

## Visual system overview

The Overview adds six local history charts: CPU utilization, RAM used (MemTotal minus MemAvailable), highest reported thermal-zone temperature, aggregate physical-network receive/send byte rates, and one-minute CPU load. A 30-second broker worker reads proc/sys counters without probing disks. CPU excludes idle/iowait; guest time is not double-counted. Rates use monotonic elapsed time and counter resets yield unavailable values. First CPU/network samples are unavailable until a second sample. Charts break lines at missing samples or gaps over 90 seconds. Status text marks history older than 90 seconds as stale. CPU load is a task/load measure, not percent utilization.

Private SQLite history is retained for 24 hours (about 2,880 measurements). The range selector offers 1, 6 or 24 hours; no older measurements are invented. Kernel uptime and core count accompany history. Physical interfaces are summed without counting bridge/VPN traffic twice; the API also retains each physical interface's rates. Storage cards show actual filesystem available capacity and RAID synchronization. Existing detailed alerts and storage evidence remain below the visual summary.

The overview uses a compact desktop layout: six short charts in a three-column grid, a small status banner, and a condensed storage row. Technical details remain collapsed. Narrow displays use two chart columns and stacked storage cards; some scrolling remains appropriate on phones.

Overview status colors use green for healthy/online, amber for monitoring or unavailable status, and bright red for critical alerts/offline volumes. The overall state follows the existing health monitor severity; colors do not change alert policy. Capacity and temperature colors use configured thresholds. Charts use distinct metric colors and retain numeric labels; RAID synchronization is amber.

The compact disk-health table lists each visible disk, model/serial, capacity, SMART self-report, temperature and power-on hours. It uses existing standby-safe inventory; no new SMART tests or USB pass-through probes run. TR-004 member health remains unavailable behind the USB enclosure. Disk temperatures use explicit display-only bands below 50°C / 50–59°C / 60°C and above, not fan control. Data-capacity totals count mounted registered filesystems once by UUID, excluding OS filesystems and locked/offline volumes. Used/reserved is total minus available and includes filesystem overhead. Array summaries deduplicate volumes on the same MD array. Synchronizing arrays remain visibly incomplete, not healthy redundancy.

## Front-panel view

The status banner contains an original CSS schematic of the TS-431XeU four-bay 1U chassis, not a photograph. Bays use the hardware daemon's ATA-port mapping, not mutable sdX ordering. An authenticated, read-only endpoint reads the existing green LED class outputs and active-low metadata; it never sends hardware commands. The visible Overview polls at 250 ms, without overlapping requests, and stops polling while the page is hidden. The cached presence/activity feed must be younger than three seconds; stale/missing readbacks turn the indicators neutral. The browser cannot reproduce sub-250-ms pulses or guarantee exact optical phase. It displays sampled output state, not evidence that a physical LED is functioning. Red error, status and network LEDs have no accepted continuous readback in this feed and are not fabricated from array health. Full front-panel mirroring remains incomplete until those signals are safely exposed and validated. The status ring remains software health, separate from the physical LED view.

Historical image experiment: an owner-supplied product reference briefly replaced the schematic. It was superseded by the original vector illustration described below. The unused product-reference PNG and its route were removed from the public source-review tree; the original is retained privately. It is not redistributed or used as live telemetry.

The front view now uses an original vector drawing based on the supplied TS-431XeU reference, with FreeQNAP branding, four vented trays and top-row indicators. LAN1 (left network indicator) maps to enp0s1 and LAN2 (right) to enp0s3; SFP+ maps to enp0s0. Link indicators use read-only sysfs carrier. The 10G indicator turns green only for a reported negotiated 10000 Mb/s link; missing driver speed reporting stays gray, not a guessed speed. On this installed driver both sysfs speed and ethtool currently do not report negotiated speed. The i indicator reflects current dashboard health policy and does not mirror or change the physical MCU status light. No artificial network-activity animation is used. Brief drive LED pulses remain sampled rather than optically synchronized.

Physical-port correction from owner observation: the connected cable is in the labeled LAN2 jack, corresponding to enp0s1. LAN1 is enp0s3. Dashboard LAN indicators and interface selector labels now reflect that mapping; no network profiles, MACs, addresses or routes were changed. RJ45 indicators use amber, matching the owner's observed gigabit front LEDs; activity animation follows measured packet-count changes and is not phase-synchronized to the physical lamp. Driver-reported speed remains unavailable.

The physical status LED now follows the health worker's policy via the existing MCU tool: green when healthy, red for critical faults, both red/green for warning or stale monitoring (hardware has no separate amber command). The tool locks the MCU, checks the ACK and reads back the mode. Writes occur only when the mode changes or after worker restart; failed writes are retried at a later health pass and never block other workers. Shutdown terminates the broker before late power-off handling; no power/fan/drive command is issued by this worker. Native tests verify policy selection and failed-write retry. Live MCU ACK/readback confirmed red under the current critical alert; optical confirmation is still an owner check.

The title-card status badge is a keyboard-accessible link that scrolls to and focuses the highest-severity active alert card on Overview. The title card also names that alert. Active critical cards use a bright red border/background and CRITICAL text; warning cards use amber and CAUTION. The same severity styling applies on Health & notifications. Resolved alerts are excluded, critical alerts sort first, and each Overview card links to the full alert actions page. RAID protection alerts explain that a disk is missing or rebuilding and that full disk-failure protection is not yet available. This presentation does not modify thresholds, severity, acknowledgment or alert delivery.

Downloads now places the queue first, Add download open below it, with destination/limits and downloaded-file menus collapsed by default. VPN & gateway adds colored summary cards, a network-flow diagram and client cards. WireGuard activity is based on a handshake within three minutes, not a persistent connection claim. OpenVPN client status uses a private, bounded, fresh status-version-3 report; the generated server config enables this for subsequent normal server applications. Existing VPNs are not restarted automatically. Missing/stale telemetry is shown as unavailable, and an unconfigured server/client is neutral rather than a failure. Remote connection/forwarding validation remains separate from service status.

### Graphical workspaces (October 31)

Network, USB Storage, Backup & Restore, Dynamic DNS, RAID & Recovery,
Health & Notifications and Activity start with compact, color-coded summaries.
Network includes every detected physical port, even without carrier. LAN1 is
`enp0s3`, LAN2 `enp0s1`, and SFP+ `enp0s0` on this accepted model. Port utilization
uses the busiest direction divided by reported link speed; absent speed is
explicitly unknown, never assumed gigabit. Green indicates link presence with
normal utilization, amber >=75%, red >=95%; busy does not imply hardware failure.
Traffic is sampled every 30 seconds; charts retain 24 hours. Compact hourly
transfer totals retain 366 days. Daily/weekly/30-day/365-day rolling averages
are weighted by observed seconds, exclude collection gaps and counter resets,
and display observed coverage. Windows have hour-level boundaries. No historical
traffic is fabricated or inferred from interface lifetime counters. Collection
starts with this release; a full year requires a year of observation.

USB cards use original vector disk graphics, connection speed, filesystem capacity
and free space where mounted, plus explicit lock and health availability states.
No vendor enclosure probes, formatting, unlocks or storage configuration changes
are triggered by viewing a summary.

Media Library opens with the collection, cover-art cards, metadata details,
cast/crew, external source and optional trailer links. Scanner, folder setup,
metadata and sharing settings are collapsed below. Browse pages contain up to
200 titles with page navigation and a local filter. Portable NFO metadata accepts
an optional `trailer` URL, editable with the other details; HTTP(S) links only
are offered and open on explicit click. No automatic trailer lookup, external
embedding or provider request occurs when browsing. Direct play uses the browser's
native player, full-screen control and optional picture-in-picture (where the
browser supports it); it does not add transcoding. Floating video placement and
always-on-top behavior are controlled by the browser/OS. Unknown codecs show a
playback error. Real populated-library playback and visual acceptance remain
separate from automated tests. No test audio is sent during deployment.

### Compact first-screen layout

All workspaces use a shorter fixed navigation bar, compact headings, smaller
status cards and charts, and tighter spacing while preserving readable status
labels and color cues. Network keeps every physical port, current transfers,
24-hour charts and four history periods together above configuration controls.
USB drives use a responsive two-column layout on wider screens. Media posters
are smaller so more titles fit per row. Secondary SMART, backup, recovery,
notification and VPN controls use named expandable sections. Active faults and
pending network-change confirmations stay visible. Long noncritical footnotes
are expandable; no status, error or confirmation is discarded. Share editing
opens its settings automatically. Mobile controls retain larger touch targets;
small displays and large datasets still require scrolling.

## Connection handling — 3 November 2026

Read requests have a 15-second deadline; the main native-status request has an
8-second deadline. Base inventory can render when native status is unavailable,
and storage operations remain disabled. Refresh polls do not overlap. A forced
refresh requested during a running refresh is retained, and a change in native
availability redraws the current workspace. Initial failures show connection
feedback rather than leaving the header indefinitely at Connecting.

Write operations retain their existing completion semantics: the browser does
not automatically abort long-running writes or retry them.

The live incident showed responsive static files, session and base-inventory
requests, with native status left pending. The NAS also accepted SSH connections
without completing its greeting, including from a second LAN host. The underlying
cause remains unconfirmed. This source fix was subsequently deployed after the owner performed a hard reset;
its served HTTPS asset matches the tested source. See the dated lockup-recovery
report for the separate RAID recovery approvals and current acceptance limits.
