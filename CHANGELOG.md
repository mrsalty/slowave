# Changelog

## [0.5.4](https://github.com/mrsalty/slowave/compare/slowave-v0.5.3...slowave-v0.5.4) (2026-06-13)


### Bug Fixes

* MCP tool name mismatch — prefix all tools with slowave_ so Cline TUI can invoke them ([1279c7e](https://github.com/mrsalty/slowave/commit/1279c7eefeb619979100c0c3b8e2d888c20a6ca9))
* MCP tool name mismatch — prefix all tools with slowave_ so Cline… ([66b3a01](https://github.com/mrsalty/slowave/commit/66b3a01f21099965743abc7bca1f34c56e423780))

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
