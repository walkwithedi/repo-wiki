#!/usr/bin/env python3
"""Shared configuration loader for the evergreen-wiki skills.

Two levels of configuration:

  Registry (user level)   kb-libraries.json: which libraries exist and where they live.
  Library (per library)   _kb.json in the library root: label, language, timezone,
                          metadata mode, sensitivity, partitions and file/folder names.

Every name a skill or script uses (summary files, archive folder, "_old" suffix, ...)
comes from resolve_names(), so a library can keep its own names (for example Chinese
ones) while the skills stay generic.

Subcommands (results on stdout, logs on stderr):
  registry [--path FILE]                    print the resolved registry as JSON
  show     LIBRARY_ROOT_OR_KB_JSON          print the resolved library config as JSON
  names    LIBRARY_ROOT_OR_KB_JSON          print the resolved names, one "key: value" per line
  limits   --language LANG                  print the default Table D length limits for a language
  validate LIBRARY_ROOT_OR_KB_JSON          check _kb.json; exit 3 on problems
  scan-a   FILE [FILE ...] [--keep-last N]  list class-A candidates (ID, card and account numbers,
                                            unmasked passwords and codes), starred; exit 3 on any
  spec     LIBRARY_ROOT [--with-revisions]  print the library spec for intake: the whole text without its
                                            revision notes (their line ranges are named instead), then
                                            which of Tables A to F were found by their titles

Only the Python 3 standard library is used. Python 3.8 or newer.
"""
import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone

log = logging.getLogger("kbconf")
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s.%(funcName)s:%(lineno)d - %(message)s"

SCHEMA = 1
KB_JSON = "_kb.json"
PARAMS_FILE = "_kb-params.md"
REGISTRY_FILE = "kb-libraries.json"

# Default English names. A library overrides any of them through "names" in _kb.json.
DEFAULT_NAMES = {
    "spec": "00_Spec.md",
    "status_card": "00_Status-Card.md",
    "index": "01_File-Index.md",
    "open_items": "01_Open-Items.md",
    "changelog": "01_Change-Log.md",
    "glossary": "01_Glossary-Issues.md",
    "archive_dir": "Archive",
    "entities_dir": "Entities",
    "sources_dir": "Sources",
    "notes_dir": "Quick-Notes",
    "notes_done_dir": "Filed",
    "old_suffix": "_old",
    "snapshot_prefix": "snapshot_",
    "readme": "README.txt",
    "run_log_prefix": "_run-log_",
    "batch_plan": "_intake-batches.json",
    "consolidation_queue": "_Consolidation-Queue.md",
    "note_marker": "Quick note:",
    "assistant_label": "Assistant",
    "user_label": "User",
}
SUMMARY_KEYS = ("spec", "status_card", "index", "open_items", "changelog", "glossary")

# Default Table D length limits by language: (heading demotion limit, file name limit).
# Chinese packs about twice the information per character, so it gets lower limits.
DEFAULT_LIMITS = {"zh": (55, 80), "ja": (55, 80), "ko": (60, 90)}
FALLBACK_LIMITS = (90, 120)

# Converting uploads to Markdown before intake (kb-ingest scripts/convert.py).
# enabled: off unless the library turns it on (new libraries from a preset do).
# image_limit: pictures in one batch that are read without asking.
# min_pdf_chars_per_page, min_chars_per_image: below these a file is read as the original.
# outline_chars: converted text longer than this also gets an outline, read first; 0 turns it off.
CONVERT_DEFAULTS = {"enabled": False, "image_limit": 10, "min_pdf_chars_per_page": 200,
                    "min_chars_per_image": 100, "outline_chars": 6000}

# Intake (kb-ingest). mode: fast files each item at once and leaves key conclusions and the
# trigger check to consolidation (scripts/prep.py, scripts/consolidate.py); full runs every step per
# item. consolidate_files: files handled in one consolidation round. Many files at once
# (scripts/batch_plan.py): a batch closes at batch_files files or batch_mb megabytes; more than one
# batch turns batch mode on. confirm: ask asks once before a fast intake run; command takes an
# explicit request to file as that confirmation when the material makes one batch.
# scheduled_rounds: consolidation rounds one scheduled (unattended) run does at most.
INTAKE_MODES = ("fast", "full")
INTAKE_CONFIRM = ("ask", "command")
INTAKE_DEFAULTS = {"mode": "fast", "confirm": "ask", "batch_files": 10, "batch_mb": 20,
                   "consolidate_files": 10, "scheduled_rounds": 3}

