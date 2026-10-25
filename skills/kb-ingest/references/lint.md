# Health check: report on the library

Trigger: "health check", "check the knowledge base". Monthly is a good rhythm. Check and report only; change nothing. Each fix is a suggestion the user decides on, then handled by intake or consolidation. Files whose topic is not in Table A are reported, never expanded.

## One script call

  python3 scripts/lint.py <root> --work <work> [--all]

The scope is the topic files changed in the last 30 days (by git history); "all" checks everything. It runs every check below except your part of check 10 and prints the report in the fixed structure of "Output", each list capped at 20 with its total. Do not repeat these checks by hand; read a file only to judge a finding.

1. Stray files in the root: names containing old_suffix, starting with snapshot_prefix or an underscore, and files that are not .md (settings, the consolidation queue and the repository files are expected).
2. Same-name copies: not applicable, a folder holds one file per name.
3. Table E and entity pages: entities without a page, pages without an entity, pages without an identity line, related-files lists out of date (fix: entity_pages.py --in-place, entity-yaml.md).
4. Format (YAML mode): no front matter; fields that most files have but this one lacks; dates not ISO; links to names outside Table E; partition differing from the file name; topic not found in Table A.
5. Suspicious dates: a year-month in the file name more than two months later than the document date.
6. Basis lines: status-card lines naming a basis without a link (count), links whose file is neither in the root nor in the index (each).
7. Core entity overviews: core pages last changed before the newest document linking them (may be stale).
8. Index consistency: index rows with no file, files in scope missing from the index.
9. Settings: _kb.json passes kbconf.py validate; partitions.max and fallback match Table A; _kb-params.md exists.
10. Possible duplicate entities (YAML mode): the script lists Table E names and aliases that match once case, spaces, hyphens and punctuation are dropped (high) or where one holds the other (medium). Your part: judge those, and compare all names and aliases for what it cannot see: translations, abbreviations and full names, short names, alternative spellings. Give each group a reason and a confidence (high: only the naming differs; medium: likely the same, depends on context; low: unsure). Different types are usually not grouped. Skip pairs the spec records as confirmed different. Suggest keeping one name and moving the others to aliases, for the user to decide; if the user says they differ, suggest recording that in the spec so it is not reported again.
11. Quick-note backlog: notes in the notes folder (not the filed subfolder) and the oldest. Over 20 notes or older than 14 days: suggest filing them.
12. Consolidation backlog: rows in the consolidation queue and the oldest; rows whose file is missing; files carrying the pending mark without a row. Rows older than 14 days, or more than 30 rows: suggest consolidation.
13. Status-card values: evidence_check.py on the items whose basis files are in scope, at most 20 basis files ("sampled" when more). Report only: a value may be derived, so the user decides with intake or consolidation.
14. Class-A data (sensitivity enabled): candidates in the files in scope, starred.

## Output (fixed structure, as lint.py prints it)

Date, library, scope
1. Stray files: N (each)
2. Same-name copies: not applicable
3. Table E and entity pages: N
4. Format problems: N
5. Suspicious dates: N
6. Basis lines: N not linked, N broken (each broken one)
7. Overviews possibly stale: N
8. Index mismatches: N
9. Settings: consistent / N mismatches (each)
10. Possible duplicate entities: N groups (each: name A, name B; reason; confidence)
11. Quick-note backlog: no notes folder / N notes, oldest YYYY-MM-DD
12. Consolidation backlog: no queue / N files, oldest YYYY-MM-DD HH:MM; N rows without file, N marked files without row
13. Status-card values: N items checked (sampled / all in scope), N values not found, N without basis link, N basis files missing (each: item number, value, basis file)
14. Class-A candidates: N (sensitivity enabled only)
Suggested actions: three to five, by priority, each naming the mode that handles it.

Without Python: do each check by hand on the files in scope, count first and sample; over 20 in one check, list the first 20 and give the total; mark the report "not script-checked".
