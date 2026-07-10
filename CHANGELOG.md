# Changelog

## [0.6.1](https://github.com/mrsalty/slowave/compare/slowave-v0.14.3...slowave-v0.6.1) (2026-07-10)


### Features

* add daily SQLite backup with gzip compression and auto-rotation ([19fb957](https://github.com/mrsalty/slowave/commit/19fb9579971867334a07ae778288363fec1c9364))
* add daily SQLite backup with gzip compression and auto-rotation ([eba1a1c](https://github.com/mrsalty/slowave/commit/eba1a1c808f3ec94b364fbb9d66258036dd02802))
* **benchmark:** WikiScenarios harness (18 scenarios, 4 ablations) + supersession and encoder improvements ([18c9597](https://github.com/mrsalty/slowave/commit/18c9597ebd1aaaabc7c6e79a5275c9e07f154435))
* client-verb-instructions-v3 ([194561f](https://github.com/mrsalty/slowave/commit/194561f2a44c53332cae4c8e85b7d60762e801bf))
* **dashboard:** 3-channel EEG waveform — thin lines, multi-signal ([df6d395](https://github.com/mrsalty/slowave/commit/df6d395547ab104e090ee6deeb550d9abc077969))
* **dashboard:** add brain pulse graph to overview ([65dd701](https://github.com/mrsalty/slowave/commit/65dd701b79276e832fc2392832c23fd0d6456537))
* **dashboard:** drill-down from evidence episodes to raw events in schemas tab ([21065cf](https://github.com/mrsalty/slowave/commit/21065cf986b0a43ac5b1c7e685e95b5386123a17))
* **dashboard:** EEG-style waveform pulse graph ([5c0592f](https://github.com/mrsalty/slowave/commit/5c0592f3c3b110fad80a7e1a33ec2d2eda9041e2))
* **dashboard:** episode session links, all scopes display, batch episode metadata ([e33e6d7](https://github.com/mrsalty/slowave/commit/e33e6d7479c1b6d232c7b835da18cf490aaae143))
* **dashboard:** pulse panel polish ([f96c10b](https://github.com/mrsalty/slowave/commit/f96c10bd6f38d72db9233a709c0aa312a12bb518))
* **dashboard:** replace Episodes tab with Explorer — schemas by stage, drill-down ([d059096](https://github.com/mrsalty/slowave/commit/d059096755d94a60b0e466f54351eda68bd9a140))
* **dashboard:** Tier 1 improvements — episode browser, session replay, salience histogram, supersession timeline ([746a9d4](https://github.com/mrsalty/slowave/commit/746a9d46c249b558173c9904327be7186ed06152))
* **evals:** make tau_seconds, salience_weight, surprise_weight injectable via CLI ([01cede9](https://github.com/mrsalty/slowave/commit/01cede921f93e55f70de8fb0ddafa3dd820932f9))
* **feedback:** complete Module 6 algorithmic deep-dive with labile/reconsolidation lifecycle ([3616c8e](https://github.com/mrsalty/slowave/commit/3616c8e3a3e423a5cccce4aa7a824ccb4b4b59ec))
* **graph:** quality deep-dive — λ₁ 1.0→0.3, diagnostics, tests, docs ([7f1f53a](https://github.com/mrsalty/slowave/commit/7f1f53a5249e373810977654e38c26da3a85b08d))
* HTTP MCP daemon transport — 2026-06-15 18:33:25 ([d7e4c91](https://github.com/mrsalty/slowave/commit/d7e4c910b467cfe6257d020beabdf12a222b76ed))
* implement brain-inspired gaps 2/3/4/5/6 ([504ddb1](https://github.com/mrsalty/slowave/commit/504ddb1567c610cc0cc2044bd2a8bb1ab43af8a8))
* implement procedural memory v4 (Tier 2 enrichment + generalization) ([6d7e492](https://github.com/mrsalty/slowave/commit/6d7e492ef1301cecf6c78088ad1a30178c34692a))
* migrate MCP transport to HTTP daemon ([ea8d3c6](https://github.com/mrsalty/slowave/commit/ea8d3c6f8524c3378981ff0f228e6c71c13661d9))
* overhaul client lifecycle instructions (v3, brain-aligned) ([397158f](https://github.com/mrsalty/slowave/commit/397158fcab0632f2d2f8e5442d235a1e90b8cb10))
* prepare 0.5.0 public release ([c9b7203](https://github.com/mrsalty/slowave/commit/c9b7203012a74bef4fb44da4c0fc3261785133b1))
* preserve backups during cleanup, add restore command ([33fba65](https://github.com/mrsalty/slowave/commit/33fba6544f39adc9524daeff24296a64c99a25d0))
* procedural memory consolidation ([cfbf9a7](https://github.com/mrsalty/slowave/commit/cfbf9a7d529addd44759d27fd35089e2e483d90f))
* remove explicit procedural layer; add emergent generalization test ([18b32fa](https://github.com/mrsalty/slowave/commit/18b32faabd594152dd28a2ff0ff226f3a307323f))
* remove explicit procedural layer; add emergent generalization test ([f64c3d5](https://github.com/mrsalty/slowave/commit/f64c3d53b6d10f772229610ac1b7a7ce41f48ab0))
* **retrieval:** spread-projection architecture + diagnostics + tests ([d664efd](https://github.com/mrsalty/slowave/commit/d664efdb53ad69d0cc799f31628a8eac648eb491))
* **retrieval:** spread-projection architecture + diagnostics + tests ([24ee773](https://github.com/mrsalty/slowave/commit/24ee773e056ee585294ab1f39c7067a51a513b4d))
* **setup:** add OpenCode client integration ([4685a06](https://github.com/mrsalty/slowave/commit/4685a062bb434f6bd5573eb3ecdb080295a99b42))
* **setup:** add OpenCode client integration ([b0cef31](https://github.com/mrsalty/slowave/commit/b0cef3129db13ac40926253bb7e38133111fc81b))
* shared ops contract layer; align CLI 100% with MCP 5-verb cycle ([5b4d3e1](https://github.com/mrsalty/slowave/commit/5b4d3e1c4c89660b179b1a01ae1bfa58626d40fb))
* thread decay-idle-days through consolidation for testability ([fa3f507](https://github.com/mrsalty/slowave/commit/fa3f507bfc62663cc7c3ebfb6eb96cb41002663b))
* v4 lifecycle block with structured cold-start hints ([271492c](https://github.com/mrsalty/slowave/commit/271492c709c6b73072aec508a3970b3d9cce85b1))
* v4 lifecycle block with structured cold-start hints ([5a69c34](https://github.com/mrsalty/slowave/commit/5a69c34a75d8fe0bda534c3787f72cb42f9dcb56))
* wrap up retrieval + sal + salience modules ([4d577d5](https://github.com/mrsalty/slowave/commit/4d577d582681aa71895dbffd38839d07408b6b70))
* wrap up retrieval + sal + salience modules ([66c496b](https://github.com/mrsalty/slowave/commit/66c496b353efa10b0e4ec6cc196c4a9c4ec82579))


### Bug Fixes

* Add missing pytest fixture to test_remember_result.py ([84110c3](https://github.com/mrsalty/slowave/commit/84110c3202aebcc92d0758abd0a7ba4e6c6c426c))
* both paths now explicitly guard against missing embeddings: ([51270f6](https://github.com/mrsalty/slowave/commit/51270f611e73ba6860bf1badeb2cb5ee45ae2e86))
* brain-faithful promotion — scope-kind becomes session-floor softener ([fed40b4](https://github.com/mrsalty/slowave/commit/fed40b43809747366e73f228e00b8d71dd76fefe))
* brain-inspired-gaps ([4d315bd](https://github.com/mrsalty/slowave/commit/4d315bd5ed5cb026426cf8d8b8eb8031b3425ffb))
* bump manifest to 0.14.2 and fix bootstrap-sha ([4b20b68](https://github.com/mrsalty/slowave/commit/4b20b682ad8a0fa6e66dc86a6d1ff3b5c0fd546a))
* Cline TUI lifecycle — write to ~/.cline/rules/slowave.md not ~/.clinerules ([d0dc3c6](https://github.com/mrsalty/slowave/commit/d0dc3c67309753cee39a033452cdf4e1906783ff))
* **consolidation:** canonicalize reinforces edge direction by schema id ([4f5257b](https://github.com/mrsalty/slowave/commit/4f5257b5e4d9df232fcf0b939ff5ebaace342e17))
* **consolidation:** canonicalize reinforces edge direction by schema id ([22fdbf6](https://github.com/mrsalty/slowave/commit/22fdbf6e4c5863e4c720e26f08fd1a9bb61e9a43))
* **consolidation:** persist facet axes so contradiction detection actually works ([650f3ff](https://github.com/mrsalty/slowave/commit/650f3ff7a73691a36355e3bfd121188e4ff0c7c3))
* contradiction judge gates on support count and recency ([ab2ccaf](https://github.com/mrsalty/slowave/commit/ab2ccaf73b0cf78f7a8ce41aef4d4df4a8da4dbc))
* contrastive TF-IDF uses global schema corpus as background ([4397042](https://github.com/mrsalty/slowave/commit/43970429a7eb14c657e2dff5a61e73139edad9ae))
* correct backwards LoCoMo hot/cold comment and update uv.lock ([37305b8](https://github.com/mrsalty/slowave/commit/37305b8f2a535c58d06b81e77e4b761f2f34b720))
* correct release-please bootstrap-sha to on-main commit ([4c6a49e](https://github.com/mrsalty/slowave/commit/4c6a49ef5f24b45deab4f0cc12e676fc23cb1a42))
* critical bug in Tier 1 enforcement — embedding deserialization ([cc0093b](https://github.com/mrsalty/slowave/commit/cc0093ba5ef648278d25246b78f56b7629263b8f))
* dashboard ([8834999](https://github.com/mrsalty/slowave/commit/8834999020421e47b2b4fdb487025a26636d4847))
* dashboard — clean error on port conflict, O(1) parent-command lookup ([0f9f66b](https://github.com/mrsalty/slowave/commit/0f9f66b86e26d9930a08bed71eaf14026a69d4a6))
* dashboard + consolidation ([2dc1506](https://github.com/mrsalty/slowave/commit/2dc150622501d1709e2aa5b6c4ea67e015b5a805))
* dashboard caches engine instead of creating per request ([01dfd14](https://github.com/mrsalty/slowave/commit/01dfd148796f7e6daf606f88e6a63ed14053b096))
* **dashboard:** accordion collapse others, larger session timeline fonts ([f90473c](https://github.com/mrsalty/slowave/commit/f90473c895a31f084de09dadaa1596f24cdf7726))
* **dashboard:** auto-scroll to expanded schema header ([0721b76](https://github.com/mrsalty/slowave/commit/0721b766d5fcf5d903597088b0fde5caea4519f8))
* **dashboard:** episodes API reads metadata, supersessions uses content_text, explicit window globals ([49850b8](https://github.com/mrsalty/slowave/commit/49850b81d91d869e123e4ba18143beadc4e02617))
* **dashboard:** evidence quotes now show real content, scope list, larger font ([9dabab3](https://github.com/mrsalty/slowave/commit/9dabab3b236016af7de2050e065f9383f2e5710b))
* **dashboard:** Explorer — collapsed stages, inline accordion detail, right panel shows evidence ([d97b621](https://github.com/mrsalty/slowave/commit/d97b621b89df6dcfd38b67a1250ea5ae50769345))
* **dashboard:** explorer schema detail uses correct API keys (evidence/outgoing/content) ([f3edafe](https://github.com/mrsalty/slowave/commit/f3edafe060107577f22fcd7b14afe2b86756c98c))
* **dashboard:** improve Generalization tab clarity ([671f514](https://github.com/mrsalty/slowave/commit/671f51467f6f418266eea6d45c11e4451bb4825d))
* **dashboard:** JS syntax error in session click handler, reorder tabs ([98a48da](https://github.com/mrsalty/slowave/commit/98a48da7db6a8de34a563b008aa2f8cd8a4652cd))
* **dashboard:** loadPrototypeDetail missing catch block caused loadSessionTimeline to be local ([2431cc2](https://github.com/mrsalty/slowave/commit/2431cc2fa9b0e16f862529bd4e3072a1c32b9062))
* **dashboard:** remove double sess_ prefix, timeline panel as fixed bottom-right overlay ([904e236](https://github.com/mrsalty/slowave/commit/904e236874ab7a6f337af925684562dbbfd4f474))
* **dashboard:** replace all &lt;a href="#"&gt; with &lt;span&gt; to avoid extension message channel errors ([ef509ed](https://github.com/mrsalty/slowave/commit/ef509ed3f9d4a7d575239cc5cbc8ecef6e49d665))
* **dashboard:** restore session link for remember()-r()-created schemas ([3fbb435](https://github.com/mrsalty/slowave/commit/3fbb4354f2a6411b148da6650fe6f3097eb6c8df))
* **dashboard:** scope query uses evidence→events→sessions chain, handle missing scope_id column ([4de22ea](https://github.com/mrsalty/slowave/commit/4de22ea59543b57005f52ba70b7ea19aa35a6cc6))
* **dashboard:** session replay click, episodes auto-load, prototype UX ([54e9d52](https://github.com/mrsalty/slowave/commit/54e9d527edd71a3b72df7e18ee1ddf78e11bcc53))
* **dashboard:** supersessions confidence column renders as HTML bar, not escaped text ([4f2c73c](https://github.com/mrsalty/slowave/commit/4f2c73c22d3f7795aa60a8f60c4b85c5ce3a4b80))
* **dashboard:** wire renderPulse into refresh loop so pulse graph updates on every poll cycle ([eea19da](https://github.com/mrsalty/slowave/commit/eea19dace605a2d87e72060cb4a19ffc5e84bfea))
* deduplicate cross-scope counts via UNION to prevent premature promotion ([da40702](https://github.com/mrsalty/slowave/commit/da40702acaeafa3c9a54705eef4d15605611538d))
* differentiate CA3/CA1 dual-scale prototype thresholds ([3e1a571](https://github.com/mrsalty/slowave/commit/3e1a571ee4e38d6e22d499d99b6a70079617f342))
* disable bump-patch-for-minor-pre-major so feat commits correctly bump minor ([8ab07df](https://github.com/mrsalty/slowave/commit/8ab07dfa6e67caa94a938023e4c509a33608b480))
* expand _STOPWORDS to filter 14 commoncommon noise tokens ([0511764](https://github.com/mrsalty/slowave/commit/0511764825c5776bf710963fa66bd05ab11f7faa))
* expand _STOPWORDS to filter 14 commoncommon noise tokens ([5075fa1](https://github.com/mrsalty/slowave/commit/5075fa152dbdb6d768ba31640f4a3ec6a2163233))
* **feedback:** Module 6 algorithmic deep-dive — labile/reconsolidation lifecycle ([9440462](https://github.com/mrsalty/slowave/commit/944046264a8264f9639962bc9e33b54ee83bffe6))
* gate P3 supersession on direction score; add P4 cross-scope reinforce ([02bd573](https://github.com/mrsalty/slowave/commit/02bd5735ee879dfeb667ed29a7f07ad77d2ba626))
* generalization stage counts only admitted context recall items ([d81cb13](https://github.com/mrsalty/slowave/commit/d81cb1344a61dbe5f927cf353f74dac761e03079))
* generalization stage counts only admitted context recall items ([6b97289](https://github.com/mrsalty/slowave/commit/6b972891f664ebdb2662b5e2158e3181eb06d98f))
* graph transition/coactivation weights accumulate across replays ([3dfd62b](https://github.com/mrsalty/slowave/commit/3dfd62b4c872404ecd9ba4f36accb1dc5cfc56e9))
* **graph:** quality deep-dive — λ₁ 1.0→0.3, diagnostics, tests, docs ([1df83c5](https://github.com/mrsalty/slowave/commit/1df83c555f29fa1e14c72efe0f300457f274e589))
* group A non-functional/benchmark-neutral fixes (Homebrew SHA, deps, README benchmarks, license, conda, dead code, docs, gitignore, results) ([be78dbf](https://github.com/mrsalty/slowave/commit/be78dbf72c24925c2b689d7b56fb922e419ceea0))
* group A non-functional/benchmark-neutral fixes (Homebrew SHA, deps, README benchmarks, license, conda, dead code, docs, gitignore, results) ([fb0e628](https://github.com/mrsalty/slowave/commit/fb0e628bece2b9b6f157b40c8f0ce0b2e8640180))
* make Windows daemon/worker auto-start reliable ([12bd92e](https://github.com/mrsalty/slowave/commit/12bd92ecc8740fd0188944575035ff632b57ba49))
* make Windows daemon/worker auto-start reliable ([d8418d7](https://github.com/mrsalty/slowave/commit/d8418d702c5b3e799713b894b47b5b55f7babca7))
* MCP tool name mismatch — prefix all tools with slowave_ so Cline TUI can invoke them ([fb23273](https://github.com/mrsalty/slowave/commit/fb23273541d06f8d14d268bd994ca8e3f38fbba0))
* MCP tool name mismatch — prefix all tools with slowave_ so Cline… ([bb5b8fd](https://github.com/mrsalty/slowave/commit/bb5b8fd1ea0a7892a26f6fe16249b600bbf835f5))
* missing embedding must not trigger supersession (Group B-1) ([51270f6](https://github.com/mrsalty/slowave/commit/51270f611e73ba6860bf1badeb2cb5ee45ae2e86))
* NameError in slowave_activate — undefined variables procedure_ma… ([3b45464](https://github.com/mrsalty/slowave/commit/3b45464fac6e078468c56d64e13c01b4b0e3d397))
* NameError in slowave_activate — undefined variables procedure_matches, cold_start, scope_id, context_id ([06097e8](https://github.com/mrsalty/slowave/commit/06097e887508966fa728a0b75754f0f0aad448f0))
* NameError in slowave_activate — undefined variables procedure_matches, cold_start, scope_id, context_id ([c58388a](https://github.com/mrsalty/slowave/commit/c58388ad1ae6d7413713df06894ed4510d001cb5))
* persist FAISS indexes to disk via faiss.write_index/read_index ([857f581](https://github.com/mrsalty/slowave/commit/857f5815fa344568022e74d5c1639a4b8519cf7c))
* populate schema_relations in pure-remember consolidation pass ([c949960](https://github.com/mrsalty/slowave/commit/c94996007a8ce26a4b1d4cb7c1d0caeffac80c84))
* populate schema_relations in pure-remember consolidation pass ([e909cd6](https://github.com/mrsalty/slowave/commit/e909cd6313924b0e77c96ac2739b90c9539c6a94))
* prevent duplicate schemas in consolidation ([6a0fe96](https://github.com/mrsalty/slowave/commit/6a0fe9621f7fdcca18382895c7b1611b2d759423))
* profile-layer memories must not be geometry-superseded (Group B-2) ([5042b6b](https://github.com/mrsalty/slowave/commit/5042b6b8967af9ed2d00c8ed7a41368fb6626542))
* relevance-dominant context ranking + noise self-cleaning ([752272c](https://github.com/mrsalty/slowave/commit/752272c18f80ab5d9749f8c9500919f54c7f96a1))
* remove LLM-era columns from consolidation_debug ([0e8e5f9](https://github.com/mrsalty/slowave/commit/0e8e5f9b3f4578a03485b3984f4aafc79284f14a))
* replace hardcoded absolute path in test_encode_never_in_procedural with pathlib relative path ([ab1a9a5](https://github.com/mrsalty/slowave/commit/ab1a9a5bfa89a5cf1545c839b889249a660e8047))
* resolve CI flakiness (Python version matrix, DB isolation, test determinism) ([be42f76](https://github.com/mrsalty/slowave/commit/be42f76a2bd88cb7954f38db7b6e74e9af24e586))
* restore [dependency-groups] accidentally removed by lint config ([0fee2ce](https://github.com/mrsalty/slowave/commit/0fee2ce281c1b014e41130741d3fdfbef8822556))
* restore missing 0.14.x CHANGELOG entries wiped by force-push ([9056567](https://github.com/mrsalty/slowave/commit/90565674aa61ceef04b096daea5dc2bfffff4a9c))
* restore wiki/temporal/trend-table in run_full_benchmark.py ([5a70dae](https://github.com/mrsalty/slowave/commit/5a70daea67d915ac58152f1458af81a920e99653))
* restore wiki/temporal/trend-table in run_full_benchmark.py ([6ebf6d5](https://github.com/mrsalty/slowave/commit/6ebf6d5b23bd1ae0e038f4f04ae3b064dfcb98b9))
* scope bonus outside identity cap — global schemas survive low-cosine queries ([9327adf](https://github.com/mrsalty/slowave/commit/9327adfaa3dae17ccb21ab867fff9a2fd0d82cf3))
* scope-filter FTS and prototype candidates at collection time ([d714c53](https://github.com/mrsalty/slowave/commit/d714c53214424732a48c95b3cc35184ea900c0f5))
* **scripts:** push-public.sh uses wrong remote name in temp clone ([4d0d093](https://github.com/mrsalty/slowave/commit/4d0d093e7d82bd7de613250c9dc4a9b270e917f3))
* session resolver uses per-thread bindings to prevent collisions ([ae02ec6](https://github.com/mrsalty/slowave/commit/ae02ec6e29e07f9385bb6a75f2ddc8ecc8a31e92))
* set bootstrap-sha to recent commit to avoid scanning old history ([e497d8e](https://github.com/mrsalty/slowave/commit/e497d8ee1a4f63eb751b6c1654cc87f81341bf82))
* stale PID file after SIGKILL blocks daemon restart ([8c2f0bd](https://github.com/mrsalty/slowave/commit/8c2f0bd6d04e7202c4af25c25af14f1dafd27c28))
* supersession exception handling — log instead of silently pass ([d31eeb3](https://github.com/mrsalty/slowave/commit/d31eeb37754d7ba576066278dac7c708b06fe55e))
* support ([9fdb5cd](https://github.com/mrsalty/slowave/commit/9fdb5cd1b65772ba8cb4e2c7ed33e52426d8ea6c))
* support ([5090ac9](https://github.com/mrsalty/slowave/commit/5090ac9e4933f358e28a297cb4b823e1947b9978))
* support ([3cb9450](https://github.com/mrsalty/slowave/commit/3cb945001a77c664f66da87c4a16597601b81269))
* sync docs, harden Windows daemon, rename safe_emoji ([8789052](https://github.com/mrsalty/slowave/commit/8789052857a942cda0e4e8061ed7e1dc25c25d9e))
* **test:** relax exploration slot assertion — cosine varies across numpy versions ([4c01e71](https://github.com/mrsalty/slowave/commit/4c01e71c546a4bd5ea990686710c47759c94e7b7))
* **test:** use cue perturbation for deterministic exploration-slot assert ([ecbaf9f](https://github.com/mrsalty/slowave/commit/ecbaf9f8e84234f6bfc6bbe449d8880f0fa4a8af))
* **test:** use dataclasses.replace for frozen Schema fields ([3412c02](https://github.com/mrsalty/slowave/commit/3412c02e93a0cdc15559f19b58a061ac999a68f5))
* **test:** use distinct embeddings to avoid MMR dedup in gate tests ([339e34f](https://github.com/mrsalty/slowave/commit/339e34f4d5524b171220f3976dfd39e92c64f132))
* **test:** verify decay via consolidate stats, not net salience ([497e6d8](https://github.com/mrsalty/slowave/commit/497e6d8a4b4bc8d66e3182ec7bed22b36317f713))
* tighten install docs and client detection logic ([011863d](https://github.com/mrsalty/slowave/commit/011863dbe902000da3c81e1179f0760a669d4287))
* tighten install docs and client detection logic ([fedc1d2](https://github.com/mrsalty/slowave/commit/fedc1d2f4f7c561cefffcca91a744b750939ed45))
* trigger release-please for 0.14.3 ([add8a52](https://github.com/mrsalty/slowave/commit/add8a522d60501909e7bd33bcc581d7a32970d9e))
* untrack generated wiki benchmark result JSONs ([43ce4f4](https://github.com/mrsalty/slowave/commit/43ce4f49b9d4eb749b18a026f9ff8c420672380d))
* update cline lifecycle test paths to match new ~/.cline/rules/slowave.md location ([a05f120](https://github.com/mrsalty/slowave/commit/a05f120b86de79d25832153f0f5056fb8bbdb35b))
* update PyPI classifier from alpha to beta ([261914f](https://github.com/mrsalty/slowave/commit/261914f8469dacc01e692fe1beab9a1071faaf5b))
* use type=fact instead of type=constraint in strict_scope test ([457cb7f](https://github.com/mrsalty/slowave/commit/457cb7f0532b8b95d0e46962dc3b3a2449012020))
* use type=fact instead of type=constraint in strict_scope test ([65a6e16](https://github.com/mrsalty/slowave/commit/65a6e16d931da073e7d795fba36bfb4111834735))
* Windows compatibility — daemon crash + emoji rendering ([7f68036](https://github.com/mrsalty/slowave/commit/7f68036d1de7752c61a5aaa1266233d424e2e308))
* Windows compatibility — daemon crash + emoji rendering ([6272548](https://github.com/mrsalty/slowave/commit/627254849c1cc7e80aaa858629e3b2de3ac910d4))
* Windows compatibility — worker window, cleanup traceback, proces… ([55eddf3](https://github.com/mrsalty/slowave/commit/55eddf365df650ba3bfba17d8dc472d00d6f1ddd))
* Windows compatibility — worker window, cleanup traceback, process detection, Cline MCP, marker corruption ([4f13400](https://github.com/mrsalty/slowave/commit/4f134000da3bdd582c9ef226fd23329d4a6696b8))
* **windows:** Claude Desktop integration - .exe paths and stdio logging ([edbf47a](https://github.com/mrsalty/slowave/commit/edbf47a7dda4c531f119fc47442cfa24b531a187))
* **working-memory:** make exploration slots additive, no, not subtractive ([1de17f9](https://github.com/mrsalty/slowave/commit/1de17f96436dbcca679f4bb27a0ab6aef903c962))


### Reverts

* remove PR summary file (use GitHub PR body instead) ([cb9bf14](https://github.com/mrsalty/slowave/commit/cb9bf14ac21ce9df717e3e9780d4a1763594afb2))


### Documentation

* add Homebrew install option to README ([2e65654](https://github.com/mrsalty/slowave/commit/2e656548191f2510691a25728dbc342a47e3a804))
* add implementation file table to 06-retrieval.md ([9b01adf](https://github.com/mrsalty/slowave/commit/9b01adf60ab08ba04e45903a8024a04cfe9044ab))
* add missing activate options to CLI reference ([b5f4c41](https://github.com/mrsalty/slowave/commit/b5f4c416bf1480b99e0c4908b3fc25df66a0ed77))
* add PR [#7](https://github.com/mrsalty/slowave/issues/7) merge analysis and iteration log ([1bd2a23](https://github.com/mrsalty/slowave/commit/1bd2a239bfc0674e159b185863b7cea39cafe688))
* add PR summary for brain-inspired gaps branch ([7d75b1f](https://github.com/mrsalty/slowave/commit/7d75b1f7f4f3c179404020b90435b6f491301ba9))
* add SECURITY.md, fix Windows support caveat, link security policy from CONTRIBUTING ([1bd5fdd](https://github.com/mrsalty/slowave/commit/1bd5fddf47fc8929efc1adbf1760ccdfb1c787a0))
* consolidate and refine design & architecture documentation ([821854c](https://github.com/mrsalty/slowave/commit/821854c39127ad8d3c9c3c5b40a45241e5ef55cd))
* enforcement proposals for slowave remember cycle ([ac8100d](https://github.com/mrsalty/slowave/commit/ac8100dd0086c716961c5f9281db7116487f8ae6))
* explain transition edges as hippocampal replay co-activation ([e327584](https://github.com/mrsalty/slowave/commit/e3275849e6befad27595dd071b13f90a55bc89c8))
* LoCoMo 79.7% → 80.1% (post-λ₁ fix full run) ([481e196](https://github.com/mrsalty/slowave/commit/481e196c890c3f3ef761898f48fd2c18124033ca))
* merge install.md into setup.md, streamline setup docs ([5f00a75](https://github.com/mrsalty/slowave/commit/5f00a751d9e6497d41be598d90d6152d85d3f493))
* note that LoCoMo category breakdown is from prior run ([e09aa6d](https://github.com/mrsalty/slowave/commit/e09aa6d0747e9685aa6e87ea6fb2606bd8118f28))
* pipx first in install section, drop macOS label from Homebrew ([2981e41](https://github.com/mrsalty/slowave/commit/2981e41a34707ec80a2939c1635af14a07bf018d))
* refine core messaging and architecture documentation ([6238a0a](https://github.com/mrsalty/slowave/commit/6238a0a5dea9ff9a894b6fe3d3565d2174d2a6cd))
* remove opencode footnote from supported clients table ([2dd9683](https://github.com/mrsalty/slowave/commit/2dd96834a6b7b3101ca617317e87a611f42b83b2))
* replace Discussions link with Issues ([7561292](https://github.com/mrsalty/slowave/commit/75612920b959388a0f10fdab246cbb69157646e4))
* sharpen README positioning — lead with value, de-jargon behavioral memory ([9e776d0](https://github.com/mrsalty/slowave/commit/9e776d091c0e554a9dda68959f3cba4fa0f373a7))
* streamline README for clarity and conciseness ([789b4f9](https://github.com/mrsalty/slowave/commit/789b4f90fcc481197d3dd3aea8dc2db910745d64))
* **temporal:** complete Module 5 algorithmic deep-dive ([13fb96b](https://github.com/mrsalty/slowave/commit/13fb96bde92994549ba8666a16cf4d6516f0985f))
* update benchmark numbers + consolidation structure ([a5b2d58](https://github.com/mrsalty/slowave/commit/a5b2d58731cc7e9ab2e8bf836c7791d9eaa6de0f))
* update benchmark numbers post-salience tuning (LoCoMo 78.7→79.7%) ([b94e34c](https://github.com/mrsalty/slowave/commit/b94e34c595bf0ab23548d1052240b4222601a689))
* update benchmark numbers to match current oracle-split results ([fff8858](https://github.com/mrsalty/slowave/commit/fff885891ab1612856e3d58735162fcaad29ff3c))
* update dashboard review with progress tracking and polish items ([82826da](https://github.com/mrsalty/slowave/commit/82826daf64a790d1c47689cecc66a1e5afc77d60))
* update LoCoMo benchmark to 74.6% (latest full suite run) ([98a07f3](https://github.com/mrsalty/slowave/commit/98a07f34ae5ce76ff4bc96f7c685aadc32e9eb99))

## [0.14.3](https://github.com/mrsalty/slowave/compare/slowave-v0.14.2...slowave-v0.14.3) (2026-07-10)


### Bug Fixes

* bump manifest to 0.14.2 and fix bootstrap-sha ([f3a1183](https://github.com/mrsalty/slowave/commit/f3a118376f32d8a9c504d43bbd463106e553dba3))
* restore missing 0.14.x CHANGELOG entries wiped by force-push ([cf9cd59](https://github.com/mrsalty/slowave/commit/cf9cd592b97772e605b9fc156e4be82cef3bfdc0))
* set bootstrap-sha to recent commit to avoid scanning old history ([7883b77](https://github.com/mrsalty/slowave/commit/7883b77c7ecc9d6482fc23f48d9465b859ce1c4a))
* trigger release-please for 0.14.3 ([60aa595](https://github.com/mrsalty/slowave/commit/60aa59552990fbfac9985c08cbb7858e6d5a31b0))

## [0.14.2](https://github.com/mrsalty/slowave/compare/slowave-v0.14.1...slowave-v0.14.2) (2026-07-09)


### Bug Fixes

* dashboard improvements ([28954d7](https://github.com/mrsalty/slowave/commit/28954d790126216906de8a7b27461a56dcbe4235))

## [0.14.1](https://github.com/mrsalty/slowave/compare/slowave-v0.14.0...slowave-v0.14.1) (2026-07-09)


### Bug Fixes

* consolidation and feedback cycle ([5169917](https://github.com/mrsalty/slowave/commit/516991725e47f7110b0bc248045d7ab62d72c54b))

## [0.14.0](https://github.com/mrsalty/slowave/compare/slowave-v0.13.0...slowave-v0.14.0) (2026-07-08)


### Features

* consolidation-stage1-3 ([ba030ca](https://github.com/mrsalty/slowave/commit/ba030ca7d250c016459feb935b0b0944cf722852))

## [0.13.0](https://github.com/mrsalty/slowave/compare/slowave-v0.12.1...slowave-v0.13.0) (2026-07-07)


### Features

* v4 lifecycle block with structured cold-start hints ([77c7d65](https://github.com/mrsalty/slowave/commit/77c7d6581e8a583b99dc7a1585018e12165b7bcd))
* v4 lifecycle block with structured cold-start hints ([a5b84b7](https://github.com/mrsalty/slowave/commit/a5b84b7f26cee1948b2a3613f28e734868a2e2f0))

## [0.12.1](https://github.com/mrsalty/slowave/compare/slowave-v0.12.0...slowave-v0.12.1) (2026-07-06)


### Bug Fixes

* expand _STOPWORDS to filter 14 commoncommon noise tokens ([f1abbce](https://github.com/mrsalty/slowave/commit/f1abbce1b36b74627a0bff16d9af8133e3d9e45e))
* expand _STOPWORDS to filter 14 commoncommon noise tokens ([4b29649](https://github.com/mrsalty/slowave/commit/4b29649399992c34854a57d0c4b862822390660c))

## [0.12.0](https://github.com/mrsalty/slowave/compare/slowave-v0.11.1...slowave-v0.12.0) (2026-07-06)


### Features

* shared ops contract layer; align CLI 100% with MCP 5-verb cycle ([65d9dba](https://github.com/mrsalty/slowave/commit/65d9dba4314a309bf13d076d34f6cc7184da3505))
* thread decay-idle-days through consolidation for testability ([ac8c6a0](https://github.com/mrsalty/slowave/commit/ac8c6a07ebc1d4eadd5176f1508d71f2d00b83ed))


### Bug Fixes

* brain-faithful promotion — scope-kind becomes session-floor softener ([537c8b2](https://github.com/mrsalty/slowave/commit/537c8b2eeae00204cc72f25e9d688fa198e6e16e))
* **dashboard:** restore session link for remember()-r()-created schemas ([db53b86](https://github.com/mrsalty/slowave/commit/db53b8678f31140fd47890d00784b56d517e8a1b))
* prevent duplicate schemas in consolidation ([f499390](https://github.com/mrsalty/slowave/commit/f499390b520f6ebd05cdf26ca93d228b29022579))
* relevance-dominant context ranking + noise self-cleaning ([1760ff5](https://github.com/mrsalty/slowave/commit/1760ff556a927fdc9cdadac0ad750e330c9cae06))
* scope bonus outside identity cap — global schemas survive low-cosine queries ([4e8bdc4](https://github.com/mrsalty/slowave/commit/4e8bdc431bb9a34c403919e43b33a52f1163cbf2))
* **test:** relax exploration slot assertion — cosine varies across numpy versions ([5850ffe](https://github.com/mrsalty/slowave/commit/5850ffefaf126905985d18c1474664c113a7b2a7))
* **test:** use cue perturbation for deterministic exploration-slot assert ([b1684d9](https://github.com/mrsalty/slowave/commit/b1684d9eaad6f3f0dbfee196a01e8a292f9cb7f0))
* **test:** use dataclasses.replace for frozen Schema fields ([f4ff613](https://github.com/mrsalty/slowave/commit/f4ff6139dc57c7eaa8610ce82013e858688a1e0e))
* **test:** use distinct embeddings to avoid MMR dedup in gate tests ([cec206f](https://github.com/mrsalty/slowave/commit/cec206fdc99942b81abde7985ffaea77dc216b44))
* **test:** verify decay via consolidate stats, not net salience ([b86d298](https://github.com/mrsalty/slowave/commit/b86d2982e229cab99e68391094445188a7e0e59f))
* **working-memory:** make exploration slots additive, no, not subtractive ([49bfd00](https://github.com/mrsalty/slowave/commit/49bfd00e23c7bd72ea83a8f0306ba480b5bcb858))


### Documentation

* add missing activate options to CLI reference ([723b83b](https://github.com/mrsalty/slowave/commit/723b83babff282e5c03685a74f915111de2e9843))
* consolidate and refine design & architecture documentation ([375336e](https://github.com/mrsalty/slowave/commit/375336e176865a49ad2937ead211ea0c50a27955))
* enforcement proposals for slowave remember cycle ([c8f4942](https://github.com/mrsalty/slowave/commit/c8f4942daefd5705a8562a6e3a7048a7080306a9))
* merge install.md into setup.md, streamline setup docs ([fde6b87](https://github.com/mrsalty/slowave/commit/fde6b87dd6c7eb843d05e660374414d6ab815bb0))
* replace Discussions link with Issues ([96c0d0a](https://github.com/mrsalty/slowave/commit/96c0d0a1ded2f7bd51f91037c0fab6b5bacec44a))

## [0.11.1](https://github.com/mrsalty/slowave/compare/slowave-v0.11.0...slowave-v0.11.1) (2026-07-05)


### Bug Fixes

* tighten install docs and client detection logic ([61d727c](https://github.com/mrsalty/slowave/commit/61d727c4e73d303d0bd7966594b8a477bc538981))
* tighten install docs and client detection logic ([bcee030](https://github.com/mrsalty/slowave/commit/bcee030a4a73d69f275c11f6be45e08a575b432f))

## [0.11.0](https://github.com/mrsalty/slowave/compare/slowave-v0.10.0...slowave-v0.11.0) (2026-07-05)


### Features

* **setup:** add OpenCode client integration ([678bc7e](https://github.com/mrsalty/slowave/commit/678bc7e551a2bafebe2649de0f8a39804abf8086))
* **setup:** add OpenCode client integration ([c59bc27](https://github.com/mrsalty/slowave/commit/c59bc27ab3e7ae237e6587cb770c597d4bee2a18))


### Documentation

* remove opencode footnote from supported clients table ([7f5e9d6](https://github.com/mrsalty/slowave/commit/7f5e9d68570f0b35d566346fae50ec1f7ab1691a))

## [0.10.0](https://github.com/mrsalty/slowave/compare/slowave-v0.9.4...slowave-v0.10.0) (2026-07-05)


### Features

* **dashboard:** drill-down from evidence episodes to raw events in schemas tab ([c10e54d](https://github.com/mrsalty/slowave/commit/c10e54df46d32196d3e9b5020f7608be13214deb))
* **dashboard:** episode session links, all scopes display, batch episode metadata ([ac8ff7d](https://github.com/mrsalty/slowave/commit/ac8ff7d9169b4c5a7e6865fed3dcde2f2efe024d))
* **dashboard:** replace Episodes tab with Explorer — schemas by stage, drill-down ([877cfb7](https://github.com/mrsalty/slowave/commit/877cfb7e8a09923132546e1a60da23dbc38052a5))
* **dashboard:** Tier 1 improvements — episode browser, session replay, salience histogram, supersession timeline ([5bbc4a2](https://github.com/mrsalty/slowave/commit/5bbc4a2680c2a2fcb4c99e9aa7f1eb04a3408c49))


### Bug Fixes

* **dashboard:** accordion collapse others, larger session timeline fonts ([0fb9026](https://github.com/mrsalty/slowave/commit/0fb90264852c5cdd6958a0e3ad4fc664292ed8ca))
* **dashboard:** auto-scroll to expanded schema header ([b025c9a](https://github.com/mrsalty/slowave/commit/b025c9ad999a1883339932c9d984c13a3b176c09))
* **dashboard:** episodes API reads metadata, supersessions uses content_text, explicit window globals ([a63de90](https://github.com/mrsalty/slowave/commit/a63de90f612b7fe8b3b3e0bcb1fadfd0fa19632e))
* **dashboard:** evidence quotes now show real content, scope list, larger font ([ec7d6cb](https://github.com/mrsalty/slowave/commit/ec7d6cb6576c38cc486d97d9f23daee91db896f1))
* **dashboard:** Explorer — collapsed stages, inline accordion detail, right panel shows evidence ([08fdb2d](https://github.com/mrsalty/slowave/commit/08fdb2d30458df67ab5d8f1acc275ae2c45f8b4f))
* **dashboard:** explorer schema detail uses correct API keys (evidence/outgoing/content) ([8165d18](https://github.com/mrsalty/slowave/commit/8165d18c14067368aa0d8dfa713e6f6b4c69e617))
* **dashboard:** JS syntax error in session click handler, reorder tabs ([482f0be](https://github.com/mrsalty/slowave/commit/482f0be7637c3855a262652c009e0ffa9491d9a2))
* **dashboard:** loadPrototypeDetail missing catch block caused loadSessionTimeline to be local ([caa24dd](https://github.com/mrsalty/slowave/commit/caa24ddb47493361514802c7d33d4f5243173bb6))
* **dashboard:** remove double sess_ prefix, timeline panel as fixed bottom-right overlay ([e9a3f97](https://github.com/mrsalty/slowave/commit/e9a3f97877ce7b1a4400f28a3f4558bfeb0cb1cf))
* **dashboard:** replace all &lt;a href="#"&gt; with &lt;span&gt; to avoid extension message channel errors ([2a8f889](https://github.com/mrsalty/slowave/commit/2a8f889ad0401f7a267e1c481902874d6f0ebc2f))
* **dashboard:** scope query uses evidence→events→sessions chain, handle missing scope_id column ([1148485](https://github.com/mrsalty/slowave/commit/1148485e8c93ba4e1d4f765f22eb7646d92f4943))
* **dashboard:** session replay click, episodes auto-load, prototype UX ([7bf46fd](https://github.com/mrsalty/slowave/commit/7bf46fdc7d49e0fbf1de30f414b27e1ff6a59f35))
* **dashboard:** supersessions confidence column renders as HTML bar, not escaped text ([fc9746a](https://github.com/mrsalty/slowave/commit/fc9746a00149b5d6b9af4a1de42fa99d716cdb16))


### Documentation

* update dashboard review with progress tracking and polish items ([c674f68](https://github.com/mrsalty/slowave/commit/c674f68170188a815284c729af87837db4530f87))

## [0.9.4](https://github.com/mrsalty/slowave/compare/slowave-v0.9.3...slowave-v0.9.4) (2026-07-04)


### Bug Fixes

* generalization stage counts only admitted context recall items ([42e848c](https://github.com/mrsalty/slowave/commit/42e848cfdbcef88de10d4e2b45111dffc70556ba))
* generalization stage counts only admitted context recall items ([7c61374](https://github.com/mrsalty/slowave/commit/7c6137434514783675a0b28adfd2207620720916))

## [0.9.3](https://github.com/mrsalty/slowave/compare/slowave-v0.9.2...slowave-v0.9.3) (2026-07-04)


### Bug Fixes

* both paths now explicitly guard against missing embeddings: ([7d9a1e0](https://github.com/mrsalty/slowave/commit/7d9a1e00f64901a55e8047f6e5dcc7a785f16a78))
* contradiction judge gates on support count and recency ([f20a267](https://github.com/mrsalty/slowave/commit/f20a267b288e62c04e994e8ddd1344267e99e5d2))
* contrastive TF-IDF uses global schema corpus as background ([87bfdec](https://github.com/mrsalty/slowave/commit/87bfdecbee011ea82b9ccbee0b40aee56c3e8a87))
* dashboard caches engine instead of creating per request ([0b34f75](https://github.com/mrsalty/slowave/commit/0b34f75289a20f26998e873c531011dfc1bdf585))
* differentiate CA3/CA1 dual-scale prototype thresholds ([c62cf60](https://github.com/mrsalty/slowave/commit/c62cf60497ac4c24315cc11f0f977299d00c732f))
* graph transition/coactivation weights accumulate across replays ([abbf206](https://github.com/mrsalty/slowave/commit/abbf206fc79a1aeebf069e676da1865194971c45))
* group A non-functional/benchmark-neutral fixes (Homebrew SHA, deps, README benchmarks, license, conda, dead code, docs, gitignore, results) ([acbb58e](https://github.com/mrsalty/slowave/commit/acbb58e0176e5ae61a33259263c62430312c9150))
* group A non-functional/benchmark-neutral fixes (Homebrew SHA, deps, README benchmarks, license, conda, dead code, docs, gitignore, results) ([d525909](https://github.com/mrsalty/slowave/commit/d5259098b4a19adc2a7b53bb60445a8698053bb4))
* missing embedding must not trigger supersession (Group B-1) ([7d9a1e0](https://github.com/mrsalty/slowave/commit/7d9a1e00f64901a55e8047f6e5dcc7a785f16a78))
* persist FAISS indexes to disk via faiss.write_index/read_index ([ca2d957](https://github.com/mrsalty/slowave/commit/ca2d957011b908101f36fde74a9acc5e9ad6857c))
* profile-layer memories must not be geometry-superseded (Group B-2) ([6ad3540](https://github.com/mrsalty/slowave/commit/6ad35403c2ecb5f33051227e75c46678f9ac00bd))
* remove LLM-era columns from consolidation_debug ([e5e94e2](https://github.com/mrsalty/slowave/commit/e5e94e2e09b0970596edd69f7b9a10477861812f))
* scope-filter FTS and prototype candidates at collection time ([691cfa1](https://github.com/mrsalty/slowave/commit/691cfa124240f67525f298d61be87250e6628459))
* session resolver uses per-thread bindings to prevent collisions ([7c0bfe1](https://github.com/mrsalty/slowave/commit/7c0bfe10aa2d6953dbf969cdfa33fc0e2ccd5e26))
* supersession exception handling — log instead of silently pass ([b37b5e0](https://github.com/mrsalty/slowave/commit/b37b5e0441169bb82753f67b22a65c78bd7adf19))
* untrack generated wiki benchmark result JSONs ([0150f88](https://github.com/mrsalty/slowave/commit/0150f88aa8ad66fe0f3e8d4b0f3ba8e5fa245e72))


### Documentation

* explain transition edges as hippocampal replay co-activation ([1823957](https://github.com/mrsalty/slowave/commit/182395737c0a530e82440adfd36d0d7eb6273ce0))
* note that LoCoMo category breakdown is from prior run ([3f20fdf](https://github.com/mrsalty/slowave/commit/3f20fdfbdce20e82da68bddf21f0eaead2e81815))
* update LoCoMo benchmark to 74.6% (latest full suite run) ([432b585](https://github.com/mrsalty/slowave/commit/432b58556d708c7e5f423c9c7df73923a330e091))

## [0.9.2](https://github.com/mrsalty/slowave/compare/slowave-v0.9.1...slowave-v0.9.2) (2026-07-03)


### Bug Fixes

* make Windows daemon/worker auto-start reliable ([94c9eeb](https://github.com/mrsalty/slowave/commit/94c9eeb3c0df2c3007df0f8bcb5b3794f5ae229b))
* make Windows daemon/worker auto-start reliable ([f659705](https://github.com/mrsalty/slowave/commit/f6597051d6973835fe7702e933c67bda40d49a23))

## [0.9.1](https://github.com/mrsalty/slowave/compare/slowave-v0.9.0...slowave-v0.9.1) (2026-07-02)


### Documentation

* sharpen README positioning — lead with value, de-jargon behavioral memory ([ea34757](https://github.com/mrsalty/slowave/commit/ea34757aa8d2440b1e4d3d7584499e1ebdbe3baa))

## [0.9.0](https://github.com/mrsalty/slowave/compare/slowave-v0.8.2...slowave-v0.9.0) (2026-06-29)


### Features

* client-verb-instructions-v3 ([cf92966](https://github.com/mrsalty/slowave/commit/cf92966718f125dd87c800400e4c045a160762f3))
* overhaul client lifecycle instructions (v3, brain-aligned) ([f6382a2](https://github.com/mrsalty/slowave/commit/f6382a2d56203b45fdda1bf19fc218a39e8bdbcb))


### Bug Fixes

* sync docs, harden Windows daemon, rename safe_emoji ([8464fb1](https://github.com/mrsalty/slowave/commit/8464fb13e81708b48054fe5b1a4fea9c69b53879))

## [0.8.2](https://github.com/mrsalty/slowave/compare/slowave-v0.8.1...slowave-v0.8.2) (2026-06-28)


### Bug Fixes

* Windows compatibility — daemon crash + emoji rendering ([c6e69d7](https://github.com/mrsalty/slowave/commit/c6e69d70e17c2b018747ed72fdcf2d160bef573f))
* Windows compatibility — daemon crash + emoji rendering ([90583c0](https://github.com/mrsalty/slowave/commit/90583c02aaf6f80c6af48c548d91a1352103a87b))

## [0.8.1](https://github.com/mrsalty/slowave/compare/slowave-v0.8.0...slowave-v0.8.1) (2026-06-26)


### Bug Fixes

* NameError in slowave_activate — undefined variables procedure_ma… ([ae05a33](https://github.com/mrsalty/slowave/commit/ae05a33e280463265b7e3a0535ce8650d6d8a1ba))
* NameError in slowave_activate — undefined variables procedure_matches, cold_start, scope_id, context_id ([e45d8e2](https://github.com/mrsalty/slowave/commit/e45d8e28ada8566a78d41f89908b74d1f7ddb5d9))
* NameError in slowave_activate — undefined variables procedure_matches, cold_start, scope_id, context_id ([5c33245](https://github.com/mrsalty/slowave/commit/5c33245ef31b9508ffb5d795872a84c661f165cd))
* stale PID file after SIGKILL blocks daemon restart ([b06fa9e](https://github.com/mrsalty/slowave/commit/b06fa9ef3d53fa8fc5ac17e93f7a6199ca6cac11))

## [0.8.0](https://github.com/mrsalty/slowave/compare/slowave-v0.7.0...slowave-v0.8.0) (2026-06-26)


### Features

* remove explicit procedural layer; add emergent generalization test ([15ee568](https://github.com/mrsalty/slowave/commit/15ee5686447b8b6a7a05f37c4ae3a4ec325ae3ab))
* remove explicit procedural layer; add emergent generalization test ([27687ed](https://github.com/mrsalty/slowave/commit/27687ed421b696d6128bedba5b60c9f37d042bec))

## [0.7.0](https://github.com/mrsalty/slowave/compare/slowave-v0.6.1...slowave-v0.7.0) (2026-06-24)


### Features

* implement brain-inspired gaps 2/3/4/5/6 ([544719f](https://github.com/mrsalty/slowave/commit/544719f7f470f437c65a4d708e62d815026cd2aa))


### Bug Fixes

* brain-inspired-gaps ([0cce071](https://github.com/mrsalty/slowave/commit/0cce0711e0f3b86fb59179cd08320f626dd4314a))
* **dashboard:** improve Generalization tab clarity ([66120ea](https://github.com/mrsalty/slowave/commit/66120ea15e72f50a9677345f0744eee3bccef23b))
* deduplicate cross-scope counts via UNION to prevent premature promotion ([3b2b1e9](https://github.com/mrsalty/slowave/commit/3b2b1e9927f21787a606d8c83442a73cae28199d))
* gate P3 supersession on direction score; add P4 cross-scope reinforce ([69acf5e](https://github.com/mrsalty/slowave/commit/69acf5ec43db37b601458fe96d0ead50cceb79ef))


### Reverts

* remove PR summary file (use GitHub PR body instead) ([a9cfc46](https://github.com/mrsalty/slowave/commit/a9cfc4699605c5df426892c786f323a68467842c))


### Documentation

* add PR summary for brain-inspired gaps branch ([7ada6c5](https://github.com/mrsalty/slowave/commit/7ada6c5820a3505b2d285b2785ff238257a8ea56))
* update benchmark numbers to match current oracle-split results ([0830f68](https://github.com/mrsalty/slowave/commit/0830f6810368f906c6901083becc168c1eee7047))

## [0.6.1](https://github.com/mrsalty/slowave/compare/slowave-v0.6.0...slowave-v0.6.1) (2026-06-23)


### Bug Fixes

* update PyPI classifier from alpha to beta ([fe669ec](https://github.com/mrsalty/slowave/commit/fe669ec63b1252ef4307ff73c8511e2b0a1890a0))

## [0.6.0](https://github.com/mrsalty/slowave/compare/slowave-v0.5.11...slowave-v0.6.0) (2026-06-23)


### Bug Fixes

* disable bump-patch-for-minor-pre-major so feat commits correctly bump minor ([4de95de](https://github.com/mrsalty/slowave/commit/4de95dec3b0f335fb38ee9046cf6130860eb57db))


### Documentation

* add SECURITY.md, fix Windows support caveat, link security policy from CONTRIBUTING ([6588bd4](https://github.com/mrsalty/slowave/commit/6588bd45303a29673b97187bbb5f10a9629d6325))

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