# Originals kept in the library (local libraries with direct delivery only): keep copies each
# filed original into names.sources_dir under its topic file's name; one larger than max_mb
# megabytes is not copied.
SOURCES_DEFAULTS = {"keep": False, "max_mb": 50}

DEFAULTS = {
    "schema": SCHEMA,
    "label": "",
    "preset": "",
    "language": "en",
    "timezone": "UTC",
    "metadata": "yaml",
    "sensitivity": {"enabled": False, "keep_last": 4},
    "partitions": {"max": 9, "topic_start": 2, "fallback": ""},
    "delivery": "",
    "convert": CONVERT_DEFAULTS,
    "intake": INTAKE_DEFAULTS,
    "sources": SOURCES_DEFAULTS,
    "names": {},
}
KNOWN_KEYS = set(DEFAULTS) | {"backend", "inbox", "notes"}


def utf8_stdio():
    """Windows consoles default to a legacy code page; library names may be CJK."""
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass  # not a reconfigurable text stream (redirected or replaced); left as it is


def setup_logging(level):
    utf8_stdio()
    logging.basicConfig(level=level, format=LOG_FORMAT, stream=sys.stderr)


def add_log_args(ap):
    ap.add_argument("--log-level", default=os.environ.get("LOG_LEVEL", "INFO").upper(),
                    choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                    help="default: environment variable LOG_LEVEL, else INFO")


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except OSError as e:
        raise ConfigError(f"cannot read {path}: {e}")
    except json.JSONDecodeError as e:
        raise ConfigError(f"{path} is not valid JSON: {e}")


class ConfigError(Exception):
    pass


def registry_candidates():
    """Places the registry is looked for, in order. Project instructions come first
    but are read by the model, not by this script."""
    out = []
    env = os.environ.get("KB_LIBRARIES")
    if env:
        out.append(os.path.expanduser(env))
    if os.name == "nt" and os.environ.get("APPDATA"):
        out.append(os.path.join(os.environ["APPDATA"], "kb", REGISTRY_FILE))
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    out.append(os.path.join(base, "kb", REGISTRY_FILE))
    here = os.path.dirname(os.path.abspath(__file__))
    out.append(os.path.join(os.path.dirname(here), "config", REGISTRY_FILE))
    return out


def load_registry(path=None):
    paths = [path] if path else registry_candidates()
    for p in paths:
        if p and os.path.isfile(p):
            log.info("registry: %s", p)
            reg = load_json(p)
            problems = check_registry(reg)
            for msg in problems:
                log.warning("registry: %s", msg)
            reg["_path"] = p
            return reg
        log.debug("no registry at %s", p)
    raise ConfigError("no registry found; looked in: " + ", ".join(p for p in paths if p))


BACKENDS = ("github",)
OTHER_BACKENDS = {"gdrive": "Google Drive libraries: use walkwithedi/drive-wiki",
                  "local": "local folders: use evergreen-wiki"}
GITHUB_ROOT_RE = re.compile(r"[A-Za-z0-9-]+/[A-Za-z0-9._-]+")


