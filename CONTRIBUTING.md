# Contributing

Thanks for the interest — a few notes so your PR lands cleanly.

## Set up

```bash
git clone https://github.com/ethiack/ethibench
cd ethibench
poetry install
poetry run ethibench --help
```

Banner shows → you're good.

## What's useful

- **Bug fixes.** Include a repro. For matching-quality issues, attach the finding + GT pair that misbehaved so we can look at it directly.
- **New agent-report converters.** `ethibench convert-report` is a starting point. If your agent (Strix, PentAGI, CAI, home-grown) emits a stable output format, a small dedicated converter is welcome.
- **Ground truth for new targets.** If you've end-to-end annotated a public vulnerable app, open an issue first so we can align on scope and licensing before you sink work into the PR.
- **Better metrics / plots / analysis.** Same deal — non-trivial → issue first.

## Less useful

- Cosmetic refactors not tied to a real problem.
- New dependencies without a strong reason. The tool is small on purpose.
- Renames without a real cause.

## Commits drive releases

We run [semantic-release](https://github.com/semantic-release/semantic-release) on `main` with [Conventional Commits](https://www.conventionalcommits.org/). The commit subject decides both whether a release fires and how the version bumps:

| Prefix | Effect |
|---|---|
| `feat:` | minor bump |
| `fix:` | patch bump |
| `perf:`, `build:`, `revert:`, `docs:` | patch bump |
| `chore:`, `ci:`, `refactor:`, `style:`, `test:` | no release |
| `feat!:` or `BREAKING CHANGE:` in the body | major bump |

So `fix: handle empty findings.jsonl` merged to `main` = a new PyPI release about two minutes later. That's intentional — nothing sits half-done in a "next" branch.

## Pull requests

- Branch off `main`, target `main`.
- One thing per PR. Two things = two PRs.
- Update the README if you change user-visible behavior.
- CI runs `poetry build` and checks the README is bundled in the wheel. There's no test suite yet — don't add one just to add one, but a targeted test for a specific bug fix is welcome.

## Questions

Open an issue. For methodology questions (why bipartite matching, why F0.5, sample-size choices, etc.), the paper has the answers: [arXiv:2605.10834](https://arxiv.org/abs/2605.10834).
