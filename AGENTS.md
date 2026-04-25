# Codex PR Review Gate

This repository requires a review gate for every implementation PR created by Codex.

## Required Workflow

1. Do implementation work on a `codex/...` branch.
2. Keep PRs as draft until checks and review are complete.
3. Run relevant local tests before publishing or updating a PR.
4. Run CodeRabbit before asking for merge:

   ```bash
   coderabbit review --agent --base main
   ```

5. Address all critical and major CodeRabbit issues before marking a PR ready.
6. Summarize remaining minor issues or accepted risks in the PR.
7. Fill in the PR template's validation and CodeRabbit findings sections.
8. If repository auto-merge is enabled, Codex may enable auto-merge after local checks pass, CodeRabbit raises no unresolved critical or major issues, and the PR review gate passes.
9. If repository auto-merge is unavailable, Codex may merge its own PR only after the same checks pass and the user has opted into this auto-merge workflow.

## Auto-Merge Preconditions

Codex-authored PRs are eligible for auto-merge only when all of these are true:

- The PR is not a draft.
- Relevant local tests or checks passed.
- `coderabbit review --agent --base main` completed successfully.
- All critical and major CodeRabbit issues are fixed.
- Any unresolved minor issues are documented in the PR body.
- The PR body satisfies the repository PR review gate.
- GitHub branch rules allow the merge.

Do not auto-merge if CodeRabbit fails, times out, cannot authenticate, or returns an unresolved critical or major issue.

## Source Of Truth

Listing, rental, and safety claims in this project must follow the prototype spec in `student-rental-agent-prototype-spec.md`.

## Review Standards

- Do not invent listing facts.
- Do not bypass source access controls.
- Do not introduce user-facing safe/unsafe area claims.
- Preserve same-day freshness and needs-verification behavior.
- Keep the OpenAI-facing MVP tool surface small unless the spec is intentionally updated.