def check_registry(reg):
    problems = []
    if not isinstance(reg, dict):
        return ["registry must be a JSON object"]
    if reg.get("schema") != SCHEMA:
        problems.append(f"schema should be {SCHEMA}, got {reg.get('schema')!r}")
    libs = reg.get("libraries")
    if not isinstance(libs, list) or not libs:
        problems.append("libraries must be a non-empty list")
        return problems
    seen = set()
    for i, lib in enumerate(libs):
        where = f"libraries[{i}]"
        if not isinstance(lib, dict):
            problems.append(f"{where} must be an object")
            continue
        lid = lib.get("id")
        if not lid or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", str(lid)):
            problems.append(f"{where}.id must be lowercase letters, digits and hyphens")
        if lid in seen:
            problems.append(f"{where}.id {lid!r} is used twice")
        seen.add(lid)
        b = lib.get("backend") or {}
        if b.get("type") in OTHER_BACKENDS:
            problems.append(f"{where}.backend.type {b['type']} is not supported: these skills serve GitHub "
                            f"libraries only ({OTHER_BACKENDS[b['type']]})")
        elif b.get("type") not in BACKENDS:
            problems.append(f"{where}.backend.type must be github")
        if not b.get("root"):
            problems.append(f"{where}.backend.root is required")
        elif b.get("type") == "github" and not GITHUB_ROOT_RE.fullmatch(str(b["root"])):
            problems.append(f"{where}.backend.root of a github library must be <owner>/<repo>")
        if not lib.get("scope"):
            problems.append(f"{where}.scope is empty; the assistant uses it to route questions")
    prefs = reg.get("preferences", {})
    if prefs and prefs.get("output") not in (None, "markdown", "plain"):
        problems.append("preferences.output must be markdown or plain")
    if prefs and prefs.get("citations") not in (None, "always", "on_request"):
        problems.append("preferences.citations must be always or on_request")
    return problems


def find_kb_json(path):
    path = os.path.expanduser(path)
    if os.path.isdir(path):
        path = os.path.join(path, KB_JSON)
    return path


def merge(base, over):
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = v
    return out


def resolve_names(names_override=None):
    names = dict(DEFAULT_NAMES)
    for k, v in (names_override or {}).items():
        if k.endswith("_key"):
            names[k] = v
        elif k in DEFAULT_NAMES:
            names[k] = v
        else:
            log.warning("unknown name key ignored: %s", k)
    for k in SUMMARY_KEYS:
        names.setdefault(k + "_key", search_key(names[k]))
    return names


def search_key(file_name):
    """Partial string used to find a summary file: '00_Status-Card.md' -> 'Status-Card'."""
    stem = re.sub(r"\.md$", "", file_name, flags=re.I)
    return re.sub(r"^\d+_", "", stem)


def load_library(path):
    p = find_kb_json(path)
    raw = load_json(p)
    cfg = merge(DEFAULTS, raw)
    cfg["names"] = resolve_names(raw.get("names"))
    cfg["_path"] = p
    for msg in validate(raw):
        log.warning("%s: %s", p, msg)
    return cfg


def validate(raw):
    problems = []
    if not isinstance(raw, dict):
        return ["_kb.json must be a JSON object"]
    if raw.get("schema") != SCHEMA:
        problems.append(f"schema should be {SCHEMA}, got {raw.get('schema')!r}")
    for k in raw:
        if k not in KNOWN_KEYS:
            problems.append(f"unknown key {k!r}")
    if raw.get("metadata", "yaml") not in ("yaml", "text"):
        problems.append("metadata must be yaml or text")
    if raw.get("delivery", "") not in ("", "direct"):
        problems.append("delivery must be direct (or left empty)")
    problems += check_convert(raw.get("convert", {}))
    problems += check_intake(raw.get("intake", {}))
    problems += check_sources(raw.get("sources", {}))
    part = raw.get("partitions", {})
    mx, ts = part.get("max", 9), part.get("topic_start", 2)
    if not (isinstance(mx, int) and isinstance(ts, int) and 0 < ts <= mx <= 99):
        problems.append("partitions needs integers with 0 < topic_start <= max <= 99")
    fb = part.get("fallback", "")
    if fb and not (re.fullmatch(r"\d{2}", str(fb)) and ts <= int(fb) <= mx):
        problems.append("partitions.fallback must be a two-digit topic partition inside the range")
    problems += check_timezone(raw.get("timezone", "UTC"))
    names = raw.get("names", {})
    for k in names:
        if not (k in DEFAULT_NAMES or (k.endswith("_key") and k[:-4] in SUMMARY_KEYS)):
            problems.append(f"unknown names key {k!r}")
    return problems


