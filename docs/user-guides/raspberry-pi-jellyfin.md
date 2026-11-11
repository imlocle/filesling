# Raspberry Pi and Jellyfin Setup

Personal reference for the Raspberry Pi setup used with FileSling.

## Overview

Raspberry Pi 4 running Jellyfin as the media server. FileSling connects to it via SSH to upload/manage video files on the external drive.

## Hardware

- Raspberry Pi 4 (4GB)
- MicroSD card (16GB+)
- External hard drive (USB, mounted at `/mnt/external`)
- HDMI cable (HDMI0 port)
- Ethernet (or Wi-Fi)

## OS Setup

1. Flash **Raspberry Pi OS (64-bit, Lite)** via Raspberry Pi Imager
2. Configure in Imager settings:
   - Username: `pi`
   - Enable SSH
   - Set Wi-Fi (if not using Ethernet)
   - Set timezone
3. Boot and update:
   ```bash
   sudo apt update && sudo apt upgrade -y
   sudo reboot
   ```

### Connect on Terminal

```bash
# Connect to the Pi using its current address
ssh pi@<pi-ip>
```

## External Drive

```bash
# Check device
lsblk

# Install filesystem support
sudo apt install -y ntfs-3g exfatprogs

# Mount
sudo mkdir -p /mnt/external
sudo chown pi:pi /mnt/external
sudo mount -o uid=1000,gid=1000 /dev/sda1 /mnt/external

# Auto-mount on boot
blkid  # get UUID
sudo nano /etc/fstab
# Add: UUID=YOUR-UUID /mnt/external exfat defaults,uid=1000,gid=1000 0 0
sudo mount -a
```

### Adding a Second Drive

```bash
# Plug in the new drive, find its device name
lsblk  # look for the new one (e.g., /dev/sdb1)

# Create mount point
sudo mkdir -p /mnt/external2
sudo chown pi:pi /mnt/external2

# Mount it
sudo mount -o uid=1000,gid=1000 /dev/sdb1 /mnt/external2

# Get UUID for auto-mount
blkid /dev/sdb1

# Add to fstab
sudo nano /etc/fstab
# Add: UUID=YOUR-NEW-UUID /mnt/external2 ntfs defaults,uid=1000,gid=1000 0 0

# Test
sudo mount -a
ls /mnt/external2
```

Then add a new library in Jellyfin pointing to `/mnt/external2/`. In FileSling, add `/mnt/external2` as a bookmark on the Pi server for quick access.

## Install Jellyfin

Use the current instructions in the [official Jellyfin Linux guide](https://jellyfin.org/docs/general/installation/linux/). For Raspberry Pi OS, the guide provides a Debian-family install script. Download the script and its checksum, verify the checksum, inspect it if desired, then run it:

```bash
# Download the installer and checksum
curl -fsSLO https://repo.jellyfin.org/install-debuntu.sh
curl -fsSLO https://repo.jellyfin.org/install-debuntu.sh.sha256sum

# Verify the downloaded installer
sha256sum -c install-debuntu.sh.sha256sum

# Optional: inspect the installer before running it
less install-debuntu.sh

# Install Jellyfin
sudo bash install-debuntu.sh

# Start and enable
sudo systemctl enable jellyfin
sudo systemctl start jellyfin
```

Access the web UI at `http://<pi-ip>:8096` to complete setup.

### Add Media Library

1. Open Jellyfin web UI, then go to Dashboard and Libraries.
2. Add library:
   - Type: Movies (or TV Shows)
   - Path: `/mnt/external/Movies` (or `/mnt/external/TV Shows`)
3. Enable NFO metadata reading (for FileSling .nfo sidecar compatibility)

### NFO Metadata (Jellyfin + FileSling)

FileSling writes `.nfo` sidecar files next to video files. Jellyfin reads these automatically:

- `movie.nfo` → movie metadata
- `tvshow.nfo` → series metadata
- Episode files use `episodedetails` type

In Jellyfin Library settings, ensure "Nfo" is enabled under Metadata Readers. FileSling can optionally request a library refresh after its queued uploads finish. Configure the Jellyfin URL and API key in the server's FileSling settings. The refresh does not configure library paths.

## SSH Access (for FileSling)

```bash
# Generate key on your Mac (if you haven't already)
ssh-keygen -t ed25519

# Copy to Pi
ssh-copy-id pi@<pi-ip>

# Test
ssh pi@<pi-ip>
```

FileSling connects using this SSH key to browse and upload files to `/mnt/external`.

## Useful Commands

```bash
# Check Jellyfin status
sudo systemctl status jellyfin

# Restart Jellyfin if the service needs recovery
sudo systemctl restart jellyfin

# Check disk space
df -h /mnt/external

# Find Pi's IP
hostname -I

# Check if drive is mounted
mount | grep external
```

## FileSling Server Config

In FileSling, add this server:

| Setting         | Value                           |
| --------------- | ------------------------------- |
| Name            | Raspberry Pi                    |
| Connection type | SSH                             |
| Host            | `<pi-ip>` (e.g., 192.168.1.100) |
| Username        | pi                              |
| SSH Key         | `~/.ssh/id_ed25519`             |
| Port            | 22                              |
| Base directory  | `/mnt/external`                 |

## Destination Profiles

After adding the Raspberry Pi connection, open the **Destination** dropdown in FileSling and choose **Manage Destinations**. Create a profile such as `Jellyfin Movies`, select the Raspberry Pi connection, and enter the matching library folder, for example `/mnt/external/Movies`. Set duplicate handling to Ask, Skip, or Overwrite. Choose whether Jellyfin scans follow the server setting, always run, or stay off. The profile reuses the saved SSH credentials.

Create another profile for `/mnt/external/TV Shows` if you want separate upload targets for movies and series.

## Troubleshooting

```bash
# Jellyfin logs
sudo journalctl -u jellyfin -f

# Check external drive
lsblk
sudo mount -a

# Restart if stuck
sudo reboot
```
