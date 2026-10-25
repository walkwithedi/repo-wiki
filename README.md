# repo-wiki

A personal knowledge base that Claude Code keeps current in a private GitHub repository. Ask it from a terminal, the desktop app or claude.ai/code on your phone and get one current answer with the file it came from; every change is a commit, so git keeps every earlier version. Three skills do the work; the library is a plain folder of Markdown files in a repository you own.

[中文说明](README.zh-CN.md)

## What it looks like

A question to the fictional [sample library](examples/) (reply shortened):

```text
You:    What is my cholesterol trend?
Claude: Library: Life
        Total cholesterol was 5.6 mmol/L at the 2025 annual checkup, above the
        reference of 5.2; a follow-up was suggested in 12 months. The library holds
        one checkup so far, so there is no trend yet.
        Basis: 02_Checkups_report_2025-annual.md
```

The answer comes from the library's status card, one line per current fact, each with its source:

```text
1. Annual checkup 2025: total cholesterol 5.6 mmol/L, above the reference 5.2;
   follow-up suggested in 12 months (basis: 02_Checkups_report_2025-annual)
2. Cloud storage subscription renews 2026-11-01, 99.00 per year (basis: ...)
```

File the 2026 checkup and say "consolidate": item 1 is proposed for an update, you accept it, and the commit records the change. Ask "what did it say before?" and the earlier version comes from git history, named with its commit.

## What you get

- **The current answer, not the best match.** A new version of a document replaces the old one under the same name, so an outdated plan or an old statement does not come back as the answer.
- **A source for every fact.** Each answer names its file; what the library does not record is said to be not recorded, never filled in from memory.
- **Every version kept.** Each intake, note or status-card update is one commit pushed to your repository; earlier versions stay in git history and answers about how something changed cite the commit.
- **Your repository, your rules.** The library lives in a private repository you own, readable in any editor or on github.com, and every write is shown to you before it happens.

| Skill | You say | It does |
| --- | --- | --- |
| kb-note | "note this", "save this answer" | keeps a remark or an answer as a quick note, filed later |
| kb-ingest | "file these", "consolidate", "health check", "get started with the knowledge base" | files material, keeps one current version of each document, updates the status card after your review, checks the library |
| kb-query | any question the library may answer | searches the library first and names the file each fact comes from |

All phrases, and what happens after each: [docs/daily-use.md](docs/daily-use.md).

## Quick start

You need Claude Code (terminal, desktop app, or claude.ai/code on the web and phone), git, Python 3.8 or newer, and a GitHub account.

1. Create an empty **private** repository on GitHub for the library. It will hold personal or work material, so never make it public.
2. Download `kb-note`, `kb-query` and `kb-ingest` from [Releases](../../releases) (three zips; the `-zh` ones have Chinese trigger phrases). Unpack them into `.claude/skills/` of the library repository, commit and push.
3. Open the repository in Claude Code and say "get started with the knowledge base". Claude asks two questions, shows a preview, writes the library and its registry into the repository's CLAUDE.md, and pushes one commit.
4. Check: start a new session on the repository and ask "which knowledge bases do I have?". If Claude names your library, you are set up.

Step by step: [docs/setup.md](docs/setup.md). Something not working: [docs/troubleshooting.md](docs/troubleshooting.md).

## Is it for you

- **For** one person keeping their own knowledge, life or work, who is happy to use Claude Code. Notes and questions work from claude.ai/code on a phone; a large intake is easiest in a local session, where the original files are on disk. To convert many files to Markdown first, a converter such as [doc2kb](https://github.com/walkwithedi/doc2kb) helps.
- **One repository per library.** A life library and a work library are two repositories, each with its own sessions.
- **Not for** teams writing to one library at the same time (pushes are rebased, and a conflict stops the write for you to sort out), anyone who wants to use the library from plain claude.ai conversations without Claude Code, or anyone who cannot keep the repository private.

## How it stays current

- **Name equals version.** A new version of a document takes the old one's name and overwrites it; git history keeps the old one.
- **One status card per library** holds the current answer to every recurring question. It is rewritten only when new material contradicts it, after you review the change, and a script checks that no line was lost and that its numbers and dates appear in the sources.
- **Evidence or no change.** Every judgement (duplicate, new version, change of fact) needs a quote; without one the skill takes the conservative choice.
- **File fast, consolidate after.** Each file is searchable as soon as it is filed; updating the status card happens when you say "consolidate".
- **One round, one commit.** Each delivery is committed with a log of what it wrote and pushed to the default branch; a write counts as done only when the push succeeded.

The reasoning: [docs/methodology.md](docs/methodology.md).

Inside a library repository:

```text
my-life-kb/
  .claude/skills/          kb-note, kb-query, kb-ingest
  CLAUDE.md                the registry and the line that tells Claude the library exists
  _kb.json, _kb-params.md  the library's settings
  00_Spec.md               partitions and topics, term fixes, thresholds
  00_Status-Card.md        current facts, each linked to its source
  01_File-Index.md         every filed document with its source file and hash
  01_Open-Items.md         due dates and to-dos (life) or open decisions (work)
  01_Change-Log.md         how facts changed over time
  02_Checkups_report_2025-annual.md
  ...
  Entities/  Quick-Notes/
```

Two presets start a library: life (health, money, insurance, home, family, IDs and legal, devices, subscriptions and travel, learning, reference) and work (goals and plans, projects and tasks, proposals and deliverables, meetings and decisions, policies and procedures, organisation and roles, data and reports, reference and templates). Every file name is configurable.

## Documentation

| Read | For |
| --- | --- |
| [setup](docs/setup.md) | requirements, installing, the first library, updating the skills, the registry |
| [daily use](docs/daily-use.md) | what to say for each task, and what happens |
| [troubleshooting](docs/troubleshooting.md) | symptoms, causes and fixes |
| [methodology](docs/methodology.md) | why the rules are what they are |
| [sample library](examples/) | a fictional library to try everything on |
| [changelog](CHANGELOG.md) | what changed |

Each release carries the three skill zips, their `-zh` versions and a zip of the whole repository ([what to download](docs/release-downloads.md)).

Contributing, repository layout and development: [CONTRIBUTING.md](CONTRIBUTING.md). Licence: [MIT](LICENSE).
