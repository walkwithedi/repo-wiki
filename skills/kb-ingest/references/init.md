# Init mode: get started, set up a new library

Trigger: "get started with the knowledge base", "first time", "set up a knowledge base", "new library", "init", "complete the settings". Also entered when kb-query or kb-note found no registry and the user accepted the offer to set one up.
Result: the repository root holds _kb.json, _kb-params.md, the spec and the empty summary files, and the repository's CLAUDE.md holds the registry block (the instructions line and the registry), so every session on the repository knows the library exists.

A library is a GitHub repository checked out in a Claude Code session (references/backend-github.md); one repository holds one library. Presets live in assets/presets/<name>/: _kb.json, _kb-params.md, 00_Spec.md and summary/ (empty summary files). A preset may also have <language>/ with translated _kb-params.md, 00_Spec.md and summary/, used for a library in that language (work has zh/). Available: life and work. For a blank start, take the closer one and remove the topics the user does not want. Placeholders {{DATE}}, {{HEADING_LIMIT}} and {{FILENAME_LIMIT}} are filled when writing.

scripts/init_library.py holds the shared definition of a new library: the suggested label, id and scope per preset and language, the files to create, the registry entry and the registry block. Use it whenever Python runs; without Python, do its job by hand as described at each step and say "not script-checked" in the report.

## Rules

1. Questions, then a preview, then writing. Nothing is written before the user confirms the preview.
2. Only create files, and the registry block in CLAUDE.md. Never delete or rewrite knowledge files, summary files or the spec of an existing library.
3. A new library needs a repository without a library: its root may hold README.md, CLAUDE.md, AGENTS.md, names starting with a dot and files that are not Markdown; any other Markdown file means an existing library.
4. Never invent rules. Every partition, topic and type comes from the preset as the user confirmed or changed it.
5. Ask as little as possible. Ask only what cannot be found out reliably; show everything else in the preview, where the user can change any item.

## Getting started (first-time guide)

For a user who has just installed the skills, or says it is the first time. Keep each message short and in the user's language.

1. Look before asking, without telling the user each check:
   - Registry (references/config.md): found, and with which libraries.
   - Python: python3 scripts/init_library.py defaults runs (it also prints the suggested timezone and language).
   - The checkout: the current directory is a git working tree whose origin remote is a GitHub repository (git remote get-url origin), in a session that can run git; the new library is that repository, "<owner>/<repo>" from the remote. No such checkout: stop and say that a library is set up in a Claude Code session with its repository checked out (references/environment.md).
2. A registered library that fails step 0 of SKILL.md (missing _kb.json or _kb-params.md) is completed by hand in its repository; say so and stop. Init mode sets up new libraries only.
3. The repository already holds a library (rule 3): say so, and that a second library needs its own repository; stop.
4. Otherwise say in two sentences what will happen: two questions, a preview, nothing is written before "confirm". Then run Round 1.
5. After Round 2, finish with the report and three things to try (Round 2, step 6).

A folder that holds the user's original files (Office, PDF, pictures, no _kb.json or spec) is material, not a library: never register it as a library. Offer to file it into a registered library. When the user's meaning is unclear, ask with the question in references/config.md, section 3.

## Round 1: questions

Two questions, one at a time, each with a suggested answer:
1. Preset: life (me and my family: IDs, health, insurance, money, home) or work (work goals and plans, projects and tasks, meetings and decisions, policies and procedures, reports). One line each; the partition table appears in the preview.
2. Scope: one sentence saying what belongs in the library, suggested from python3 scripts/init_library.py defaults --preset <preset> --language <language>. Explain that it decides which library each request goes to.

Found out, not asked (all shown in the preview):
- Label and id: from the defaults for the preset.
- Language: the language the user writes in. It sets the Table D limits (python3 scripts/kbconf.py limits --language <lang>).
- Timezone: from the defaults command (the system timezone); where the system timezone is meaningless (often UTC on a server), the timezone the user's messages indicate, else ask in the preview.
- Sensitivity and masking: the preset's setting (on for life, off for work).
- Conversion: on, as both presets set it. Uploads are turned into Markdown by a script before intake, which saves tokens and time (references/convert.md). Say in the preview what it does in a few words, so the user can turn it off there.
- Partitions: the preset's Table A, unchanged unless the user edits it in the preview. Partition numbers stay two-digit and continuous; the fallback partition stays the preset's unless the user changes it.

