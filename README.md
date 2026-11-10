# Elden Ring weapon tables

Flat tables of every weapon (including shields, staves, seals, and Shadow of the Erdtree weapons),
expanded across every infusion and every smithing level. Use them to plan builds.

Data: Elden Ring 1.17 vanilla param data, taken from
[ThomasJClark/elden-ring-weapon-calculator](https://github.com/ThomasJClark/elden-ring-weapon-calculator)
(MIT, license in `data/`). `scripts/er_weapons.py` expands it. No dependencies beyond Python 3.

## Tables (`output/`)

| File | Rows | One row per |
|---|---|---|
| `weapons_by_level.csv` | 82,736 | weapon × infusion × smithing level (+0 to +25, or +0 to +10 for somber) |
| `weapons_summary.csv` | 3,296 | weapon × infusion, with +0 and max level side by side |
| `stat_scaling_curves.csv` | 11 | scaling curve; columns are stat 1–99, values are percent of the scaling value |

Columns in `weapons_by_level.csv`:

- `weapon`, `base_weapon`, `type`, `infusion`, `dlc`, `upgrade_path` (Smithing, Somber, None), `level`, `max_level`
- `req_str` … `req_arc`: attribute requirements
- `dmg_phy`, `dmg_mag`, `dmg_fire`, `dmg_ltng`, `dmg_holy`: base damage at that level, before stat scaling
- `scl_str` … `scl_arc`: scaling letter. `scl_*_val`: the number behind the letter (A is 1.4 and up, S is 1.75 and up)
- `status_*`: status buildup (bleed, poison, rot, frost, sleep, madness, death blight)
- `scales_with`: which stats feed each damage type, e.g. `phy:str+dex mag:int`
- `curves_phy_mag_fire_ltng_holy`: scaling curve ID per damage type (see `stat_scaling_curves.csv`)
- `paired`: no two-handing bonus. `spell_tool`: sorcery and/or incantation catalyst

`infusion` is `Unique` for weapons that cannot take an Ash of War infusion.

## Attack rating for your stats

```
python3 -I scripts/er_weapons.py ar --str 40 --dex 40 --int 9 --fai 9 --arc 9 \
    --level 25 --somber-level 10 --type katana --dlc exclude --top 20
```

Options: `--two-hand`, `--infusion Keen`, `--name moonveil`, `--dlc only|exclude`, `--csv out.csv`
(writes every match instead of printing). Run `python3 -I scripts/er_weapons.py build` to
regenerate `output/`.

The AR math follows the source project: scaling is the sum of (scaling value × curve value) per
stat, unmet requirements replace the bonus with a 40% penalty, and two-handing multiplies Strength
by 1.5 (rounded down), except for paired weapons.

## The original calculator (`calculator/`)

A copy of [ThomasJClark/elden-ring-weapon-calculator](https://github.com/ThomasJClark/elden-ring-weapon-calculator)
at commit `3539d87` (MIT, see `calculator/COPYING`), without its git history. Its web app lists
weapons by your stats, with AR and status buildup. Run it with `yarn install && yarn start` inside
`calculator/`, or use the hosted version at [eldenring.tclark.io](https://eldenring.tclark.io/).

To check `scripts/er_weapons.py` against that project's own code (needs Node 22.6+):

```
node --experimental-strip-types scripts/crosscheck_ref.mjs data/regulation-vanilla-v1.17.json ref.json
python3 -I scripts/crosscheck_compare.py ref.json
```

It compares damage, status buildup, spell scaling, and unmet requirements for all 3,296 weapons across
six stat spreads, one- and two-handed, at +0, +7, and max level. The comparison script's plumbing
is tested on synthetic data. The reference run itself has not been done.

## Checks and limits

- Checked against the Fextralife Uchigatana and Moonveil pages (wiki values are rounded down,
  these tables keep decimals). Read in full from the page: Uchigatana Standard +0/+10/+25, Heavy +25,
  Keen +25, and Moonveil +0/+10. All match on damage and scaling letters. Keen +0/+10, Quality,
  Fire, Lightning, Sacred, Magic, and Cold variants also match, but those figures came from a
  partly summarized read of the page.
- The AR function was **not** cross-checked against the source project's own code. Running that
  code was blocked in the session that built this. Run the cross-check above, or compare a few
  weapons in the [tarnished.dev calculator](https://tarnished.dev/weapon-calculator). Two outside
  spell-scaling figures (Albinauric Staff 327, Carian Regal Scepter 373 at 80 Int, from a Reddit
  build post) match this function within a point.
- Not in this data: weight, guard negation, stability, critical modifier, skills, and
  weapon-specific passive effects other than status buildup.
- Shadow of the Erdtree weapons are flagged `dlc`. The Scadutree Blessing damage bonus is not
  modeled.
- Patch 1.17 vanilla only. Later patches need new source data.
