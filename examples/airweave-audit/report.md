# PR Backlog Audit — airweave-ai/airweave

**Generated:** 2026-05-14
**Open PRs audited:** 79
**Open issues:** 51

## TL;DR

- **6** quick wins (batch-mergeable)
- **2** contested issues (multiple PRs solving the same thing)
- **22** AI-flagged concerns
- **47** stale PRs to close or revive

## 1. Quick wins — merge in batch this week (6)

| # | Title | Author | Size | CI | Tests | Age | AI score | Notes |
|---|---|---|---|---|---|---|---|---|
| [#1519](https://github.com/airweave-ai/airweave/pull/1519) | chore(deps): bump python from 3.13.12-slim to 3.14.0-slim in /backend… | dependabot[bot] | tiny | passing | — | 71d | 7 | Dependabot-generated patch is mechanically sound, but Python 3.14.0 is too new to merge without explicit compatibility testing and sign-off  |
| [#1741](https://github.com/airweave-ai/airweave/pull/1741) | chore(deps): bump node from 24.14.0-alpine to 24.15.0-alpine in /mcp … | dependabot[bot] | tiny | passing | — | 42d | 9 | Straightforward Dependabot Node.js patch bump with consistent pinned digests across Dockerfile stages; safe to merge following normal depend |
| [#1767](https://github.com/airweave-ai/airweave/pull/1767) | fix(teams): strip non-printable control characters from message body | octo-patch | small | passing | ✓ | 17d | 9 | High-quality fix that solves the Vespa ingestion failure by sanitizing control characters at entity creation time, with comprehensive unit t |
| [#1779](https://github.com/airweave-ai/airweave/pull/1779) | security: remove hardcoded encryption key and credentials from manual… | sebastiondev | small | passing | ✓ | 5d | 9 | Clean, well-tested security fix that removes hardcoded credentials from a manual dev script and replaces them with mandatory env var checks; |
| [#1784](https://github.com/airweave-ai/airweave/pull/1784) | fix(embedders): use /.well-known/ready instead of /health for local e… | awesome-pro | tiny | passing | ✓ | 1d | 9 | Well-scoped bug fix with correct endpoint replacement across all locations and matching test updates; minor code clarity improvement would b |

_…and 1 more in `pr_data.json`._

## 2. High-impact — review and merge this week (0)

_None._

## 3. Contested — pick one, close the others (2)

### Issue #1735

- **[#1758](https://github.com/airweave-ai/airweave/pull/1758)** by qflen (2026-04-20), CI passing, has tests, medium diff — AI: merge (8/10)
- **[#1783](https://github.com/airweave-ai/airweave/pull/1783)** by awesome-pro (2026-05-12), CI passing, no tests, small diff — AI: merge (8/10)

## 4. AI-flagged — review concerns before merging (22)

### [#1669](https://github.com/airweave-ai/airweave/pull/1669) — feat: add MiniMax as agentic search LLM provider

**AI summary:** Well-architected fallback LLM provider following repo patterns with solid test coverage; minor concerns about tokenizer approximation and local testing guidance do not block merge.

**Concerns:**
- API search rate-limited during review (unable to verify against past issues/discussions, but PR title/description appear self-contained)
- Tokenizer approximation (o200k_harmony for undocumented MiniMax tokenizer) could cause budget estimation drift; no fallback strategy documented if estimate is wrong
- Integration test skips silently without API key—no clear guidance in README on testing this provider locally
- Schema cleaning via _clean_schema_basic inherited from BaseLLM; no override if MiniMax has different JSON schema requirements
- Hardcoded temperature=0.3 in structured_output; no configurability (though consistent with other providers)
- Think-tag stripping uses regex with DOTALL flag; edge case if response contains literal `</think>` outside actual tags unlikely but not impossible

**Smell flags:** `hardcoded_secret:1, disabled_test:1`

**Recommendation:** merge

### [#1627](https://github.com/airweave-ai/airweave/pull/1627) — feat(embedders): Gemini Embedding 2 multimodal — native PDF, image, audio, video

**AI summary:** High-quality feature with excellent architecture, documentation, and configurability, but diff truncation obscures ~40% of the implementation (embedder class, error handling, converters, tests)—maintainer must verify full code before merge.

**Concerns:**
- PR description truncated in diff (marked `...[truncated]...`); cannot verify full implementation of GeminiDenseEmbedder class, error handling, or test coverage
- MediaChunker, video OCR deduplication, transcription backends, and file converters not visible in diff—cannot assess correctness or test quality for those critical paths
- Offline character-based tokenization heuristic (~4 chars/token for 40K char limit) is conservative but unvalidated; Gemini may reject inputs sooner or accept more
- Temporary keyframe JPEG cleanup relies on `finally` blocks; abnormal process termination could orphan files in system temp directory
- Scene detection threshold (0.3) and deduplication threshold (0.8) are hardcoded magic numbers presented as empirical but not parameterized or tested against diverse video types
- No visible integration tests for end-to-end embedding → Vespa storage → hybrid search workflows

**Smell flags:** `disabled_test:3, very_long_line:8`

**Recommendation:** needs_changes

### [#1600](https://github.com/airweave-ai/airweave/pull/1600) — feat: Enhance GitHub repository name handling

**AI summary:** Solid feature with good UX improvements, but needs test coverage for config validators and tighter validation after normalization to match repo's quality standards.

**Concerns:**
- No test coverage added despite config validation being critical infrastructure; repo patterns show unit tests exist for similar validators
- Validator order: `normalize_repo_name` (mode='before') runs first, then `validate_repo_name` runs second—this works but is implicit coupling between two validators
- Removed inline comments ('Split by commas...', 'Accept both YYYY/MM/DD...') without replacement; reduced documentation for other validators
- Type ignore comments (`# type: ignore[no-any-return]`) suggest the return type annotation may not match actual behavior—worth reviewing if these are legitimate or indicate a deeper type issue
- Frontend validation removes trailing slashes but doesn't validate format after normalization—could accept invalid input like `https://github.com/invalid`
- No validation of owner/repo segments after normalization (e.g., no check that neither is empty after splitting)

**Recommendation:** needs_changes

### [#1580](https://github.com/airweave-ai/airweave/pull/1580) — feat: GitHub connector OAuth

**AI summary:** Well-structured credential unification and OAuth validation refactor that aligns with domain/adapter patterns, but requires clarification on SourceLifecycleService integration, migration impact, and test coverage before merging.

**Concerns:**
- Critical: `SourceLifecycleService.validate(source_name, token_string)` signature unclear—does it internally instantiate source and config? Diff doesn't show the implementation or its integration tests, making it hard to verify the token flows correctly through the lifecycle
- Missing test coverage for the new `source_lifecycle` injection in factory.py and its integration with OAuth callback flow
- Frontend auth method selection logic now harder to follow (nested ternaries in loop) vs. previous explicit checks; readability trade-off for ordering support not discussed
- No migration guide for external sources or plugins that may have directly instantiated `GitHubSource(personal_access_token=...)` or relied on that field name
- Monke broker's `access_token` → `token` normalization (line added) only runs if `token` is missing; unclear if this handles all provider-specific field mappings or could mask credential bugs
- VSCode launch.json adds `--reload-exclude` flags but doesn't explain why `local_storage` reload was problematic (performance? test pollution?)

**Smell flags:** `hardcoded_secret:6`

**Recommendation:** needs_discussion

### [#1544](https://github.com/airweave-ai/airweave/pull/1544) — feat: browse tree node selection with targeted sync

**AI summary:** Strong architectural alignment with repo conventions, but diff truncation prevents full verification of domain internals; credential leakage in manual test and missing async Factory pattern need fixing before merge.

**Concerns:**
- Diff truncated—cannot verify complete domain implementation (protocols, service.py, repository.py, types.py all missing from visible diff)
- No visible database migrations for NodeSelection model—how is schema being created?
- Manual test script uses hardcoded credentials (AD_PASSWORD, SP passwords) in source control—security risk
- BrowseTreeServiceProtocol dependency injection in container.py but no visible protocol definition or concrete implementation in diff
- Frontend SupportsBrowseTree flag added to Store and Source but no visible API endpoint documenting how sources declare this capability
- No error handling visible for lazy-loaded tree nodes or timeout scenarios

**Smell flags:** `debug_print:59`

**Recommendation:** needs_changes

## 5. Stale — close or revive (47)

| # | Title | Author | Size | CI | Tests | Age | AI score | Notes |
|---|---|---|---|---|---|---|---|---|
| [#1441](https://github.com/airweave-ai/airweave/pull/1441) | [code blue] cursor rules v1 | felixschmetz | medium | passing | — | 83d | 8 | This is a high-quality, actionable refactoring guide that accurately codifies the Code Blue architecture already visible in the repo's conve |
| [#1408](https://github.com/airweave-ai/airweave/pull/1408) | feat: add Google Document AI OCR adapter  | felixschmetz | medium | passing | ✓ | 91d | 8 | Strong architectural fit with solid fallback tests, but GoogleDocumentAIOcrAdapter lacks unit tests and auth/wiring documentation; needs cla |
| [#1406](https://github.com/airweave-ai/airweave/pull/1406) | fix(search): skip non-filterable source fields in query interpretation | marc-rutzou | small | failing | — | 91d | 8 | Solid defensive fix that solves the Vespa 500 error by whitelisting filterable fields and updating the LLM prompt; clean implementation with |
| [#1262](https://github.com/airweave-ai/airweave/pull/1262) | feat(sync): add collection-level deduplication with per-sync entity r… | orhanrauf | large | failing | ✓ | 121d | 7 | Solid feature implementation with good handler tests and clear intent, but lacks tests for the core resolver logic, has test fixture duplica |
| [#1199](https://github.com/airweave-ai/airweave/pull/1199) | feat(app): New TanStack frontend app with component library | AnandChowdhary | xlarge | failing | ✓ | 132d | 5 | Large, feature-rich frontend v2 PR lacks a viewable diff and raises architectural/security questions; maintainer should request the actual d |

_…and 42 more in `pr_data.json`._

## 6. Risky — large diffs, missing tests, or failing CI (0)

_None._

## Patterns observed

- 8 dependabot PRs in queue. Consider enabling auto-merge for dependency groups.
- 30 PRs from first-time contributors. Worth a fast first-touch reply to keep them engaged.
- 12 mid/large PRs land without tests. Worth flagging in CONTRIBUTING.md.
- 43 PRs have failing CI. These won't merge until fixed.

---

## Methodology

This audit was generated by `pr-audit`, an open-source tool that ranks open PRs 
via heuristics (CI status, diff size, test inclusion, linked issues, competing PRs, 
staleness) and LLM-assisted code review.

- Read-only: only fetches public data via the GitHub API.
- Does not run tests; reads the maintainer's own CI status.
- LLM reviews are heuristic. Maintainer judgment is the final word.
