# Setup

How to start a library in a GitHub repository, what each step writes, and how to update the skills or try the sample. [中文](setup.zh-CN.md)

## What you need

Check each item before you start; a missing one usually shows up later as a skill that does nothing or answers from memory.

- [ ] Claude Code: in a terminal, the desktop app, or claude.ai/code on the web and in the Claude phone app.
- [ ] git and Python 3.8 or newer where the session runs. Cloud sessions on claude.ai/code have both; the scripts use only the Python standard library.
- [ ] A GitHub account, and for cloud sessions GitHub connected to claude.ai with access to the library repository.
- [ ] A **private**, empty repository for each library. A README or a licence file in it is fine.

Keep the repository private. It will hold your documents, quick notes and the status card; anyone who can read the repository can read the library.

## 1. Put the skills into the repository

From the [Releases](../../../releases) page download three zips: `kb-note-<version>.zip`, `kb-query-<version>.zip` and `kb-ingest-<version>.zip`. Take the `-zh` zips instead if you want Chinese trigger phrases; never install both versions of one skill, since they would answer the same requests.

Unpack each zip into `.claude/skills/` of a checkout of the library repository, so that the folders read:

```text
.claude/skills/kb-ingest/SKILL.md
.claude/skills/kb-note/SKILL.md
.claude/skills/kb-query/SKILL.md
```

Commit and push them. Claude Code loads skills from the repository's `.claude/skills/`, so every session on the repository, local or in the cloud, has them.

```bash
git clone https://github.com/<you>/<library-repo>.git && cd <library-repo>
mkdir -p .claude/skills
unzip ~/Downloads/kb-note-<version>.zip -d .claude/skills
unzip ~/Downloads/kb-query-<version>.zip -d .claude/skills
unzip ~/Downloads/kb-ingest-<version>.zip -d .claude/skills
git add .claude/skills && git commit -m "Add knowledge base skills" && git push
```

## 2. Set up the library

Open a Claude Code session on the repository (run `claude` in the checkout, or start a session for the repository on claude.ai/code) and say "get started with the knowledge base" ("开始使用知识库"). kb-ingest:

1. Finds the repository from the checkout's origin remote; there is no folder to name.
2. Asks two questions, one at a time: the preset (life or work) and one sentence on what belongs in the library (the scope).
3. Works out the rest: label and id, language, timezone, sensitivity (on for life), conversion of uploads to Markdown (on).
4. Shows a preview of everything it will write, with a reminder that the repository must be private. Nothing is written before you reply "confirm"; any item can be changed first.
5. Writes into the repository root: `_kb.json`, `_kb-params.md`, the spec (`00_Spec.md`) and the empty summary files. No folders are created yet: git keeps no empty folders, and the skills create Quick-Notes and Entities when they first write into them.
6. Adds the registry to the repository's `CLAUDE.md`, together with the line that tells Claude the library exists. Every other line of CLAUDE.md stays as it is.
7. Commits everything as one commit ("Init: <label>") and pushes it. Setup is done only when the push has succeeded.

Check the setup: start a new session on the repository (Claude Code reads CLAUDE.md when a session starts) and ask "which knowledge bases do I have?". Claude should name the library and its scope. If it does not, see [troubleshooting](troubleshooting.md).

## 3. Try it

1. Give Claude a document and say "file this": in a local session name the file or folder on disk, in any session paste the text or attach a file where your Claude Code app allows it. Intake places it in a partition, names it, checks for duplicates and versions, writes it after a preview, commits and pushes, and reports one line with the commit. It is searchable at once.
2. Ask a question the document answers. kb-query reads the status card, then the file, and names the file in its answer.
3. Say "consolidate". kb-ingest adds the file's key conclusions and proposes changes to the status card as a numbered list for you to accept.

Other requests: "note this: ..." (kb-note), "file my quick notes", "health check". All of them, with what happens after each: [daily-use.md](daily-use.md).

## More libraries

One repository holds one library. For a second library (for example work next to life), create another private repository, put the skills into it and run step 2 there. Each library is used in sessions on its own repository; init refuses a CLAUDE.md that already registers another library.

## Updating the skills

Download the new zips, replace the three folders under `.claude/skills/` with the unpacked new ones (delete the old folders first, so files a release removed do not linger), commit and push. The library files need no change unless the changelog says otherwise.

```bash
rm -rf .claude/skills/kb-note .claude/skills/kb-query .claude/skills/kb-ingest
unzip ~/Downloads/kb-note-<version>.zip -d .claude/skills    # and the other two
git add -A .claude/skills && git commit -m "Update knowledge base skills to <version>" && git push
```

## The registry

Init writes the registry into `CLAUDE.md` as a block like this (shown for an English library):

````text
I keep knowledge bases: Life (me and my family: IDs, health, insurance, money, home). For questions about these, use kb-query before searching code or answering from memory; to save something, use kb-note. At the start of a conversation, if a library holds an unfinished batch intake, ask whether to continue it.

Knowledge base registry (kb-libraries.json):

```json
{
  "schema": 1,
  "preferences": {"language": "en"},
  "libraries": [
    {"id": "life", "label": "Life", "scope": "me and my family: IDs, health, insurance, money, home",
     "backend": {"type": "github", "root": "<you>/<library-repo>"}}
  ]
}
```
````

- `scope` decides what belongs in the library; keep it a clear sentence.
- `backend.root` is the repository as `<owner>/<repo>`; the skills work only in a checkout whose origin is that repository.
- `preferences.output` may be added: `markdown` or `plain` (no Markdown markup in replies).
- `preferences.citations` may be added: `always` (default; every fact names its basis file) or `on_request` (answers read as plain statements; the basis files are listed when you ask where something came from).
- To change the scope or label, edit the block by hand and commit, or say "init" and let init mode show the change first.

## Settings of a library

`_kb.json` and `_kb-params.md` sit in the repository root; the skills read them every time. The keys of `_kb.json` (language, timezone, names, sensitivity, partitions, conversion, intake) are described in [skills/kb-ingest/references/config.md](../skills/kb-ingest/references/config.md).

## Commits

The skills commit only the files each round wrote, with a first line naming the mode and the count ("Intake: 3 files", "Quick note: <file name>"), and push to the default branch. They never create branches, open pull requests or force-push. Author identity and message rules come from git's configuration and from the repository's own CLAUDE.md, so add a line there if you want commits in a certain language or under a certain name.
