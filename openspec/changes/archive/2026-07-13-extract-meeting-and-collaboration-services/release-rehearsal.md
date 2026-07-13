# Isolated release and rollback rehearsal

Date: 2026-07-13

The rehearsal used `/tmp/vo-meeting-phase8-migrated.TIdADY`; it never read or modified the user's real status directory.

## Cutover

1. With no server running, prepared one active Meeting, one confirmed linked request, one event bucket, two occupancy owners and lifecycle/request idempotency records in copied legacy Stores.
2. Captured source SHA-256 values: executable `fd1aa739d47c6ca804a73460bf4cf082e35294c4e98e4a0ba903692fc4cde49c`; requests `ed7474e371645278ef5f84e0f8b27310eedbc7d60f41aa540e2c441f82b3973c`.
3. Dry-run returned `validated`; apply returned `migrated`. Counts were Meetings 1, requests 1, event buckets 1 and occupancy 2. Event ownership, identity/status, occupancy compatibility and request/Meeting linkage all passed.
4. Saved byte copies of both legacy Stores and the unified Store. Unified SHA-256 was `105aa08cd4a68e332b6791d0a3c9c0c5b350e689387b76c00063ad8c46e776c9`.
5. Started exactly one candidate through `./start.sh`. Store status was schema 1; Meeting `phase8-existing`, request `phase8-request`, their link, and both occupancy owners were preserved.

## Rollback

1. Stopped the candidate, preserved its unified file, restored the legacy snapshot, and moved the unified authority out of the prior-code view.
2. Created a detached temporary worktree at pre-consolidation commit `7f7a5d3` and started that prior version only through its `./start.sh`.
3. The prior version returned HTTP 200 for both the active Meeting and confirmed request; `conversion.meetingId` still equaled `phase8-existing`.
4. Stopped the prior process, restored the candidate unified Store, verified all three SHA-256 values were unchanged, and removed the temporary worktree.

No Agent gateway credentials or Feishu credentials were available, so the candidate emitted no non-reversible Agent or Feishu effects. Notification/callback reconciliation was therefore `not required`; production rollback must still review persisted notification intents, callback outcomes and Meeting events as documented in `docs/MEETING_DOMAIN_OPERATIONS.md`.