def check_convert(conv):
    if not isinstance(conv, dict):
        return ["convert must be an object such as {\"enabled\": true}"]
    problems = []
    for k, v in conv.items():
        if k not in CONVERT_DEFAULTS:
            problems.append(f"unknown convert key {k!r}")
        elif k == "enabled" and not isinstance(v, bool):
            problems.append("convert.enabled must be true or false")
        elif k != "enabled" and not (isinstance(v, int) and not isinstance(v, bool) and v >= 0):
            problems.append(f"convert.{k} must be a whole number of 0 or more")
    return problems


def check_intake(intake):
    if not isinstance(intake, dict):
        return ["intake must be an object such as {\"batch_files\": 10}"]
    problems = []
    for k, v in intake.items():
        if k not in INTAKE_DEFAULTS:
            problems.append(f"unknown intake key {k!r}")
        elif k == "mode":
            if v not in INTAKE_MODES:
                problems.append("intake.mode must be fast or full")
        elif k == "confirm":
            if v not in INTAKE_CONFIRM:
                problems.append("intake.confirm must be ask or command")
        elif not (isinstance(v, int) and not isinstance(v, bool) and v >= 1):
            problems.append(f"intake.{k} must be a whole number of 1 or more")
    return problems


def check_sources(src):
    if not isinstance(src, dict):
        return ["sources must be an object such as {\"keep\": true}"]
    problems = []
    for k, v in src.items():
        if k not in SOURCES_DEFAULTS:
            problems.append(f"unknown sources key {k!r}")
        elif k == "keep" and not isinstance(v, bool):
            problems.append("sources.keep must be true or false")
        elif k == "max_mb" and not (isinstance(v, int) and not isinstance(v, bool) and v >= 0):
            problems.append("sources.max_mb must be a whole number of 0 or more")
    return problems


def keeps_sources(cfg, backend_type="local"):
    """True when intake copies originals into the library: sources.keep is on and the library is a
    local one (a GitHub library never carries originals)."""
    return bool((cfg.get("sources") or {}).get("keep")) and backend_type == "local" and \
        default_delivery(cfg, backend_type) == "direct"


class TimezoneUnavailable(ConfigError):
    """The name may be fine, but this Python cannot resolve IANA names
    (3.8 has no zoneinfo; Windows has no system timezone database)."""


def check_timezone(name):
    """Validate the spelling only, so a config checks the same on every system."""
    if name in (None, "", "UTC", "Z") or re.fullmatch(r"[+-]\d{2}:?\d{2}", str(name)):
        return []
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_+-]*(/[A-Za-z0-9_+-]+){0,2}", str(name)):
        return [f"timezone {name!r} is neither an IANA name nor an offset like +08:00"]
    try:
        tzinfo(name)
    except TimezoneUnavailable:
        pass  # the name is well formed; this Python only lacks the zone data to load it
    except ConfigError as e:
        return [str(e)]
    return []


UTC_NAMES = ("Etc/UTC", "Etc/GMT", "Etc/Universal", "Etc/Zulu", "GMT", "Universal", "Zulu")


