# Findings

Condensed results from the research that led to this public base. This is not an official MetaQuotes EX5 specification.

## Official documentation (public)

- MetaEditor documents compilation to EX4/EX5 in a proprietary format that **hides the original algorithm**.
- Public materials sometimes describe MQL5 as compiling to native x86/x64. That does **not** publish an on-disk ISA, opcode table, or loader ABI.
- No public MetaQuotes EX5 instruction manual was found.

## Empirical results on ordinary self-authored EX5

### Worked enough to keep as tooling

- Files typically start with an `EX5` magic.
- Limited cleartext metadata can appear (for example UTF-16 copyright / version strings in an early window on many builds).
- Inspection CLI (`inspect` / `analyze`) is useful for hashing, entropy, and string surveys.

### Failed or inconclusive for decoding

- **Compile differentials** for tiny arithmetic edits did not isolate a validated opcode or immediate encoding.
- **Plain integer immediate search** (e.g. multiply-by-3 vs multiply-by-5) did not produce a compile-invariant decoding rule under the protocols used.
- **Same-source recompiles** often change size and most post-header bytes (high entropy bodies).
- **Runtime load** in MetaTrader / Strategy Tester proves execution; it did not deliver an offline guest ISA.
- **Memory / page-permission studies** did not produce distinguishing, attributable evidence of an EX5-specific JIT image suitable for decoding.
- **Ghidra-as-x64-on-a-dump** style approaches were not shown to recover EX5 to MQ5 semantics.
- **AI-suggested opcode tables** without binary proof were not accepted.

## Bottleneck

```text
EX5 bytes -> container/metadata -> ??? executable representation ??? -> operations -> CFG -> ProgramIR -> MQ5
```

The unknown stage is recovering a verified executable representation from the opaque payload.

## Advice vs proof

Forum tips, architecture guesses, and AI proposals are not evidence. Progress requires a falsifiable rule and independent demonstration on held-out binaries.
