# Release process

Slowave uses [Release Please](https://github.com/googleapis/release-please) to
prepare releases from `main`.

## Day-to-day workflow

1. Merge normal PRs into `main` with Conventional Commit PR titles, for example:

   ```text
   fix: default CLI to local DB
   feat: add local dashboard
   docs: update agent setup guide
   chore: update CI
   ```

2. The **Release Please** workflow opens or updates a release PR.
3. When you are ready to publish, merge the release PR.
4. Release Please updates `pyproject.toml`, `.release-please-manifest.json`, and
   `CHANGELOG.md`, creates the `vX.Y.Z` tag, creates the GitHub release, builds
   the Python package, and attaches the artifacts to the release.

The existing tag-triggered `.github/workflows/release.yml` remains available for
manually pushed `v*` tags.

Release Please is bootstrapped from the `v0.1.2` release commit, so its first
generated release PR only considers commits after `0.1.2`.

## Version bump rules

Release Please derives the next version from Conventional Commits:

| Commit type | Meaning | Bump while `0.x` |
|---|---|---|
| `fix:` | Bug fix / small user-visible correction | patch |
| `feat:` | New user-visible capability | patch, by current config |
| `feat!:` or `BREAKING CHANGE:` | Breaking change | minor |
| `docs:`, `test:`, `ci:`, `chore:` | Maintenance only | no release by default |

The current config sets:

```json
"bump-minor-pre-major": true,
"bump-patch-for-minor-pre-major": true
```

This keeps pre-`1.0` releases conservative: features become patch bumps and
breaking changes become minor bumps. After `1.0.0`, standard SemVer applies:
`fix:` = patch, `feat:` = minor, breaking changes = major.

## Important GitHub Actions note

Release Please uses `GITHUB_TOKEN` by default. GitHub does not trigger other
workflows from tags created by `GITHUB_TOKEN`, so the Release Please workflow
builds and uploads release artifacts itself.

If you later want Release Please-created tags to trigger separate workflows,
create a fine-grained PAT secret and pass it to the action as `token:`.

## PyPI publishing

PyPI publishing is not enabled yet. When ready, prefer PyPI Trusted Publishing:

1. Register/configure the `slowave` project on PyPI.
2. Add a PyPI trusted publisher for this repository and workflow.
3. Add a publish job gated by `steps.release.outputs.release_created`.