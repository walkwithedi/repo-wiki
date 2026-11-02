---
name: kb-query
description: Answers questions from the user's own knowledge base of Markdown files in a GitHub repository by searching it first, not from memory; facts name their source files (or only when asked). Use when a question may be recorded there - what was agreed or decided, current values and limits, owners, dates, status, open items, terms, how something changed; personal records such as IDs, health, insurance, money, contracts, due dates; or whether some material is filed. Also before a writing task (trim, polish, draft, reply) whose content falls in a library's scope, to check names, terms and figures. Examples: "When is the launch date?", "Who owns Project Atlas?". When a knowledge base is set up (a kb-libraries.json registry, KB_LIBRARIES, or project instructions), check it before code or general knowledge, even if the user does not say "check my knowledge base". Not for unrelated questions or the code of these skills. Read-only; intake, archive, health checks and setup: kb-ingest; notes: kb-note.
---

# Knowledge base questions

Version: 3.5.0

Read-only: search, read and answer. Never create, change, move or delete anything in a library. Partitions, topics and terms are read from the library, never from this file.

Read references/config.md and references/environment.md once before starting.

## Step 1: which library

1. A question or task unrelated to every library's scope (general knowledge, writing on other subjects, code): do not search; answer normally.
2. Load the registry and match the question against each scope. Search the libraries that fit.
3. Unclear, or more than one could hold the answer: search every library that might, without asking.
4. If unsure whether a question falls in a library, read that library's spec Table A to check; still unsure, treat as rule 3.
5. Intake, archive, health check or setup requests belong to kb-ingest.
6. A writing task (trim, polish, draft, translate, reply) whose content falls in a library's scope: search the names, terms, numbers and dates it mentions (Step 3), and also the occasion behind the text (the meeting, assignment, project or trip it is about) by its subject words, not only by the category of the request (a cost, a leave, an approval); then do the task as asked, keeping the user's meaning. Do not change the text to match the library; after the result, add a section "to check" (「待核对」) listing each name, term, number or date that differs from the records, with the recorded form. Nothing differs: no such section. Step 4 rules 2, 4 and 7 to 10 apply to that section only.
7. A question about the libraries themselves ("which knowledge bases do I have?", "where does this go?"): load the registry and answer from it, one line per library with its label and scope, without searching any library. No registry: references/config.md, section 1.

For each library searched, read its backend file (references/backend-github.md) and _kb.json. Start the answer with: Library: <label(s)> (not with citations on_request).

After the answer, check each library searched for files waiting for consolidation (references/config.md, section 5); remind once per conversation (not with citations on_request). This skill only reminds and hands "consolidate" to kb-ingest.

## Step 2: which file first

| Question about | Read first |
| --- | --- |
| conclusions, positions, definitions, owners, boundaries, numbers, the current state of something | status card (always consulted: its blocks that match the keywords; the whole card only for a question about the overall state) |
| whether some material is filed | file index |
| open decisions (work) or due dates, renewals, follow-ups, payments, to-dos (life) | open items |
| how something changed, what it used to be | change log, with the status card for the current state |
| how a term is written, whether a name is standard, open issues | glossary, checked against the status card |
| which partition a subject belongs to | spec, Table A |
| details (meeting content, design specifics, reports, contract terms, statements) | status card to locate, then the source material |

## Step 3: search

Use the operations in the backend file, always inside the chosen library root.

A GitHub library (a checkout on disk) is synced as the backend file says (before the first read of the conversation, and again when the user asks for the latest state), then searched locally in one call per round, not file by file:

  python3 scripts/kbfind.py ask <root> --q "<wording>|<wording>|<wording>" [--q ...] [--all] [--entities]

One --q per keyword, with up to three of its wordings (below). The script adds the spec's Table B forms and the Table E names and aliases of each keyword itself, so do not read the spec, the glossary or the entities for wordings. It prints, in this order: the matching blocks of the status card and the file index, then of the open items, change log and glossary, then the source files (those the status card or index hits name first), the entity pages of the keywords, the quick notes only when the library itself has nothing, and which hits still wait in the consolidation queue. --all keeps only blocks that hold every keyword; --entities also searches the entities folder (questions about one person, organisation, system or project as a whole). Read only what it prints; read further in a file by line number, or list its sections with kbfind.py toc, only when a block is cut off or the answer needs the rest of its section. Each ask counts as one search per keyword; a reworded retry is a second ask with wordings not tried yet. Rules 3, 4, 5 and 7 below are applied by the script. Then go on with Step 4.

Other libraries:

Wordings first: for each keyword, list the ways the library may write it: the user's words, the standard term in the status card and glossary, the old forms the spec's Table B maps to it, and for a person, organisation, system or project its Table E name and aliases (from files already read for this question; do not fetch extra files just for this). Search a keyword with up to three of its wordings at once, as the backend file says for several wordings.

- Summary files: find_by_name with the search key (references/config.md).
- Source material by name: find_by_name. File names look like <partition>_<topic>_<type>_<short title>.md, so a partition can be searched with its prefix ("05_"). Family material in a life library carries the family member in the short title.
- Source material by content: find_by_text.

