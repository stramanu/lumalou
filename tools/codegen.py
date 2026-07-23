#!/usr/bin/env python3
"""
Code generation: spec/protocol.json -> generated modules for each language.

Keeps opcodes and enums identical across bindings (single source of truth).

    python tools/codegen.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = json.loads((ROOT / "spec" / "protocol.json").read_text())
PY_OUT = ROOT / "packages" / "python" / "src" / "lumalou" / "_generated.py"
TS_OUT = ROOT / "packages" / "js" / "src" / "generated.ts"

HEADER = "AUTO-GENERATED from spec/protocol.json by tools/codegen.py. Do not edit."


def gen_python():
    e = SPEC["enums"]
    lines = [f'"""{HEADER}"""', "from enum import IntEnum", ""]
    lines.append(f"GATT = {json.dumps(SPEC['gatt'], indent=4)}")
    lines.append("")
    lines.append(f"COMMANDS = {json.dumps(SPEC['commands'], indent=4)}")
    lines.append(f"DAY_ROUTINE = {json.dumps(SPEC['dayRoutineCommands'], indent=4)}")
    lines.append(f"RESPONSES = {{{', '.join(f'{v}: {json.dumps(k)}' for k, v in SPEC['responses'].items())}}}")
    lines.append("")
    for enum_name, members in e.items():
        lines.append(f"class {enum_name}(IntEnum):")
        for m, v in members.items():
            lines.append(f"    {m} = {v}")
        lines.append("")
    PY_OUT.write_text("\n".join(lines) + "\n")
    print("wrote", PY_OUT.relative_to(ROOT))


def gen_ts():
    e = SPEC["enums"]
    out = [f"// {HEADER}", ""]
    out.append(f"export const GATT = {json.dumps(SPEC['gatt'], indent=2)} as const;")
    out.append("")
    out.append(f"export const COMMANDS = {json.dumps(SPEC['commands'], indent=2)} as const;")
    out.append(f"export const DAY_ROUTINE = {json.dumps(SPEC['dayRoutineCommands'], indent=2)} as const;")
    resp = ", ".join(f"{v}: {json.dumps(k)}" for k, v in SPEC["responses"].items())
    out.append(f"export const RESPONSES: Record<number, string> = {{ {resp} }};")
    out.append("")
    for enum_name, members in e.items():
        body = ", ".join(f"{m}: {v}" for m, v in members.items())
        out.append(f"export const {enum_name} = {{ {body} }} as const;")
        out.append(f"export type {enum_name} = (typeof {enum_name})[keyof typeof {enum_name}];")
        out.append("")
    TS_OUT.write_text("\n".join(out) + "\n")
    print("wrote", TS_OUT.relative_to(ROOT))


if __name__ == "__main__":
    gen_python()
    gen_ts()
