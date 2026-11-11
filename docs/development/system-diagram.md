# System Diagram

> **Last updated:** November 2026: Version 3.8.0

## High-Level Architecture

```mermaid
graph TB
    subgraph UI["UI Layer (PySide6)"]
        MW[MainWindow]
        FE[FileExplorerWidget]
        TQ[TransferQueueWidget]
        DP[DetailPanel]
        BB[BookmarksBar]
        VCM[VideoConvertManager]
        SS[SettingsWindow]
    end

    subgraph Dialogs["Dialogs"]
        SSD[ServerSelectionDialog]
        BRD[BatchRenameDialog]
        BMD[BatchMetadataDialog]
        CSD[ConvertSettingsDialog]
        FPD[FolderPickerDialog]
        MID[MediaInfoDialog]
        QFD[QuickFixDialog]
        TSW[TrackSelectionWidget]
    end

    subgraph Controllers["Controller Layer"]
        MWC[MainWindowController]
        CC[ConnectionController]
        DC[DownloadController]
        FOC[FileOperationsController]
        MTC[MediaToolsController]
        TC[TransferController]
    end

    subgraph Workers["Background Threads (src/workers/)"]
        CW[ConnectionWorker]
        TW[TransferWorker]
        DW[DownloadWorker]
        DL[DirectoryLoader]
        NFW[NfoCacheWorker]
        SW[SearchWorker]
        DU[DiskUsageWorker]
        IW[IMDbWorker]
        JFW[JellyfinRefreshWorker]
        CVW[ConvertWorker]
        QFW[QuickFixWorker]
    end

    subgraph Clients["Device Clients (src/clients/)"]
        DC_PROTO[DeviceClient Protocol]
        ADB[ADBClient]
        IOS[IOSClient]
        SFTP[Paramiko SFTPClient]
        SSHCmd[SSH session helper]
    end

    subgraph Services["Service Layer"]
        CM[ConnectionManagerService]
        RFS[RemoteFileService]
        MFS[MediaFileService]
        FDS[FileDeletionService]
        BRS[BatchRenameService]
        AHS[ActivityHistoryService]
        NS[NotificationService]
        KS[KeychainService]
        RS[RsyncService]
        RCS[RcloneService]
        FF[FfmpegService]
        RMS[RemoteMediaService]
        NFC[NfoMetadataCacheService]
        TQS[TransferQueueService]
        SI[SleepInhibitorService]
        MB[MenuBarService]
        IS[IMDbService]
    end

    subgraph Repositories["Persistence Repositories"]
        SRepo[SettingsRepository]
        AHR[ActivityHistoryRepository]
        TQR[TransferQueueRepository]
    end

    subgraph MetadataAPIs["Metadata Providers (HTTP)"]
        OMDB[OMDb API]
        TMDB[TMDB API]
    end

    subgraph MediaServer["Media Server API"]
        Jellyfin[Jellyfin HTTP API]
    end

    subgraph Platform["Platform Layer (src/platform/)"]
        PM[macOS: Keychain, notifications, caffeinate, Finder]
        PW[Windows: credential manager, tray notifications, sleep control, Explorer]
    end

    subgraph External["External Systems"]
        SSH[SSH/SFTP Server]
        Android[Android Device USB/WiFi]
        iPhone[iOS Device USB]
        FS[Local Filesystem]
    end

    subgraph Config["Configuration & Storage"]
        Settings[Settings Singleton]
        JSON["~/.FileSling/config.json"]
        History["~/.FileSling/activity_history.json"]
        Queue["~/.FileSling/transfer_queue.json"]
        Errors["~/.FileSling/logs/errors.json"]
        Keychain["Operating system credential store"]
    end

    MW --> MWC
    MW --> FE
    MW --> TQ
    MW --> DP
    MW --> BB
    MWC --> CC
    MWC --> DC
    MWC --> FOC
    MWC --> MTC
    MWC --> TC
    FE --> MTC
    MWC --> NS
    CC --> CW
    CC --> CM
    TC --> TW
    TC --> TQS
    DC --> DW
    FE --> DL
    FE --> NFW
    FE --> NFC
    FE --> SW
    FE --> DU
    VCM --> FF
    MTC --> RMS
    QFD --> TSW
    NFW --> RMS
    NFW --> NFC
    MTC --> CVW
    MTC --> QFW
    MTC --> AHS
    BRD --> BRS
    BRS --> AHS
    BRS --> MFS
    AHS --> AHR
    TQS --> TQR
    RMS --> SSHCmd
    FF --> SSHCmd
    TW --> SSHCmd
    DU --> SSHCmd
    QFW --> SSHCmd
    Settings --> SRepo
    SRepo --> JSON
    AHR --> History
    TQR --> Queue
    MID --> IW
    IW --> IS
    IS --> OMDB
    IS --> TMDB
    MWC --> JFW
    JFW --> Jellyfin

    DC_PROTO <|.. SFTP
    DC_PROTO <|.. ADB
    DC_PROTO <|.. IOS

    CM --> SSH
    ADB --> Android
    IOS --> iPhone
    FDS --> FS
    AHS --> History
    KS --> Keychain
    RS --> SSH
    RCS --> SSH
    Settings --> JSON
    TC --> Queue

    TW --> SFTP
    TW --> ADB
    TW --> IOS
    DW --> SFTP
    DW --> ADB
    DW --> IOS
    DL --> SFTP
    DL --> ADB
    DL --> IOS
    NFW --> SFTP
```

