# Local health and optional notifications

Health incidents are retained in the root-private NAS database. The monitor evaluates inventory, RAID, SATA SMART, filesystem capacity, CPU temperature, backup failures/staleness and required services in independent scopes. A malformed or stale collector sample does not resolve earlier hardware faults, and a failed scope does not prevent later checks. RAID initial synchronization remains a visible protection-incomplete condition.

Acknowledgment records operator awareness without clearing, muting or hiding a fault. A successful check must observe a healthy condition under the current configured thresholds before resolution. Changing thresholds can change that classification; acknowledgment alone cannot. A new occurrence receives a new incident identity; severity escalation clears the acknowledgment. Backup failures remain visible while retrying until that same job succeeds. No automatic failure-history purge is performed.

The default thresholds are 90/97 percent used capacity and 75/85 C CPU warning/critical temperature, configurable in the dashboard. Root storage separately warns below 1 GiB and becomes critical below 512 MiB. These are monitoring thresholds, not fan controls or hardware acceptance. Fan-fault, UPS and physical thermal-failure behavior remain separate tests.

Health monitoring uses an independent broker thread and its own durable tables. It does not stop NAS job dispatch or make a healthy service process equivalent to successful backups or notification receipt. The dashboard shows monitor staleness and keeps the other NAS controls independent if monitor state cannot be read.

The local incident engine passed host regression tests for restart persistence, stale/partial samples, failed-check isolation, acknowledgment/escalation, recurrence, root capacity, missing arrays, required services and retained failed backups. Physical fault injection and owner notification receipt remain unaccepted. Outbound email and browser push are disabled unless separately configured and enabled; no owner test notification has been sent.


## Optional SMTP

In Health & notifications configure the mail hostname/address, port, verified STARTTLS or implicit TLS, sender, up to five recipients, optional username/app password and optional public CA certificate for a private mail server. Plaintext transport, certificate-validation bypasses, header/control-character injection and private-key uploads are not supported. OAuth mail flows are not implemented; use a suitable SMTP relay or supported app password. SMTP passwords stay in root-private mode-0600 files, outside operation/job payloads. They are included only in the selected encrypted NAS recovery capture, never in public documentation.

Routine email is disabled by default. An explicit test button can queue a test after confirmation, even while routine email is disabled. Installation/maintenance sends no owner test message. Each recipient has an independent durable attempt: a failure or ambiguous acceptance stays retryable without blocking later destinations. A positive SMTP response is recorded as **SMTP accepted**, not proof of inbox receipt. Retries may duplicate ambiguous sends; stable per-notification Message-IDs help recipients identify them but do not promise deduplication.

## PWA and browser push

The dashboard has an installable manifest, standard icons and a minimal service worker. It has no fetch interception or offline cache and never stores administrator sessions, file contents or private API responses offline. Use trusted HTTPS; browser warnings are not bypassed. On iPhone/iPad add the dashboard to the Home Screen, launch that app, then press Enable push on this device. Permission is requested only from that click. A denied permission creates no subscription.

Push is independently disabled by default. After a browser opts in, configure its VAPID contact email and explicitly enable future-incident push if desired. The NAS generates and retains its own private P-256 VAPID key; browser subscriptions/keys remain root-private. Status shows device labels and relay providers, without endpoint tokens or encryption keys. Restore the VAPID key with the protected configuration or re-enroll clients after replacement. An expired relay subscription retains unsuccessful work for review and needs device re-enrollment.

Standard Web Push uses the browser vendor's relay (Apple, Google, Mozilla or supported Microsoft hosts). The NAS sends encrypted generic health messages with VAPID authentication. Endpoint validation, globally routable DNS-result pinning and verified HTTPS prohibit arbitrary/private push destinations and redirects. Relay acceptance is **not device receipt**. Actual phone/browser delivery remains an owner acceptance test; the maintenance campaign used only isolated cryptographic/transport fixtures.

Push itself uses outbound connections and does not require opening inbound router ports. Remote dashboard access is a separate review of hostname/certificate, firewall/source restrictions and routing. DDNS alone does not commission remote administration. This feature opens no ports or broadens the existing LAN HTTPS allowlist. See [local HTTPS](LOCAL-HTTPS.md) and [DDNS](DYNAMIC-DNS.md).

## Durable delivery and reconciliation

New notification settings and newly enrolled devices use durable event-ID watermarks, so old incidents are not silently replayed when a channel is enabled or the clock moves. Each destination is queued independently. Interrupted sends are retained as ambiguous and may retry; exponential backoff is bounded, without abandoning work after a retry count. Configuration/subscription changes hold older sends for explicit review.

Transport history exposes pending/retrying/accepted/needs-review states separately from health acknowledgment. An explicit replay plan shows the original time and original currently enabled destination, warns of possible duplicate/stale delivery, and applies only to that selected item. A changed recipient cannot silently inherit old sends. Explicit discard prevents that queued item from being re-created by normal event processing; it does not clear its health incident. Failed/held delivery and failed DDNS updates also appear in local health. No automatic live restore of queues, credentials or enabled policies exists. Before any future manual configuration restore, disable and reconcile outbound channels/policies before worker activation; never resume a restored notification backlog without specific review.

## Native validation

The complete native ARMhf suite includes real P-256 ECDH/aes128gcm payload encryption/decryption and VAPID signature verification, subscription privacy/expiry/enrollment watermarks, SMTP TLS-before-authentication, refusal handling and durable retry/replay behavior. An isolated network namespace additionally exercised actual STARTTLS and implicit-TLS SMTP servers, a failed recipient alongside a later accepted recipient, restart/retry recovery, and untrusted-certificate denial. No owner mailbox, push subscription or public DNS provider was contacted. A Node campaign verified no service-worker data cache, same-origin notification clicks and no registration/API request following permission denial.

Optional signed Debian packages are `python3-cryptography`, `python3-http-ece` and `python3-py-vapid`. Missing dependencies are reported explicitly; they are not silently downloaded at first notification. Real provider interoperability, trusted client installation and independently observed email/phone receipt remain acceptance steps.

References: [MDN Push API](https://developer.mozilla.org/en-US/docs/Web/API/Push_API), [WebKit Home Screen Web Push](https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/), [VAPID RFC 8292](https://www.rfc-editor.org/rfc/rfc8292), [Web Push encryption RFC 8291](https://www.rfc-editor.org/rfc/rfc8291).
