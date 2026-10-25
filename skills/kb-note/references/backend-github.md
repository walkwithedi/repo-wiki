# Backend: GitHub repository

The library is a GitHub repository; backend.root in the registry is "<owner>/<repo>". The skills work on a local checkout of it, in a coding agent such as Claude Code that can read and write files, run Python and run git. Without such an environment (claude.ai with only a GitHub connector, for example), stop and say that this library is used from a coding agent session with the repository checked out.

## The checkout

1. Find the checkout: the current directory's git working tree when its origin remote names <owner>/<repo> (git remote get-url origin; ignore letter case and a trailing .git), else a directory the project instructions name. None found: stop and say which repository is missing; never clone into or write to another folder.
2. The library root is the top of that working tree (git rev-parse --show-toplevel).
3. Before the first read in a conversation, bring the checkout up to date: git pull --ff-only on the default branch. If it fails (local changes, a diverged branch), stop and report git's message; never reset, stash or force anything.
4. Work on the default branch. Never create branches, open pull requests or rewrite history for library changes.

## Operations

| Operation | How |
| --- | --- |
| find_by_name | list the folder (one level, not recursive) and match names containing the string |
| find_exact | test whether <folder>/<name> exists |
| find_by_text | kb-query: python3 scripts/kbfind.py find <root> <keyword> [<keyword> ...] [--in <subfolder>]; elsewhere grep -l -F in the folder, one level only |
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
   (fast intake: add --run <work>/run.json). Show the preview: new files and files whose current version will be overwritten. End with: reply "confirm" to write. The turn ends here, except within a fast intake run, which was confirmed at its start.
2. After the user confirms: python3 scripts/package.py deliver --plan <work>/deliver-plan.json
   The script re-checks every target, writes the new files and overwrites the updated ones, and keeps the readme and run log in the work folder (it prints where). Nothing is written into the library besides the delivered files.
3. Commit and push (below). Delivery is complete only when the push has succeeded.

Without Python, write the files yourself after the same preview, then commit with a log of the same lines.

## Commit and push

One commit per delivery round. In a fast or batch intake run, one commit when each batch is delivered (one batch: when the run ends). A quick note, an init step or the second round of quick-note filing is one commit each.

1. git add only the paths this round wrote, moved or overwrote; never git add -A. Check with git status that nothing else is staged.
2. Commit message in the library language: a first line naming the mode and the count (for example "Intake: 3 files", "Quick note: <file name>", "Consolidation: 5 files"), a blank line, then the run log lines the script printed (or the written file names). Follow the repository's own instructions (CLAUDE.md, AGENTS.md) for author identity and message rules.
3. git pull --rebase, then git push. A rebase conflict: stop, run git rebase --abort, and report the conflicting files; never force-push.
4. Report the short commit hash with the counts. A failed push leaves the commit local: say so, with git's message, and do not report the delivery as complete.

## History

Earlier versions live in git history, not in an archive folder. Use them only after the change log and the status card, when those do not answer how something changed or what an earlier version said, or when the user asks for an old version:

- git log --follow --format="%h %ad %s" --date=short -- <file> lists the versions of a file.
- git show <hash>:<path> prints one version; git log -S "<words>" --format="%h %ad %s" --date=short -- <file> finds when a wording appeared or vanished.

Name every such basis as a superseded version with its commit date and short hash, for example "basis: 00_Status-Card.md as of 2026-05-01 (a1b2c3d), superseded". The current file is always the current state.
