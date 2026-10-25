# Backend: GitHub repository

The library is a GitHub repository; backend.root in the registry is "<owner>/<repo>". The skills work on a local checkout of it, in a coding agent such as Claude Code that can read and write files, run Python and run git. Without such an environment (claude.ai with only a GitHub connector, for example), stop and say that this library is used from a coding agent session with the repository checked out.

## The checkout

1. Find the checkout: the current directory's git working tree when its origin remote names <owner>/<repo> (git remote get-url origin; ignore letter case and a trailing .git), else a directory the project instructions name. None found: stop and say which repository is missing; never clone into or write to another folder. In a cloud session (claude.ai/code) say that the repository is to be added to this session (in a coding agent with an add-repository tool, offer to add it), not cloned by hand.
2. The library root is the top of that working tree (git rev-parse --show-toplevel).
3. Bring the checkout up to date with python3 scripts/kbgit.py sync <root> (kb-query adds --read-only). It finds the remote's default branch, switches a checkout that is on another branch (a cloud session checks out a branch of its own) to the default branch when that loses nothing, fetches, fast-forwards when the branch is only behind, and prints its status lines. When:
   - kb-query: before the first read of a conversation, and again when the user asks for the latest state ("pull", "sync", 「拉取最新」「同步」).
   - kb-ingest: at the start of every task: an intake run, a consolidation round, a quick-note filing; a health check syncs with --read-only, as it writes nothing.
   - kb-note: note.py save syncs before it writes; no separate call.
   kb-query never stops here: when the remote cannot be reached, the branch has diverged or cannot be switched, it answers from the local copy and adds once that the library may not be current. kb-ingest and kb-note stop on exit 3 or 4 and report the lines; never reset, stash or force anything (the one exception is drop-local under "Commit and push"). Without Python: git switch to the default branch when the current one holds no commits of its own, then git pull --ff-only, with the same rules.
4. Work on the default branch: sync switches to it and kbgit.py commit refuses any other branch. Never create branches, open pull requests or rewrite history for library changes.
5. A fresh copy needs no other mechanism: the sync above, or, when it cannot fast-forward, drop-local after the user confirms (under "Commit and push"). A cloud session clones the repository afresh when it starts; never clone by hand.
6. Everything happens in the checkout: read, search and compare files there with scripts and local tools. Never fetch library files through a GitHub connector or API.

## Operations

| Operation | How |
| --- | --- |
| find_by_name | list the folder (one level, not recursive) and match names containing the string |
| find_exact | test whether <folder>/<name> exists |
| find_by_text | kb-query: python3 scripts/kbfind.py ask (its SKILL.md, Step 3), or kbfind.py find <root> <keyword> [<keyword> ...] [--in <subfolder>] for one folder; elsewhere grep -l -F in the folder, one level only |
| find_folder | test whether <parent>/<name> is a directory |
| list | list the folder with modification times |
| read | read the file as UTF-8 |
| write_new | write a new file; refuse if the name already exists |
| ensure_folder | create the folder if it does not exist |
| move_rename | git mv; refuse if the target exists |
| replace_content | overwrite the file |
| folder_name | label in _kb.json, else the repository name |

## Rules

1. Stay inside the library root. Never touch files outside it, and never copy library content into another repository, an issue, a pull request or any other service.
2. Searches cover the root folder only, not subfolders; read the entities or notes folder only when a step says so.
3. Repository files are not knowledge files: README.md, CLAUDE.md, AGENTS.md and every name starting with a dot (.git, .claude, .gitignore and the like) are skipped by every search, read and health check, and are never delivered or changed by the skills. The one exception: kb-ingest init mode writes the registry block into CLAUDE.md.
4. A folder holds one file per name, so a new version overwrites the old one in place. There is no archive folder and no old-suffix copies: git history keeps every earlier version. Wherever the skills say an old version moves to the archive folder, in this backend it is overwritten instead, and archive mode does not apply (say so in one line when it is asked for). Never delete a file except where a step names it.
5. Before any write that is not a brand-new file, show a preview and wait for the user to confirm, as the skills say. A batch or fast intake run is confirmed once at its start.
6. Keep line endings as LF and encoding as UTF-8.

## Delivery (delivery = direct)

