#!/usr/bin/env python3
"""Expand Elden Ring weapon regulation data into flat, build-ready tables.

Source data: data/regulation-vanilla-v1.17.json, extracted from the game's param files by
ThomasJClark/elden-ring-weapon-calculator (MIT). The attack-rating math below follows that
project's src/calculator/calculator.ts and src/regulationData.ts.

Usage (run from anywhere):
    python3 -I scripts/er_weapons.py build
    python3 -I scripts/er_weapons.py ar --str 40 --dex 25 --level 25 --somber-level 10 --top 30
"""

import argparse
import csv
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "regulation-vanilla-v1.17.json"
OUT = ROOT / "output"

ATTRS = ("str", "dex", "int", "fai", "arc")
DAMAGE = {0: "phy", 1: "mag", 2: "fire", 3: "ltng", 4: "holy"}
STATUS = {
    5: "poison",
    6: "scarlet_rot",
    7: "bleed",
    8: "frost",
    9: "sleep",
    10: "madness",
    11: "death_blight",
}
DEFAULT_DAMAGE_GRAPH = 0
DEFAULT_STATUS_GRAPH = 6
# Vanilla: only these status types scale with Arcane. Rot, frost and death blight do not.
STATUS_ARC_SCALING = {5, 7, 9, 10}

AFFINITIES = {
    -1: "Unique",
    0: "Standard",
    1: "Heavy",
    2: "Keen",
    3: "Quality",
    4: "Fire",
    5: "Flame Art",
    6: "Lightning",
    7: "Sacred",
    8: "Magic",
    9: "Cold",
    10: "Poison",
    11: "Blood",
    12: "Occult",
}

WEAPON_TYPES = {
    1: "Dagger",
    3: "Straight Sword",
    5: "Greatsword",
    7: "Colossal Sword",
    9: "Curved Sword",
    11: "Curved Greatsword",
    13: "Katana",
    14: "Twinblade",
    15: "Thrusting Sword",
    16: "Heavy Thrusting Sword",
    17: "Axe",
    19: "Greataxe",
    21: "Hammer",
    23: "Great Hammer",
    24: "Flail",
    25: "Spear",
    28: "Great Spear",
    29: "Halberd",
    31: "Reaper",
    35: "Fist",
    37: "Claw",
    39: "Whip",
    41: "Colossal Weapon",
    50: "Light Bow",
    51: "Bow",
    53: "Greatbow",
    55: "Crossbow",
    56: "Ballista",
    57: "Glintstone Staff",
    59: "Dual Catalyst",
    61: "Sacred Seal",
    65: "Small Shield",
    67: "Medium Shield",
    69: "Greatshield",
    87: "Torch",
    88: "Hand-to-Hand",
    89: "Perfume Bottle",
    90: "Thrusting Shield",
    91: "Throwing Blade",
    92: "Backhand Blade",
    93: "Light Greatsword",
    94: "Great Katana",
    95: "Beast Claw",
}
# Bows and ballistae are always two-handed, so they always get the 1.5x Strength bonus.
ALWAYS_TWO_HANDED = {50, 51, 53, 56}


# --------------------------------------------------------------------------------------------
# Loading and expanding the raw data
# --------------------------------------------------------------------------------------------


def evaluate_graph(stages):
    """Turn a CalcCorrectGraph (list of stages) into a list of scaling values by stat level.

    Index i holds the scaling at stat level i (1..148). Index 0 is unused.
    """
    arr = [0.0] * 149
    for i in range(1, len(stages)):
        prev, stage = stages[i - 1], stages[i]
        lo = 1 if i == 1 else prev["maxVal"] + 1
        hi = 148 if i == len(stages) - 1 else stage["maxVal"]
        for stat in range(lo, hi + 1):
            ratio = (stat - prev["maxVal"]) / (stage["maxVal"] - prev["maxVal"])
            ratio = max(0.0, min(1.0, ratio))
            if prev["adjPt"] > 0:
                ratio = ratio ** prev["adjPt"]
            elif prev["adjPt"] < 0:
                ratio = 1 - (1 - ratio) ** -prev["adjPt"]
            arr[stat] = prev["maxGrowVal"] + (stage["maxGrowVal"] - prev["maxGrowVal"]) * ratio
    return arr


