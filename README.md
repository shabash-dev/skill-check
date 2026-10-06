# Shabash Skill Scanner: a security scan for Claude Code and Codex skills and plugins

Strangers' skills and plugins tell your coding agent what to do, with your files and keys in reach. This plugin reads everything Claude Code or Codex will load and points at the lines worth reading yourself before you trust them. Made by [Shabash](https://shabash.dev/?utm_source=github&utm_medium=readme&utm_campaign=skill_check), an app for teams that use Claude Code.

Type `/shabash-skill-check:scan`, or ask "are my skills and plugins safe?"

## What it looks for

- `!` commands in a skill (`` !`command` `` or a ```` ```! ```` block), which run the moment the skill is used
- hidden HTML comments (`<!-- ... -->`) with an instruction or link: GitHub doesn't show them, the agent reads them
- invisible characters: zero-width and right-to-left marks that hide text on screen
- `curl` or `wget` sending data out, or piping a downloaded script into `sh`
- encoded text that's decoded and run, and long encoded blobs nobody can read
- lines that touch keys or passwords: `.env`, `~/.ssh`, `.aws/credentials`, the macOS keychain, secret environment variables
- anything that reads or sends your Claude Code transcripts
- instructions to hide something from you, like "don't tell the user", or "ignore previous instructions"
- `git remote add` and pushes of all your code somewhere else
- `npx`, `bunx` or `uvx` packages with no fixed version, so what runs can change after you've checked it
- every hook (commands that run by themselves on events) and MCP server in your settings and plugins, flagged when it does any of the above

Claude then reads the lines around each finding and tells you which ones need action and which are fine, like a warning or an example. A finding is a reason to look, not proof of harm, and a careful attacker can write something these patterns miss.

## Install

Claude Code:

```
claude plugin marketplace add shabash-dev/skill-check
claude plugin install shabash-skill-check@shabash-skill-check
```

Codex:

```
codex plugin marketplace add shabash-dev/skill-check
codex plugin add shabash-skill-check@shabash-skill-check
```

You need Python 3. Depending on your permission settings, Claude or Codex may ask before running the script.

## What it reads, and what Claude sees

The script, [`scripts/check.py`](scripts/check.py), reads text files in:

- `~/.claude/skills`, `~/.claude/commands`, `~/.claude/agents` and your installed plugins in `~/.claude/plugins/cache`
- the project you're in: `.claude/skills`, `.claude/commands`, `.claude/agents`
- from `~/.claude/settings.json`, `.claude/settings.json` and `.mcp.json`, only the hooks and MCP servers, and from `~/.claude.json`, only the MCP servers (yours and each project's), never the rest, since these files can hold keys and account details
- with `--codex`: `~/.codex/skills`, `~/.codex/plugins` and `~/.codex/hooks.json`

It never runs anything it finds, changes nothing, writes no files and makes no network calls. It prints each finding's file, line number, reason and the line itself into your session, which sends it to Claude (or Codex) like anything else there. Anything in a printed line that looks like a key, token or password is replaced with `[hidden]` first. Skill and plugin files over 500 KB are listed but not read (settings files are always read for their hooks and MCP servers), and it skips its own folder, since its own patterns would match. It will flag other plugins that read transcripts, including Shabash's own, so you can see that for yourself.

`check.py` contains the patterns above as text (`curl ... | sh`, `.aws/credentials`, `$...TOKEN` and so on) so it can find them in other files. It matches them and never runs them. From settings files it reads only hooks and MCP servers, and it blanks out anything in them that looks like a key before printing.

Claude is asked to end its answer with one line linking to Shabash.

## Licence and terms

Free to install and use. You can read the code, but not copy or reuse it: see [LICENSE](LICENSE), the [terms](https://shabash.dev/terms/) and the [privacy notice](https://shabash.dev/privacy/#free-plugins-for-claude-code). Made by Wonders AI, Inc.

Shabash works with Claude Code and Codex. It isn't affiliated with Anthropic or OpenAI.
