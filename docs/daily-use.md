# Daily use

What to say for each task, what happens next, and what waits for your reply. Each library is its own repository, so work in a session on that repository. [中文](daily-use.zh-CN.md)

## What to say

| You want to | Say | What happens | Waits for you |
| --- | --- | --- | --- |
| Ask something | just ask | kb-query reads the status card, then the files it needs, and names the file behind each fact | no |
| Ask how something changed | "what did it say before?", "how did this change?" | the change log and status card first; when they do not answer, git history, naming the commit date and short hash of each earlier version | no |
| Keep a remark | "note this: ..." | kb-note saves it as a quick note in the Quick-Notes folder, commits and pushes, and replies with the file name | no |
| Keep an answer | "save this answer" | the question, the answer and its basis files become a quick note | no |
| File documents | name, paste or attach them, then "file these" | each item is placed in a partition, named, checked for duplicates and versions, written, committed and pushed; searchable at once | a preview at the start of the run: reply "confirm" |
| Continue a large intake | "continue intake", "finish intake" | the next batch of the plan made at the start; only within the same conversation | the batch preview |
| Bring the status card up to date | "consolidate" | key conclusions for the files filed since the last round, and proposed status-card changes as a numbered list, each value checked against its source | you accept or reject each change |
| File quick notes | "file my quick notes" | notes are grouped into material and filed; then the filed notes move to the filed folder | a preview, then "confirm" for the move |
| Check the library | "health check" | a report of stale, duplicate, missing and badly formatted items, and a sample check of the status card | no; it changes nothing |

Add "full intake" to a filing request to update the status card for each file as it is filed, instead of waiting for consolidation.

"Archive old versions" does not apply to a GitHub library: a new version overwrites the old one in place, and git history keeps it.

## The life of a document

```text
material --"file these"--> filed: named, indexed, searchable at once, one commit
                             |
                             +--"consolidate"--> key conclusions written,
                                                 status card change proposed --you accept--> status card updated, one commit
                             |
next version, same name --> overwrites the file; the old version stays in git history
```

Until a file is consolidated, the status card may not reflect it. Answers that rely on such a file say so, and the skills remind you once per conversation when files are waiting.

## Where the material comes from

Material is read where it is and never moved, changed or committed: only the cleaned library files are. In a local session, name the files or folders on your computer; many files are planned into batches. In any session, pasted text works, and attached files where your Claude Code app accepts them. On a phone, notes and questions are the natural fit; file large piles of documents from a computer.

## A rhythm that works

- File material when it arrives; the library is searchable at once.
- Say "consolidate" when reminded, or once a week. Or let a scheduled task (Claude Code scheduled tasks) say "scheduled consolidation" each night: it accepts the changes on its own, turns those the evidence check flags into open items, and sends a notification when it consolidated something or stopped.
- Say "file my quick notes" when kb-note says notes are piling up.
- Run a "health check" once a month.

Nothing is lost: every earlier version of every file is in git history, and the repository's commit list shows every round.

When something does not behave as described: [troubleshooting.md](troubleshooting.md).
