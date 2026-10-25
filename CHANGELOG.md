# Changelog

Releases follow the "Version:" line of the three SKILL.md files; merging a version change to main publishes v<version> (.github/workflows/release.yml).

## 2.3.0

First release of repo-wiki: the skills, setup and documentation for a library kept in a private GitHub repository and used from Claude Code.

- Init sets up a new library in a checked-out repository: it takes the repository from the origin remote, accepts a root that holds only README.md, CLAUDE.md, AGENTS.md, dot files and non-Markdown files, creates no empty folders, writes the registry and the instructions line as one block into the repository's CLAUDE.md (one repository holds one library), reminds you that the repository must be private, and commits and pushes once.
- Every delivery round (intake batch, quick note, consolidation, filing quick notes) is one commit with its run log, pushed to the default branch after a rebase; it counts as done only when the push succeeded. No branches, pull requests or force-pushes.
- A new version overwrites the old one in place; there is no archive folder, and archive mode is declined. Earlier versions come from git history, cited by commit date and short hash.
- Searches, reads and health checks skip README.md, CLAUDE.md, AGENTS.md and dot files.
