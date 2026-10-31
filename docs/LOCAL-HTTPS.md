# Local HTTPS administration

FreeQNAP can place a LAN-only HTTPS proxy in front of its existing loopback console. The dashboard still requires its separate administrator password. The SSH-tunnel endpoint remains available for setup and recovery; no public hosting, DNS provider or cloud certificate service is involved.

## Create a private local authority

On a trusted local administration computer with Python 3 and OpenSSL:

```sh
python3 tools/local-https.py create-ca --directory YOUR_PRIVATE_CA_DIRECTORY
python3 tools/local-https.py issue --ca YOUR_PRIVATE_CA_DIRECTORY --directory NEW_SERVER_BUNDLE --address YOUR_PRIVATE_LAN_IP --network YOUR_CLIENT_SUBNET --name YOUR_NAS.local
```

Use a new private directory for each output. The helper refuses existing outputs and sets private permissions. It explicitly uses named P-256 curve parameters for compatibility between macOS LibreSSL and Debian OpenSSL. Both certificate types carry explicit subject/authority key identifiers; the authority identifier is added at signing, not requested in the CSR. Issuance and NAS preflight use strict X.509 verification. This avoids relying on OpenSSL to add an issuer identifier that macOS LibreSSL may omit. Generated CA certificates have a ten-year lifetime; server certificates have a one-year lifetime and are restricted to server authentication. Review expiration rather than assuming automatic renewal. The CA signing key stays on the administration computer: **never upload `ca.key` to the NAS or install it on a client.** Keep a protected independent copy of the CA directory for future issuance. CA replacement requires new client trust.

Copy only `ca.crt`, `server.crt`, `server.key` and `public.json` from the server bundle into a new root-private directory on the converted NAS. The bundle contains no CA signing key. Use authenticated transfer and keep `server.key` mode 0600.

## Install on the NAS

Install the current signed Debian `nginx` package with its stock `nginx.service` masked first. The stock HTTP/default-site service must not briefly expose port 80. Review the source, then run:

```sh
sudo python3 deploy/install-local-https.py --bundle YOUR_ROOT_PRIVATE_SERVER_BUNDLE --verify-only
sudo python3 deploy/install-local-https.py --bundle YOUR_ROOT_PRIVATE_SERVER_BUNDLE
```

The installer checks the exact supported board, certificate chain/server purpose/IP/key match, strict private client subnets, and an address actually assigned to LAN1 or LAN2. It creates an unprivileged `freeqnap-https` account with no login shell and a separate `freeqnap-https.service`. Nginx binds only the reviewed private address on port 443. Other source networks and unknown Host headers are denied. No port-80 or all-interface listener is created. Proxy buffering/cache staging and identity-header trust are disabled; application host/origin, cookie/session and CSRF checks remain.

The persistent server key remains root-only. Systemd supplies the proxy with read-only credential copies of the key, certificate and fixed nginx configuration. The service retains strict filesystem/home/device protections and only the low-port binding capability. It does not need root, setuid, chown, routing or storage capabilities. The console remains unprivileged and bound to loopback. A narrow service drop-in adds the HTTPS origin allowlist without removing its existing isolation.

A successful service start is insufficient: the installer also requires a certificate-verified HTTPS response. Settings reports service state **and** that actual endpoint check. It never claims the browser trusts the local CA. A failed or interrupted installation is retained for explicit reconciliation rather than being blindly rerun over an existing deployment.

## Trust on your own clients

In **Settings → Local HTTPS**, download the public CA certificate and compare its SHA-256 fingerprint with the trusted local issuer record. Install only that public certificate into the trust store of each intended client.

On macOS, import the certificate with Keychain Access into your chosen user keychain. Open the certificate's Trust settings and trust it for SSL. The user performs the import/trust confirmation; FreeQNAP does not install trust or click through browser security warnings. Other client platforms have their own certificate-installation procedure.

Then open the displayed HTTPS IP address. It must work without a certificate warning. Keep using the authenticated SSH tunnel until it does. A certificate's optional `.local` name does not itself create name discovery; use the IP unless local resolution is verified. Installing a private authority grants trust to certificates it issues, so protect its signing key and limit installation to your own intended devices.

## Maintenance and rollback

A DHCP/static address change requires a matching certificate and bind configuration. The existing deployment deliberately fails closed if its address disappears; the SSH tunnel remains the maintenance path. Choose a stable address policy before depending exclusively on LAN HTTPS. Changing networking from the dashboard still requires its independent confirmation/rollback process.

The initial installer refuses overwriting an existing TLS deployment. Rotation is a separate staged/reviewed maintenance operation: issue a fresh server bundle using the retained CA, validate it with Debian OpenSSL, retain the previous key/certificate/configuration privately, test the resulting nginx configuration, reload and prove a verified response. Do not change the authority or widen client networks as an incidental renewal. Automated renewal/rotation and DHCP reissuance are not claimed as implemented.

The selected encrypted NAS recovery archive includes the root-private HTTPS server artifacts and service configuration; the offline CA signing key is excluded because it never resides on the NAS. After a recovery to different addresses/identities, review and reissue the leaf certificate before activation. Removing LAN HTTPS must preserve the original loopback console and restore its service command without deleting administrator state.

## Validation

A real strict TLS handshake in the host regression suite verifies the generated certificate chain and IP identity without weakening verification flags. A live replacement server certificate under the same offline authority passed strict verification on both Mac and NAS; the previous leaf/key were retained privately, and only the proxy was restarted. No CA trust or NAS boot setting changed.

Native ARMhf tests in an isolated network namespace verified TLS 1.2 and 1.3, untrusted-CA rejection, unknown Host and unapproved client-subnet denial, ignored forwarded identities, invalid-origin/CSRF denial, Secure/HttpOnly/SameSite cookie login, and logout invalidation with disposable accounts. The live spare additionally returned its real session-status response through CA-verified LAN HTTPS while running as the dedicated unprivileged account. No real password was used by those tests. Browser trust and real-client login remain owner acceptance steps.

References: [nginx HTTPS configuration](https://nginx.org/en/docs/http/configuring_https_servers.html), [nginx proxy behavior](https://nginx.org/en/docs/http/ngx_http_proxy_module.html), [local administration](ADMINISTRATION.md).
