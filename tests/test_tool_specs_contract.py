"""H11: wire-format contract tests — TOOL_SPECS is frozen by snapshot.

Any accidental schema drift (changed default, range, description, field, or
tool order) fails this test. To change the wire format *deliberately*, edit
``companion/tools/tool_schemas.py`` and re-bless the snapshot:

    GEMINI_API_KEY= .venv/bin/python -c "import json,sys; sys.path.insert(0,'.'); \
from companion.tools.cad_fea import TOOL_SPECS; \
open('tests/snapshots/tool_specs.json','w',encoding='utf-8').write(json.dumps(TOOL_SPECS, indent=2, ensure_ascii=False) + '\n')"

then include the snapshot diff in the commit (ADR-013 / ADR-006: schema
changes are deliberate decisions, never side effects).
"""

from __future__ import annotations

import json
from pathlib import Path

from companion.tools.cad_fea import TOOL_SPECS

SNAPSHOT_PATH = Path(__file__).parent / "snapshots" / "tool_specs.json"

# Numeric geometry params whose program floors must stay visible in the wire
# format (ADR-004 ranges + ADR-011 meshable minimum).
_FLOOR_PROPERTIES = (
    ("create_brake_pedal", "cell_size_mm"),
    ("create_brake_pedal", "strut_radius_mm"),
    ("create_uav_arm", "arm_length_mm"),
    ("create_uav_arm", "cell_size_mm"),
    ("create_uav_arm", "strut_radius_mm"),
    ("create_cantilever", "length_mm"),
    ("create_cantilever", "width_mm"),
    ("create_cantilever", "height_mm"),
)


def test_tool_specs_match_frozen_snapshot():
    snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    assert TOOL_SPECS == snapshot, (
        "TOOL_SPECS drifted from the frozen wire-format snapshot "
        f"({SNAPSHOT_PATH}). If the change is deliberate, edit "
        "companion/tools/tool_schemas.py, then re-bless the snapshot with the "
        "command in tests/test_tool_specs_contract.py's module docstring and "
        "commit the diff."
    )


def test_every_spec_keeps_the_wire_shape():
    assert len(TOOL_SPECS) == len({spec["name"] for spec in TOOL_SPECS})
    for spec in TOOL_SPECS:
        assert set(spec) == {"name", "description", "parameters"}, spec["name"]
        assert spec["description"].strip()
        assert spec["parameters"].get("type") == "object", spec["name"]
        for prop, schema in spec["parameters"].get("properties", {}).items():
            assert schema.get("description", "").strip(), (spec["name"], prop)


def test_program_floors_stay_in_the_wire_format():
    by_name = {spec["name"]: spec["parameters"]["properties"] for spec in TOOL_SPECS}
    for tool, prop in _FLOOR_PROPERTIES:
        schema = by_name[tool][prop]
        assert "minimum" in schema and "maximum" in schema, (tool, prop)
