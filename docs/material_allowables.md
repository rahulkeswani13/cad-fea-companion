# Material allowables cheat-sheet (demo values)

These are **approximate teaching values**, not design allowables for production parts.

## Mild / structural steel (approx.)

- Young's modulus `E`: 200–210 GPa
- Poisson's ratio `nu`: 0.29–0.30
- Density: ~7850 kg/m^3
- Typical yield strength (Fy): **250 MPa** (A36-like ballpark)
- Ultimate strength (Fu): often 400+ MPa depending on grade

## Aluminum 6061-T6 (approx.)

- `E`: ~69 GPa
- Yield: ~240–276 MPa
- Density: ~2700 kg/m^3

## Safety framing for chat answers

- If max von Mises is **under 50 MPa**, it is comfortably below mild-steel yield (~250 MPa) for the cantilever demo.
- The default cantilever demo with `100 N` on `100x20x5 mm` reaches about **120 MPa**, which is still below 250 MPa yield but **above 50 MPa**.
- Engine-mount demo (Al 6061-T6, ~276 MPa yield): target **safety factor ≥ 1.5** on max von Mises for the 20000 N pad-load compare step.
- Always state assumptions (geometry, load direction, material grade) when comparing stress to a limit.

## Units

- Companion tools use millimeters for geometry and newtons for force.
- Stress is reported in MPa (`N/mm^2`).