## Preview

Fixed structure:
  Library: <label> (id <id>) | repository <owner>/<repo>
  Scope: <one sentence> | language: <lang> | timezone: <tz> | sensitivity: on / off
  Convert uploads to Markdown first: on / off (fewer tokens and faster intake; pictures in a batch over the limit are read only if you agree)
  1. _kb.json: new
  2. _kb-params.md: new from preset <name>
  3. Spec: new from preset (version v1, today), partitions: <number name, one line each>
  4. Summary files: list of files to create with their names
  5. Folders: none now; created when first written to; no archive folder, git history keeps old versions
  6. Registry and instructions line: the block in this repository's CLAUDE.md, new or updated
  The repository must be private, since the library holds personal or work material; check it on GitHub (Settings > General > Danger Zone, Change visibility) before filing anything.
End with: reply "confirm" to write, or name any item to change. The turn ends here.

With Python, python3 scripts/init_library.py plan --root <checkout> --preset <preset> --label <label> --id <id> --scope "<scope>" --language <lang> --timezone <tz> --sensitivity on|off --convert on|off prints items 1 to 5 and checks that the repository holds no library yet (rule 3).

## Round 2: write (after confirmation)

1. Re-check: the checkout is up to date (python3 scripts/kbgit.py sync <checkout>, references/backend-github.md) and still passes the plan check; anything changed since the preview: stop and report.
2. Write the files: python3 scripts/init_library.py write --root <checkout> with the confirmed options. It creates no folders; the skills create the notes and entities folders when they first write into them. Partition changes from the preview: apply them to Table A of the spec just written. Without Python, fill the preset files yourself: the spec template with the confirmed Table A, type list and Table D limits, version v1 and today's date; summary files with their title, "Last updated: <today>" and empty headers; the file index header is
     Entries: 0
     Last updated: YYYY-MM-DD
     | File name | Source file name | Source hash |
     | --- | --- | --- |
   so scripts/index_tool.py can maintain it.
3. Registry and instructions line, both in the repository's CLAUDE.md:
   python3 scripts/init_library.py register --registry <work>/kb-libraries.json --id <id> --label <label> --scope "<scope>" --type github --root <owner>/<repo> --language <lang>
   python3 scripts/init_library.py instructions --registry <work>/kb-libraries.json --file <checkout>/CLAUDE.md --block --apply
   The block is the instructions line, the registry heading and the registry as a json code block. It is added to the end of CLAUDE.md, or replaces the block already there; every other line stays as it is. A CLAUDE.md that registers another library is refused (exit 3): one repository holds one library; report it and stop. Without Python, write the same block by hand; the instructions line is
   "I keep knowledge bases: <label> (<scope>). For questions about these, use kb-query before searching code or answering from memory; to save something, use kb-note. At the start of a conversation, if a library holds an unfinished batch intake, ask whether to continue it."
   In Chinese: "我有知识库：<名称>（<范围>）。相关问题先用 kb-query 查知识库，再查代码或凭记忆回答；要记录用 kb-note。新对话开始时，如知识库有未完成的分批入库，先提醒是否继续。"
4. Check: python3 scripts/kbconf.py validate <checkout>/_kb.json passes, and the block in CLAUDE.md parses as a registry with this one library.
5. Commit and push as one init step (references/backend-github.md, "Commit and push"): python3 scripts/kbgit.py commit <checkout> --title "Init: <label>" (in the library language) --allow-instructions with a --path for each file of step 2 and for CLAUDE.md. Init is complete only when it printed "pushed:".
6. Report in a few lines, in the library language: what was written, the short commit hash, that the repository must be private, then a check and three things to try.
   The check: start a new session on this repository (Claude Code reads CLAUDE.md when a session starts) and ask "which knowledge bases do I have?" ("我有哪些知识库？"). The answer should name the library with its scope.
   Three things to try: "note this: <a fact that fits the scope>"; a question the library will answer once material is filed ("what is due this month?" for life, "what did we decide about <topic>?" for work); "file these" with a document attached.