## NFO Cache Flow

```mermaid
sequenceDiagram
    participant FE as FileExplorerWidget
    participant DL as DirectoryLoader
    participant NW as NfoCacheWorker
    participant SFTP as Metadata SFTP channel
    participant Cache as NfoMetadataCacheService
    participant DP as DetailPanel

    FE->>DL: Load current directory
    DL-->>FE: Listing and NFO sidecar names
    FE->>NW: Prefetch listed sidecars in background
    NW->>SFTP: Read NFO files
    NW-->>Cache: Parsed metadata by NFO path
    FE->>Cache: Get metadata for selected file
    Cache-->>FE: Cached metadata
    FE->>DP: Render sidecar values
```

## Upload Flow

```mermaid
sequenceDiagram
    participant User
    participant Explorer as FileExplorerWidget
    participant MW as MainWindow
    participant TC as TransferController
    participant TW as TransferWorker
    participant Client as DeviceClient (SFTP/ADB/iOS)
    participant NS as NotificationService

    User->>Explorer: Drag files from Finder (onto folder or explorer)
    Explorer->>MW: files_dropped signal (with target dir)
    MW->>MW: Check for duplicates (stat)
    alt Duplicates found
        MW->>User: Show overwrite/skip/cancel dialog
    end
    MW->>TQ: add_transfer (visual queue)
    MW->>TC: queue_transfer(paths, destination)
    TC->>TC: Persist to transfer_queue.json
    TC->>TC: _process_next()
    alt SSH with rclone available and key authentication
        TC->>Client: Try rclone (4 parallel transfers)
        TC->>Client: Verify uploaded files with SHA-256
        alt rclone fails
            TC->>Client: Try rsync
            alt rsync fails
                TC->>Client: Fallback to SFTP
            end
        end
    else SFTP / ADB / iOS
        TC->>Client: Open dedicated session
    end
    TC->>TW: Start on QThread
    TW->>TW: Skip already-uploaded files (resume)
    TW->>TW: Compress folder if configured
    TW->>Client: put() / push
    TW-->>TC: progress signal
    TW-->>TC: finished signal
    Note over TW,Client: SFTP stages each file remotely and verifies SHA-256 before replacement
    TC->>AHS: Record in activity history
    TC->>NS: Send notification + update Dock badge
    TC->>MW: transfer_completed signal
    MW->>Explorer: refresh()
    opt Jellyfin refresh enabled for this server
        MW->>MW: Wait until queued transfers finish, then debounce request
        MW->>JFW: Request library refresh over HTTP
    end
```

## Download Flow

```mermaid
sequenceDiagram
    participant User
    participant Explorer as FileExplorerWidget
    participant DC as DownloadController
    participant DW as DownloadWorker
    participant Client as DeviceClient (SFTP/ADB/iOS)
    participant Local as Local Filesystem
    participant NS as NotificationService

    User->>Explorer: Right-click → Download (or Download All)
    Explorer->>DC: file_download_requested signal
    DC->>DC: Check local duplicates
    alt File exists locally (single)
        DC->>User: Overwrite? Yes/No
    end
    DC->>TQ: add_transfer + set_in_progress
    DC->>Client: Open dedicated session
    DC->>DW: Start on QThread
    DW->>Client: get() / pull
    DW->>Local: Write to download_directory (per-server or global)
    DW-->>DC: progress signal
    DW-->>DC: finished signal
    alt Download failed
        DC->>DC: Retry (up to 3 attempts)
    end
    DC->>AHS: Record in activity history
    DC->>TQ: set_completed
    DC->>NS: Send macOS notification
    opt Reveal in Finder enabled
        DC->>Local: Open Finder at download path
    end
```