def system_zone():
    """The IANA name of this computer's time zone (TZ, /etc/localtime, /etc/timezone), or ""."""
    tz = os.environ.get("TZ", "").lstrip(":")
    if tz:
        return tz
    try:
        m = re.search(r"zoneinfo/(?:posix/|right/)?(.+)$", os.path.realpath("/etc/localtime"))
        if m:
            return m.group(1)
    except OSError:
        log.debug("/etc/localtime cannot be read; trying /etc/timezone")
    try:
        with open("/etc/timezone", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def tzinfo(name):
    """IANA name or a fixed offset such as +08:00 / UTC."""
    if name in (None, "", "UTC", "Z"):
        return timezone.utc
    m = re.fullmatch(r"([+-])(\d{2}):?(\d{2})", name)
    if m:
        sign = 1 if m.group(1) == "+" else -1
        return timezone(sign * timedelta(hours=int(m.group(2)), minutes=int(m.group(3))))
    if name in UTC_NAMES:
        return timezone.utc
    try:
        import zoneinfo  # Python 3.9+
    except ImportError:
        # The library's zone is usually this computer's own (setup writes the system zone): its current
        # offset is then the right one, without the zone data this Python lacks.
        if name == system_zone():
            return datetime.now().astimezone().tzinfo
        raise TimezoneUnavailable(f"timezone {name!r} needs Python 3.9+; use a fixed offset like +08:00")
    try:
        return zoneinfo.ZoneInfo(name)
    except Exception:
        if not zoneinfo.available_timezones():
            raise TimezoneUnavailable(f"this system has no timezone database for {name!r} "
                                      "(usual on Windows); use a fixed offset like +08:00")
        raise ConfigError(f"unknown timezone {name!r}")


def now(tz_name):
    return datetime.now(tzinfo(tz_name))


def default_limits(language):
    lang = (language or "en").split("-")[0].lower()
    return DEFAULT_LIMITS.get(lang, FALLBACK_LIMITS)


def default_delivery(cfg, backend_type):
    """Always direct: the files are written into the checkout after a preview."""
    return "direct"


# ---------- tables of the spec ----------
# A table starts at its title line: a short line that names it near its start ("2. Table B: term fixes",
# "5. 表 E（Table E）：实体", "五、表E　实体"); mentions of a table inside sentences are not titles. The
# section runs to the next title. Its rows are the lines split by "｜", "|" or "→" into two or more
# cells; the first row is the header (a lead-in such as "列：" before it is dropped), notes and blank
# lines between the header and the rows are skipped, and the table ends at the first other line
# after its rows. A table written as running text (one line per partition, no separators) has no
# rows: spec_section gives its lines.

TABLE_LABEL = re.compile(r"(?:Table|表)\s*([A-F])\b")
SEPARATORS = ("｜", "|", "→")


def title_letter(line):
    """The letter of the table this line is the title of, or None."""
    s = line.strip()
    m = TABLE_LABEL.search(s)
    rest = re.sub(r"（[^（）]*）|\([^()]*\)", "", s[m.end():]) if m else ""  # a bracketed note may hold commas
    if not m or m.start() > 8 or len(s) > 40 or row_cells(s) or re.search(r"[。，、；,;]", rest):
        return None  # a sentence that mentions tables ("see Table A, Table B") is no title
    return m.group(1)


def row_cells(line):
    """The cells of a table row, or None when the line is no row (or a --- separator row)."""
    s = line.strip()
    for sep in SEPARATORS:
        if sep in s:
            if sep == "|" or sep == "｜":
                s = s.strip(sep)
            cells = [c.strip() for c in s.split(sep)]
            if len(cells) < 2:
                return None
            if all(re.fullmatch(r":?-{3,}:?", c) for c in cells if c) and "-" in s:
                return []
            return cells
    return None


def spec_section(spec, letter):
    """The lines of the spec's Table <letter> section after its title, or None when it has no title."""
    lines = spec.split("\n")
    start = next((i for i, ln in enumerate(lines) if title_letter(ln) == letter), None)
    if start is None:
        return None
    end = next((j for j in range(start + 1, len(lines)) if title_letter(lines[j])), len(lines))
    return lines[start + 1:end]


def spec_table(spec, letter):
    """(header cells, rows of cells) of the spec's Table <letter>, or None when it has no such table."""
    section = spec_section(spec, letter)
    if section is None:
        return None
    header, rows, gap = None, [], 0
    for line in section:
        cells = row_cells(line)
        if cells == []:
            continue  # --- separator row
        if cells:
            if header is None:
                first = re.split(r"[：:]", cells[0])
                header = [first[-1].strip()] + cells[1:] if len(first) > 1 else cells
            else:
                rows.append(cells)
            gap = 0
        elif not line.strip():
            continue
        elif header is not None:
            if rows:
                break
            gap += 1
            if gap > 2:
                break
    return (header, rows) if header else None


# Revision notes ("修订说明：…", "本次修订说明（v5.2）", "修订历史", "Revision: …") record how the spec changed; intake
# needs them only for topic expansion. A note runs from its first line over blank, indented and numbered
# lines and further notes, and ends at the first other line.
REVISION_START = re.compile(r"^\s*(?:本次)?修订(?:说明|记录|历史)|^\s*Revision(?:s| notes?)?\s*[:：(（]", re.I)
REVISION_CONT = re.compile(r"^(?:\s|\u3000|$)|^(?:[一二三四五六七八九十]+、|\d+[.、)）]|[（(]\d+[)）]|[-*·] )")


def revision_ranges(spec):
    """[(first, last)] 1-based line ranges of the spec's revision notes."""
    lines, out, i = spec.split("\n"), [], 0
    while i < len(lines):
        if REVISION_START.match(lines[i]) and not title_letter(lines[i]):
            j = i + 1
            while j < len(lines) and not title_letter(lines[j]) and not lines[j].startswith("#") and (
                    REVISION_START.match(lines[j]) or REVISION_CONT.match(lines[j])):
                j += 1
            while j - 1 > i and not lines[j - 1].strip():
                j -= 1  # trailing blank lines stay in the text
            out.append((i + 1, j))
            i = j
        else:
            i += 1
    return out


def spec_brief(spec, with_revisions=False):
    """The spec text for intake: revision notes replaced by one line naming their range, and a closing
    line on which tables were found by their titles."""
    lines = spec.split("\n")
    skip = [] if with_revisions else revision_ranges(spec)
    out, k = [], 0
    for i, line in enumerate(lines, 1):
        if k < len(skip) and skip[k][0] <= i <= skip[k][1]:
            if i == skip[k][0]:
                a, b = skip[k]
                out.append(f"[revision notes, lines {a}-{b} ({b - a + 1} lines), left out: read them for topic expansion]")
            if i == skip[k][1]:
                k += 1
            continue
        out.append(line)
    found = [x for x in "ABCDEF" if spec_section(spec, x) is not None]
    missing = [x for x in "ABCDEF" if x not in found]
    out.append(f"[tables found by title: {', '.join(found) or 'none'}"
               + (f"; not found: {', '.join(missing)}" if missing else "") + "]")
    return "\n".join(out), skip


def term_pairs(spec):
    """[(original wording, standard wording)] of Table B, or None when there is no Table B."""
    t = spec_table(spec, "B")
    if t is None:
        return None
    return [(r[0], r[1] if len(r) > 1 else "") for r in t[1] if r and r[0]]


# Cell values that mean "none" (an alias column filled with them lists no alias); one character is never an alias.
PLACEHOLDERS = {"无", "暂无", "空", "none", "n/a", "na", "-", "--", "—", "——", "/", "／"}


def entity_list(spec):
    """[(name, [aliases])] of Table E, or None when there is no Table E."""
    t = spec_table(spec, "E")
    if t is None:
        return None
    header, rows = t
    col = next((k for k, h in enumerate(header) if h.casefold() in ("aliases", "alias", "别名", "别称")), 2)
    brackets = "([（【「《\"“)]）】」》\"”"
    out = []
    for r in rows:
        if r and r[0]:
            aliases = [x.strip().strip(brackets).strip() for x in re.split(r"[;；]", r[col] if col < len(r) else "")]
            out.append((r[0], [a for a in aliases if len(a) >= 2 and a.casefold() not in PLACEHOLDERS]))
    return out


# ---------- class-A data (sensitivity.enabled) ----------
# Mechanical safety net for what must be masked before anything is written or committed: ID numbers
# with a valid check digit, card-like numbers, 16 to 19 digits in a row, numbers written in groups of
# four, and a password or one-time code written after its label without asterisks. A hit is a place
# to look at, not proof: an order number can look like a card number.

ID18_RE = re.compile(r"(?<![0-9A-Za-z])([1-9]\d{5}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx])"
                     r"(?![0-9A-Za-z])")
LONG_RE = re.compile(r"(?<![0-9A-Za-z])(\d{16,19})(?![0-9A-Za-z])")
GROUPED_RE = re.compile(r"(?<![0-9A-Za-z-])(\d{4}(?:[ -]\d{4}){3,4}(?:[ -]\d{1,3})?)(?![0-9A-Za-z])")
SECRET_RE = re.compile(r"(密码|口令|验证码|校验码|动态码|password|passcode|passwd|pin|one-time code|otp|"
                       r"verification code)\s*[:：=]\s*([^\s，,；;。]+)", re.I)
ID_WEIGHTS = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)


