# Changelog

## [0.7.0](https://github.com/mrsalty/slowave/compare/slowave-v0.6.0...slowave-v0.7.0) (2026-06-23)


### Features

* add daily SQLite backup with gzip compression and auto-rotation ([3c643e9](https://github.com/mrsalty/slowave/commit/3c643e97f5f03b5e9adaccb8c8370e63287be2dd))
* add daily SQLite backup with gzip compression and auto-rotation ([87d3ef6](https://github.com/mrsalty/slowave/commit/87d3ef68db033a411bc9715f1759b11d08a3ad28))
* **benchmark:** WikiScenarios harness (18 scenarios, 4 ablations) + supersession and encoder improvements ([4d296cb](https://github.com/mrsalty/slowave/commit/4d296cbd3bf42e64a027b7ca23c7bb6f7ceb5a39))
* **dashboard:** 3-channel EEG waveform — thin lines, multi-signal ([7061d58](https://github.com/mrsalty/slowave/commit/7061d58c0964e9993098aef9bc974206663ffbbb))
* **dashboard:** add brain pulse graph to overview ([bd42a03](https://github.com/mrsalty/slowave/commit/bd42a03e26326abd1796649a32c124e844f43dda))
* **dashboard:** EEG-style waveform pulse graph ([14e3625](https://github.com/mrsalty/slowave/commit/14e3625a660be7aa47905cb3b99c05971467afee))
* **dashboard:** pulse panel polish ([d27a300](https://github.com/mrsalty/slowave/commit/d27a300dc2927855654a7f32a4e3d145a3b2b9c3))
* HTTP MCP daemon transport — 2026-06-15 18:33:25 ([ea8ca5c](https://github.com/mrsalty/slowave/commit/ea8ca5ce7c539caf57471c3eeacd8522a7a50357))
* implement procedural memory v4 (Tier 2 enrichment + generalization) ([922e3bd](https://github.com/mrsalty/slowave/commit/922e3bd9eba4df3b1eb4eb62111a2fd3278fff56))
* migrate MCP transport to HTTP daemon ([1332e81](https://github.com/mrsalty/slowave/commit/1332e81d4adbfc61fecb6b5281018a740a2b7a65))
* prepare 0.5.0 public release ([18b414f](https://github.com/mrsalty/slowave/commit/18b414f3c970b5556990c6f2449b1e58a8d074a7))
* preserve backups during cleanup, add restore command ([80fd2e9](https://github.com/mrsalty/slowave/commit/80fd2e964867cfe225bd5840698f107bbfd7c29f))
* procedural memory consolidation ([1051c23](https://github.com/mrsalty/slowave/commit/1051c23e78ad824d844184bf867dd430cc0ed282))


### Bug Fixes

* Add missing pytest fixture to test_remember_result.py ([ccf69f3](https://github.com/mrsalty/slowave/commit/ccf69f396eecc9c5e7c42be647284ebef1022038))
* Cline TUI lifecycle — write to ~/.cline/rules/slowave.md not ~/.clinerules ([62b842c](https://github.com/mrsalty/slowave/commit/62b842cdee366b575deb1ae0dfa678bea4693407))
* correct backwards LoCoMo hot/cold comment and update uv.lock ([50dfe33](https://github.com/mrsalty/slowave/commit/50dfe3306ec82804c3d434c4257125de69f8dd97))
* critical bug in Tier 1 enforcement — embedding deserialization ([e873f12](https://github.com/mrsalty/slowave/commit/e873f12d7b6d5cdff27294e3dcc88e9fa0c489d3))
* dashboard — clean error on port conflict, O(1) parent-command lookup ([7753cfd](https://github.com/mrsalty/slowave/commit/7753cfd97dfc91e1f29161f33af8f2f482448a5c))
* **dashboard:** wire renderPulse into refresh loop so pulse graph updates on every poll cycle ([0ed0960](https://github.com/mrsalty/slowave/commit/0ed0960d8e40499994b9db09eeff2dad898260c6))
* MCP tool name mismatch — prefix all tools with slowave_ so Cline TUI can invoke them ([1279c7e](https://github.com/mrsalty/slowave/commit/1279c7eefeb619979100c0c3b8e2d888c20a6ca9))
* MCP tool name mismatch — prefix all tools with slowave_ so Cline… ([66b3a01](https://github.com/mrsalty/slowave/commit/66b3a01f21099965743abc7bca1f34c56e423780))
* replace hardcoded absolute path in test_encode_never_in_procedural with pathlib relative path ([ab68f1d](https://github.com/mrsalty/slowave/commit/ab68f1db5ef9b2dc92886befb49f7effdb3ed41f))
* resolve CI flakiness (Python version matrix, DB isolation, test determinism) ([c1a180d](https://github.com/mrsalty/slowave/commit/c1a180db37a9081540763d63b9e79f432b0c53e2))
* update cline lifecycle test paths to match new ~/.cline/rules/slowave.md location ([06a5e47](https://github.com/mrsalty/slowave/commit/06a5e4729c2f3a0454602e8146e68fc3b6a13cd4))
* use type=fact instead of type=constraint in strict_scope test ([1cd2360](https://github.com/mrsalty/slowave/commit/1cd2360465fb328712c06c0f656cffad761ab2c5))
* use type=fact instead of type=constraint in strict_scope test ([9a3d0cb](https://github.com/mrsalty/slowave/commit/9a3d0cbfd48329ab371a69326cfde62456cdad64))
* Windows compatibility — worker window, cleanup traceback, proces… ([72c0157](https://github.com/mrsalty/slowave/commit/72c0157fcf3e53d9c33af2f9d5cd063cf931ae46))
* Windows compatibility — worker window, cleanup traceback, process detection, Cline MCP, marker corruption ([951f9ee](https://github.com/mrsalty/slowave/commit/951f9eea558096cb2bdfcd6aaceb70d77e6fcfde))
* **windows:** Claude Desktop integration - .exe paths and stdio logging ([bd6b87a](https://github.com/mrsalty/slowave/commit/bd6b87a78fd11a00638ee0bf63745687b39e2f1f))


### Documentation

* add Homebrew install option to README ([a1f7600](https://github.com/mrsalty/slowave/commit/a1f760099533c6b6e9657b624e59782203b2013b))
* add PR [#7](https://github.com/mrsalty/slowave/issues/7) merge analysis and iteration log ([c745516](https://github.com/mrsalty/slowave/commit/c74551618c2e1117d3628c8c028b457de3838a8b))
* add SECURITY.md, fix Windows support caveat, link security policy from CONTRIBUTING ([6588bd4](https://github.com/mrsalty/slowave/commit/6588bd45303a29673b97187bbb5f10a9629d6325))
* pipx first in install section, drop macOS label from Homebrew ([b67e823](https://github.com/mrsalty/slowave/commit/b67e8231a6cdf439ca90e709d3fc7df9681c75fa))
* refine core messaging and architecture documentation ([c32f4ec](https://github.com/mrsalty/slowave/commit/c32f4ecaa8031a72da1ef6b365e2fcbc0683e5a6))
* streamline README for clarity and conciseness ([fc2cbe8](https://github.com/mrsalty/slowave/commit/fc2cbe8a4e28071cd2975a47cb98db01138ee1fd))

## [0.6.0b1](https://github.com/mrsalty/slowave/compare/slowave-v0.5.11...slowave-v0.6.0b1) (2026-06-23)


### Features

* first beta release — procedural memory v4 (Tier 1 enforcement + Tier 2 enrichment/generalization)
* supersession manifold (SVD1-based latent supersession direction)
* HTTP MCP daemon (streamable-HTTP transport, single-instance PID guard)
* local dashboard web UI (dependency-free, port 8765)
* daily SQLite backup with gzip compression and auto-rotation
* feedback system with brain-inspired numeric learning signals
* working-memory gating for token-budget-aware context
* session-idle reaper and per-scope implicit session resolver
* WikiScenarios: 18 ablation scenarios for systematic evaluation


### Bug Fixes

* critical bug in Tier 1 enforcement — embedding deserialization ([e873f12](https://github.com/mrsalty/slowave/commit/e873f12d7b6d5cdff27294e3dcc88e9fa0c489d3))
* **dashboard:** wire renderPulse into refresh loop ([0ed0960](https://github.com/mrsalty/slowave/commit/0ed0960d8e40499994b9db09eeff2dad898260c6))
* replace hardcoded absolute path in test with pathlib relative path ([ab68f1d](https://github.com/mrsalty/slowave/commit/ab68f1db5ef9b2dc92886befb49f7effdb3ed41f))
* correct backwards LoCoMo hot/cold comment and update uv.lock ([50dfe33](https://github.com/mrsalty/slowave/commit/50dfe3306ec82804c3d434c4257125de69f8dd97))


### Chores

* remove deprecated MCP tools: slowave_context, slowave_session_start/session_end/event, slowave_retrieval_feedback, slowave_context_feedback
* disable bump-patch-for-minor-pre-major in release-please so future feat commits correctly produce minor bumps

## [0.5.11](https://github.com/mrsalty/slowave/compare/slowave-v0.5.10...slowave-v0.5.11) (2026-06-23)


### Features

* implement procedural memory v4 (Tier 2 enrichment + generalization) ([922e3bd](https://github.com/mrsalty/slowave/commit/922e3bd9eba4df3b1eb4eb62111a2fd3278fff56))
* procedural memory consolidation ([1051c23](https://github.com/mrsalty/slowave/commit/1051c23e78ad824d844184bf867dd430cc0ed282))


### Bug Fixes

* correct backwards LoCoMo hot/cold comment and update uv.lock ([50dfe33](https://github.com/mrsalty/slowave/commit/50dfe3306ec82804c3d434c4257125de69f8dd97))
* critical bug in Tier 1 enforcement — embedding deserialization ([e873f12](https://github.com/mrsalty/slowave/commit/e873f12d7b6d5cdff27294e3dcc88e9fa0c489d3))
* **dashboard:** wire renderPulse into refresh loop so pulse graph updates on every poll cycle ([0ed0960](https://github.com/mrsalty/slowave/commit/0ed0960d8e40499994b9db09eeff2dad898260c6))
* replace hardcoded absolute path in test_encode_never_in_procedural with pathlib relative path ([ab68f1d](https://github.com/mrsalty/slowave/commit/ab68f1db5ef9b2dc92886befb49f7effdb3ed41f))

## [0.5.10](https://github.com/mrsalty/slowave/compare/slowave-v0.5.9...slowave-v0.5.10) (2026-06-21)


### Features

* add daily SQLite backup with gzip compression and auto-rotation ([3c643e9](https://github.com/mrsalty/slowave/commit/3c643e97f5f03b5e9adaccb8c8370e63287be2dd))
* add daily SQLite backup with gzip compression and auto-rotation ([87d3ef6](https://github.com/mrsalty/slowave/commit/87d3ef68db033a411bc9715f1759b11d08a3ad28))
* **dashboard:** 3-channel EEG waveform — thin lines, multi-signal ([7061d58](https://github.com/mrsalty/slowave/commit/7061d58c0964e9993098aef9bc974206663ffbbb))
* **dashboard:** add brain pulse graph to overview ([bd42a03](https://github.com/mrsalty/slowave/commit/bd42a03e26326abd1796649a32c124e844f43dda))
* **dashboard:** EEG-style waveform pulse graph ([14e3625](https://github.com/mrsalty/slowave/commit/14e3625a660be7aa47905cb3b99c05971467afee))
* **dashboard:** pulse panel polish ([d27a300](https://github.com/mrsalty/slowave/commit/d27a300dc2927855654a7f32a4e3d145a3b2b9c3))
* preserve backups during cleanup, add restore command ([80fd2e9](https://github.com/mrsalty/slowave/commit/80fd2e964867cfe225bd5840698f107bbfd7c29f))


### Bug Fixes

* resolve CI flakiness (Python version matrix, DB isolation, test determinism) ([c1a180d](https://github.com/mrsalty/slowave/commit/c1a180db37a9081540763d63b9e79f432b0c53e2))
* use type=fact instead of type=constraint in strict_scope test ([1cd2360](https://github.com/mrsalty/slowave/commit/1cd2360465fb328712c06c0f656cffad761ab2c5))
* use type=fact instead of type=constraint in strict_scope test ([9a3d0cb](https://github.com/mrsalty/slowave/commit/9a3d0cbfd48329ab371a69326cfde62456cdad64))


### Documentation

* add Homebrew install option to README ([a1f7600](https://github.com/mrsalty/slowave/commit/a1f760099533c6b6e9657b624e59782203b2013b))
* pipx first in install section, drop macOS label from Homebrew ([b67e823](https://github.com/mrsalty/slowave/commit/b67e8231a6cdf439ca90e709d3fc7df9681c75fa))

## [0.5.9](https://github.com/mrsalty/slowave/compare/slowave-v0.5.8...slowave-v0.5.9) (2026-06-20)


### Features

* **benchmark:** WikiScenarios harness (18 scenarios, 4 ablations) + supersession and encoder improvements ([4d296cb](https://github.com/mrsalty/slowave/commit/4d296cbd3bf42e64a027b7ca23c7bb6f7ceb5a39))


### Documentation

* streamline README for clarity and conciseness ([fc2cbe8](https://github.com/mrsalty/slowave/commit/fc2cbe8a4e28071cd2975a47cb98db01138ee1fd))

## [0.5.8](https://github.com/mrsalty/slowave/compare/slowave-v0.5.7...slowave-v0.5.8) (2026-06-16)


### Bug Fixes

* **windows:** Claude Desktop integration - .exe paths and stdio logging ([bd6b87a](https://github.com/mrsalty/slowave/commit/bd6b87a78fd11a00638ee0bf63745687b39e2f1f))

## [0.5.7](https://github.com/mrsalty/slowave/compare/slowave-v0.5.6...slowave-v0.5.7) (2026-06-15)


### Features

* HTTP MCP daemon transport — 2026-06-15 18:33:25 ([ea8ca5c](https://github.com/mrsalty/slowave/commit/ea8ca5ce7c539caf57471c3eeacd8522a7a50357))
* migrate MCP transport to HTTP daemon ([1332e81](https://github.com/mrsalty/slowave/commit/1332e81d4adbfc61fecb6b5281018a740a2b7a65))

## [0.5.6](https://github.com/mrsalty/slowave/compare/slowave-v0.5.5...slowave-v0.5.6) (2026-06-13)


### Features

* prepare 0.5.0 public release ([18b414f](https://github.com/mrsalty/slowave/commit/18b414f3c970b5556990c6f2449b1e58a8d074a7))


### Bug Fixes

* Add missing pytest fixture to test_remember_result.py ([ccf69f3](https://github.com/mrsalty/slowave/commit/ccf69f396eecc9c5e7c42be647284ebef1022038))
* Cline TUI lifecycle — write to ~/.cline/rules/slowave.md not ~/.clinerules ([62b842c](https://github.com/mrsalty/slowave/commit/62b842cdee366b575deb1ae0dfa678bea4693407))
* dashboard — clean error on port conflict, O(1) parent-command lookup ([7753cfd](https://github.com/mrsalty/slowave/commit/7753cfd97dfc91e1f29161f33af8f2f482448a5c))
* MCP tool name mismatch — prefix all tools with slowave_ so Cline TUI can invoke them ([1279c7e](https://github.com/mrsalty/slowave/commit/1279c7eefeb619979100c0c3b8e2d888c20a6ca9))
* MCP tool name mismatch — prefix all tools with slowave_ so Cline… ([66b3a01](https://github.com/mrsalty/slowave/commit/66b3a01f21099965743abc7bca1f34c56e423780))
* update cline lifecycle test paths to match new ~/.cline/rules/slowave.md location ([06a5e47](https://github.com/mrsalty/slowave/commit/06a5e4729c2f3a0454602e8146e68fc3b6a13cd4))
* Windows compatibility — worker window, cleanup traceback, proces… ([72c0157](https://github.com/mrsalty/slowave/commit/72c0157fcf3e53d9c33af2f9d5cd063cf931ae46))
* Windows compatibility — worker window, cleanup traceback, process detection, Cline MCP, marker corruption ([951f9ee](https://github.com/mrsalty/slowave/commit/951f9eea558096cb2bdfcd6aaceb70d77e6fcfde))


### Documentation

* add PR [#7](https://github.com/mrsalty/slowave/issues/7) merge analysis and iteration log ([c745516](https://github.com/mrsalty/slowave/commit/c74551618c2e1117d3628c8c028b457de3838a8b))
* refine core messaging and architecture documentation ([c32f4ec](https://github.com/mrsalty/slowave/commit/c32f4ecaa8031a72da1ef6b365e2fcbc0683e5a6))

## [0.5.5](https://github.com/mrsalty/slowave/compare/slowave-v0.5.4...slowave-v0.5.5) (2026-06-13)


### Bug Fixes

* **Cline TUI lifecycle:** `~/.clinerules` is not a globally-read path for Cline TUI — only `.clinerules` inside cwd is read; global rules live in `~/.cline/rules/`; change `_clinerules_path()` to write `~/.cline/rules/slowave.md` so lifecycle instructions are injected into every session regardless of working directory ([20260613_cline_clinerules_global_path](docs/iterations/20260613_cline_clinerules_global_path.md))
* **dashboard:** port-conflict error surfaced as raw Python traceback; wrap `ThreadingHTTPServer` bind in `try/except OSError`, detect `EADDRINUSE` by errno, print actionable message and exit cleanly ([7753cfd](https://github.com/mrsalty/slowave/commit/7753cfd))
* **dashboard:** `_slowave_processes()` spawned one `ps -p <ppid>` subprocess per process found, making `/api/status` O(N) subprocesses per poll; fix: build pid→command dict in a single `ps -axo` pass — O(1) lookup ([7753cfd](https://github.com/mrsalty/slowave/commit/7753cfd))

## [0.5.4](https://github.com/mrsalty/slowave/compare/slowave-v0.5.3...slowave-v0.5.4) (2026-06-13)


### Bug Fixes

* **MCP:** all tool names registered without `slowave_` prefix — LLM instructed to call `slowave_activate` but wire name was `activate`; all tool invocations failed silently on Cline TUI and any client that does not apply a server-name prefix; renamed all 6 tools to `slowave_activate`, `slowave_remember`, `slowave_recall`, `slowave_reinforce`, `slowave_commit`, `slowave_stats` ([20260613_cline_mcp_tool_name_mismatch](docs/iterations/20260613_cline_mcp_tool_name_mismatch.md))


## [0.5.3](https://github.com/mrsalty/slowave/compare/slowave-v0.5.2...slowave-v0.5.3) (2026-06-13)


### Bug Fixes

* Windows compatibility — worker window, cleanup traceback, proces… ([72c0157](https://github.com/mrsalty/slowave/commit/72c0157fcf3e53d9c33af2f9d5cd063cf931ae46))
* Windows compatibility — worker window, cleanup traceback, process detection, Cline MCP, marker corruption ([951f9ee](https://github.com/mrsalty/slowave/commit/951f9eea558096cb2bdfcd6aaceb70d77e6fcfde))

## [0.5.2](https://github.com/mrsalty/slowave/compare/slowave-v0.5.1...slowave-v0.5.2) (2026-06-13)


### Bug Fixes

* Add missing pytest fixture to test_remember_result.py ([ccf69f3](https://github.com/mrsalty/slowave/commit/ccf69f396eecc9c5e7c42be647284ebef1022038))


### Documentation

* refine core messaging and architecture documentation ([c32f4ec](https://github.com/mrsalty/slowave/commit/c32f4ecaa8031a72da1ef6b365e2fcbc0683e5a6))

## [0.5.1](https://github.com/mrsalty/slowave/compare/slowave-v0.5.0...slowave-v0.5.1) (2026-06-13)


### Features

* prepare 0.5.0 public release ([18b414f](https://github.com/mrsalty/slowave/commit/18b414f3c970b5556990c6f2449b1e58a8d074a7))

## Changelog
