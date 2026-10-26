# Methodology

Why the skills work the way they do: every rule below exists because a looser one lets answers go stale or facts get lost. The exact procedures are in the skills. [中文](methodology.zh-CN.md)

## The problem

An assistant can answer from your documents, but raw documents disagree with each other: an old plan, a newer decision, a meeting that changed it again. Searching them at question time returns whichever matches best, not whichever is current. The fix is to do the reconciling once, when material arrives, and keep the result: a library the assistant maintains, rather than retrieval over a pile.

## Four layers

1. Source documents, cleaned but never shortened, one file each, named `<partition>_<topic>_<type>_<short title>.md`.
2. Summary files: the status card (what is true now), the change log (how it changed), open items, the glossary. These answer most questions without opening a source document.
3. Entity pages: one per person, organisation, system or project, linked from every document that mentions it.
4. The spec: the library's own rules (partitions, topics, term fixes, thresholds, entities). The skills hold the process; the spec holds the rules, and grows with the library.

## Rules that keep it evergreen

- **Name equals version.** Documents carry no date in their name, so the next version of the same document lands on the same name and overwrites the previous one, which git history keeps. Two different documents must never share a name; when unsure, rename. This single rule removes most "which version is current?" questions.
- **Evidence or the conservative choice.** Duplicate, new version or change of fact: each call needs a quote. No quote, no change. A file's content hash is recorded in the index, so the same file filed twice is recognised whatever its name.
- **Three questions before touching the status card.** Does the new material carry this kind of fact; does the card have an entry for it; do they disagree. Only three yeses trigger a rewrite. Rolling process data (daily progress, single purchases) never does.
- **Rewrites are checked by a script.** The old card and the new card are compared item by item; every missing item must be explained in a change list, and the new card may not shrink below 70% without the owner's consent.
- **Values are checked against their sources.** Before a status-card change is shown for review, a script looks up its dates, longer quotes and specific numbers in the basis files; any value it cannot find is marked for the owner to decide, since a derived value may still be right. The health check runs the same look-up over the card.
- **Every item gets a disposition.** New, update, disputed or no new information. Disputed material leaves the status card unchanged and puts both quotes to the owner; material with no new information is still filed and searchable, but adds nothing to the change list.
- **Never delete, never edit sources.** Older versions stay in git history; the original material is read where it is and never committed; issues are recorded, not silently fixed. Personal identifiers are the one exception: masked before anything is written.
- **No silent growth.** When material fits no topic, the skill adds a topic to the closest partition (never a new partition), rewrites the spec with a revision note, and lists the change for review.
- **File fast, consolidate after.** Writing an item into the library and reconciling it with the summary files are separate steps. Filing is mechanical and happens per item, so material is searchable as soon as it arrives; reconciling needs close reading and the owner's review, so it happens in rounds over many filed items, from a queue kept in the library. Until an item is consolidated, answers that rely on it say so.
- **Search caps and fixed reading order.** The assistant reads the status card first, then the specific list, then sources, and stops after a fixed number of searches. A keyword is searched in the ways the library may write it (the user's words, the standard term, older forms, aliases), up to three at once. Answers name their basis file (with `preferences.citations` set to `on_request`, only when the user asks where something came from); what the library does not record is said to be not recorded.
- **The owner decides what changes.** Every write is preceded by a preview, and nothing outside the library repository is touched.

## Quick notes

Not everything worth keeping arrives as a document. kb-note saves a remark from the conversation as a small file in the library's quick-notes folder: the words, the key points and the context, nothing else changed. Notes are searchable at once (marked "quick note, not yet filed" in answers) and are filed later in batches, grouped by partition and topic, with the notes' own words as the evidence. A note marked unconfirmed never changes the status card.

An answer worth keeping ("save this answer") is saved the same way, as a snapshot of the question and the answer with its basis files. It is filed as an answer archive: searchable, dated, never used as evidence for the status card, since its basis is the library itself.

## Sensitive data

A library can turn on sensitivity classes (`_kb.json` `sensitivity`; on in the life preset). Identifiers such as ID, card and account numbers and passwords are masked to their last few characters before anything is written or shown; health and money facts are recorded as they are and never interpreted, so answers report what is recorded and give no advice.

## Why a GitHub repository and Claude Code

- **Plain files you own.** A library is a folder of Markdown files in your own repository: readable without the skills, on github.com, in any editor or as an Obsidian vault in a local checkout.
- **Every version, without an archive folder.** A repository holds one file per name, so a new version overwrites the old one in place and git keeps every earlier version. The library root stays clean: no archive folder, no time-stamped copies.
- **History answers questions.** When the change log and the status card do not say how something changed, kb-query looks up git history and cites an earlier version by its commit date and short hash, marked as superseded. The current file is always the current state.
- **One round, one commit.** Each delivery commits exactly the files it wrote, with the run log in the message, and pushes it. A failed push leaves the delivery unfinished and is reported as such; nothing is force-pushed, and the skills never create branches or rewrite history.
- **The registry lives with the library.** The repository's CLAUDE.md names the library and holds its registry, so every Claude Code session on the repository, local or in the cloud, knows the library exists without any other setup.
- **Scripts run where the library is.** The skills read and write the checkout directly and run their checks with the Python standard library; there is no connector and no upload step between Claude and the files.
- **Private by your settings.** The repository's visibility decides who can read the library. It must stay private; the skills remind you at setup but cannot check it.

## What the presets give you

Two starting points, both editable during setup: a work library (goals and plans, projects and tasks, proposals and deliverables, meetings and decisions, policies and procedures, organisation and roles, data and reports, reference and templates) and a life library (health, money, insurance, home, family, IDs and legal, devices, subscriptions and travel, learning, reference). The life preset includes sensitivity classes.
