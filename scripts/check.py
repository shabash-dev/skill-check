#!/usr/bin/env python3
"""Look through the skills, commands, agents, hooks and plugins Claude Code or Codex will load, for lines worth a
human look before you trust them: commands that run by themselves, text you can't see, instructions to send data
somewhere or to hide things from you.

  check.py [--project DIR] [--codex] [--all]

It reads files only. It never runs anything it finds, changes nothing and makes no network calls. Places it reads:
~/.claude/skills, commands, agents and installed plugins (~/.claude/plugins/cache), the hooks and MCP servers in
~/.claude/settings.json, and the same in the project folder (.claude/, .mcp.json). With --codex: ~/.codex/skills,
~/.codex/plugins and ~/.codex/hooks.json. It skips its own folder, and files over 500 KB. It prints file, line and
the reason for each finding, with anything that looks like a key blanked out; --all also lists every hook command
and MCP server, flagged or not.
"""
import argparse, glob, json, os, re

HOME = os.path.expanduser("~")
TEXT = (".md", ".json", ".sh", ".py", ".js", ".ts", ".mjs", ".yaml", ".yml", ".toml", ".txt")
MAX_BYTES = 500_000

# (reason, pattern). Each is a reason to read the line yourself, not proof of harm.
CHECKS = [
    ("runs a shell command the moment the skill is used (a `!` command)", re.compile(r"!`[^`]+`|^\s*```!")),
    ("sends data out with curl or wget", re.compile(r"\b(curl|wget)\b[^\n]*(\s-d\b|--data|-F\b|--form|-T\b|--upload|-X\s*(POST|PUT))", re.I)),
    ("downloads a script and runs it", re.compile(r"\b(curl|wget)\b[^\n]*\|\s*(ba|z)?sh\b|\bbash\s*<\s*\(\s*curl", re.I)),
    ("decodes hidden text and runs it", re.compile(r"base64\s+(-d|--decode)[^\n]*\|\s*(ba|z)?sh|\beval\s*\(?\s*(atob|base64)", re.I)),
    ("touches keys or passwords (.env, SSH, cloud credentials, keychain)",
     re.compile(r"((?<!\w)\.env\b(?!\.example)|~/\.ssh|id_rsa|id_ed25519|\.aws/credentials|\.npmrc|\.netrc|"
                r"security\s+find-(generic|internet)-password|gcloud/credentials|\.kube/config)", re.I)),
    ("reads secret environment variables", re.compile(r"\b(printenv|env\s*\|)|\$\{?[A-Z_]*(TOKEN|SECRET|API_KEY|PASSWORD)\b")),
    ("reads or sends your Claude Code transcripts", re.compile(r"transcript_path|\.claude/projects|history\.jsonl", re.I)),
    ("tells the agent to hide something from you",
     re.compile(r"(don'?t|do not|never)\s+(tell|mention|show|inform|reveal)[^\n]{0,40}\b(user|human|them)\b|"
                r"without (telling|asking|notifying) the user|silently (send|upload|run|execute|delete|install|push|post)|ignore (all |any )?(previous|prior|above) instructions", re.I)),
    ("pushes code or adds a git remote", re.compile(r"git\s+remote\s+add|git\s+push\s+\S+\s+--all|git\s+push\s+--mirror", re.I)),
]
UNPINNED = re.compile(r"\b(npx|bunx|uvx|pipx\s+run)\s+(?:-y\s+|--yes\s+)?([@\w][\w@./-]*)")


def unpinned(line):
    """Packages run with no fixed version: what runs can change after you've checked it."""
    return [m.group(2) for m in UNPINNED.finditer(line) if not re.search(r"@\d|==\d", m.group(2))]
INVISIBLE = re.compile("[​-‏‪-‮⁠-⁤⁦-⁩﻿\U000e0000-\U000e007f]")
COMMENT = re.compile(r"<!--(.{0,4000}?)-->", re.S)  # bounded, so an unclosed comment can't make the scan slow
ACTION = re.compile(r"https?://|\b(run|curl|wget|send|upload|post|push|execute|install|ignore|always|never|must|"
                    r"do not|don't|instead|secret|key|token|password|\.env)\b", re.I)
BLOB = re.compile(r"[A-Za-z0-9+/=]{300,}")


SECRET = re.compile(r"((?:bearer|basic)\s+|--(?:token|api-key|apikey|password|secret)[=\s]+|[?&](?:key|token|access_token|api_key|sig)=|"
                    r"://[^\s/:@]+:)[^\s\"'&@,]{4,}|(sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_\w{20,}|AKIA[0-9A-Z]{16}|xox[abposr]-[\w-]{10,}|"
                    r"AIza[\w-]{30,}|eyJ[\w-]{20,}\.[\w-]{10,}|\b[0-9a-f]{32,}\b|"
                    r"((token|secret|password|api[_-]?key|authorization)[\"']?\s*[:=]\s*[\"']?(?:bearer\s+|basic\s+)?)[^\s\"',]{6,})", re.I)
CONFIG = ("settings.json", "settings.local.json", ".mcp.json", "hooks.json")


def redact(s):
    """The line with anything that looks like a key or password blanked out, so it never reaches the chat."""
    return SECRET.sub(lambda m: (m.group(1) or m.group(3) or "") + "[hidden]", s)


SELF = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))  # this plugin: its own patterns would flag it


