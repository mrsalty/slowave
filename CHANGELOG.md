# Changelog

## [0.5.5](https://github.com/mrsalty/slowave/compare/slowave-v0.5.4...slowave-v0.5.5) (2026-06-13)


### Bug Fixes

* **Cline TUI lifecycle:** `~/.clinerules` is not a globally-read path for Cline TUI — only `.clinerules` inside cwd is read; global rules live in `~/.cline/rules/`; change `_clinerules_path()` to write `~/.cline/rules/slowave.md` so lifecycle instructions are injected into every session regardless of working directory ([20260613_cline_clinerules_global_path](docs/iterations/20260613_cline_clinerules_global_path.md))


## [0.5.4](https://github.com/mrsalty/slowave/compare/slowave-v0.5.3...slowave-v0.5.4) (2026-06-13)


### Bug Fixes

* **MCP:** all tool names registered without `slowave_` prefix — LLM instructed to call `slowave_activate` but wire name was `activate`; all tool invocations failed silently on Cline TUI; renamed all 7 tools to `slowave_*` ([20260613_cline_mcp_tool_name_mismatch](docs/iterations/20260613_cline_mcp_tool_name_mismatch.md))


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