## Connection Flow

```mermaid
flowchart TD
    Start[App Launch] --> CheckDefault{Default server set?}
    CheckDefault -->|Yes| LoadServer[Load server config]
    CheckDefault -->|No| ShowDialog[Show Server Selection]
    ShowDialog --> LoadServer

    LoadServer --> CheckType{Connection type?}
    CheckType -->|SSH| StartCW[Start ConnectionWorker]
    CheckType -->|ADB| CheckADB{ADB installed?}
    CheckType -->|iOS| CheckIOS{pymobiledevice3 installed?}

    StartCW --> CheckAuth{Auth method?}
    CheckAuth -->|Key| ConnSSH[SSH Connect with key + optional passphrase]
    CheckAuth -->|Password| ConnSSHPW[SSH Connect with password]
    CheckAuth -->|Credential store| FetchKC[Fetch from platform credential store]
    FetchKC --> ConnSSHPW
    ConnSSH --> Connected
    ConnSSHPW --> Connected

    CheckADB -->|No| PromptInstall{Homebrew available?}
    PromptInstall -->|Yes| BrewInstall[brew install android-platform-tools]
    PromptInstall -->|No| OpenGoogle[Open Google download page]
    BrewInstall --> CheckADB
    OpenGoogle --> End[User installs manually]

    CheckADB -->|Yes| FindDevice[adb devices]
    FindDevice --> DeviceFound{Device found?}
    DeviceFound -->|No| ShowError[Show 'No device' error]
    DeviceFound -->|Yes| ConnADB[Create ADBClient + test listdir]

    CheckIOS -->|No| PromptPip[pip install pymobiledevice3]
    CheckIOS -->|Yes| FindIOS[Detect iOS device]
    FindIOS --> IOSFound{Device found & trusted?}
    IOSFound -->|No| TrustPrompt[Guide user to tap Trust]
    IOSFound -->|Yes| ConnIOS[Create IOSClient]

    ConnADB --> Connected[Connected ✓]
    ConnIOS --> Connected
    Connected --> SetExplorer[Bind client to FileExplorer]
    SetExplorer --> Refresh[Load directory listing]
    Refresh --> HealthTimer[Start 15s health check timer]
    HealthTimer --> CheckAlive{Connection alive?}
    CheckAlive -->|Yes| UpdateLatency[Update latency indicator + reset attempts]
    CheckAlive -->|No| Guard{Reconnect allowed?}
    Guard -->|already reconnecting / disabled| SkipRC[Skip]
    Guard -->|attempts >= MAX| GiveUp[Give up: disable until manual connect]
    Guard -->|OK| BeginRC[_begin_reconnect: disconnect + async worker]
    BeginRC --> StartCW
    StartCW --> RCResult{Worker result?}
    RCResult -->|connected| RebindRefresh[Rebind channels + refresh, reset attempts]
    RCResult -->|failed & capped| GiveUp
    RCResult -->|failed| MarkDisc[Mark disconnected]
```

## Auto-Reconnect (bounded, off the UI thread)

```mermaid
flowchart TD
    Trigger[Dead socket OR explorer listdir failure] --> G{Guard}
    G -->|_reconnecting or _reconnect_disabled| Ignore[Ignore]
    G -->|attempts >= MAX_AUTO_RECONNECT_ATTEMPTS| GiveUp[_give_up_reconnect<br/>disable until manual connect]
    G -->|allowed| Type{Connection type?}

    Type -->|SSH| Begin[_begin_reconnect<br/>disconnect + set _reconnecting]
    Begin --> Async[_start_async_connect → ConnectionWorker on QThread]
    Async --> Conn[connect_should_cancel: interruptible retry loop]
    Conn -->|connected| OK[_on_reconnect_succeeded<br/>rebind + refresh]
    OK -->|first directory listing succeeds| Reset[Reset attempts and clear guard]
    OK -->|first directory listing fails| Retry[Count failure and retry or give up]
    Conn -->|failed| Fail[_on_reconnect_failed]
    Fail -->|capped| GiveUp
    Fail -->|below cap| Disc[Mark disconnected]

    Type -->|ADB/iOS| Local[_reconnect_local<br/>synchronous, fast USB, same cap]
    Local -->|success| ResetL[Reset attempts]
    Local -->|capped| GiveUp

    style Async fill:#87CEEB
    style OK fill:#90EE90
    style GiveUp fill:#f4a3a3
```

