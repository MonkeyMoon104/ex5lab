# Status

`DECODER_AVAILABLE = False`

**ex5lab** is a research toolkit and incomplete base for EX5 to MQ5 work. It is not a production decompiler.

## Available today

- Read-only EX5 inspection (hashes, entropy, magic/prefix, printable and UTF-16 strings, hex previews)
- Binary comparison helpers
- Analyze pipeline that records structural observations into `output/`
- Synthetic ProgramIR fixtures to MQ5 text generation (scaffolding only)
- Helpers to evaluate third-party claimed MQ5 reconstructions against ground truth you control

## Not available

- Verified EX5 opcode / ISA specification
- Offline unpack of the opaque EX5 payload into an executable representation
- Control-flow recovery from EX5 bytes
- Complete, precise EX5 to MQ5 rewrite of real programs

## Product boundary

Production decode must not depend on Strategy Tester, MetaEditor, or live terminal execution. Those tools may be used for separate research experiments, but demonstrated knowledge must be reimplemented offline.
