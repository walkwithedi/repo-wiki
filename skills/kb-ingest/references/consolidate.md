# Consolidation: conclusions and summary files for items filed by fast intake

Fast intake (references/fast.md) files each item without its key conclusions and without comparing it with the status card. Consolidation does that work for the files in the consolidation queue (names.consolidation_queue), a round at a time: it reads each file closely where needed, writes its key conclusions into it, judges the triggers, and rewrites the summary files once per round after the user has reviewed every change. Nothing reaches the status card without that review, except in a scheduled run (below), which the user allowed beforehand and reports afterwards.

Trigger: "consolidate", "整合", "整合入库", the choice after a fast intake or a batch run, or the reminder of references/config.md, section 5. A scheduled task that says "scheduled consolidation" ("定时整合") runs it unattended, as "Scheduled run" says.

## Before the first round

1. Step 0, then read the spec, status card and open items (on disk the spec and status card as Check 2 of SKILL.md says: kbconf.py spec, and the status-card blocks of each queued file with kbfind.py find; the open items whole); of the file index and the change log only what you need (their reading conditions in params assume a trigger; consolidation always may change them, item by item as hard rule 9 says). Read the glossary when a term issue comes up.
2. Copy the queue into a work folder and list the round:
   python3 scripts/consolidate.py list <work>/<queue name> --limit <intake.consolidate_files>
   Empty queue: say so and stop.
3. Say in one line how many files wait and how many rounds that makes; go straight on with the first round.

## Each round

For each file of the round, in queue order:

1. Close-read files (queue column yes): the topic file carries the pending mark. Read it section by section (scripts/kbfind.py toc lists them, or read the headings) and write the key conclusions as step 3 of SKILL.md says, each naming its section heading. Then write the new head to <work>/head_<file stem>.md: the old head exactly as it is (front matter or text header, section labels) without the mark line, followed by the key conclusions in the place params give them. Then:
   python3 scripts/consolidate.py fill <library root>/<file> <work>/head_<file stem>.md <work>/out/<file>
   It refuses a file without the mark, a head that drops the original line, and anything that would change the body. A refusal: fix the head and run it again; never edit the body.
2. All files: step 5 of SKILL.md, starting with the disposition line. A file with No new information gets its key conclusions as usual (close-read files) but adds nothing to the change list and leaves the queue in this round; list it in the readme ("no new information: <files>"). Disputed items go into the change list as "Disputed: <status card item> / <file, section>" with both quotes; accepting one means keeping the status card as it is and adding an open item. For the rest, ask step 5's three questions for each trigger class, quoting the new material and the status card; no quote, no trigger. Write the twenty lines into this round's notes, not into the reply. Record each trigger as a change: the class, the status-card item with its old wording, the new wording, and the file with its section. Items that settle or open an open item are recorded the same way. A file filed as the same-name new version of an older one also gets its change log entry here.
3. Topics and entities a batch run recorded and has not written into the spec yet (batch_plan.py status, when a progress file is open) are written into the spec in this round: one rewrite, one version step, a revision note for each, as topic expansion says. The batch run's final step is then done (batches.md, section 3).

Then the summary files:

4. Re-check every recorded change against the current status card (an earlier change in this round may have touched the same item). Write the change list for the user, numbered, one line each:
   <n>. <status card | change log | open items>: <old wording> -> <new wording> (<file>, <section>)
   Deletions: <n>. Delete: <old wording> (reason).
   No change: "No summary rewrite this round".
   Before showing the list, run the evidence check of SKILL.md on a draft of the new status card for every new or changed item. Fix wording that differs from the source; a value still not found keeps "(not found in the source: <value>, …)" on its line, so the user sees it when deciding.
5. Ask once, as a choice: Accept all (recommended) / Leave some out first / Cancel the round. In Chinese: 全部采用 / 先剔除其中几条 / 取消本轮. When the request says the run is unattended (the user allowed everything beforehand and nobody answers), do not ask: take Accept all, and write "unattended, all accepted" into the readme's change section. "Leave some out": ask which numbers, as a second choice when there are four or fewer, otherwise in one line; changes left out are not applied and their files stay in the queue with a note in the readme ("changes not accepted: <numbers>"). Cancel: nothing is written; the queue is unchanged.
6. Apply the accepted changes to the status card, change log and open items (and entity overviews where a trigger names a core entity) with card_patch.py, one patch per file, as SKILL.md step 5 and "Rewrite check" say; the numbered change list of step 4 becomes the patches. Never deliver a file that fails the check.
7. Remove the consolidated files from the queue copy:
   python3 scripts/consolidate.py done <work>/<queue name> --name <file> [--name <file> ...]
   Files whose changes were left out stay.
8. Put the queue copy, the rewritten summary files and the spec into <work>/out/ next to the filled topic files, write the readme (params sections; the change section lists the accepted changes by number), and deliver as the backend file says: the preview shows that each filled topic file's pre-consolidation copy moves to the archive folder. The user already reviewed the changes, so deliver after the preview without asking again.
9. One progress line:
   Round <r>/<rounds>: <n> files consolidated, <c> summary changes, <q> files still in the queue.
   In Chinese: 第 <r>/<轮数> 轮：整合 <n> 个文件，状态卡等改动 <c> 条，队列还剩 <q> 个。
   Go on with the next round. When the conversation is getting long, stop after a delivered round and tell the user to say "consolidate" in a new conversation; the queue keeps the rest.

Without Python: do the same by hand. For a close-read file write the topic file again as the new head, one blank line and the body copied unchanged from after the mark; compare old and new summary files item by item; edit the queue table. Mark the readme "not script-checked".

## Rules that do not change

Every judgement needs a quote. Never infer, never trim or edit body text, never delete: old versions of topic files and summary files move to the archive folder. Process data never triggers. A file that the status card cannot be matched with goes into open items as SKILL.md says.

## Scheduled run

A scheduled task can run consolidation each night with nobody watching: its prompt names the library and says "scheduled consolidation" ("定时整合"). Everything above applies, with these differences:

1. Nobody answers, so never ask. The library comes from the prompt or the project instructions; when it is not clear, stop and notify (item 6). There is no reminder of section 5 of references/config.md and no closing choice.
2. Empty queue (or no queue file): do nothing more. No commit, no readme, no notification; end with one line saying the queue was empty.
3. At most intake.scheduled_rounds rounds (default 3), each its own delivery and commit; the rest waits for the next run.
4. Step 5 takes Accept all, and the readme's change section says "scheduled run, all accepted". Except:
   - A change the evidence check flags (a value not found in its basis file, no basis link, basis file missing) is not applied to the status card. It becomes an open item instead: what the change would have said, the evidence-check line, and the file and section, for the user to decide. The file still leaves the queue.
   - Disputed items are handled as above: the status card keeps its wording and an open item records both quotes.
   - A topic expansion or a new entity is applied as usual and listed under "Topics added this run (please review)".
5. A failure stops the run where it is: a sync that stops (exit 3 or 4), a conflict with newer commits (exit 3 of the commit; never drop-local, never force), a push that failed (exit 5), a check that fails, a spec or status card not found. Rounds already delivered stay; nothing more is written. Notify (item 6) with the step, the message, and what is left.
6. Notification: when the run consolidated at least one file or stopped on a failure, send one push notification to the user (the environment's notification tool; without one, the final reply is the record). In the library language, at most a few lines: library label; files consolidated and still in the queue; status-card, change-log and open-item changes by count, with the status-card items by name; changes turned into open items by the evidence check; topics or entities added; the commit short hashes; on a failure, what stopped and what is left. Send nothing when the queue was empty. Never send library content beyond these names and counts to any other service.
