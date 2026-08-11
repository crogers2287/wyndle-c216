# Architecture

Milestones 0–1 deliberately contain only configuration, structured logging, and a diagnostic
probe. Higher-level Wyndle code must consume camera capabilities through a stable adapter only
after the physical C216 paths are measured. The probe never records continuous media and does
not print camera credentials.
