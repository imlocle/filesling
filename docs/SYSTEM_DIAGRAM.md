# System Diagram

> **Last updated:** July 2026 — Version 3.5.1

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
    end

    subgraph Controllers["Controller Layer"]
        MWC[MainWindowController]
        CC[ConnectionController]
        DC[DownloadController]
        FOC[FileOperationsController]
        TC[TransferController]
    end

    subgraph Workers["Background Threads (src/workers/)"]
        CW[ConnectionWorker]
        TW[TransferWorker]
        DW[DownloadWorker]
        DL[DirectoryLoader]
        SR[SearchWorker]
        DU[DiskUsageWorker]
    end

    subgraph Clients["Device Clients (src/clients/)"]
        DC_PROTO[DeviceClient Protocol]
        ADB[ADBClient]
        IOS[IOSClient]
        SFTP[Paramiko SFTPClient]
    end

    subgraph Services["Service Layer"]
        CM[ConnectionManagerService]
        RFS[RemoteFileService]
        FDS[FileDeletionService]
        AHS[ActivityHistoryService]
        NS[NotificationService]
        KS[KeychainService]
        RS[RsyncService]
        FF[FfmpegService]
        SI[SleepInhibitorService]
        MB[MenuBarService]
    end

    subgraph Platform["Platform Layer (src/platform/)"]
        PM[macOS — Keychain, osascript, caffeinate, Finder]
        PW[Windows — keyring, toast, SetThreadExecutionState, Explorer]
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
        History["~/.FileSling/transfer_history.json"]
        Queue["~/.FileSling/transfer_queue.json"]
        Errors["~/.FileSling/logs/errors.json"]
        Keychain["macOS Keychain"]
    end

    MW --> MWC
    MW --> FE
    MW --> TQ
    MW --> DP
    MW --> BB
    MWC --> CC
    MWC --> DC
    MWC --> FOC
    MWC --> TC
    MWC --> NS
    CC --> CW
    CC --> CM
    TC --> TW
    DC --> DW
    FE --> DL
    FE --> SR
    FE --> DU
    VCM --> FF

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
    alt SSH with rsync available
        TC->>Client: Try rsync (delta transfer)
        alt rsync fails
            TC->>Client: Fallback to SFTP
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
    TC->>AHS: Record in activity history
    TC->>NS: Send notification + update Dock badge
    TC->>MW: transfer_completed signal
    MW->>Explorer: refresh()
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
    CheckAuth -->|Keychain| FetchKC[Fetch from macOS Keychain]
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
    CheckAlive -->|Yes| UpdateLatency[Update latency indicator]
    CheckAlive -->|No| AutoReconnect[Auto-reconnect]
    AutoReconnect --> StartCW
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
    CheckType -->|SSH| CheckRsync{rsync available?}
    CheckType -->|ADB| UseADB[adb push]
    CheckType -->|iOS| UseIOS[AFC write]

    CheckRsync -->|Yes| TryRsync[rsync --progress]
    CheckRsync -->|No| UseSFTP[SFTP put]

    TryRsync --> RsyncOK{Success?}
    RsyncOK -->|Yes| Done[Transfer complete ✓]
    RsyncOK -->|No| UseSFTP

    UseSFTP --> Done
    UseADB --> Done
    UseIOS --> Done

    style TryRsync fill:#90EE90
    style UseSFTP fill:#87CEEB
    style UseADB fill:#FFD700
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
