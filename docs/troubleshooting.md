# Troubleshooting

Symptoms, their usual causes and what to do. Setup steps are in [setup.md](setup.md). [中文](troubleshooting.zh-CN.md)

## Setup and access

| Symptom | Usual cause | What to do |
| --- | --- | --- |
| Claude answers a question about your records from general knowledge, with no file named | The session is not on the library repository, or CLAUDE.md has no registry block | Start the session on the library repository. Check that CLAUDE.md holds the block init wrote, then ask "which knowledge bases do I have?" |
| The skills do not appear | `.claude/skills/` is missing, unpacked one level too deep, or not pushed | Each skill's SKILL.md must be at `.claude/skills/<skill>/SKILL.md` on the default branch. Fix, commit, push, and start a new session |
| Two skills answer the same request | Both language versions of a skill are installed | Keep one version of each skill under `.claude/skills/` |
| "This library is used from a coding agent session with the repository checked out" | The request came from a plain claude.ai conversation, or the session's checkout is a different repository | Use Claude Code in a session on the library repository |
| "No checkout of <owner>/<repo>" | The current directory's origin remote is not the repository named in the registry | Run the session in the library's own checkout; check `git remote get-url origin` and `backend.root` in CLAUDE.md |
| Init refuses the repository as a new library | The repository root holds Markdown files other than README.md, CLAUDE.md and AGENTS.md | Use an empty repository for a new library. A repository that already holds a library is completed by hand |
| Init refuses to write CLAUDE.md | CLAUDE.md already registers another library | One repository holds one library; set up the other library in its own repository |

## Git

| Symptom | Usual cause | What to do |
| --- | --- | --- |
| The skill stops before reading: `git pull --ff-only` failed | Local changes or a diverged branch in the checkout | Commit or remove the local changes, or bring the branch back in line with the remote, then repeat the request. The skills never reset or stash anything |
| "The commit is local; the push failed" | No push permission, a network problem, or branch protection on the default branch | Fix the cause and run `git push` yourself; the delivery counts as done only after the push. The skills push to the default branch, so branch protection must allow it |
| A rebase conflict stopped the delivery | The repository changed elsewhere (another session, an edit on github.com) on the same file | The skill aborted the rebase and named the files. Resolve it by hand (often: pull, then repeat the request), never by force-pushing |
| A cloud session cannot push | GitHub access for claude.ai does not include the repository | Grant the Claude GitHub app access to the repository and start a new session |

## Filing and answers

| Symptom | Usual cause | What to do |
| --- | --- | --- |
| A file was filed but the status card did not change | Fast intake files first and updates the status card at consolidation | Say "consolidate" and review the proposed changes. Answers that rely on a file waiting for consolidation say so |
| The intake stops at a preview | Every write is previewed first | Reply "confirm" to write, or name what to change |
| A large intake is slow or stops part way | Many files mean a long run | Material is filed in batches; say "continue intake" in the same conversation. A new conversation starts the intake again and skips files already filed |
| An answer says the library does not record something you filed | The wording differs, or the file is not filed yet | Ask with the words the document uses, or ask "is <document> filed?" to check the file index |
| "Archive old versions" is declined | A GitHub library has no archive folder | Nothing to do: the old versions are in git history |

Still stuck: open an [issue](../../../issues) with the request you made, the reply you got and the library's `_kb.json` without private names.
