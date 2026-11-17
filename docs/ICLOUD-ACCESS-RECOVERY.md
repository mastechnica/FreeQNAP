# Restore Apple web access for iCloud Photos

If photo access expires or its approval times out, open **Photos → Import & iCloud → Request Apple web access again**. Refresh the dashboard first if the new button is missing. Approve the separate iCloud Photos web-access request on your trusted iPhone or Mac. A six-digit sign-in code and web-access approval are different steps. If Apple requests sign-in or a new code, complete those fields privately in the trusted HTTPS dashboard.

This control recreates the in-memory Apple client using the saved sign-in files and requests photo access again. It retains cookies, configuration, archived originals, and resumable partial files. It does not delete or reconfigure the archive. Apple may still require full authentication if the saved session is no longer valid. The backend prevents concurrent checks/downloads and rate-limits repeated authentication requests.

Once **Connected · photo access verified** appears, enabled scheduled downloads can resume. Use **Download new items now** if no download is running. Existing imported originals are retained and matched during subsequent passes. The discovered pending count is not the number remaining in iCloud until remote inventory has completed.

The gallery now links to access recovery when Apple approval is blocked. Historical checking/downloading messages are not shown as current work when no download is running.

## Deployment and validation

The change was deployed on 10 November 2026 to the existing release, after comparing both source baselines and checking that no queued/running NAS jobs or active iCloud operation prevented a broker reload. The two prior files were retained under `/var/backups/freeqnap-maintenance/icloud-reapproval-20261110`. No NAS reboot, driver change, Apple approval attempt or download restart was performed by deployment.

Ninety personal-photo tests and ten photo-feedback JavaScript tests passed, including fresh-client recreation without deleting saved sign-in files, busy-task rejection, rate limiting and approval-button state. The live HTTPS service was verified to serve the new control. Actual Apple approval requires my trusted device and has not been claimed from fixtures.
