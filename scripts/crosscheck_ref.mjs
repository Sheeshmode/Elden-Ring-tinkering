// Reference run: the calculator's own TypeScript (calculator/src) on the vanilla data.
// Needs Node 22.6+.
//
//   node --experimental-strip-types scripts/crosscheck_ref.mjs data/regulation-vanilla-v1.17.json ref.json
//   python3 -I scripts/crosscheck_compare.py ref.json
//
// Writes one row per weapon x stat spread x hand x level (zero, +7, max):
//   [weaponIndex, spreadIndex, twoHanding, level, attackPower, spellScaling, ineffectiveAttributes]
import fs from "node:fs";

const src = new URL("../calculator/src/", import.meta.url);
const { decodeRegulationData } = await import(new URL("regulationData.ts", src));
const { default: getWeaponAttack } = await import(new URL("calculator/calculator.ts", src));

const [dataPath, outPath] = process.argv.slice(2);
if (!dataPath || !outPath) {
  console.error("usage: crosscheck_ref.mjs <regulation.json> <out.json>");
  process.exit(1);
}
const data = JSON.parse(fs.readFileSync(dataPath, "utf8"));
const spreads = JSON.parse(
  fs.readFileSync(new URL("crosscheck_spreads.json", import.meta.url), "utf8"),
);
const weapons = decodeRegulationData(data);

const out = [];
spreads.forEach((attributes, si) => {
  for (const twoHanding of [false, true]) {
    for (const levelSelector of ["zero", "mid", "max"]) {
      weapons.forEach((weapon, wi) => {
        const max = weapon.attack.length - 1;
        const upgradeLevel =
          levelSelector === "zero" ? 0 : levelSelector === "max" ? max : Math.min(7, max);
        const r = getWeaponAttack({ weapon, attributes, twoHanding, upgradeLevel });
        out.push([
          wi,
          si,
          twoHanding ? 1 : 0,
          upgradeLevel,
          r.attackPower,
          r.spellScaling,
          r.ineffectiveAttributes,
        ]);
      });
    }
  }
});
fs.writeFileSync(outPath, JSON.stringify(out));
console.log("reference rows:", out.length);