class Weapon:
    """One weapon with one infusion, expanded across every smithing level."""

    def __init__(self, raw, data, graphs, element_correct):
        self.name = raw["name"]
        self.base_name = raw["weaponName"]
        self.type_id = raw["weaponType"]
        self.type = WEAPON_TYPES.get(raw["weaponType"], f"Type {raw['weaponType']}")
        self.affinity_id = raw["affinityId"]
        self.infusion = AFFINITIES.get(raw["affinityId"], f"Affinity {raw['affinityId']}")
        self.dlc = bool(raw.get("dlc"))
        self.paired = bool(raw.get("paired"))
        self.sorcery_tool = bool(raw.get("sorceryTool"))
        self.incantation_tool = bool(raw.get("incantationTool"))
        self.requirements = {a: raw["requirements"].get(a, 0) for a in ATTRS}
        self.reinforce_id = raw["reinforceTypeId"]

        self.element_correct = element_correct[raw["attackElementCorrectId"]]
        graph_ids = {int(k): v for k, v in raw.get("calcCorrectGraphIds", {}).items()}
        self.graph_ids = {}
        for t in DAMAGE:
            self.graph_ids[t] = graph_ids.get(t, DEFAULT_DAMAGE_GRAPH)
        for t in STATUS:
            self.graph_ids[t] = graph_ids.get(t, DEFAULT_STATUS_GRAPH)
        self.graphs = {t: graphs[g] for t, g in self.graph_ids.items()}

        reinforce = data["reinforceTypes"][str(self.reinforce_id)]
        base_attack = {t: v for t, v in raw["attack"]}
        base_scaling = {a: v for a, v in raw["attributeScaling"]}
        status_ids = raw.get("statusSpEffectParamIds", [])

        # attack[level][type] and scaling[level][attr], same expansion as regulationData.ts
        self.attack = []
        self.scaling = []
        for rp in reinforce:
            atk = {t: v * rp["attack"].get(str(t), 0) for t, v in base_attack.items()}
            offsets = [rp.get("statusSpEffectId1"), rp.get("statusSpEffectId2"), rp.get("statusSpEffectId3")]
            for i, sp_id in enumerate(status_ids):
                if sp_id:
                    params = data["statusSpEffectParams"].get(str(sp_id + (offsets[i] or 0)))
                    if params:
                        atk.update({int(k): v for k, v in params.items()})
            self.attack.append(atk)
            self.scaling.append(
                {a: v * rp["attributeScaling"][a] for a, v in base_scaling.items()}
            )
        self.max_level = len(reinforce) - 1

    @property
    def path(self):
        if self.max_level == 25:
            return "Smithing"
        if self.max_level == 10:
            return "Somber"
        return "None"

    @property
    def is_catalyst(self):
        return self.sorcery_tool or self.incantation_tool

    def curve_label(self):
        return ",".join(str(self.graph_ids[t]) for t in DAMAGE)

    def scaling_stats(self, damage_type):
        """Stats this damage type scales with (weapon has a nonzero scaling value for them)."""
        flags = self.element_correct.get(damage_type, {})
        return [a for a in ATTRS if flags.get(a) and self.scaling[0].get(a, 0)]


def load(path=DATA):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    graphs = {int(k): evaluate_graph(v) for k, v in data["calcCorrectGraphs"].items()}
    element_correct = {}
    for key, per_type in data["attackElementCorrects"].items():
        entry = {int(t): dict(flags) for t, flags in per_type.items()}
        # Status types are not stored in the param table; the calculator adds them here.
        for status_type in STATUS:
            entry[status_type] = {"arc": True} if status_type in STATUS_ARC_SCALING else {}
        element_correct[int(key)] = entry
    weapons = [Weapon(raw, data, graphs, element_correct) for raw in data["weapons"]]
    tiers = [(float(t), g) for t, g in data["scalingTiers"]]
    return weapons, graphs, tiers


def grade(value, tiers):
    """Scaling letter (S/A/B/C/D/E) for a numeric scaling coefficient, or '' for none."""
    for threshold, letter in tiers:
        if value >= threshold:
            return letter
    return ""


# --------------------------------------------------------------------------------------------
# Attack rating
# --------------------------------------------------------------------------------------------


