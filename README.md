# Condor AI

**English** · [Português](README.pt-BR.md) · [Español](README.es.md)

A personal AI system that runs **on its owner's computer**, with one persistent identity, encrypted memory and explicit control over every sensitive capability.

It is not a wrapper around one model. Local models, OpenAI and Claude are interchangeable engines; what persists is the identity, the memory policy, the permissions and the interface.

---

## Why it exists

A hosted AI assistant has a structural problem: its memory belongs to someone else. You talk for months, and that history — who you are, what you already explained, what you decided — lives on a server that can change its rules, its price or its owner.

Condor inverts that. The memory sits encrypted on the owner's disk; the model is the replaceable part.

## Design principles

- **One mind:** PC, mobile viewer and the optional cloud companion are interfaces to the same canonical identity.
- **Local ownership:** private state stays under the owner's control and is never committed with the source.
- **Automation that fails closed:** computer, file and physical-device actions pass through policy and explicit approval.
- **Model independence:** the deterministic core keeps working without a paid API.
- **Inspectable security:** encryption, integrity checks, audit chaining and recovery paths are documented and tested.

## Capabilities

- A FastAPI core bound to `127.0.0.1`, with its own desktop interface.
- Vault and memory snapshot encrypted with **AES-256-GCM**, key derived with **scrypt**.
- Persistent facts, conversations, tasks, project state and versioned drafts.
- A stable `condor-core-identity-v1` identity above the model router.
- Selectable Local, OpenAI and Claude connectors, with secret redaction.
- Local speech, optional wake word, authentication-only computer vision and private image generation.
- Permission-scoped tools for files, applications, research and development work.
- A **read-only** mobile viewer on the private network — no command, memory or vault routes.
- Condor X: an experimental space for 3D design and bounded engineering simulation.
- An optional PWA foundation (`cloud/`) for encrypted chat, notes and memory while the PC is off.

## Backup: the one irreplaceable part

The code comes back from a `git clone`. The **memory, identity and vault do not** — they exist only in `~/.condor`, on this machine.

So the backup is automated rather than a good intention:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_backup_task.ps1
```

It asks for a destination folder, asks for the passphrase **once**, and schedules a daily run plus one five minutes after each logon — for the days the PC was off at the appointed hour.

The passphrase is protected by Windows DPAPI, readable only by this account on this machine. **The backup file itself stays portable:** it opens with the passphrase on any computer — which is exactly the point if this machine dies. The fourteen most recent are kept.

Testing the restore is part of the procedure, because a backup nobody has restored is a hope, not a backup:

```powershell
powershell -File scripts\restore_condor_data.ps1 -BackupFile "<file.enc>" -CondorHome "$env:TEMP\restore-test"
```

## Security boundary

The full core must stay loopback-only. **Never expose port `7777` to the internet.** The mobile viewer runs as a separate process on a separate port, is restricted to private networks, requires pairing and returns sanitised read-only data.

Secrets, biometric templates, memory, configuration, logs and user files live outside the repository, in `~/.condor` by default. The repository restores the application, but it cannot restore that private state. Never publish or recreate an existing `~/.condor` when publishing the source.

Read the [security model](SECURITY.md), the [architecture](ARCHITECTURE.md) and the [operations guide](OPERATIONS.md).

## Architecture at a glance

```text
Desktop UI / voice / local projects
                |
          Local FastAPI core
                |
   identity + policy + encrypted memory
        /           |             \
 deterministic   local model   optional APIs

Separate boundaries:
- read-only mobile viewer
- encrypted cloud companion foundation
```

## Windows setup

Requires Python 3.11 or newer.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_new_windows_pc.ps1
```

Manual installation:

```powershell
.\scripts\install.ps1
.\scripts\install_local_ai.ps1
.\scripts\run.ps1
```

The initial model downloads can be large. After that, configured local models run without an external AI account.

## Verification

```powershell
.\.venv\Scripts\python.exe testes\rodar_testes.py
.\.venv\Scripts\python.exe scripts\doctor.py
```

The suite covers policy, vault encryption, memory, identity, provider routing, interface boundaries, device safety and the Condor X simulation rules — **without requiring a paid API**. With 114 tests, it is the best-covered repository of the set.

The cloud companion is verified separately:

```powershell
Set-Location cloud
npm.cmd install
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run build
```

## Repository map

```text
condor/        Core, memory, security, devices, UI and project engines
cloud/         Optional encrypted PWA companion foundation
deploy/        Private-network deployment examples
scripts/       Installation, diagnostics, backup and local runtime
testes/        Security and behaviour regression suite
windows/       Native Windows launcher identity
```

## Status, without makeup

Condor is an active personal R&D system, not a finished consumer assistant. Local PC operation and tested safety boundaries are implemented. The cloud companion is a foundation that still needs its own infrastructure, real authentication and end-to-end validation. The Condor X tools are prototypes and simulations — they claim no validated physical performance.

## Licence

A source-available, proprietary portfolio project. Public visibility grants no permission to copy, redistribute or commercialise.

Built and maintained by [Kauã Diniz Souza](https://github.com/Kauadsouza).
