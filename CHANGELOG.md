# Changelog

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

* **MCP:** all tool names registered without `slowave_` prefix — LLM instructed to call `slowave_activate` but wire name was `activate`; all tool invocations failed silently on Cline TUI and any client that does not apply a server-name prefix; renamed all 7 tools to `slowave_activate`, `slowave_remember`, `slowave_recall`, `slowave_reinforce`, `slowave_commit`, `slowave_stats`, `slowave_remember_procedure` ([20260613_cline_mcp_tool_name_mismatch](docs/iterations/20260613_cline_mcp_tool_name_mismatch.md))


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