def id_check_ok(s):
    total = sum(int(c) * w for c, w in zip(s[:17], ID_WEIGHTS))
    return "10X98765432"[total % 11] == s[17].upper()


def luhn_ok(digits):
    total = 0
    for i, c in enumerate(reversed(digits)):
        d = int(c)
        if i % 2:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def shown(value, keep=4):
    """A hit as it may appear in a reply: everything but the last characters starred."""
    v = re.sub(r"[ -]", "", value)
    return "*" * max(len(v) - keep, 0) + v[-keep:]


def scan_class_a(text, keep=4):
    """[(line number, kind, starred value)] for every class-A candidate in text."""
    hits = []
    for no, line in enumerate(text.split("\n"), 1):
        seen = set()
        for m in ID18_RE.finditer(line):
            if id_check_ok(m.group(1)):
                hits.append((no, "ID number", shown(m.group(1), keep)))
                seen.add(m.span(1))
        for m in LONG_RE.finditer(line):
            if any(a <= m.start(1) < b for a, b in seen):
                continue
            kind = "card number" if luhn_ok(m.group(1)) else "16-19 digits (order or serial number?)"
            hits.append((no, kind, shown(m.group(1), keep)))
        for m in GROUPED_RE.finditer(line):
            hits.append((no, "number in groups of four", shown(m.group(1), keep)))
        for m in SECRET_RE.finditer(line):
            value = m.group(2)
            if "*" not in value and any(c.isalnum() for c in value):
                hits.append((no, f"{m.group(1)} not masked", shown(value, min(keep, 2))))
    return hits


