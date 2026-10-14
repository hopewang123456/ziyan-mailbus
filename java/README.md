# mailbus-j — the Java implementation of mailbus

> Status: **scaffold (M1 in progress)**. The Python implementation under
> `../python` (moving there in the monorepo restructure) is the stable one;
> this subtree reaches parity over milestones M1–M4 (see the architecture
> plan in the Vault: `Projects/mailbus/plans/2026-10-14-java-rewrite-architecture.md`).

## Build & test

```bash
cd java
mvn test          # unit tests + ArchUnit layering gates (CI-enforced hexagonal)
mvn package       # build all modules
```

Requires JDK 17+ today; built with the host's JDK 17. When the host upgrades
to JDK 21, flip `<java.version>` in the root `pom.xml` and set
`spring.threads.virtual.enabled=true` (M2 scheduler). No code changes needed.

## Module map (Ports & Adapters, mirrors the Python layering)

| Module | Layer | Contents |
|---|---|---|
| `mailbus-domain` | Domain | `MessageState` FSM, `MsgRecord` (UTC-only timestamps, single state field) |
| `mailbus-ports` | Ports | `MessageRepository` interface (SQLite/in-memory bind in boot) |
| `mailbus-app` | Application | `InboxService` use case — zero framework deps |
| `mailbus-adapters` | Adapters | `InMemoryMessageRepository` (fake/demo); SQLite adapter lands in M1 |
| `mailbus-infra` | Infra | cross-cutting (clock, logging) — placeholder |
| `mailbus-api` | API | thin REST (`/api/inbox`), grows toward the M2 OpenAPI contract |
| `mailbus-cli` | CLI | picocli `send` / `inbox` / `ack` |
| `mailbus-boot` | Composition root | `MailbusApplication` (the only module seeing all layers), Flyway `V1__init.sql` (sqlite), ArchUnit gates |

## Storage policy (architecture plan §5)

- Message bodies: **files** (one file per message, atomic write) — DB never owns the truth.
- Metadata: SQLite by default (`jdbc:sqlite:./store/metadata.db`), MySQL via
  config switch only (`spring.datasource.*`), Flyway dual-dialect
  (`db/migration/sqlite` / `db/migration/mysql`), common-SQL-subset discipline.
- Search/semantics/graph: FTS5 + sqlite-vec + recursive CTE inside the same
  SQLite file (upgrade trigger lines in the plan §5.3).

## Run (once M1 wires the boot jar)

```bash
mvn -pl mailbus-boot spring-boot:run   # serves :9815 (9814 stays with Python serve)
```
