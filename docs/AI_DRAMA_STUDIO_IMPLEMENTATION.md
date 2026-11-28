# AI Drama Studio — implementation architecture

## Product boundary

AI Drama Studio is a Director-tier episodic production workspace. It extends the existing Movie Studio instead of replacing its screenplay, storyboard, shot-generation, audio and FFmpeg mastering engine.

The Director gate is shared with Movie Studio through `can_access_movie_studio`. Admin access continues through the existing entitlement service.

## Production model

- A **DramaSeries** is the long-lived story container.
- A **DramaCharacter** is the canonical series-level character profile and portrait.
- A **DramaEpisode** represents one episode and links to one existing **MovieProject**.
- **DramaEpisodeCharacter** snapshots a series character into the episode's Movie Studio cast.
- **DramaShotCharacter** explicitly assigns episode cast members to individual shots. New series production uses these assignments before the legacy prompt-name fallback.
- **DramaProductionJob** is the durable orchestration record.
- **DramaMonthlyUsage** tracks reserved and completed episode slots per user and calendar month.
- **DramaUsageLedger** records idempotent reservations, releases and production spend.

## Initial Director allowance

The first implementation uses a configurable service constant of 30 episode slots per calendar month. A slot is reserved when an episode workspace is created, converted to completed when production succeeds, and released when production fails. This is episode-count accounting; provider/credit costs remain separately accounted for by the existing video generation credit gate and the Drama usage ledger.

The allowance is a product setting to validate against actual provider economics before public launch.

## Episode workflow

1. Create a series and define its genre, language, aspect ratio and episode duration.
2. Build the recurring character library and generate canonical character portraits.
3. Create an episode; the service creates a MovieProject and copies the current character profiles into its cast.
4. Add or remove episode cast and assign characters explicitly to shots.
5. Continue screenplay, storyboard, shot generation, dialogue, lip-sync and mastering in the existing Movie Studio workspace.
6. Finalize the monthly episode slot only once; duplicate callbacks are ignored.

## Current implementation status

### Implemented on the feature branch

- Series and episode models, constraints and indexes.
- Series-level character library and portrait propagation to episode cast copies.
- Explicit shot-to-character assignments.
- Director-only series dashboard and series workspace.
- Episode creation linked to existing MovieProject workspaces.
- Monthly quota reservation, completion and release accounting.
- Durable production job and usage-ledger records.
- Alembic migration merging the two existing migration heads before adding Drama Studio tables.
- Startup schema-repair registration consistent with the repository's existing Movie Studio table setup.

### Not yet implemented

- Automated worker that consumes DramaProductionJob records and executes the complete episode pipeline.
- Full episode editing UI for shot-level cast assignment and per-episode character selection.
- Admin usage/cost dashboard and measured per-episode unit economics.
- Recovery/retry policy for interrupted provider jobs and render workers.
- End-to-end integration tests against real provider callbacks.

## Production safety

- No changes to the production `main` branch.
- No production database migration has been run.
- No deployment has been performed.
- Provider generation remains subject to existing Director entitlements and credit billing.
