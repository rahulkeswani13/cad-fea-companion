# Material properties table (F09)

Room-temperature handbook / datasheet values used by the `compare_materials`
tool and the `material` design-program parameter. Source of truth:
`data/materials.json` (ADR-010); this page mirrors those numbers so answers can
cite them. `tests/test_materials.py` asserts the two stay in sync.

**Scope caveat (solver honesty):** these are *bulk* room-temperature values —
not as-built additive-manufacturing allowables. Fatigue, temperature
dependence, moisture uptake (PA12), and build-orientation knockdowns are **not
verified** anywhere in this repo. Scaled comparisons assume linear elasticity:
stress is taken as E-independent, deflection scales with the modulus ratio.

## Summary

| Material | id | E | nu | Density | Yield (Rp0.2) | Cost class |
|---|---|---|---|---|---|---|
| Al 6061-T6 | `al6061t6` | 69 GPa | 0.33 | 2700 kg/m^3 | 276 MPa | low |
| Al 7075-T6 | `al7075t6` | 71.7 GPa | 0.33 | 2810 kg/m^3 | 503 MPa | medium |
| Ti-6Al-4V (Grade 5, annealed) | `ti6al4v` | 113.8 GPa | 0.342 | 4430 kg/m^3 | 880 MPa | high |
| PA12 (nylon, SLS, dry) | `pa12` | 1.8 GPa | 0.40 | 1010 kg/m^3 | 45 MPa | low |
| Steel-Generic | `steel` | 210 GPa | 0.30 | 7900 kg/m^3 | 250 MPa | low |

## Al 6061-T6 (`al6061t6`)

- Young's modulus: 69 GPa (MatWeb: Aluminum Al 6061-T6, room temperature)
- Density: 2700 kg/m^3 (MatWeb: Aluminum Al 6061-T6)
- Yield: 276 MPa (MatWeb / MMPDS: 6061-T6 Rp0.2)
- Workhorse aluminum alloy: good machinability and weldability, moderate
  strength. Default material for the brake pedal in this repo.

## Al 7075-T6 (`al7075t6`)

- Young's modulus: 71.7 GPa (MatWeb: Aluminum Al 7075-T6, room temperature)
- Density: 2810 kg/m^3 (MatWeb: Aluminum Al 7075-T6)
- Yield: 503 MPa (MatWeb / MMPDS: 7075-T6 Rp0.2)
- High-strength aerospace aluminum; ~1.8x the yield of 6061-T6 at similar
  density, but lower fracture toughness and poor weldability.

## Ti-6Al-4V Grade 5, annealed (`ti6al4v`)

- Young's modulus: 113.8 GPa (MatWeb: Titanium Ti-6Al-4V Grade 5 annealed, RT)
- Density: 4430 kg/m^3 (MatWeb: Titanium Ti-6Al-4V)
- Yield: 880 MPa (MatWeb / MMPDS: Ti-6Al-4V annealed Rp0.2)
- Best strength-to-weight of the table; ~56% denser than aluminum but 3.2x
  the yield. High material + machining cost; the classic AM/lattice material.
  Aliases: `ti`, `ti64`, `titanium`, `grade5`.

## PA12 nylon, SLS, dry (`pa12`)

- Young's modulus: 1.8 GPa (MatWeb / EOS PA12 datasheet, dry, room temp)
- Density: 1010 kg/m^3 (EOS PA12 datasheet)
- Yield: 45 MPa (EOS / MatWeb PA12, dry)
- Laser-sintered polymer: cheapest per part and lightest, but E is ~38x lower
  than aluminum — **deflections leave the small-strain regime**, so linearly
  scaled PA12 deflection is NOT VERIFIED; run a live solve. Moisture-dependent.

## Steel-Generic (`steel`)

- Young's modulus: 210 GPa, nu 0.30 (FreeCAD material database: Steel-Generic)
- Density: 7900 kg/m^3 (FreeCAD material database: Steel-Generic)
- Yield: 250 MPa (typical mild steel S235; not part of the FreeCAD card)
- FreeCAD's generic steel card — the pre-F09 default for the cantilever, kept
  as that part's default for backward compatibility.

## Using materials

- Ask "compare Ti vs Al" -> the `compare_materials` tool scales the best
  available run per material and cites the sources above per row.
- Change a part's material: `update_design_program` with
  `changes={"material": "ti6al4v"}` — rebuild + revision bump; mass updates
  with density, safety factor with the new yield.
- Unknown ids fail with one correction listing every valid material.
