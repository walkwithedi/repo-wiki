# Working environment

These skills follow the Agent Skills format and run in any assistant that supports it. Check what you can do once, at the start, and pick the matching path.

## Claude Code and Codex

Use the complete skill folder from the current entrypoint: `.claude/skills/<name>/` in Claude Code, `.agents/skills/<name>/` in Codex. If automatic discovery is unavailable, read the SKILL.md named by the project's instructions explicitly, then its required references. Scripts and references are relative to that same folder. Do not assume that listing the files means the host has loaded them.

After locating an existing library, run `python3 <skill folder>/scripts/kbdoctor.py <library root>` once per conversation. It checks local capabilities without changing files, fetching or testing a push. Missing PDF tools are warnings unless `--require-pdf` is given; they do not block queries or notes. Install dependencies through the environment's setup mechanism, not by changing knowledge files. Do not run this check on a not-yet-created library in init mode.

Use the host's file-reading, editing, shell and image-viewing tools. Claude tool names, settings and lifecycle hooks do not configure Codex. For a required choice, use the available question tool or show the same options in the conversation and wait. Keep all existing preview and confirmation points; a prior authorization is not requested twice. Never create Claude approval markers to simulate approval.

Cloud uploads must be accessible as files to the executor before conversion. If a file or image is unavailable, say which input is missing; never invent its content. A scheduled run needs a separately configured scheduler and prior authorization; a skill alone does not schedule anything. Use the final reply as the record when no notification tool is available.

## Work and output folders

- Work folder: a scratch folder for copies of summary files, change lists and plan files. Use your environment's temporary or scratch directory and create work/ and out/ inside it (a temporary directory outside the library). When the request names a work folder ("Work folder: <path>", "工作文件夹：<路径>"), use that folder and create work/ and out/ inside it.
- Never use the library root as the work folder.
- Handing a file to the user: use whatever your environment offers (a download link or file card, or the path on disk). With direct delivery there is nothing to hand over; the files land in the library.

## Running scripts

Paths such as scripts/batch_plan.py are relative to this skill's folder, not to the current directory. Run a script by its full path in the skill's folder, or as cd <skill folder> && python3 scripts/<name>.py ..., one command per call, with no pipes, redirections or chained commands; put text arguments in quotes.

## Capabilities and fallbacks

| Missing | What to do |
| --- | --- |
| Cannot run Python | Do each script's job by hand, following the "Without Python" note at that step, and mark the result "not script-checked" in the delivery note. |
| Cannot reach the library (no checkout of the GitHub repository, path not found) | Stop. Say which repository or path is missing. Never answer from memory. |
| Cannot write files | kb-note: show the finished note in the reply so the user can save it. kb-ingest: show every output file in full. |
| No registry | Offer setup once, as references/config.md describes; never guess a library location. |

## Time

Take the current time in the library timezone (_kb.json timezone). Write dates as YYYY-MM-DD and times as HH:MM. Convert to UTC only where a backend query needs it.

## Replies

Reply in the library language (_kb.json language, else preferences.language, else the user's language). Follow preferences.output for formatting. Knowledge files keep their own formats: YAML front matter, Markdown tables in summary files and the Bases code block in entity pages are file formats, not reply formatting.
