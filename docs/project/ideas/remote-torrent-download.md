# Feature Idea: Download Torrents Directly to the Raspberry Pi

**Status:** Initial qBittorrent integration implemented for FileSling 3.8.0
**User workflow:** Torrent locally, then use FileSling to transfer the media to a Raspberry Pi running Jellyfin.

## Current Raspberry Pi setup

Checked on November 11, 2026: `qbittorrent-nox` is installed and running as the enabled `qbittorrent-nox.service`. The service has been active since November 5, 2026, and its process was started with `--webui-port=8080`. The Web UI is listening on a wildcard address at port 8080, so it is not limited to loopback. FileSling checks Web UI reachability and authentication when opening remote downloads. Keep the port blocked from the public internet; FileSling's SSH tunnel does not change qBittorrent's listener or firewall settings.

## The idea

Let the user submit a magnet link or `.torrent` file from FileSling and have a torrent client running on the Raspberry Pi download the payload directly into a chosen server-side folder.

FileSling would send the torrent job and monitor it. The Raspberry Pi would receive the torrent pieces from peers and write the completed media to its own storage. The media payload would not pass through the user's computer or through FileSling.

## Why it could help

- Avoids downloading a full copy to the computer before transferring it.
- Saves local disk space and removes the extra manual transfer step.
- Lets the Raspberry Pi download over its own network connection and remain active while the computer is off.
- Could hand completed files to the existing Jellyfin library refresh workflow.

There is an important network detail: when the computer and Pi are on the same home network, FileSling's current transfer normally travels over the local network, not the internet. In that setup, the torrent consumes internet data once; the extra computer-to-Pi transfer consumes local network bandwidth. Direct-to-Pi downloading still saves local storage and effort. If the Pi is off-site, the current workflow can also send the media over the internet from the computer to the Pi.

## Current user flow

1. Choose a destination profile for the Raspberry Pi.
2. Paste a `magnet:` link or add a `.torrent` file.
3. Choose a server-side folder, optionally using the selected destination profile.
4. FileSling submits the job to qBittorrent on the Pi and shows its status in a download window.
5. The Pi downloads the data directly to the chosen folder.
6. When complete, FileSling can request a Jellyfin library refresh if it observes completion while the window is open. qBittorrent retains control of the file if it is still seeding.

## Implemented in FileSling 3.8.0

- FileSling connects to qBittorrent's Web UI API on the SSH server through an SSH direct channel to `127.0.0.1`.
- The server-specific settings store the Web UI port, username, and download folder. The password is stored in the OS credential store.
- A Settings button in the remote downloads window opens the active SSH server's settings and reloads qBittorrent credentials after saving.
- Users can add a magnet link or a local `.torrent` file, view the qBittorrent job list, pause, resume, relocate, and remove jobs.
- Removing a job can keep its downloaded data or delete it after confirmation.
- A selected destination profile provides the initial server-side download folder.
- When a job completes while the remote downloads window is open, FileSling can request a Jellyfin refresh using the existing server or profile setting.
- The qBittorrent service owns download and seed work, so jobs continue if FileSling closes.

This separates control from payload: FileSling sends a small torrent job and receives status updates, while the torrent data travels directly between peers and the Pi. FileSling currently detects completion for Jellyfin refreshes only while its remote downloads window is open.

The first integration targets an already running qBittorrent Web UI. FileSling does not install or configure a torrent client or verify the server-side destination before adding the job.

## Follow-up ideas

- Should downloads go into a staging folder and move after completion, or should the torrent client manage the completed path so seeding continues?
- Should destination profiles also select a qBittorrent category?
- Should FileSling keep monitoring completion when the downloads window is closed, and request scans for jobs that finish while FileSling is not open?
- Should the status view include remaining size, ETA, seeders, and peers?

## Security and reliability considerations

- FileSling's qBittorrent API calls go through the verified SSH connection. Keep qBittorrent's Web UI port blocked from the public internet.
- Store API credentials in the operating system credential store, consistent with FileSling's existing SSH and Jellyfin secrets handling.
- Validate magnet links and torrent files as data. Do not interpolate user-provided links into remote shell commands.
- Show whether a job is downloading, paused, complete, seeding, or failed, and allow FileSling to reconnect to jobs that continue on the Pi.
- Make destination permissions and available disk space clear before submission where the client API supports those checks.
- Avoid moving or renaming a completed file behind the torrent client's back while it is seeding.

## Milestone status

The initial qBittorrent milestone is implemented. Keep the existing FileSling upload and download workflows unchanged while considering the follow-up ideas above.
