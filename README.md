# mailbus

File-based **Agent-to-Agent** message bus. Framework-agnostic: Hermes, OpenClaw, Codex, OpenCode, Claude Code, and more via adapters.

No Redis / RabbitMQ required — messages are JSON files, CLI push, agent ack.

## Pick your implementation

mailbus ships **multiple language implementations of the same bus** — one
repo, one contract, your choice of runtime:

| Directory | Implementation | Status |
|---|---|---|
| `python/` | Python >= 3.10 (`pip install -e .`) | **stable** |
| `java/` | Java 17+ / Spring Boot 3 (`mvn -pl mailbus-boot -am package`) | preview (core landed, dual-run verified) |
| `web/` | Shared React cockpit (both implementations serve it) | shared |
| `shared/` | Language-neutral assets: `store/` runtime data, `docker-agents/`, `skills/`, `rules/`, `access/`, `contracts/openapi-v0.json` | shared |

**The contract is the same** whichever you run: same store layout (files as
the source of truth), same REST API surface (`shared/contracts/openapi-v0.json`),
same cockpit UI. A `migrate` / `reconcile` pair moves and audits a store
between implementations — dual-run and switch when you're ready.

### Quick start - Python

```bash
cd python
pip install -e .
mailbus demo          # full lifecycle in one command
mailbus serve         # cockpit on :9814
```

### Quick start - Java

```bash
cd java
mvn -pl mailbus-boot -am package -DskipTests
java -jar mailbus-boot/target/mailbus-boot-0.1.0.jar demo   # CLI mode
java -jar mailbus-boot/target/mailbus-boot-0.1.0.jar        # serve on :9815
```

More per-implementation details: `python/README.md`, `java/README.md`.

## Adding another language

The layout is the contract: a new implementation gets one top-level
directory, talks to the shared store layout under `shared/store`, serves
the same REST contract, and can host the same `web/` cockpit. Nothing
else in the repo needs to move.

## Optional

- An agent CLI (Claude Code / Codex / Hermes / OpenClaw / OpenCode) or a remote A2A endpoint — only for connecting your own agents
- Ollama (local routing), Docker + Compose, AgentMemory, Obsidian Vault — enhancement layers, never required for the demo

## Connect your own agents

Settings page in the cockpit (three fields: `type / run_target /
install_path`) or `mailbus agent-add` / the java CLI equivalent; the
**Test connection** flow runs probe -> test push -> activity profile.

```bash
mailbus init --data-dir ./shared/store
mailbus send agent-executor --msg "Hello" --from agent-dispatcher
mailbus status
```

Copy `python/migrate/env.template` -> `.env` and set keys / paths.
**Never commit `.env`.**