1. python3 scripts/package.py preview <work>/out --library <root> --plan <work>/deliver-plan.json --max-name-len <Table D> --in-place
   (fast intake: add --run <work>/run.json). Show the preview: new files and files whose current version will be overwritten. End with: reply "confirm" to write. The turn ends here.
2. After the user confirms: python3 scripts/package.py deliver --plan <work>/deliver-plan.json --commit "<title>"
   The script re-checks every target, writes the new files and overwrites the updated ones, keeps the readme and run log in the work folder, then commits and pushes exactly the files it wrote (below). Nothing is written into the library besides the delivered files.
3. A run confirmed at its start (a batch run's "Start", a fast intake's "Start") does both in one call per delivery: package.py preview ... --in-place --confirmed --commit "<title>". The preview it prints is the record; there is no second question.

The title is the first line of the commit message (below). Delivery is complete only when the script printed "pushed:". Exit 5: delivered into the checkout but not pushed; say so with the message, and do not report the delivery as complete. With sensitivity enabled the preview scans every output file for class-A data and stops on a candidate (exit 3): mask it in the output and preview again; only when the user confirms that a candidate is not class-A data (an order or serial number), preview again with --class-a-reviewed and name it in the delivery note.

Without Python, write the files yourself after the same preview, then commit with a log of the same lines.

## Commit and push

One commit per delivery round. In a batch run, one commit per batch; in a fast intake run, one per item (each item is delivered on its own). A quick note, an init step or the second round of quick-note filing is one commit each.

  python3 scripts/kbgit.py commit <root> --title "<title>" --path <path> [--path ...] [--log <run log>]

(package.py --commit runs it for a delivery, with every written file and the run log.) In one call it:
1. stages only the paths given (new, changed, moved with git mv, or removed); it refuses repository files and anything else already staged, and never runs git add -A;
2. with sensitivity enabled, scans the added lines and the message for class-A data and refuses on a candidate (as for the preview; --class-a-reviewed only after the user confirmed);
3. commits as the identity the repository's own instructions name (CLAUDE.md or AGENTS.md, a "Name <email>" on the line about the author), else --author, else git's own; the message is the title, a blank line and the run log lines, with no assistant trailers (Co-Authored-By, session links, "Generated with");
4. git pull --rebase and git push to the default branch, retrying network errors after 2, 4, 8 and 16 seconds; a push rejected because another session pushed first pulls and pushes again, up to 3 times. It prints the short hash.

The title is in the library language and names the mode and the count (for example "Intake: 3 files", "Quick note: <file name>", "Consolidation: 5 files"). Report the short hash with the counts.

- Exit 5: committed but not pushed. Say so with git's message; the delivery is not complete. The next commit or sync pushes it.
- Exit 3 after "conflict with newer commits": another window changed the same files first. The rebase was aborted and the commit stays local. Report the conflicting files and ask once, as a choice: Redo this round on the current library (recommended): kbgit.py drop-local <root> --yes, which resets to the remote branch, then run the round again from fresh copies / Stop here: the commit stays local and nothing more is written. Never drop local commits without that answer, and never force-push.

Deliver each round as soon as it is ready and never leave written files uncommitted: a cloud session can end at any time, and what is not pushed is lost with it. Report exit 5 at once.

Several sessions: quick notes are new files and can be saved from several sessions at once. Intake, consolidation and quick-note filing change the file index and summary files, so run them in one session per library at a time; a conflict is still handled as exit 3 above.

Without Python: git add only the paths of this round (never git add -A), check with git status that nothing else is staged, commit with the identity and message above, git pull --rebase, git push.

## History

Earlier versions live in git history, not in an archive folder. Use them only after the change log and the status card, when those do not answer how something changed or what an earlier version said, or when the user asks for an old version:

- kb-query: python3 scripts/kbfind.py history <root> <file> [--words "<words>"] [--at <hash>] does the steps below in one call.
- git log --follow --format="%h %ad %s" --date=short -- <file> lists the versions of a file.
- git show <hash>:<path> prints one version; git log -S "<words>" --format="%h %ad %s" --date=short -- <file> finds when a wording appeared or vanished.

Name every such basis as a superseded version with its commit date and short hash, for example "basis: 00_Status-Card.md as of 2026-05-01 (a1b2c3d), superseded". The current file is always the current state.
