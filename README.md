# Condor AI

Condor is a local-first personal AI system designed to run on its owner's computer with one persistent identity, encrypted memory and explicit control over every sensitive capability.

It is not a wrapper around a single model. Local models, OpenAI and Claude can act as interchangeable cognitive engines, while Condor keeps the same identity, memory policy, permissions and user interface.

## Design goals

- **One mind:** PC, mobile viewer and the optional cloud companion are interfaces to the same canonical Condor identity.
- **Local ownership:** private state lives under the owner's control and is not committed with the source code.
- **Fail-closed automation:** computer, file and physical-device actions are gated by policy and explicit approval.
- **Model independence:** the deterministic core remains available without a paid API.
- **Inspectable security:** encryption, integrity checks, audit chaining and recovery paths are documented and tested.

## Current capabilities

- FastAPI core bound to `127.0.0.1` with a self-contained desktop interface.
- AES-256-GCM encrypted vault and memory snapshot.
- Persistent facts, conversations, tasks, project state and versioned drafts.
- Stable `condor-core-identity-v1` identity above the model router.
- Selectable Local, OpenAI and Claude connectors with secret redaction.
- Local speech, optional wake word, authentication-only computer vision and private image generation.
- Permission-scoped tools for approved files, applications, research and development workflows.
- Separate read-only mobile viewer on the private network; it exposes no command, memory or vault routes.
- ARTX Hub integration for project organisation without sharing PC permissions or private memory.
- Condor X experimental project workspace for 3D design and bounded engineering simulations.
- Optional `cloud/` PWA foundation for encrypted chat, notes and memory access while the PC is offline.

## Security boundary

The full Condor core must remain loopback-only. Never expose port `7777` to the internet. The mobile viewer uses a separate process and port, is restricted to private networks, requires pairing and returns sanitised read-only data.

Secrets, biometric templates, memory, configuration, logs and user files live outside the repository in `~/.condor` by default. The repository can restore the application, but it cannot restore that private state. Never upload or recreate an existing private Condor home during source publication.

Read the detailed [security model](SECURITY.md), [architecture](ARCHITECTURE.md) and [operations guide](OPERATIONS.md).

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
- ARTX Hub organisation layer
```

## Windows setup

Requires Python 3.11 or newer.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_new_windows_pc.ps1
```

For a manual installation:

```powershell
.\scripts\install.ps1
.\scripts\install_local_ai.ps1
.\scripts\run.ps1
```

The initial model downloads can be large. After installation, configured local models can run without an external AI account.

## Verification

```powershell
.\.venv\Scripts\python.exe testes\rodar_testes.py
.\.venv\Scripts\python.exe scripts\doctor.py
```

The automated suite exercises policy, vault encryption, memory, identity, provider routing, interface boundaries, device safety and Condor X simulation rules without requiring paid APIs.

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
scripts/       Installation, diagnostics and local runtime helpers
testes/        Security and behaviour regression suite
windows/       Native Windows launcher identity
```

## Honest status

Condor is an active personal R&D system, not a finished general-purpose consumer assistant. Local PC operation and tested safety boundaries are implemented. The cloud companion is a foundation that still requires its own infrastructure, real authentication and end-to-end deployment validation. Condor X engineering tools are prototypes and simulations; they do not claim validated physical performance.

## Licence

Proprietary source-available portfolio project. No permission to copy, redistribute or commercialise the code is granted by its public visibility.

Built and maintained by [Kauã Diniz Souza](https://github.com/Kauadsouza).
