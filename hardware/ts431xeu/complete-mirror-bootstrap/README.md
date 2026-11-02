# Accepted complete-mirror bootstrap profile

These `select-root.sh` and `boot-record.sh` bytes match the generic dev004
bootstrap used by the physically accepted installed image. The security-only
6.12.115/FreeQNAP6 build pins both hashes and its original `init` hash. It retains
the complete OS mirror requirement; it does not adopt experimental one-member
root boot during an unrelated security update.

The genuine common `boot-policy.sh` library is packaged for the shared bootstrap
audit, but the pinned selector never sources it. This does not fabricate a policy
implementation or weaken the required-file/identity audits. The separate
restricted-survivor candidate continues to use the installer target sources and
its own RAM-only acceptance boundary.

This source/profile separation is not permission to flash an image. New artifacts
remain RAM-only and flash-prohibited until their own hardware/rollback review.
