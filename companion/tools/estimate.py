"""F07 pre-flight analytical estimates: expected-vs-actual with divergence flag.

Rules (ADR-007):

Every solve carries an ``expected_vs_actual`` block: a closed-form beam
idealization computed from the part's design constants is compared against the
returned max von Mises. The comparison annotates only — it never blocks or
rewrites a solve result (solver honesty: state what was estimated, the method,
and what was not verified).

Divergence band: actual/expected inside [0.33, 3.0] is accepted noise for a
beam idealization of a real bracket (stress concentrations at holes, coarse
tets under-predicting peaks). Outside the band the ``divergence_flag`` fires —
a prompt to re-check mesh size and the idealization assumptions, not proof
that either number is wrong.

Lattice variants compare against the solid-section estimate; the ``caveat``
key says so explicitly.
"""

from __future__ import annotations

import math
from typing import Any

from companion.tools import brake_pedal as bp
from companion.tools import uav_arm as ua

DIVERGENCE_BAND = (0.33, 3.0)


def brake_pedal_expected_mpa(force_n: float) -> tuple[float, str]:
    """Overhang cantilever from the nearest support (clevis ring).

    Load F at the footpad center, arm L = |footpad - clevis|, rectangular
    section b = 2*arm_half (the connector bar width from build_w_outer) x
    h = pedal thickness. The pivot support makes the real part stiffer, so
    this is the conservative end of the band.
    """
    length_mm = math.hypot(
        bp.FOOTPAD_CX - bp.CLEVIS_XY[0], bp.FOOTPAD_CY - bp.CLEVIS_XY[1]
    )
    arm_half = max(16.0, bp.RIM_MM * 3.0 + 6.0)  # mirrors build_w_outer
    b = 2.0 * arm_half
    h = bp.THICKNESS_Z
    sigma = 6.0 * force_n * length_mm / (b * h * h)
    assumptions = (
        f"overhang cantilever from the clevis ring (L={length_mm:.0f} mm), "
        f"rectangular section {b:.0f} x {h:.0f} mm, tip load at the footpad; "
        "pivot support, holes, fillets, and lattice fill ignored"
    )
    return sigma, assumptions


def cantilever_expected_mpa(
    length_mm: float, width_mm: float, height_mm: float, force_n: float
) -> tuple[float, str]:
    """Euler-Bernoulli cantilever, tip load, weak-axis bending: 6FL/(b h^2).

    Same reference as ``cad_fea.analytical_cantilever_stress`` (tests
    cross-check the two stay equal); kept local to avoid an import cycle.
    """
    sigma = 6.0 * force_n * length_mm / (width_mm * height_mm * height_mm)
    assumptions = (
        "Euler-Bernoulli cantilever, tip load, bending about the weak axis "
        "(sigma = 6FL/(b h^2))"
    )
    return sigma, assumptions


def uav_arm_expected_mpa(arm_length_mm: float, force_n: float) -> tuple[float, str]:
    """UAV arm as a cantilever from the boss face, tip load at the ring center.

    Bending about the weak (Z) axis of the ROOT section — the tapered arm only
    gets thicker toward the root, so this is the conservative end of the band.
    """
    length_mm = float(arm_length_mm) + ua.RING_OR - ua.RING_BITE_MM
    b = ua.ARM_ROOT_W
    h = ua.ARM_ROOT_H
    sigma = 6.0 * force_n * length_mm / (b * h * h)
    assumptions = (
        f"cantilever from the boss face (L={length_mm:.0f} mm to the ring "
        f"center), rectangular root section {b:.0f} x {h:.0f} mm, transverse "
        "tip load along Z; taper, bolt holes, fillets, and the solid "
        "boss/ring material ignored"
    )
    return sigma, assumptions


def expected_vs_actual(
    part: str | None,
    geometry: dict[str, Any] | None,
    force_n: float,
    actual_mpa: Any,
) -> dict[str, Any] | None:
    """Build the ``expected_vs_actual`` block for a solve result.

    Returns None for unknown parts (nothing honest to estimate). Missing or
    non-finite actuals keep the expected value and set ratio/divergence to
    None instead of guessing.
    """
    geometry = geometry or {}
    part = str(part or "").strip()
    try:
        if part == "brake_pedal":
            expected, assumptions = brake_pedal_expected_mpa(float(force_n))
        elif part == "cantilever":
            expected, assumptions = cantilever_expected_mpa(
                float(geometry.get("length_mm", 100.0)),
                float(geometry.get("width_mm", 20.0)),
                float(geometry.get("height_mm", 5.0)),
                float(force_n),
            )
        elif part == "uav_arm":
            expected, assumptions = uav_arm_expected_mpa(
                float(geometry.get("arm_length_mm", ua.ARM_LENGTH_MM)),
                float(force_n),
            )
        else:
            return None
    except (TypeError, ValueError):
        return None

    out: dict[str, Any] = {
        "expected_mpa": round(expected, 2),
        "actual_mpa": None,
        "ratio": None,
        "band": list(DIVERGENCE_BAND),
        "divergence_flag": None,
        "method": "analytical_beam_idealization",
        "assumptions": assumptions,
    }
    try:
        actual = float(actual_mpa)
        if math.isfinite(actual) and actual > 0.0:
            out["actual_mpa"] = round(actual, 2)
            ratio = actual / expected if expected > 0.0 else None
            if ratio is not None:
                out["ratio"] = round(ratio, 3)
                out["divergence_flag"] = not (
                    DIVERGENCE_BAND[0] <= ratio <= DIVERGENCE_BAND[1]
                )
    except (TypeError, ValueError):
        pass

    web_type = str(geometry.get("web_type") or "").strip()
    if web_type and web_type != "solid":
        out["caveat"] = (
            "estimate assumes the solid section; lattice variants carry less "
            "material and can sit outside this band by design"
        )
    return out
