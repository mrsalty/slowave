# Post-Install Setup: Reducing Installation Friction

> **Source:** Design discussion — June 2026.
> **Status:** Pending implementation.
> **Key constraint:** Must not fight pip/PEP 517 packaging model; all changes additive and idempotent.

---

## Context

Currently users must manually run `slowave setup` after installing the package. The question was whether setup could be triggered automatically as part of installation to eliminate that friction.

---

## Feasibility by install channel

| Install method | Post-install hook | Notes |
|---|---|---|
| `pip install` / `pipx install` | ❌ None (PEP 517/518) | `setup.py install` deprecated and ignored by modern pip |
| Homebrew `brew install` | ✅ `post_install` DSL | Runs after bottle link; binaries already in PATH |
| `conda install` | ✅ `post-link` scripts | Shell script runs after linking |
| OS packages (`.deb`, `.rpm`) | ✅ `postinst` / `%post` | Standard package manager hooks |
| `pip install -e .` (dev/source) | ❌ Same as pip | No hook |

**Verdict:** For pip/pipx — the primary distribution channel — there is no sanctioned post-install hook in the modern packaging ecosystem. Any workaround (patching entry-point wrappers, `sitecustomize.py`, `__init__.py` abuse) is fragile and violates the principle of least surprise.

---

## Recommended approach: two complementary mechanisms

### 1. `--yes` / `-y` flag on `setup_cmd`

A non-interactive flag that skips the confirmation prompt. Small, safe, and purely additive.

```
slowave setup --yes
```

Unlocks:
- Homebrew `post_install` block (see below)
- Conda `post-link` scripts
- CI/CD pipelines and provisioning scripts
- Any future automated install path

### 2. Homebrew `post_install` block

Add to `Formula/slowave.rb`:

```ruby
def post_install
  system bin/"slowave", "setup", "--yes"
rescue => e
  opoo "Slowave post-install setup failed: #{e}. Run `slowave setup` manually."
end
```

This is idiomatic Homebrew — used by `git-lfs`, `gh`, `mas`, and others. The worker service install inside setup should be a soft failure (warn, don't abort) since `launchctl`/`systemctl` may behave differently in Homebrew's install environment on some CI machines.

### 3. First-run detection for pip/pipx users

On the first invocation of any `slowave` subcommand (excluding `setup` itself), detect that setup hasn't run and prompt inline:

```
⚡ Slowave is not configured yet. Set up now? [Y/n]
```

If yes → run setup. If no → print `Run 'slowave setup' when ready.` and continue.

This is the established pattern for CLI tools requiring a one-time post-install step (`gh auth login`, `aws configure`, `heroku login`, etc.). Detection is based on a sentinel file written by `setup` on successful completion (`~/.slowave/.setup_done`).

---

## Implementation plan

### Phase 1 — `--yes` flag + sentinel file (foundation, ~1h)

1. Add `--yes` / `-y` `auto_yes` flag to `setup_cmd` in `slowave/cli/setup.py` — skip confirmation when set.
2. Add `_setup_sentinel_path()`, `is_setup_done()`, `mark_setup_done()` helpers to `slowave/cli/setup.py`.
3. Call `mark_setup_done()` at the end of `setup_cmd` when `not dry_run`.

### Phase 2 — Homebrew formula update (~15min)

4. Add `post_install` block to `Formula/slowave.rb` calling `system bin/"slowave", "setup", "--yes"` wrapped in a `rescue` that `opoo`s on failure (never hard-abort a brew install).

### Phase 3 — First-run detection for pip/pipx (~1h)

5. In `slowave/cli/main.py`, add a `_maybe_prompt_setup()` helper that:
   - Returns immediately if `is_setup_done()` is true.
   - Returns immediately if the current subcommand is `setup`, `doctor`, or `--help`.
   - Prints a one-line notice and prompts `[Y/n]`.
   - If confirmed, invokes `setup_cmd` programmatically (via `click`'s `standalone_mode=False`).
6. Call `_maybe_prompt_setup()` at the top of the `cli` group callback.

---

## Non-goals

- Shipping a separate `install.sh` curl-pipe script — antipattern, breaks reproducibility, security red flag.
- Patching pip entry-point wrappers or `sitecustomize.py` — fragile, not sanctioned.
- Blocking / hard-failing the worker service install during Homebrew's `post_install` — must be a soft warn.

---

## Files to change

| File | Change |
|---|---|
| `slowave/cli/setup.py` | Add `--yes` flag, sentinel helpers, `mark_setup_done()` call |
| `slowave/cli/main.py` | Add `_maybe_prompt_setup()` first-run detection |
| `Formula/slowave.rb` | Add `post_install` block |