## Backend Abstraction

```mermaid
classDiagram
    class DeviceClient {
        <<Protocol>>
        +listdir(path) List~str~
        +listdir_attr(path) List~Any~
        +stat(path) Any
        +put(local, remote, callback)
        +get(remote, local, callback)
        +rename(old, new)
        +mkdir(path)
        +remove(path)
        +rmdir(path)
        +close()
    }

    class SFTPClient {
        Paramiko SSH/SFTP
    }

    class ADBClient {
        Android USB/WiFi
        +listdir_attr_stream(path, batch_size)
        +pull(remote, local, callback)
    }

    class IOSClient {
        iPhone/iPad AFC
    }

    class FileExplorerWidget {
        +sftp: DeviceClient
        +refresh()
        +navigate(item)
        +set_sftp(client)
    }

    DeviceClient <|.. SFTPClient : implements
    DeviceClient <|.. ADBClient : implements
    DeviceClient <|.. IOSClient : implements
    FileExplorerWidget --> DeviceClient : uses
```

## Transfer Method Selection

```mermaid
flowchart LR
    Start[Upload requested] --> CheckType{Connection type?}
    CheckType -->|SSH| CheckRclone{rclone available and key auth?}
    CheckType -->|ADB| UseADB[adb push]
    CheckType -->|iOS| UseIOS[AFC write]

    CheckRclone -->|Yes| TryRclone[rclone --transfers 4]
    CheckRclone -->|No| CheckRsync{rsync available?}
    CheckRsync -->|Yes| TryRsync[rsync --progress]
    CheckRsync -->|No| UseSFTP[SFTP put]

    TryRclone --> RcloneOK{Success and SHA-256 verified?}
    RcloneOK -->|Yes| Done[Transfer complete ✓]
    RcloneOK -->|No| CheckRsync
    TryRsync --> RsyncOK{Success?}
    RsyncOK -->|Yes| Done
    RsyncOK -->|No| UseSFTP

    UseSFTP --> Done
    UseADB --> Done
    UseIOS --> Done

    style TryRsync fill:#90EE90
    style UseSFTP fill:#87CEEB
    style UseADB fill:#FFD700
```

## IMDb Metadata Fetch Flow

```mermaid
flowchart TD
    Start[User enters IMDb ID → Fetch] --> Worker[IMDbWorker on QThread]
    Worker --> Normalize[Normalize ID<br/>tt0983514 / digits / IMDb URL]
    Normalize --> Keys{Which keys set?}
    Keys -->|None| ErrKeys[Error: add OMDb or TMDB key]
    Keys -->|OMDb set| OMDb[OMDb lookup]

    OMDb --> OMDbResult{Result?}
    OMDbResult -->|Found| MapO[Map fields + resolve show name] --> Done[Populate tag fields ✓]
    OMDbResult -->|Auth / network error| Stop[Error: report to user]
    OMDbResult -->|Not found| HasTMDB{TMDB key set?}

    Keys -->|Only TMDB| TMDB
    HasTMDB -->|No| Surface[Surface OMDb 'not found']
    HasTMDB -->|Yes| TMDB[TMDB /find?external_source=imdb_id]

    TMDB --> TMDBResult{Result?}
    TMDBResult -->|Episode| Ep[Map episode + /tv/show_id for name & genres] --> Done
    TMDBResult -->|Movie / TV| MapT[Map result + resolve genres] --> Done
    TMDBResult -->|Empty| NotFound[Error: no metadata on OMDb or TMDB]

    style OMDb fill:#90EE90
    style TMDB fill:#87CEEB
    style Done fill:#90EE90
```

## SFTP Channel Architecture

```mermaid
graph LR
    subgraph Transport["SSH Transport (single TCP connection)"]
        CH1[sftp_client<br/>Main thread: UI ops]
        CH2[sftp_metadata<br/>Detail panel: NFO, ffprobe]
        CH3[sftp_background<br/>DirectoryLoader, DiskUsage, Search]
    end

    subgraph Dynamic["Per-operation sessions"]
        S1[Upload session 1]
        S2[Download session 1]
        S3[Download session 2]
        S4[Convert SSH connection]
    end

    Transport --- Dynamic
```
