# Codex PR Review Gate

This repository requires a review gate for every implementation PR created by Codex.

## Required Workflow

1. Do implementation work on a `codex/...` branch.
2. Keep PRs as draft until checks and review are complete.
3. Run relevant local tests before publishing or updating a PR.
4. Run CodeRabbit before asking for merge:

   ```bash
   coderabbit review --agent --base main -c AGENTS.md
   ```

5. Address all critical and major CodeRabbit issues before marking a PR ready.
6. Summarize remaining minor issues or accepted risks in the PR.
7. Do not merge Codex-authored PRs automatically. The user or repository owner merges after review.

## Source Of Truth

Listing, rental, and safety claims in this project must follow the prototype spec in `student-rental-agent-prototype-spec.md`.

## Review Standards

- Do not invent listing facts.
- Do not bypass source access controls.
- Do not introduce user-facing safe/unsafe area claims.
- Preserve same-day freshness and needs-verification behavior.
- Keep the OpenAI-facing MVP tool surface small unless the spec is intentionally updated.
