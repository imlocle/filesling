# Remote Torrent Downloads

FileSling can submit magnet links and `.torrent` files to qBittorrent running on
an SSH server. The server receives torrent data directly from peers. FileSling
sends only the torrent job and status requests over its SSH connection.

## Requirements

- A saved FileSling SSH connection to the server running qBittorrent.
- qBittorrent running as a service with its Web UI enabled.
- The qBittorrent Web UI username, password, and port. The usual port is `8080`.
- A server folder that qBittorrent can write to. If Jellyfin should index the
  downloads, the folder must also be in a Jellyfin library.

FileSling connects to `127.0.0.1:<port>` on the SSH server through an SSH direct
channel. It does not connect to the Web UI through the local network. Keep the
qBittorrent Web UI port blocked from the public internet with the server firewall
and router. FileSling's SSH tunnel does not change qBittorrent's listener or
firewall configuration.

## Configure the server

1. Connect to the saved SSH server running qBittorrent.
2. Open **Remote Torrent Downloads** from FileSling's toolbar or File menu.
3. If qBittorrent credentials are missing, FileSling opens the active SSH server's
   settings. Enter the Web UI port, username, and password. Leave the port at
   `8080` if qBittorrent uses its usual default.
4. Optionally enter a default download folder on the server. Leave it blank to
   use qBittorrent's configured default folder.
5. Save the server settings. FileSling stores the Web UI password in the operating
   system credential store. To edit these settings later, choose **Settings** in
   the remote downloads window, or choose **Manage Servers** in the server
   dropdown, select the SSH connection, and choose **Edit**. Saving settings in
   the downloads window reloads the qBittorrent credentials and refreshes the job
   list.

You can use a destination profile to choose a different download folder for a
particular library. When the selected profile belongs to the active server, its
folder is filled into the download window. You can edit the folder before adding
each job.

## Add and manage downloads

1. Open **Remote Torrent Downloads** from the toolbar button or the File menu.
2. Paste a magnet link and choose **Add Magnet**, or choose **Add .torrent File**.
3. Check the server-side download folder, then add the job.
4. Select a job to pause, resume, move, or remove it. To move a torrent, enter
   the destination folder in **Download folder on server** and choose
   **Move Selected**. qBittorrent moves the data and keeps tracking the torrent.
   The folder must exist and be writable by qBittorrent.
5. **Remove Job, Keep Data** removes the job from qBittorrent without deleting
   its downloaded files. **Delete Job + Data** permanently deletes both the job
   and its downloaded files after confirmation.

Local `.torrent` files can be up to 32 MB.

FileSling refreshes the job list every ten seconds while this window is open.
You can keep entering a magnet link during a refresh. If you submit while a
refresh is already running, FileSling queues the request and sends it when the
refresh finishes. The qBittorrent service continues downloading and seeding if
FileSling closes.
Opening the window later shows the jobs still known to qBittorrent. To relocate
a torrent, use **Move Selected** so qBittorrent updates its location and keeps
seeding from the new folder.

### A job shows Error

`Error` means qBittorrent stopped the job because of an error. Select **Resume**
to retry it. If it returns to Error, check the qBittorrent Web UI or service logs
for the cause. Also confirm that the selected server folder exists and that the
account running qBittorrent can access and write to it. FileSling's status list
shows qBittorrent's error state, but older qBittorrent API versions may not
provide the underlying error message.

## Jellyfin refresh

When a job reaches 100% while the remote downloads window is open, FileSling
requests a Jellyfin library refresh if scanning is enabled in the server settings
or the active destination profile. Configure a Jellyfin URL and API key in the
server settings. Jellyfin must already have a library that includes the download
folder. The refresh requests a library scan; it does not add or change Jellyfin
library paths.

The completion scan depends on FileSling observing the job finish. If FileSling
is closed while a job completes, the download remains in qBittorrent, but this
version does not trigger a delayed scan when FileSling next opens.

For qBittorrent 4.5.2 API details, see the
[official WebUI API documentation][qbittorrent-api].

[qbittorrent-api]: https://github.com/qbittorrent/qBittorrent/wiki/WebUI-API-%28qBittorrent-4.1%29
