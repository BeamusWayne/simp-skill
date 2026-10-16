# simp-skill · Love Strategist

Context-aware relationship discussion and natural message drafting. This is the **v2 P0–P3 development version**, not a final v2.0 release. Deterministic romance scores, fixed pursuit stages and MBTI-based decisions have been removed.

Keep SKILL.md, prompts/, tools/ and docs/ together when installing through your host's skill mechanism. Slash-command registration is host-dependent; installation across hosts has not been verified. Simple drafting requires no profile. Modes sweet/strategic/hybrid affect expression only.

Python 3.12 is the tool target. Activate a virtual environment, install requirements-dev.txt, then run `python -m pytest -q`. Core parsing and memory use the standard library; Pillow supports photo metadata. Example: `python tools/chat_parser.py tests/fixtures/v2/direct.json Alice --json`.

Memory is opt-in through explicit profile creation. Import requires an existing profile plus --track-time --slug NAME --base-dir DIR. Facts, user reports, assessments, drafts, confirmed actions and outcomes have separate record types and provenance. Identity/fact corrections invalidate dependent conclusions. Backups restore the entire checkpoint after saving current state.

See [chat format](docs/CHAT-FORMAT.md), [memory contract](docs/MEM-SYS.md), [migration/recovery](docs/V2-MIGRATION.md) and [evaluation protocol](evals/README.md). Migration previews by default; old judgments remain unverified legacy records. --score/--stage are rejected; --golden describes recorded active hours only.

Tools run locally and do not call a model API. If the host sends their results to a model, its data handling applies; local parsing does not guarantee offline analysis. All committed fixtures are synthetic. Never commit personal profiles or evaluation transcripts containing private material.

P4 persistent style learning and the independent review workflow remain planned. P5 includes the full 216-run model comparison, host validation and release work. Automated tool tests do not establish model-behavior superiority. Baseline commit: 71f64215f50aeb5b619fb34fa44adb9247c85770. See LICENSE.