def attack_rating(w, level, stats, two_handing=False, penalty=0.4):
    """Attack rating by type for weapon `w` at smithing level `level` with player `stats`.

    Returns (damage, status, spell_scaling, missing_stats). Damage and status hold raw floats.
    """
    level = min(level, w.max_level)
    adjusted = dict(stats)
    if (two_handing and not w.paired) or w.type_id in ALWAYS_TWO_HANDED:
        adjusted["str"] = math.floor(stats["str"] * 1.5)

    missing = [a for a, req in w.requirements.items() if req and adjusted[a] < req]
    damage, status, spell = {}, {}, {}
    for t in list(DAMAGE) + list(STATUS):
        is_damage = t in DAMAGE
        base = w.attack[level].get(t, 0)
        if not (base or w.is_catalyst):
            continue
        flags = w.element_correct.get(t, {})
        total = 1.0
        if any(flags.get(a) for a in missing):
            total = 1 - penalty
        else:
            effective = adjusted if is_damage else stats
            for a in ATTRS:
                flag = flags.get(a)
                if not flag:
                    continue
                if flag is True:
                    s = w.scaling[level].get(a, 0)
                else:
                    denom = w.scaling[0].get(a, 0)
                    s = flag * w.scaling[level].get(a, 0) / denom if denom else 0
                if s:
                    total += w.graphs[t][effective[a]] * s
        if base:
            (damage if is_damage else status)[t] = base * total
        if is_damage and w.is_catalyst:
            spell[t] = 100 * total
    return damage, status, spell, missing


# --------------------------------------------------------------------------------------------
# Table output
# --------------------------------------------------------------------------------------------


def fmt(x, places=2):
    if x is None or x == 0:
        return ""
    return f"{x:.{places}f}".rstrip("0").rstrip(".")


def scales_with(w):
    parts = []
    for t, label in DAMAGE.items():
        if w.attack[0].get(t) or w.is_catalyst:
            stats = w.scaling_stats(t)
            if w.attack[0].get(t):
                parts.append(f"{label}:{'+'.join(stats) if stats else 'none'}")
    return " ".join(parts)


def level_record(w, level, tiers):
    """One table row (as a dict keyed by LEVEL_HEADER names) for a weapon at a smithing level."""
    atk, scl = w.attack[level], w.scaling[level]
    rec = {
        "weapon": w.name,
        "base_weapon": w.base_name,
        "type": w.type,
        "infusion": w.infusion,
        "dlc": "Y" if w.dlc else "",
        "upgrade_path": w.path,
        "level": level,
        "max_level": w.max_level,
        "scales_with": scales_with(w),
        "curves_phy_mag_fire_ltng_holy": w.curve_label(),
        "paired": "Y" if w.paired else "",
        "spell_tool": "+".join(
            name
            for name, on in (("sorcery", w.sorcery_tool), ("incantation", w.incantation_tool))
            if on
        ),
    }
    for a in ATTRS:
        rec[f"req_{a}"] = w.requirements[a] or ""
        rec[f"scl_{a}"] = grade(scl.get(a, 0), tiers)
        rec[f"scl_{a}_val"] = fmt(scl.get(a), 3)
    for t in DAMAGE:
        rec[f"dmg_{DAMAGE[t]}"] = fmt(atk.get(t))
    for t in STATUS:
        rec[f"status_{STATUS[t]}"] = fmt(atk.get(t))
    return rec


LEVEL_HEADER = (
    ["weapon", "base_weapon", "type", "infusion", "dlc", "upgrade_path", "level", "max_level"]
    + [f"req_{a}" for a in ATTRS]
    + [f"dmg_{DAMAGE[t]}" for t in DAMAGE]
    + [f"scl_{a}" for a in ATTRS]
    + [f"scl_{a}_val" for a in ATTRS]
    + [f"status_{STATUS[t]}" for t in STATUS]
    + ["scales_with", "curves_phy_mag_fire_ltng_holy", "paired", "spell_tool"]
)

SUMMARY_FIXED = (
    ["weapon", "base_weapon", "type", "infusion", "dlc", "upgrade_path", "max_level"]
    + [f"req_{a}" for a in ATTRS]
)
SUMMARY_PER_LEVEL = (
    [f"dmg_{DAMAGE[t]}" for t in DAMAGE]
    + [f"scl_{a}" for a in ATTRS]
    + [f"status_{STATUS[t]}" for t in STATUS]
)
SUMMARY_TAIL = ["scales_with", "paired", "spell_tool"]