Rules:
1. Never use a file ID or path from memory; use what the search returns.
2. Search with partial strings, not full titles; for a file name the user gives, search its short title without the partition and topic (kbfind.py ask adds it itself). When a keyword finds nothing, or its hits are all incidental (no hit file is about the subject asked), its reworded retry (rule 6) uses wordings not tried yet, preferring the subject, the people or the occasion over the category words.
3. Stay in the root folder level; never widen the search beyond the library. The entities folder is searched only for questions about one person, organisation, system or project as a whole.
4. Never use the ignored files listed in references/config.md.
5. Several copies of one summary file: use the most recently modified and add "several copies of this file exist; the newest was used".
6. Search cap: one search and one reworded retry per keyword; at most 8 searches for one library and 4 more for each extra library. Then stop and answer as "not found".
7. Several source files match: prefer the ones the status card or index mention, then newest first; read at most 5 per library.
8. Each library is searched with its own root only.

Quick-note fallback: only when the library itself has nothing relevant, search its notes folder (names.notes_dir) with find_by_text, not its filed subfolder. These count toward the cap.

History: only when the user asks for old versions, search the archive folder, and say the result is a superseded version. A GitHub library has no archive folder: use git history, also when the change log and status card do not answer how something changed: python3 scripts/kbfind.py history <root> <file> --words "<wording>" lists the versions of the file and the commits where the wording appeared or vanished, and with --at <hash> shows the blocks holding it in that version. Cite it as the backend file says ("History"); these calls count toward the cap.


## Step 4: answer

1. Priority: status card, then change log and lists, then source material. If source material disagrees with the status card, answer with the status card as current, point out the difference and where it is; do not decide who is right.
2. Every statement of fact names its basis file (full file name), with the library when several were searched: "basis: Life 00_Status-Card.md".
3. Use the standard terms from the status card and glossary; if the user used an older form, give the standard one and the old one in brackets once.
4. Numbers and dates exactly as written, with units and the time they refer to; no conversion or estimate. Where files disagree, list each with its source.
5. No inference. What the library does not record: "not recorded in the knowledge base". If general knowledge is really needed, put it in a separate paragraph headed "not from the knowledge base".
6. Items still open in the open-items list: state that and the deadline recorded.
7. A basis file that is still in the consolidation queue (names.consolidation_queue; read the queue once when a source file is the basis): add "this file is not consolidated yet; the status card may not reflect it yet" (「该文件尚未整合，状态卡可能还没有反映它的内容」). When it disagrees with the status card, say which is newer by the filed time in the queue, and still do not decide who is right.
8. Quick notes: mark "quick note, not yet filed" with the note's file name, and that it has not been checked; keep any "unconfirmed" mark.
9. Answer snapshots (files of the type "answer archive", or quick notes whose source is "knowledge base answer"): use one only when the status card and source material do not answer; say it is a snapshot of its date that is not updated when its sources change, and name the basis files it cites. Where it disagrees with the status card, the status card is current.
10. Nothing found: say which libraries, files, keywords and wordings were searched, conclude "nothing found in the knowledge base", and suggest rewording or checking whether the material was filed.
11. With sensitivity enabled: never show class-A data in full (ID, card and account numbers, passwords, codes); mask with asterisks, at most the last keep_last characters. No health, money or investment advice and no interpretation of results, diagnoses, returns or coverage; report only what is recorded.
12. Answer only what was asked; mention the search process only when nothing was found or sources conflict.
13. Replies follow the library language and preferences.output.
14. With preferences.citations on_request, see "Citations on request"; it replaces rules 2, 4 to 10 and 12 where they differ.

## Citations on request

When the registry sets preferences.citations to on_request (references/config.md, section 1), search and choose exactly as above, but write the reply as plain statements of fact:

1. No basis file names, no library label, no consolidation reminder, and no words about a knowledge base, a library, searching, querying, records as evidence or sources (such as 「知识库」「查询」「检索」「依据」「佐证」「根据记录」).
2. Nothing found: say only that there is no record of it (「没有相关记录」). If general knowledge is really needed, answer it in a separate paragraph worded so it reads as general practice, not as a recorded fact; no heading.
3. Sources disagree (status card and source material, two files, a dated value and a newer one): give the current value first, then one sentence "another version says ... (date)" (「另有一种说法是……（日期）」), with no file names. Do not decide who is right.
4. A file not yet consolidated, an answer snapshot or git history: no notice of its own. When it changes the answer, write it as in item 3, with its date.
5. A quick note: mark the statement "unconfirmed" (「未核实」), without the file name.
6. Keep the rest: standard terms, exact numbers and dates with units, open items with their deadlines, masking with sensitivity enabled.
7. The user asks where something came from (「出处」「依据」「哪来的」「来源」, "source"): do not search again; for the previous answer, list each statement with the full file name(s) it rests on, with the library when several were searched, and each version separately where sources disagreed. If the earlier search results are no longer in the conversation, search again first.
8. Writing tasks (Step 1, rule 6): the "to check" section follows items 1 to 5.
