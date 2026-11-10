#!/usr/bin/env python3
"""Compare scripts/er_weapons.py against output from scripts/crosscheck_ref.mjs.

    python3 -I scripts/crosscheck_compare.py ref.json

Exits with status 1 if any weapon, stat spread, hand, or level differs by more than 1e-6.
"""

import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOLERANCE = 1e-6


def load_module():
    spec = importlib.util.spec_from_file_location("er_weapons", HERE / "er_weapons.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: crosscheck_compare.py <ref.json>")
    er = load_module()
    weapons, _graphs, _tiers = er.load()
    spreads = json.loads((HERE / "crosscheck_spreads.json").read_text())
    rows = json.loads(Path(sys.argv[1]).read_text())

    mismatches = []
    for wi, si, two, level, ref_attack, ref_spell, ref_ineffective in rows:
        weapon = weapons[wi]
        damage, status, spell, missing = er.attack_rating(
            weapon, level, spreads[si], bool(two)
        )
        mine_attack = {str(t): v for t, v in {**damage, **status}.items()}
        mine_spell = {str(t): v for t, v in spell.items()}

        problems = []
        for label, mine, ref in (
            ("attack", mine_attack, ref_attack),
            ("spell", mine_spell, ref_spell),
        ):
            if set(mine) != set(ref):
                problems.append(f"{label} keys {sorted(mine)} vs {sorted(ref)}")
                continue
            for key in mine:
                if abs(mine[key] - ref[key]) > TOLERANCE:
                    problems.append(f"{label}[{key}] {mine[key]:.6f} vs {ref[key]:.6f}")
        if set(missing) != set(ref_ineffective):
            problems.append(f"missing reqs {sorted(missing)} vs {sorted(ref_ineffective)}")
        if problems:
            mismatches.append(
                f"{weapon.name} spread {si} {'2H' if two else '1H'} +{level}: " + "; ".join(problems)
            )

    print(f"compared {len(rows)} rows, {len(mismatches)} mismatches")
    for line in mismatches[:25]:
        print("  " + line)
    sys.exit(1 if mismatches else 0)


if __name__ == "__main__":
    main()
