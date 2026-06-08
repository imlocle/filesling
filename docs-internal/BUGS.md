# Bugs

> Known issues and potential bugs. For fixed bugs, see [CHANGELOG.md](CHANGELOG.md).

---

## Open Bugs

None.

---

## Accepted / Won't Fix

- **BUG-DA-22: Cancel during retry window can hit wrong queue item** — 1-second window after retry re-insert where pending positions may be out of sync. Extremely rare race condition; complexity of fix outweighs the risk.
- **BUG-DA-16: Download progress only updates every 500ms** — timer-based refresh, by design for performance.
- **BUG-DA-24: Drag-to-Finder freezes UI for large files** — synchronous download on main thread. Acceptable for small files (photos). Large files should use right-click → Download.
