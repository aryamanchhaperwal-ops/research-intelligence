# AGENTS.md

Instructions for AI coding assistants working in this repository.

## Workflow

- When asked to create a research project, use the template at `templates/research-project/`. Either copy it manually or run `scripts/New-ResearchProject.ps1` (PowerShell) which does the copy and fills in metadata.
- Use `.md` (Markdown) for all text content. Keep files plain-text friendly.
- Prefer writing files over creating ad-hoc commands that modify file contents.

## Conventions

- Keep all project files inside the project folder. Do not create files at the repository root unless they describe the workspace itself.
- Project folders live under `projects/<domain>/<topic-slug>/`.
- Domain folders: `technology`, `society`, `environment`, `esg`, `culture`, `business`, plus `other` if a topic has no clear domain.
- Do not add code comments; commit to readable, self-documenting content.
- Never add outside-source articles/videos to a project's `findings/` or `outputs/` folders — those are for original synthesis.

## Project template structure

A research project contains:

- `README.md` — metadata, status, key question.
- `PLAN.md` — research plan, questions, method, timeline.
- `SOURCES.md` — table of sources with claim + quality notes.
- `NOTES.md` — running notes and synthesis.
- `findings/` — intermediate findings, one file per finding (e.g., `01-title.md`).
- `outputs/` — the final deliverables (reports, slide decks, briefs).

## When to verify

- If you modify or create a PowerShell script, publish with `powershell.exe -NoProfile -File` syntax errors checked (e.g., `-WhatIf` support).
- After creating a structure, list the tree to confirm.