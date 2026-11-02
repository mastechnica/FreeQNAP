"""Read-only acceptance policy for shared-disk OS/data MD synchronization."""
def completion_ready(root_degraded, root_action, root_progress, data_degraded, data_action):
    if root_degraded != 0:
        raise ValueError("OS mirror is degraded")
    if root_action not in ("idle", "resync", "check"):
        raise ValueError("Unexpected OS mirror synchronization state: " + root_action)
    if data_degraded not in (0, 1) or data_action not in ("idle", "recover", "resync"):
        raise ValueError("Unexpected data-array synchronization state")
    if data_action == "idle" and data_degraded:
        raise ValueError("Data recovery stopped without redundancy")
    if root_action in ("resync", "check") and root_progress == "delayed" and data_action == "idle":
        raise ValueError("OS maintenance remains delayed without active data synchronization")
    return root_action == "idle" and data_action == "idle" and data_degraded == 0