def files_under(root):
    for d, dirs, names in os.walk(root):
        dirs[:] = [x for x in dirs if os.path.realpath(os.path.join(d, x)) != SELF]
        for n in names:
            if n.endswith(TEXT):
                yield os.path.join(d, n)


def places(project, codex):
    """(label, folder or file) for everything the agent loads that this looks at."""
    claude = os.path.join(HOME, ".claude")
    out = [("your skills", os.path.join(claude, "skills")), ("your commands", os.path.join(claude, "commands")),
           ("your agents", os.path.join(claude, "agents")), ("installed plugins", os.path.join(claude, "plugins", "cache")),
           ("your Claude Code settings", os.path.join(claude, "settings.json"))]
    if project:
        p = os.path.abspath(project)
        out += [("this project's skills", os.path.join(p, ".claude", "skills")),
                ("this project's commands", os.path.join(p, ".claude", "commands")),
                ("this project's agents", os.path.join(p, ".claude", "agents")),
                ("this project's settings", os.path.join(p, ".claude", "settings.json")),
                ("this project's MCP servers", os.path.join(p, ".mcp.json"))]
    if codex:
        cx = os.path.join(HOME, ".codex")
        out += [("Codex skills", os.path.join(cx, "skills")), ("Codex plugins", os.path.join(cx, "plugins")),
                ("Codex hooks", os.path.join(cx, "hooks.json"))]
    seen, kept = set(), []
    for label, path in out:
        real = os.path.realpath(path)
        if os.path.exists(path) and real not in seen:
            seen.add(real)
            kept.append((label, path))
    return kept


def scan_text(path, text):
    """[(line number, reason, the line)] for one file."""
    found = []
    for m in COMMENT.finditer(text):
        body = " ".join(m.group(1).split())
        if body and path.endswith(".md") and ACTION.search(body):
            found.append((text.count("\n", 0, m.start()) + 1, "hidden HTML comment with an instruction or link: GitHub doesn't show it, the agent reads it", body))
    for i, line in enumerate(text.lstrip("\ufeff").splitlines(), 1):  # a byte-order mark at the start is normal
        if INVISIBLE.search(line):
            found.append((i, "invisible characters: text you can't see on screen", INVISIBLE.sub("�", line)))
        if BLOB.search(line):
            found.append((i, "a long encoded blob: you can't read what it says", line))
        for reason, rx in CHECKS:
            if rx.search(line):
                found.append((i, reason, line))
        if unpinned(line):
            found.append((i, "runs a package with no fixed version: what runs can change after you've checked it", line))
    return found


def hooks_and_servers(path):
    """[(what, command)] for every hook and MCP server a JSON settings or plugin file declares."""
    try:
        with open(path) as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    out = []
    hooks = data.get("hooks") if isinstance(data.get("hooks"), dict) else {}
    for event, groups in hooks.items():
        for g in groups if isinstance(groups, list) else []:
            for h in (g.get("hooks") if isinstance(g, dict) else None) or []:
                if isinstance(h, dict):
                    out.append((f"hook on {event}, runs by itself", h.get("command") or h.get("url") or json.dumps(h)))
    servers = data.get("mcpServers") if isinstance(data.get("mcpServers"), dict) else {}
    for name, s in servers.items():
        if isinstance(s, dict):
            args = [str(a) for a in s.get("args") or [] if isinstance(s.get("args"), list)]
            out.append((f"MCP server {name}", " ".join([str(s.get("command") or s.get("url") or "")] + args)))
    return out


def cut(s, n=200):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[:n - 1] + "…"


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument("--project", default=os.getcwd(), help="project folder to include (default: here)")
    ap.add_argument("--codex", action="store_true")
    ap.add_argument("--all", action="store_true", help="list every hook and MCP server")
    a = ap.parse_args()
    where, total_files, flagged = places(a.project, a.codex), 0, 0
    if not where:
        return print("Found no skills, commands, agents, plugins or hook settings to check.")
    for label, path in where:
        paths = [path] if os.path.isfile(path) else sorted(files_under(path))
        lines = []
        for f in paths:
            try:
                if os.path.getsize(f) > MAX_BYTES:
                    lines.append(f"- {f}: over {MAX_BYTES // 1000} KB, not read")
                    continue
                with open(f, errors="ignore") as fh:
                    text = fh.read()
            except OSError:
                continue
            total_files += 1
            config = os.path.basename(f) in CONFIG
            hits = [] if config else scan_text(f, text)  # settings files can hold keys: only their hooks and servers are read
            if f.endswith(".json"):
                for what, cmd in hooks_and_servers(f):
                    risky = [r for r, rx in CHECKS if rx.search(cmd)] + (["no fixed version"] if unpinned(cmd) else [])
                    if risky or a.all:
                        hits.append((0, what + (": " + "; ".join(risky) if risky else ""), cmd))
            flagged += bool(hits)
            by_line = {}
            for n, reason, line in hits:
                by_line.setdefault((n, line), []).append(reason)
            for (n, line), reasons in sorted(by_line.items(), key=lambda kv: kv[0][0]):
                lines.append(f"- {f}" + (f":{n}" if n else "") + f"\n  why: {'; '.join(reasons)}\n  line: {cut(redact(line))}")
        print(f"## {label} ({path}): {len(paths)} files" + ("" if lines else ", nothing flagged"))
        for l in lines:
            print(l)
        print()
    print(f"Checked {total_files} files; {flagged} have something worth reading yourself.")


if __name__ == "__main__":
    main()