def build(weapons, graphs, tiers):
    OUT.mkdir(exist_ok=True)

    with open(OUT / "weapons_by_level.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LEVEL_HEADER)
        writer.writeheader()
        rows = 0
        for w in weapons:
            for level in range(w.max_level + 1):
                writer.writerow(level_record(w, level, tiers))
                rows += 1
    print(f"output/weapons_by_level.csv: {rows} rows")

    header = list(SUMMARY_FIXED)
    for tag in ("lv0", "max"):
        header += [f"{tag}_{col}" for col in SUMMARY_PER_LEVEL]
    header += SUMMARY_TAIL
    with open(OUT / "weapons_summary.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        for w in weapons:
            first, last = level_record(w, 0, tiers), level_record(w, w.max_level, tiers)
            row = {col: first[col] for col in SUMMARY_FIXED + SUMMARY_TAIL}
            for tag, rec in (("lv0", first), ("max", last)):
                row.update({f"{tag}_{col}": rec[col] for col in SUMMARY_PER_LEVEL})
            writer.writerow(row)
    print(f"output/weapons_summary.csv: {len(weapons)} rows")

    with open(OUT / "stat_scaling_curves.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["curve_id"] + [f"stat_{s}" for s in range(1, 100)])
        for gid in sorted(graphs):
            writer.writerow([gid] + [f"{graphs[gid][s] * 100:.2f}" for s in range(1, 100)])
    print(f"output/stat_scaling_curves.csv: {len(graphs)} curves, stat 1-99 (percent of scaling)")


def spell_label(spell):
    """Spell scaling as 'all:281' when every damage type matches, else one entry per type."""
    values = {t: round(v) for t, v in spell.items()}
    if not values:
        return ""
    if len(set(values.values())) == 1:
        return f"all:{next(iter(values.values()))}"
    return " ".join(f"{DAMAGE[t]}:{v}" for t, v in values.items() if v != 100)


def ar_command(weapons, args):
    stats = {a: getattr(args, a) for a in ATTRS}
    rows = []
    for w in weapons:
        if args.dlc == "only" and not w.dlc:
            continue
        if args.dlc == "exclude" and w.dlc:
            continue
        if args.type and args.type.lower() not in w.type.lower():
            continue
        if args.infusion and args.infusion.lower() != w.infusion.lower():
            continue
        if args.name and args.name.lower() not in w.name.lower():
            continue
        if w.max_level == 25:
            level = args.level
        elif w.max_level == 10:
            level = args.somber_level
        else:
            level = 0
        level = min(level, w.max_level)
        damage, status, spell, missing = attack_rating(
            w, level, stats, args.two_hand, args.penalty
        )
        parts = {DAMAGE[t]: math.floor(v) for t, v in damage.items()}
        rows.append(
            {
                "weapon": w.name,
                "type": w.type,
                "infusion": w.infusion,
                "dlc": "Y" if w.dlc else "",
                "level": f"+{level}",
                **{DAMAGE[t]: parts.get(DAMAGE[t], "") for t in DAMAGE},
                "ar_total": sum(parts.values()),
                "status": " ".join(
                    f"{STATUS[t]}:{math.floor(v)}" for t, v in status.items()
                ),
                "spell_scaling": spell_label(spell),
                "missing_reqs": ",".join(missing),
            }
        )
    rows.sort(key=lambda r: r["ar_total"], reverse=True)

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["weapon"])
            writer.writeheader()
            writer.writerows(rows)
        print(f"{args.csv}: {len(rows)} rows")
        return

    shown = rows[: args.top]
    if not shown:
        print("No weapons match.")
        return
    cols = list(shown[0])
    widths = {c: max(len(c), *(len(str(r[c])) for r in shown)) for c in cols}
    print("  ".join(c.ljust(widths[c]) for c in cols))
    for r in shown:
        print("  ".join(str(r[c]).ljust(widths[c]) for c in cols))
    print(f"\n{len(shown)} of {len(rows)} weapons shown.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build", help="write the CSV tables to output/")

    ar = sub.add_parser("ar", help="attack rating for every weapon at the stats you give")
    for a, default in zip(ATTRS, (20, 20, 10, 10, 10)):
        ar.add_argument(f"--{a}", type=int, default=default)
    ar.add_argument("--level", type=int, default=25, help="smithing level for standard weapons (0-25)")
    ar.add_argument("--somber-level", type=int, default=10, help="level for somber weapons (0-10)")
    ar.add_argument("--two-hand", action="store_true", help="apply the 1.5x Strength bonus")
    ar.add_argument("--penalty", type=float, default=0.4, help="damage penalty for unmet requirements")
    ar.add_argument("--type", help="weapon type contains this text, e.g. katana")
    ar.add_argument("--infusion", help="exact infusion, e.g. Keen, Unique")
    ar.add_argument("--name", help="weapon name contains this text")
    ar.add_argument("--dlc", choices=["any", "only", "exclude"], default="any")
    ar.add_argument("--top", type=int, default=25)
    ar.add_argument("--csv", help="write all matching rows to this CSV instead of printing")
    args = parser.parse_args()

    weapons, graphs, tiers = load()
    if args.command == "build":
        build(weapons, graphs, tiers)
    else:
        for a in ATTRS:
            if not 1 <= getattr(args, a) <= 99:
                sys.exit(f"--{a} must be between 1 and 99")
        ar_command(weapons, args)


if __name__ == "__main__":
    main()
