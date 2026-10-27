# Changelog

Releases follow the "Version:" line of the three SKILL.md files; merging a version change to main publishes v<version> (.github/workflows/release.yml).

## 3.4.0

An explicit request to file can serve as the confirmation, missing dates are asked for before writing, and consolidation can run on a schedule.

- `_kb.json` intake key `confirm`: `ask` (default, unchanged) or `command`. With `command`, an explicit request to file ("intake", "file this") is the confirmation of a fast intake when the library is clear and the material makes one batch, so the item is written and pushed without a question; material that makes more than one batch still gets the batch plan first.
- Missing dates: when params ask for a date and neither the material nor the conversation gives one, fast and full intake ask once before writing (including "Not known, leave it empty"), record the answer with the note params use for a date not taken from the material, and never fill one in; each item still makes one commit.
- Scheduled consolidation ("scheduled consolidation", "定时整合"): a scheduled task runs consolidation unattended and never asks. An empty queue makes no commit and no notification. At most `intake.scheduled_rounds` rounds (default 3), one commit each. Changes are accepted, except that a change the evidence check flags becomes an open item instead of reaching the status card, and disputed items stay open items. A failed sync, conflict, push or check stops the run where it is, with no drop-local and no force push. When files were consolidated or the run failed, one push notification gives the library, file counts, change counts with status-card item names, commit short hashes and the failure.
- kbconf.py checks `intake.confirm` (`ask` or `command`) and `intake.scheduled_rounds` (a positive integer).
- The Chinese description of kb-ingest names 「定时整合」.

## 3.3.0

Citations can be given on request, and writing tasks are checked against the library.

- Registry preference `preferences.citations`: `always` (default, unchanged: every fact names its basis file) or `on_request`. With `on_request`, kb-query answers as plain statements: no basis files, no library label, no consolidation reminder and no words about knowledge bases, searching or sources. Nothing found is stated as no record; general knowledge goes in a separate paragraph. When sources disagree, the current value comes first, then one sentence with the other version and its date. Unconsolidated files, answer snapshots and git history get no notice of their own; quick notes are marked unconfirmed. Asked where something came from, kb-query lists the full basis file names for each statement of the previous answer, searching again only when the earlier results are no longer in the conversation.
- kb-query also runs before a writing task (trim, polish, draft, translate, reply) whose content falls in a library's scope: it searches the names, terms, numbers and dates, does the task as asked without changing the meaning, and lists anything that differs from the records in a closing "to check" section.
- kb-note: an answer snapshot of an answer given without basis lines records the basis files from that answer's search.
- kbconf.py rejects any `preferences.citations` value other than `always` or `on_request`.

## 3.2.0

Reads stay in the local checkout and only writes reach the remote; the mechanical steps run as scripts.

- Sync and commit (scripts/kbgit.py, in every skill): sync finds the remote's default branch (git ls-remote --symref origin HEAD, else main), switches a checkout on another branch to it when no tracked file has uncommitted changes and the branch holds no commits of its own, fetches and fast-forwards; kb-query falls back to the local copy and says it may not be current, the writing skills stop. commit stages only the paths of the round, refuses repository files and anything else staged, commits as the identity the repository instructions name, drops assistant trailers, scans for class-A data when sensitivity is on, rebases and pushes to the default branch only, retries network errors and pulls again when another session pushed first. A rebase conflict keeps the commit local; drop-local resets to the remote after the user confirms.
- When to sync: kb-query before the first read of a conversation and when the user asks for the latest state; kb-ingest at the start of every task (a health check read-only); kb-note inside note.py save, which writes nothing when the sync stops.
- kb-query (scripts/kbfind.py, now shared with kb-ingest): ask searches the whole library in one call, adding the spec's Table B and Table E forms of each keyword, and prints only matching blocks; history lists the versions of a file and the commits where a wording appeared or vanished.
- kb-note: note.py save names, writes, commits and pushes a note in one call and reports the backlog.
- kb-ingest reads less: kbconf.py spec prints the spec without its revision notes (their line ranges are named) and lists the tables found by title; the status card and change log are read as matching blocks (kbfind.py toc and find), not whole. Table titles are found by position and length, with punctuation inside brackets allowed.
- kb-ingest scripts: prep.py scan-batch and file-batch file a batch in two calls; meta.py apply writes confirmed term fixes and masks at once; card_patch.py changes summary files item by item and checks the result; package.py preview --confirmed --commit delivers, commits and pushes; lint.py runs the health check in one call; entity_pages.py keeps the related-files list of each entity page between its markers.
- kbconf.py scan-a lists class-A candidates (ID, card and account numbers, unmasked passwords and codes), starred.
- The Google Drive backend and its archive scripts are removed; the registry accepts only github libraries.

## 2.3.0

First release of repo-wiki: the skills, setup and documentation for a library kept in a private GitHub repository and used from Claude Code.

- Init sets up a new library in a checked-out repository: it takes the repository from the origin remote, accepts a root that holds only README.md, CLAUDE.md, AGENTS.md, dot files and non-Markdown files, creates no empty folders, writes the registry and the instructions line as one block into the repository's CLAUDE.md (one repository holds one library), reminds you that the repository must be private, and commits and pushes once.
- Every delivery round (intake batch, quick note, consolidation, filing quick notes) is one commit with its run log, pushed to the default branch after a rebase; it counts as done only when the push succeeded. No branches, pull requests or force-pushes.
- A new version overwrites the old one in place; there is no archive folder, and archive mode is declined. Earlier versions come from git history, cited by commit date and short hash.
- Searches, reads and health checks skip README.md, CLAUDE.md, AGENTS.md and dot files.
