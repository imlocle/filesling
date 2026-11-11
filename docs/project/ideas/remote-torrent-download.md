# Feature Idea: Download Torrents Directly to the Raspberry Pi

**Status:** Brainstorming, not scheduled or implemented
**User workflow:** Torrent locally, then use FileSling to transfer the media to a Raspberry Pi running Jellyfin.

## Current Raspberry Pi setup

Checked on November 11, 2026: `qbittorrent-nox` is installed and running as the enabled `qbittorrent-nox.service`. The service has been active since November 5, 2026, and its process was started with `--webui-port=8080`. The Web UI is listening on a wildcard address at port 8080, so it is not limited to loopback. This makes the existing qBittorrent service the natural first integration target. The listener output alone does not show whether a firewall or router permits access from outside the Pi's network. FileSling still needs to verify Web UI reachability and authentication before submitting jobs.

## The idea

Let the user submit a magnet link or `.torrent` file from FileSling and have a torrent client running on the Raspberry Pi download the payload directly into a chosen server-side folder.

FileSling would send the torrent job and monitor it. The Raspberry Pi would receive the torrent pieces from peers and write the completed media to its own storage. The media payload would not pass through the user's computer or through FileSling.

## Why it could help

- Avoids downloading a full copy to the computer before transferring it.
- Saves local disk space and removes the extra manual transfer step.
- Lets the Raspberry Pi download over its own network connection and remain active while the computer is off.
- Could hand completed files to the existing Jellyfin library refresh workflow.

There is an important network detail: when the computer and Pi are on the same home network, FileSling's current transfer normally travels over the local network, not the internet. In that setup, the torrent consumes internet data once; the extra computer-to-Pi transfer consumes local network bandwidth. Direct-to-Pi downloading still saves local storage and effort. If the Pi is off-site, the current workflow can also send the media over the internet from the computer to the Pi.

## Possible user flow

1. Choose a destination profile for the Raspberry Pi.
2. Paste a `magnet:` link or add a `.torrent` file.
3. Choose a category or destination folder.
4. FileSling submits the job to the torrent client on the Pi and shows its status in a download queue.
5. The Pi downloads the data directly to its configured incomplete or completed location.
6. When complete, FileSling can request a Jellyfin library refresh. The torrent client should retain control of the file if it is still seeding.

## Possible implementation shape

The Pi would run a torrent client as a persistent service. FileSling would connect to that service through an authenticated API, preferably over the home network or a private VPN. The service would keep downloading if FileSling closes, and FileSling could reconnect later to recover job status.

This separates control from payload: FileSling sends a small torrent job and receives status updates, while the torrent data travels directly between peers and the Pi. A persistent torrent daemon is a better fit than starting a long-running download as a child process of the desktop app.

FileSling should not need to install or configure a torrent client automatically for an initial version. It could guide the user through configuring an already-running supported client, then test the connection and destination permissions.

## Questions to decide before implementation

- Should FileSling support the existing qBittorrent-nox instance first, then consider an adapter boundary for other clients?
- Should downloads go into a staging folder and move after completion, or should the torrent client manage the completed path so seeding continues?
- Should choosing a destination profile also select a torrent category and trigger a Jellyfin scan after completion?
- Which controls belong in FileSling for the first version: pause, resume, cancel, and remove, or status monitoring only?

## Security and reliability considerations

- Keep the torrent client's API private to the LAN or VPN. Do not expose an unauthenticated control interface to the public internet.
- Store API credentials in the operating system credential store, consistent with FileSling's existing SSH and Jellyfin secrets handling.
- Validate magnet links and torrent files as data. Do not interpolate user-provided links into remote shell commands.
- Show whether a job is downloading, paused, complete, seeding, or failed, and allow FileSling to reconnect to jobs that continue on the Pi.
- Make destination permissions and available disk space clear before submission where the client API supports those checks.
- Avoid moving or renaming a completed file behind the torrent client's back while it is seeding.

## Suggested first milestone

Connect to one torrent client already installed on the Pi, submit magnet links and `.torrent` files, show persistent job status, and optionally request a Jellyfin scan when a download completes. Keep the existing FileSling upload and download workflows unchanged.
