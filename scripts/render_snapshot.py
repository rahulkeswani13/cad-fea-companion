#!/usr/bin/env python
"""Render a binary/ASCII STL to a PNG snapshot (text-to-cad snapshot rule).

Reviewing a rendered snapshot of every created artifact is mandatory in the
text-to-cad workflow; this is the deterministic, headless version for the
companion: parse the exported STL (pure Python — no FreeCAD), draw the
triangles with matplotlib, and write a PNG next to the workspace for the
demo checklist. Multimodal agent review (F16) builds on these snapshots.

Usage: .venv/bin/python scripts/render_snapshot.py <model.stl> [out.png]
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

MAX_TRIANGLES = 400_000  # guard: coarse demo meshes are ~10k facets


def read_binary_stl(path: Path) -> list[tuple[tuple[float, float, tuple[float, float, float]]]]:
    """[(normal, (v1, v2, v3))] from a binary STL."""
    blob = path.read_bytes()
    if len(blob) < 84:
        raise ValueError(f"{path} too short for a binary STL")
    count = struct.unpack_from("<I", blob, 80)[0]
    if count > MAX_TRIANGLES:
        raise ValueError(f"{path} declares {count} facets (limit {MAX_TRIANGLES})")
    if len(blob) < 84 + count * 50:
        raise ValueError(f"{path} truncated for {count} facets")
    tris = []
    off = 84
    for _ in range(count):
        nx, ny, nz, x1, y1, z1, x2, y2, z2, x3, y3, z3 = struct.unpack_from(
            "<12fH", blob, off
        )
        off += 50
        tris.append(
            (
                (nx, ny, nz),
                ((x1, y1, z1), (x2, y2, z2), (x3, y3, z3)),
            )
        )
    return tris


def read_ascii_stl(path: Path):
    """Best-effort facet parse for ASCII STLs (vertex lines only)."""
    verts: list[tuple[float, float, float]] = []
    tris = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split()
        if len(parts) == 4 and parts[0] == "vertex":
            verts.append(tuple(float(v) for v in parts[1:4]))
            if len(verts) == 3:
                tris.append(((0.0, 0.0, 1.0), tuple(verts)))
                verts = []
    if not tris:
        raise ValueError(f"{path} contains no STL facets")
    return tris


def read_stl(path: Path):
    head = path.read_bytes()[:512].lstrip()
    if head[:5] == b"solid" and b"facet" in head:
        return read_ascii_stl(path)
    return read_binary_stl(path)


def render(tris, out_png: Path, title: str) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    except ImportError:
        print("matplotlib is required: .venv/bin/pip install matplotlib")
        raise SystemExit(2)

    fig = plt.figure(figsize=(10, 7), dpi=120)
    ax = fig.add_subplot(projection="3d")
    polys = [tri for _, tri in tris]
    coll = Poly3DCollection(polys, facecolor="#9fc4e8", edgecolor="#33506b", linewidths=0.1)
    ax.add_collection3d(coll)

    xs = [v[0] for tri in polys for v in tri]
    ys = [v[1] for tri in polys for v in tri]
    zs = [v[2] for tri in polys for v in tri]
    lo = [min(xs), min(ys), min(zs)]
    hi = [max(xs), max(ys), max(zs)]
    span = max(h - l for l, h in zip(lo, hi))
    centers = [(l + h) / 2.0 for l, h in zip(lo, hi)]
    ax.set_xlim(centers[0] - span / 2, centers[0] + span / 2)
    ax.set_ylim(centers[1] - span / 2, centers[1] + span / 2)
    ax.set_zlim(centers[2] - span / 2, centers[2] + span / 2)
    ax.set_box_aspect((1, 1, 1))
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")
    ax.set_zlabel("Z (mm)")
    ax.set_title(f"{title} — {len(polys)} facets")
    ax.view_init(elev=22, azim=-58)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, bbox_inches="tight")
    plt.close(fig)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    stl = Path(argv[1])
    if not stl.exists():
        print(f"no such file: {stl}")
        return 2
    out = Path(argv[2]) if len(argv) > 2 else stl.with_suffix(".snapshot.png")
    tris = read_stl(stl)
    render(tris, out, stl.stem)
    print(f"snapshot: {out} ({len(tris)} facets)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
