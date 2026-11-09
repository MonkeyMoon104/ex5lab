# ex5lab

Research toolkit and open base for studying MetaTrader 5 **EX5** binaries and working toward **EX5 to MQ5** recovery.

**This is not a working decompiler.** There is no verified EX5 instruction decoder and no complete, precise rewrite from EX5 back to original MQL5.

```text
DECODER_AVAILABLE = False
```

Repository: [github.com/MonkeyMoon104/ex5lab](https://github.com/MonkeyMoon104/ex5lab)

---

## What this project is

`ex5lab` is a Python package plus documentation for developers who want to investigate how ordinary (non-Cloud Protector) EX5 files are structured, and whether executable semantics can eventually be recovered offline.

Target production pipeline (not implemented for real EX5 instruction decode):

```text
EX5 file
  -> offline decoder
  -> binary-derived semantic IR
  -> ProgramIR
  -> MQ5 source
```

What you get today:

- Inspect / compare / analyze EX5-like binaries (hashes, entropy, magic, strings, hex)
- Structural helpers and research scaffolding (ProgramIR fixtures to MQ5 text)
- Black-box helpers to evaluate *claimed* third-party MQ5 reconstructions against ground truth you control
- Condensed notes on what was tried and what failed

What you do **not** get:

- A public EX5 opcode map
- Automatic recovery of trading logic from arbitrary EX5
- Anything that bypasses Market / Cloud Protector / licensing

---

## Why publish a "failed" research base?

A full EX5 to MQ5 solution would be valuable. A long internal research effort did **not** reach one. Publishing the tooling and negative results is intentional: so other people can fork, try different approaches, and if they succeed, **demonstrate** recovery with evidence instead of recycling unverified advice.

Several **AI assistants** were used to propose experiments and improvements. That did not produce a working decoder. Ideas, architectures, and "try X" suggestions remain **irrelevant until someone implements them and proves** correct recovery on held-out self-authored EX5 files.

---

## What we tested (and the outcome)

These lines of work were exercised with ordinary self-authored MQ5/EX5 (not protected Market builds). Summary only. Details: [`docs/FINDINGS.md`](docs/FINDINGS.md).

| Approach | What we hoped | Outcome |
|----------|---------------|---------|
| Header / metadata inspection | Stable fields useful for tooling | **Partial success.** Magic `EX5` and some UTF-16 metadata (e.g. copyright) are often readable. Useful for inspection, not for instruction decode. |
| Compile differentials (tiny source edits) | Isolatable opcode / immediate bytes | **Failed for executable semantics.** Rebuild churn and high-entropy bodies. Expression changes did not yield a stable, validated instruction rule. |
| Plain immediate search (`*3` vs `*5`, constants) | Cleartext integer encodings in EX5 | **No usable rule.** Immediates were not found as stable plain fields under the protocols used. |
| Same-source recompile comparison | Deterministic executable payload | **Mostly unstable** after early header/metadata windows. |
| Strategy Tester / terminal load as research tool | Observe runtime transformation of EX5 | Programs run, but this **did not** yield an offline instruction map. |
| Host memory / page-permission observation | Distinguish JIT vs interpreter vs mapped guest code | **No distinguishing architecture evidence** suitable for a decoder. Raw EX5 bytes in memory are not a decoded ISA. |
| Ghidra / "dump then disassemble as x64" style claims | Native guest code visible as PE/ELF | **Not validated** as an EX5 to MQ5 path. Packaging dumps as ELF does not invent opcodes. |
| Synthetic ProgramIR to MQ5 generator | End-to-end source emit | **Works only for fixtures**, not fed by real EX5 decode. |
| Third-party "decompiler" marketing / videos | Possible external breakthrough | Treated as **unverified claims** until blind, held-out demonstration exists. |
| AI-proposed opcode tables / speculative SLEIGH | Shortcut to a decoder | **Rejected** without independent binary proof. |

**Bottom line:** the first missing stage remains transforming the opaque EX5 payload into a **verified executable representation**. Without that, CFG reconstruction and "pretty" MQ5 output are not decompilation.

---

## Current status

| Capability | Status |
|------------|--------|
| `ex5lab inspect` / `compare` / `analyze` | Available |
| Synthetic ProgramIR to MQ5 scaffolding | Available (not binary-derived) |
| Verified EX5 opcode / ISA map | Missing |
| Opaque payload to executable representation | Missing (primary bottleneck) |
| Complete precise EX5 to MQ5 rewrite | Not achieved |

Also see [`docs/STATUS.md`](docs/STATUS.md).

---

## Quick start

Python 3.11+.

```powershell
git clone https://github.com/MonkeyMoon104/ex5lab.git
cd ex5lab
python -m pip install -e .
```

Put an **authorized** `.ex5` in `input/` (gitignored):

```powershell
python -m ex5lab --version
python -m ex5lab inspect input\your_file.ex5
python -m ex5lab analyze --input input --output output
```

Optional research extras:

```powershell
python -m pip install -e ".[research]"
```

Example MQ5 stubs for local MetaEditor experiments: [`examples/`](examples/).

---

## Repository layout

| Path | Role |
|------|------|
| `src/ex5lab/` | Python package |
| `examples/` | Minimal self-authored MQ5 samples |
| `docs/` | Status and findings |
| `scripts/` | Small utilities |
| `input/` | Local EX5 inputs (gitignored) |
| `oracle/` | Optional local MQ5 oracle sources (gitignored) |
| `output/` | Local analysis outputs (gitignored) |

---

## What would count as real progress

Recover **one** independently verified executable primitive from an ordinary EX5 (for example a specific integer operation), with:

1. Bytes or structured fields from the EX5
2. A reproducible decoding rule
3. A matching operation
4. Validation on a held-out self-authored EX5 not used to invent the rule
5. A path to implement that rule **offline** (product must not depend on MetaTrader)

---

## Contributing

Fork and experiment. Prefer PRs and write-ups with **methods + evidence**. Speculative advice without implementation is low value.

Keep proprietary EX5/MQ5 out of git. Use English for code and docs here.

---

## Disclaimer

- Personal and informational research use.
- Authors and contributors accept **no liability** for how you use this software or what you analyze/publish.
- Only study files you own or are authorized to study.
- Do not bypass Market protection, Cloud Protector, DRM, or licensing.
- Do not redistribute MetaTrader binaries or proprietary third-party EAs.
- Respect MetaQuotes licenses and local law. This README is not legal advice.

## License / warranty

Research / personal / informational use. **No warranty** of any kind. Use at your own risk.