def scan_files(paths, keep=4):
    """[(path, line number, kind, starred value)] over files read as UTF-8."""
    out = []
    for p in paths:
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as e:
            raise ConfigError(f"cannot read {p}: {e}")
        out += [(p, no, kind, v) for no, kind, v in scan_class_a(text, keep)]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    add_log_args(ap)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("registry"); p.add_argument("--path")
    for c in ("show", "names", "validate"):
        p = sub.add_parser(c); p.add_argument("library")
    p = sub.add_parser("limits"); p.add_argument("--language", required=True)
    p = sub.add_parser("scan-a"); p.add_argument("files", nargs="+")
    p.add_argument("--keep-last", type=int, default=4)
    p = sub.add_parser("spec"); p.add_argument("library")
    p.add_argument("--with-revisions", action="store_true", help="keep the revision notes in")
    a = ap.parse_args()
    setup_logging(a.log_level)
    try:
        if a.cmd == "scan-a":
            hits = scan_files(a.files, a.keep_last)
            for p, no, kind, v in hits:
                print(f"{p}:{no}: {kind}: {v}")
            print(f"result: {len(hits)} class-A candidates" if hits else "result: no class-A candidates")
            if hits:
                sys.exit(3)
        elif a.cmd == "registry":
            reg = load_registry(a.path)
            print(json.dumps(reg, ensure_ascii=False, indent=2))
        elif a.cmd == "show":
            print(json.dumps(load_library(a.library), ensure_ascii=False, indent=2))
        elif a.cmd == "names":
            for k, v in load_library(a.library)["names"].items():
                print(f"{k}: {v}")
        elif a.cmd == "limits":
            h, f = default_limits(a.language)
            print(f"heading: {h}\nfilename: {f}")
        elif a.cmd == "spec":
            cfg = load_library(a.library)
            path = os.path.join(os.path.dirname(cfg["_path"]), cfg["names"]["spec"])
            try:
                with open(path, encoding="utf-8") as f:
                    spec = f.read().replace("\r\n", "\n")
            except (OSError, UnicodeDecodeError) as e:
                raise ConfigError(f"cannot read the spec {path}: {e}")
            text, skip = spec_brief(spec, a.with_revisions)
            log.info("spec %s: %d chars, %d revision note range(s) left out, %d chars printed",
                     path, len(spec), len(skip), len(text))
            print(text)
        elif a.cmd == "validate":
            p = find_kb_json(a.library)
            problems = validate(load_json(p))
            for msg in problems:
                print(f"problem: {msg}")
            print("result: " + ("failed" if problems else "ok"))
            if problems:
                sys.exit(3)
    except ConfigError as e:
        log.error("%s", e)
        print(f"error: {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()
