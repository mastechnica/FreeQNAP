# Dynamic DNS

Dynamic DNS is optional and disabled by default. It updates registered DNS records; it does not expose the NAS, change a router/firewall, solve CGNAT, configure a reverse proxy or issue a matching public HTTPS certificate. The existing LAN-only HTTPS address/source restrictions remain in force.

## Provider profiles

The dashboard offers sixteen typed adapters: Cloudflare API token, DuckDNS, Dynu, DynDNS, No-IP, DigitalOcean, Namecheap, FreeDNS/afraid.org, FreeMyIP, ChangeIP, easyDNS, OVH DynHost, ZoneEdit, Domeneshop/Domainnameshop, Infomaniak and a custom DynDNS2 HTTPS provider. These use the signed Debian `ddclient` drivers; a configured provider account and live acceptance are still required. API changes or provider account restrictions can make an adapter unavailable. Presence of a driver is not a successful provider test.

Use the provider's least-privilege DNS-update token where available. Choose one exact registered hostname and, where required, its existing DNS zone. DuckDNS maps its registered `.duckdns.org` name to the driver's short label. Namecheap maps a hostname to its relative label or zone apex and uses the zone as the driver's login. The interface rejects hostnames outside their selected zone. Supported address families appear per adapter; an unreviewed family is not silently offered. Sixteen local profiles are supported, with duplicate enabled hostname/family controllers rejected.

An explicit review shows the hostname, provider, address source, family, interval and external effects before saving. Tokens are submitted separately from the plan, retained only in private server files, and never returned by status or placed in arguments, jobs or public source. Blank token entry preserves the prior token only for the same provider. Driver-incompatible whitespace, quotes, backslashes, commas and `#` are rejected with a request to use a provider token. No raw configuration, arbitrary hooks/scripts, shell commands, router credentials or proxy is accepted.

## Address detection and updates

Choose an explicitly entered globally routable address or verified-HTTPS public-egress discovery through ipify. IPv4 and IPv6 profiles use distinct address sources. Discovery refuses redirects and invalid/private/CGNAT results. A VPN may make the NAS's detected egress different from its router WAN; verify the address before relying on inbound access.

The stock ddclient daemon stays masked. FreeQNAP schedules one due profile per independent worker pass, at a configurable 5–1440 minute interval. Failures retain the prior provider acceptance and back off independently. A manual request respects error/rate backoff. Updates execute as the non-login `freeqnap-ddns` account in a fixed transient systemd unit with no capabilities, private temporary/devices, strict filesystem/home protections, bounded runtime and credential-file handoff. Passwords never enter command arguments or environment variables.

A successful process exit is insufficient. The exact-host private driver cache must positively report the selected address and good provider status with an acceptance timestamp. The dashboard distinguishes a fresh provider acceptance from an unchanged address that was accepted earlier. This does not independently prove worldwide DNS propagation or remote service reachability.

Removing a profile removes local scheduling only; it does not delete the provider-side record. Private credentials/cache are retained for reviewed reconciliation rather than unexpectedly deleting recovery material.

## Dependencies and validation

Install signed Debian `ddclient`, keeping its stock service masked, then rerun the NAS service installer to create the dedicated non-login account. No provider is configured during package installation.

The native ARMhf campaign ran the real ddclient DynDNS2 driver under the production unprivileged transient-unit protections against an isolated HTTPS fixture. Verified TLS, Basic authentication, exact-host/address cache acceptance, provider rejection and untrusted-certificate denial passed. No external provider or owner account was contacted. Unit tests additionally cover typed adapters, injection, plan changes, duplicate controllers, zero-exit-without-receipt refusal, private credentials and failure fairness. Your actual provider still needs a live test after you choose its hostname/token.

References: [ddclient documentation](https://ddclient.net/), [protocol documentation](https://ddclient.net/protocols.html), [upstream source](https://github.com/ddclient/ddclient).
