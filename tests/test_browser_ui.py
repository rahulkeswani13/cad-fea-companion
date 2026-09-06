"""Browser UI automation tests using Playwright against mocked CAD/FEA companion server.

Tests all 36 demo prompts + 9 multi-turn feature journeys (45 total tests).
"""

from __future__ import annotations

import json

import re
import pytest
from playwright.sync_api import Page, expect


# --- Helper Functions ---

def wait_for_ui_ready(page: Page) -> None:
    """Waits for SSE stream to conclude and input box to re-enable."""
    expect(page.locator("#send")).to_be_enabled(timeout=6000)


def send_chat_prompt(page: Page, text: str) -> None:
    """Types a prompt into the chat box, clicks Send, and waits for readiness."""
    page.fill("#input", text)
    page.click("#send")
    wait_for_ui_ready(page)


def init_browser_session(page: Page, test_server_url: str) -> list[str]:
    """Navigates to the app and attaches a JS error listener."""
    errors: list[str] = []
    page.on("pageerror", lambda err: errors.append(err.message))
    page.goto(test_server_url)
    expect(page.locator("h1")).to_contain_text("CAD/FEA Chat Companion")
    return errors


# =========================================================================
# PART 1: 36 Isolated Single-Shot Prompt Tests
# =========================================================================

# --- Group 1: F01 Grounded RAG ---

def test_ui_f01_al6061_properties(page: Page, test_server_url: str):
    errors = init_browser_session(page, test_server_url)
    send_chat_prompt(page, "What is the yield strength and density of Al 6061-T6?")
    last_msg = page.locator(".msg.assistant").last
    expect(last_msg).to_contain_text("276 MPa")
    expect(last_msg).to_contain_text("docs/reference/materials.md")
    assert len(errors) == 0


def test_ui_f01_cantilever_analytical_formula(page: Page, test_server_url: str):
    errors = init_browser_session(page, test_server_url)
    send_chat_prompt(page, "What is the analytical bending stress formula for a rectangular cantilever beam?")
    last_msg = page.locator(".msg.assistant").last
    expect(last_msg).to_contain_text("6FL")
    assert len(errors) == 0


def test_ui_f01_structural_steel_modulus(page: Page, test_server_url: str):
    errors = init_browser_session(page, test_server_url)
    send_chat_prompt(page, "What Young's modulus should I assume for structural steel in this demo?")
    last_msg = page.locator(".msg.assistant").last
    expect(last_msg).to_contain_text("210 GPa")
    assert len(errors) == 0


def test_ui_f01_ti6al4v_allowables(page: Page, test_server_url: str):
    errors = init_browser_session(page, test_server_url)
    send_chat_prompt(page, "What are the allowable stress limits for Titanium Ti-6Al-4V?")
    last_msg = page.locator(".msg.assistant").last
    expect(last_msg).to_contain_text("880 MPa")
    assert len(errors) == 0


# --- Group 2: F02 Outcome Envelope ---

def test_ui_f02_solve_without_geometry(page: Page, test_server_url: str):
    errors = init_browser_session(page, test_server_url)
    send_chat_prompt(page, "Run an FEA solve without creating any geometry first.")
    last_msg = page.locator(".msg.assistant").last
    expect(last_msg).to_be_visible()
    expect(page.locator("#send")).to_be_enabled()
    assert len(errors) == 0


def test_ui_f02_unknown_tool_recovery(page: Page, test_server_url: str):
    errors = init_browser_session(page, test_server_url)
    send_chat_prompt(page, "Execute tool nonexistent_cad_generator.")
    last_msg = page.locator(".msg.assistant").last
    expect(last_msg).to_be_visible()
    assert len(errors) == 0


def test_ui_f02_cantilever_negative_length(page: Page, test_server_url: str):
    errors = init_browser_session(page, test_server_url)
    send_chat_prompt(page, "Create a cantilever beam with length -50 mm.")
    last_msg = page.locator(".msg.assistant").last
    expect(last_msg).to_contain_text("Rejected")
    assert len(errors) == 0


def test_ui_f02_pedal_negative_cell_size(page: Page, test_server_url: str):
    errors = init_browser_session(page, test_server_url)
    send_chat_prompt(page, "Create a brake pedal with cell size -5 mm.")
    last_msg = page.locator(".msg.assistant").last
    expect(last_msg).to_contain_text("Rejected")
    assert len(errors) == 0


# --- Group 3: F03 B-Rep Geometry Validation Gate ---

def test_ui_f03_self_intersecting_lattice_rejection(page: Page, test_server_url: str):
    errors = init_browser_session(page, test_server_url)
    send_chat_prompt(page, "Create a brake pedal with strut radius 8 mm and cell size 6 mm.")
    last_msg = page.locator(".msg.assistant").last
    expect(last_msg).to_contain_text("B-Rep Rejected")
    assert len(errors) == 0


def test_ui_f03_zero_height_cantilever(page: Page, test_server_url: str):
    errors = init_browser_session(page, test_server_url)
    send_chat_prompt(page, "Create a cantilever beam with height 0 mm.")
    last_msg = page.locator(".msg.assistant").last
    expect(last_msg).to_contain_text("B-Rep Rejected")
    assert len(errors) == 0


def test_ui_f03_invalid_web_type(page: Page, test_server_url: str):
    errors = init_browser_session(page, test_server_url)
    send_chat_prompt(page, "Create a brake pedal with invalid web type voronoi.")
    last_msg = page.locator(".msg.assistant").last
    expect(last_msg).to_contain_text("Invalid Web Type")
    assert len(errors) == 0


def test_ui_f03_explicit_validate_geometry(page: Page, test_server_url: str):
    errors = init_browser_session(page, test_server_url)
    send_chat_prompt(page, "Validate the current CAD geometry.")
    last_msg = page.locator(".msg.assistant").last
    expect(last_msg).to_contain_text("watertight")
    assert len(errors) == 0


# --- Group 4: F04 Design Program Layer ---

def test_ui_f04_baseline_pedal_init(page: Page, test_server_url: str):
    errors = init_browser_session(page, test_server_url)
    send_chat_prompt(page, "Create an X-truss brake pedal with 15 mm cells and solve 500 N.")
    last_msg = page.locator(".msg.assistant").last
    expect(last_msg).to_contain_text("21.8 MPa")
    assert len(errors) == 0


def test_ui_f04_parameter_update_and_rebuild(page: Page, test_server_url: str):
    errors = init_browser_session(page, test_server_url)
    send_chat_prompt(page, "Update the brake pedal cell size to 12 mm and re-solve.")
    last_msg = page.locator(".msg.assistant").last
    expect(last_msg).to_contain_text("12 mm")
    assert len(errors) == 0


def test_ui_f04_noop_idempotency(page: Page, test_server_url: str):
    errors = init_browser_session(page, test_server_url)
    send_chat_prompt(page, "Set the brake pedal cell size to 12 mm again.")
    last_msg = page.locator(".msg.assistant").last
    expect(last_msg).to_contain_text("No-Op")
    assert len(errors) == 0


def test_ui_f04_dry_run_preview(page: Page, test_server_url: str):
    errors = init_browser_session(page, test_server_url)
    send_chat_prompt(page, "Preview changing strut radius to 3.5 mm without applying.")
    last_msg = page.locator(".msg.assistant").last
    expect(last_msg).to_contain_text("Dry-Run")
    assert len(errors) == 0


# --- Group 5: F06 Spatial Run History ---

def test_ui_f06_latest_solve_spatial_stress(page: Page, test_server_url: str):
    errors = init_browser_session(page, test_server_url)
    send_chat_prompt(page, "What was the peak stress in the latest solve and where is it located?")
    last_msg = page.locator(".msg.assistant").last
    expect(last_msg).to_contain_text("coordinate")
    assert len(errors) == 0


def test_ui_f06_list_session_runs(page: Page, test_server_url: str):
    errors = init_browser_session(page, test_server_url)
    send_chat_prompt(page, "List all simulation runs in this session.")
    last_msg = page.locator(".msg.assistant").last
    expect(last_msg).to_contain_text("run_01")
    assert len(errors) == 0


def test_ui_f06_compare_two_runs(page: Page, test_server_url: str):
    errors = init_browser_session(page, test_server_url)
    send_chat_prompt(page, "Compare run 1 and run 2.")
    last_msg = page.locator(".msg.assistant").last
    expect(last_msg).to_contain_text("Run Comparison")
    assert len(errors) == 0


def test_ui_f06_hotspot_coordinates(page: Page, test_server_url: str):
    errors = init_browser_session(page, test_server_url)
    send_chat_prompt(page, "Show me the coordinate of the maximum von Mises stress on the brake pedal.")
    last_msg = page.locator(".msg.assistant").last
    expect(last_msg).to_contain_text("21.8 MPa")
    assert len(errors) == 0


# --- Group 6: F07 Analytical Closed-Form ---

def test_ui_f07_cantilever_solve_and_analytical(page: Page, test_server_url: str):
    errors = init_browser_session(page, test_server_url)
    send_chat_prompt(page, "Create a cantilever beam 100x20x5 mm and solve under 100 N.")
    last_msg = page.locator(".msg.assistant").last
    expect(last_msg).to_contain_text("120.0 MPa")
    assert len(errors) == 0


def test_ui_f07_expected_bending_stress_query(page: Page, test_server_url: str):
    errors = init_browser_session(page, test_server_url)
    send_chat_prompt(page, "What is the expected analytical bending stress for this cantilever?")
    last_msg = page.locator(".msg.assistant").last
    expect(last_msg).to_contain_text("120.0")
    assert len(errors) == 0


def test_ui_f07_pedal_analytical_estimate(page: Page, test_server_url: str):
    errors = init_browser_session(page, test_server_url)
    send_chat_prompt(page, "What is the analytical stress estimate for a brake pedal under 500 N?")
    last_msg = page.locator(".msg.assistant").last
    expect(last_msg).to_contain_text("23.4 MPa")
    assert len(errors) == 0


def test_ui_f07_fea_vs_analytical_divergence_check(page: Page, test_server_url: str):
    errors = init_browser_session(page, test_server_url)
    send_chat_prompt(page, "How does the 3D FEA stress compare to the beam theory estimate?")
    last_msg = page.locator(".msg.assistant").last
    expect(last_msg).to_contain_text("0.0% divergence")
    assert len(errors) == 0


# --- Group 7: F08 Automated Mesh Convergence ---

def test_ui_f08_pedal_mesh_convergence_study(page: Page, test_server_url: str):
    errors = init_browser_session(page, test_server_url)
    send_chat_prompt(page, "Run a mesh convergence study on the brake pedal.")
    last_msg = page.locator(".msg.assistant").last
    expect(last_msg).to_contain_text("Recommended Mesh")
    assert len(errors) == 0


def test_ui_f08_fcc_convergence_refusal(page: Page, test_server_url: str):
    errors = init_browser_session(page, test_server_url)
    send_chat_prompt(page, "Run a mesh convergence study on an FCC lattice pedal.")
    last_msg = page.locator(".msg.assistant").last
    expect(last_msg).to_contain_text("Refused")
    assert len(errors) == 0


def test_ui_f08_custom_mesh_sizes_study(page: Page, test_server_url: str):
    errors = init_browser_session(page, test_server_url)
    send_chat_prompt(page, "Run convergence on the cantilever at mesh sizes 4.0, 2.5, and 1.5 mm.")
    last_msg = page.locator(".msg.assistant").last
    expect(last_msg).to_contain_text("Recommended Mesh")
    assert len(errors) == 0


def test_ui_f08_deflection_mesh_sensitivity(page: Page, test_server_url: str):
    errors = init_browser_session(page, test_server_url)
    send_chat_prompt(page, "How does tip deflection change between the coarse and fine meshes?")
    last_msg = page.locator(".msg.assistant").last
    expect(last_msg).to_contain_text("1.69 mm")
    assert len(errors) == 0


# --- Group 8: F09 Material Selection ---

def test_ui_f09_ti_vs_al7075_trade_study(page: Page, test_server_url: str):
    errors = init_browser_session(page, test_server_url)
    send_chat_prompt(page, "Compare making the brake pedal from Titanium vs Aluminum 7075-T6.")
    last_msg = page.locator(".msg.assistant").last
    expect(last_msg).to_contain_text("Al 7075-T6")
    assert len(errors) == 0


def test_ui_f09_pa12_polymer_disclaimer(page: Page, test_server_url: str):
    errors = init_browser_session(page, test_server_url)
    send_chat_prompt(page, "What happens if we switch the brake pedal material to PA12 Nylon?")
    last_msg = page.locator(".msg.assistant").last
    expect(last_msg).to_contain_text("NOT VERIFIED")
    assert len(errors) == 0


def test_ui_f09_unknown_alloy_rejection(page: Page, test_server_url: str):
    errors = init_browser_session(page, test_server_url)
    send_chat_prompt(page, "Change the brake pedal material to Vibranium-X.")
    last_msg = page.locator(".msg.assistant").last
    expect(last_msg).to_be_visible()
    assert len(errors) == 0


def test_ui_f09_material_program_rebuild(page: Page, test_server_url: str):
    errors = init_browser_session(page, test_server_url)
    send_chat_prompt(page, "Set the pedal material to 7075 aluminum and rebuild.")
    last_msg = page.locator(".msg.assistant").last
    expect(last_msg).to_contain_text("Al 7075-T6")
    assert len(errors) == 0


# --- Group 9: F26 Flagship UAV Arm ---

def test_ui_f26_solid_uav_arm_120n_solve(page: Page, test_server_url: str):
    errors = init_browser_session(page, test_server_url)
    send_chat_prompt(page, "Create a solid aluminum UAV arm and solve it under a 120 N tip thrust.")
    last_msg = page.locator(".msg.assistant").last
    expect(last_msg).to_contain_text("44.6 MPa")
    expect(last_msg).to_contain_text("157 g")
    assert len(errors) == 0


def test_ui_f26_uav_arm_generative_xtruss(page: Page, test_server_url: str):
    errors = init_browser_session(page, test_server_url)
    send_chat_prompt(page, "Change the UAV arm to an X-truss lattice with 12 mm cells and 1.8 mm struts and solve.")
    last_msg = page.locator(".msg.assistant").last
    expect(last_msg).to_contain_text("130 g")
    assert len(errors) == 0


def test_ui_f26_strut_radius_floor_rejection(page: Page, test_server_url: str):
    errors = init_browser_session(page, test_server_url)
    send_chat_prompt(page, "Set UAV arm strut radius to 0.8 mm.")
    last_msg = page.locator(".msg.assistant").last
    expect(last_msg).to_contain_text("Preflight Rejected")
    assert len(errors) == 0


def test_ui_f26_arm_length_scaling(page: Page, test_server_url: str):
    errors = init_browser_session(page, test_server_url)
    send_chat_prompt(page, "Make the UAV arm 220 mm long and check new mass and stress.")
    last_msg = page.locator(".msg.assistant").last
    expect(last_msg).to_contain_text("220 mm")
    assert len(errors) == 0


# =========================================================================
# PART 2: 9 Multi-Turn Continuous Journey Tests
# =========================================================================

def test_journey_uav_arm_lifecycle(page: Page, test_server_url: str):
    """J1: Continuous 4-turn engineering arc on UAV Arm."""
    errors = init_browser_session(page, test_server_url)

    # Turn 1: Create baseline
    send_chat_prompt(page, "Create a solid aluminum UAV arm and solve it under a 120 N tip thrust.")
    expect(page.locator(".msg.assistant").last).to_contain_text("157 g")

    # Turn 2: Lightweight to X-truss
    send_chat_prompt(page, "Change the UAV arm to an X-truss lattice with 12 mm cells and 1.8 mm struts and solve.")
    expect(page.locator(".msg.assistant").last).to_contain_text("130 g")

    # Turn 3: Invalid strut rejection
    send_chat_prompt(page, "Set UAV arm strut radius to 0.8 mm.")
    expect(page.locator(".msg.assistant").last).to_contain_text("Preflight Rejected")

    # Turn 4: Parametric length scale
    send_chat_prompt(page, "Make the UAV arm 220 mm long and check new mass and stress.")
    expect(page.locator(".msg.assistant").last).to_contain_text("220 mm")

    assert len(errors) == 0


def test_journey_brake_pedal_optimization(page: Page, test_server_url: str):
    """J2: Brake pedal parametric optimization arc."""
    errors = init_browser_session(page, test_server_url)

    send_chat_prompt(page, "Create an X-truss brake pedal with 15 mm cells and solve 500 N.")
    expect(page.locator(".msg.assistant").last).to_contain_text("21.8 MPa")

    send_chat_prompt(page, "Update the brake pedal cell size to 12 mm and re-solve.")
    expect(page.locator(".msg.assistant").last).to_contain_text("12 mm")

    send_chat_prompt(page, "Set the brake pedal cell size to 12 mm again.")
    expect(page.locator(".msg.assistant").last).to_contain_text("No-Op")

    send_chat_prompt(page, "Preview changing strut radius to 3.5 mm without applying.")
    expect(page.locator(".msg.assistant").last).to_contain_text("Dry-Run")

    assert len(errors) == 0


def test_journey_mesh_convergence_study(page: Page, test_server_url: str):
    """J3: Mesh convergence validation journey."""
    errors = init_browser_session(page, test_server_url)

    send_chat_prompt(page, "Create a cantilever beam 100x20x5 mm and solve under 100 N.")
    send_chat_prompt(page, "Run convergence on the cantilever at mesh sizes 4.0, 2.5, and 1.5 mm.")
    expect(page.locator(".msg.assistant").last).to_contain_text("Recommended Mesh")

    send_chat_prompt(page, "How does tip deflection change between the coarse and fine meshes?")
    expect(page.locator(".msg.assistant").last).to_contain_text("1.69 mm")

    send_chat_prompt(page, "Run a mesh convergence study on an FCC lattice pedal.")
    expect(page.locator(".msg.assistant").last).to_contain_text("Refused")

    assert len(errors) == 0


def test_journey_material_selection_and_rebuild(page: Page, test_server_url: str):
    """J4: Material trade study & program rebuild."""
    errors = init_browser_session(page, test_server_url)

    send_chat_prompt(page, "Create an X-truss brake pedal with 15 mm cells and solve 500 N.")
    send_chat_prompt(page, "Compare making the brake pedal from Titanium vs Aluminum 7075-T6.")
    expect(page.locator(".msg.assistant").last).to_contain_text("Al 7075-T6")

    send_chat_prompt(page, "What happens if we switch the brake pedal material to PA12 Nylon?")
    expect(page.locator(".msg.assistant").last).to_contain_text("NOT VERIFIED")

    send_chat_prompt(page, "Set the pedal material to 7075 aluminum and rebuild.")
    expect(page.locator(".msg.assistant").last).to_contain_text("Al 7075-T6")

    assert len(errors) == 0


def test_journey_analytical_rigor(page: Page, test_server_url: str):
    """J5: Analytical formula vs 3D FEA cross-check."""
    errors = init_browser_session(page, test_server_url)

    send_chat_prompt(page, "Create a cantilever beam 100x20x5 mm and solve under 100 N.")
    send_chat_prompt(page, "What is the analytical bending stress formula for a rectangular cantilever beam?")
    expect(page.locator(".msg.assistant").last).to_contain_text("6FL")

    send_chat_prompt(page, "How does the 3D FEA stress compare to the beam theory estimate?")
    expect(page.locator(".msg.assistant").last).to_contain_text("0.0% divergence")

    send_chat_prompt(page, "What is the analytical stress estimate for a brake pedal under 500 N?")
    expect(page.locator(".msg.assistant").last).to_contain_text("23.4 MPa")

    assert len(errors) == 0


def test_journey_spatial_run_history(page: Page, test_server_url: str):
    """J6: Multi-run logging and coordinate extraction."""
    errors = init_browser_session(page, test_server_url)

    send_chat_prompt(page, "Create a cantilever beam 100x20x5 mm and solve under 100 N.")
    send_chat_prompt(page, "Create a solid aluminum UAV arm and solve it under a 120 N tip thrust.")
    send_chat_prompt(page, "List all simulation runs in this session.")
    expect(page.locator(".msg.assistant").last).to_contain_text("run_01")

    send_chat_prompt(page, "What was the peak stress in the latest solve and where is it located?")
    expect(page.locator(".msg.assistant").last).to_contain_text("coordinate")

    assert len(errors) == 0


def test_journey_brep_guardrails(page: Page, test_server_url: str):
    """J7: B-Rep geometry rejection & recovery."""
    errors = init_browser_session(page, test_server_url)

    send_chat_prompt(page, "Create a brake pedal with invalid web type voronoi.")
    expect(page.locator(".msg.assistant").last).to_contain_text("Invalid Web Type")

    send_chat_prompt(page, "Create a brake pedal with strut radius 8 mm and cell size 6 mm.")
    expect(page.locator(".msg.assistant").last).to_contain_text("B-Rep Rejected")

    send_chat_prompt(page, "Create an X-truss brake pedal with 15 mm cells and solve 500 N.")
    expect(page.locator(".msg.assistant").last).to_contain_text("21.8 MPa")

    send_chat_prompt(page, "Validate the current CAD geometry.")
    expect(page.locator(".msg.assistant").last).to_contain_text("watertight")

    assert len(errors) == 0


def test_journey_outcome_envelope_recovery(page: Page, test_server_url: str):
    """J8: F02 error recovery and graceful retry."""
    errors = init_browser_session(page, test_server_url)

    send_chat_prompt(page, "Run an FEA solve without creating any geometry first.")
    send_chat_prompt(page, "Execute tool nonexistent_cad_generator.")
    send_chat_prompt(page, "Create a cantilever beam with length -50 mm.")
    expect(page.locator(".msg.assistant").last).to_contain_text("Rejected")

    send_chat_prompt(page, "Create a cantilever beam 100x20x5 mm and solve under 100 N.")
    expect(page.locator(".msg.assistant").last).to_contain_text("120.0 MPa")

    assert len(errors) == 0


def test_journey_rag_and_out_of_domain(page: Page, test_server_url: str):
    """J9: Grounded materials RAG and out-of-domain refusal."""
    errors = init_browser_session(page, test_server_url)

    send_chat_prompt(page, "What is the yield strength and density of Al 6061-T6?")
    expect(page.locator(".msg.assistant").last).to_contain_text("276 MPa")

    send_chat_prompt(page, "What are the allowable stress limits for Titanium Ti-6Al-4V?")
    expect(page.locator(".msg.assistant").last).to_contain_text("880 MPa")

    send_chat_prompt(page, "What Young's modulus should I assume for structural steel in this demo?")
    expect(page.locator(".msg.assistant").last).to_contain_text("210 GPa")

    send_chat_prompt(page, "What is the weather in Tokyo?")
    expect(page.locator(".msg.assistant").last).to_contain_text("do not have access")

    assert len(errors) == 0


# =========================================================================
# PART 3: React console at /app (ADR-015) — UI mechanics, mocked LLM
# =========================================================================

def _console_errors(page: Page, test_server_url: str) -> list[str]:
    """Opens /app with a JS-error listener attached."""
    errors: list[str] = []
    page.on("pageerror", lambda err: errors.append(err.message))
    page.goto(test_server_url + "/app")
    expect(page.locator("h1")).to_contain_text("CAD/FEA Companion")
    return errors


def test_console_shell_loads(page: Page, test_server_url: str):
    errors = _console_errors(page, test_server_url)
    expect(page.get_by_test_id("status-readout")).to_be_visible()
    expect(page.get_by_test_id("rail-left")).to_be_visible()
    expect(page.get_by_test_id("rail-right")).to_be_visible()
    expect(page.get_by_test_id("design-program")).to_be_visible()
    expect(page.get_by_test_id("run-history")).to_be_visible()
    expect(page.get_by_test_id("solver-status")).to_be_visible()
    assert len(errors) == 0


def test_console_prompt_library_renders(page: Page, test_server_url: str):
    errors = _console_errors(page, test_server_url)
    library = page.get_by_test_id("prompt-library")
    expect(library).to_be_visible()
    # Task-oriented groups (ADR-017 PR 2); validation group present but collapsed.
    expect(library).to_contain_text("Create a part", ignore_case=True)
    expect(library).to_contain_text("Run analysis", ignore_case=True)
    assert len(errors) == 0


def test_console_dropdown_inserts_prompt(page: Page, test_server_url: str):
    errors = _console_errors(page, test_server_url)
    page.get_by_test_id("prompts-button").click()
    menu = page.get_by_test_id("prompt-menu")
    expect(menu).to_be_visible()
    expect(menu).to_contain_text("Engineering help", ignore_case=True)
    menu.get_by_role("button").filter(has_text="Al 6061-T6 yield strength").first.click()
    value = page.get_by_test_id("composer-input").input_value()
    assert "yield strength" in value.lower()
    assert len(errors) == 0


def test_console_palette_sends_prompt(page: Page, test_server_url: str):
    """ADR-017 PR 2: palette Enter fills the composer — the send shortcut
    is retired (only Send executes)."""
    errors = _console_errors(page, test_server_url)
    page.keyboard.press("ControlOrMeta+k")
    palette = page.get_by_test_id("command-palette")
    expect(palette).to_be_visible()
    palette.get_by_role("textbox").fill("convergence")
    page.keyboard.press("Enter")
    value = page.get_by_test_id("composer-input").input_value()
    assert "convergence" in value.lower()
    assert page.get_by_test_id("msg-user").count() == 0
    assert len(errors) == 0


def test_console_walkthrough_run_step(page: Page, test_server_url: str):
    """ADR-017 PR 2: guided journeys replace feature tours — manual
    navigation (Previous/Next), explicit step position, and Use prompt
    fills the composer without sending."""
    errors = _console_errors(page, test_server_url)
    page.get_by_test_id("journey-list").get_by_role("button").filter(
        has_text="UAV arm design iteration"
    ).first.click()
    detail = page.get_by_test_id("journey-detail")
    expect(detail).to_be_visible()
    expect(detail).to_contain_text("step 1 of 5")
    expect(detail).to_contain_text("prerequisites", ignore_case=True)

    prev = page.get_by_test_id("journey-prev")
    nxt = page.get_by_test_id("journey-next")
    expect(prev).to_be_disabled()
    nxt.click()
    expect(detail).to_contain_text("step 2 of 5")
    nxt.click()
    expect(detail).to_contain_text("step 3 of 5")
    prev.click()
    expect(detail).to_contain_text("step 2 of 5")

    # Use prompt fills the composer; nothing executes.
    page.get_by_test_id("journey-detail").get_by_role("button", name="Use prompt").click()
    value = page.get_by_test_id("composer-input").input_value()
    assert "UAV" in value or "uav" in value
    assert page.get_by_test_id("msg-user").count() == 0
    assert len(errors) == 0


def test_console_every_entry_fills_not_sends(page: Page, test_server_url: str):
    """ADR-017 PR 2: sidebar, palette Enter, and starters all fill the
    composer; only Send executes."""
    errors = _console_errors(page, test_server_url)

    # Sidebar library item → fills.
    page.get_by_test_id("prompt-library").get_by_role("button").filter(
        has_text="Al 6061-T6 yield strength"
    ).first.click()
    value = page.get_by_test_id("composer-input").input_value()
    assert "yield strength" in value.lower()
    assert page.get_by_test_id("msg-user").count() == 0

    # Palette Enter → fills (the send shortcut is retired).
    page.keyboard.press("ControlOrMeta+k")
    palette = page.get_by_test_id("command-palette")
    expect(palette).to_be_visible()
    palette.get_by_role("textbox").fill("convergence")
    page.keyboard.press("Enter")
    value = page.get_by_test_id("composer-input").input_value()
    assert "convergence" in value.lower()
    assert page.get_by_test_id("msg-user").count() == 0

    # Composer keeps the filled text for inspection and editing.
    assert page.get_by_test_id("command-palette").count() == 0

    assert len(errors) == 0


def test_console_starters_fill_composer(page: Page, test_server_url: str):
    errors = _console_errors(page, test_server_url)
    starters = page.get_by_test_id("starters")
    expect(starters).to_be_visible()
    starters.get_by_role("button", name="Create a brake pedal").click()
    value = page.get_by_test_id("composer-input").input_value()
    assert "brake pedal" in value.lower()
    assert page.get_by_test_id("msg-user").count() == 0
    assert len(errors) == 0


def test_console_hitl_toggle(page: Page, test_server_url: str):
    """ADR-016: the HITL gate is a live switch — default on, flips via API."""
    from companion.agent import confirm

    errors = _console_errors(page, test_server_url)
    try:
        toggle = page.get_by_test_id("hitl-toggle")
        expect(toggle).to_be_visible()
        expect(toggle).to_have_attribute("aria-checked", "true")  # default ON
        row = page.get_by_test_id("hitl-row")
        expect(row).to_contain_text("confirm each tool")

        toggle.click()  # off
        expect(toggle).to_have_attribute("aria-checked", "false")
        expect(row).to_contain_text("auto")

        toggle.click()  # back on
        expect(toggle).to_have_attribute("aria-checked", "true")
        expect(row).to_contain_text("confirm each tool")
        assert len(errors) == 0
    finally:
        # The mocked server shares this process — never leak the override.
        confirm.reset_require_tool_confirm()


def test_console_light_theme_default(page: Page, test_server_url: str):
    """ADR-016: light theme is the default; dark stays a persisted choice."""
    errors = _console_errors(page, test_server_url)
    assert page.locator("html").get_attribute("data-theme") == "light"
    page.get_by_test_id("theme-toggle").click()
    assert page.locator("html").get_attribute("data-theme") is None  # dark = root
    assert len(errors) == 0


# =========================================================================
# PART 4: React console honesty pass (ADR-017) — method labels, execution
# status, numeric honesty, sources/technical details. These tests intercept
# /api/chat/stream (and /api/runs) with deterministic SSE fixtures so result
# *presentation* is tested independently of which solver the host machine has.
# =========================================================================

def _sse_final(payload: dict) -> str:
    return "data: " + json.dumps(payload) + "\n\n"


def _mock_stream_by_keyword(page: Page, payloads: dict[str, dict]) -> None:
    """Fulfill /api/chat/stream with a fixture chosen by a keyword in the
    sent message. Each response is one `final` SSE frame."""

    def handler(route):
        body = route.request.post_data_json
        message = str(body.get("message", "")).lower() if isinstance(body, dict) else ""
        for keyword, payload in payloads.items():
            if keyword in message:
                route.fulfill(status=200, content_type="text/event-stream", body=_sse_final(payload))
                return
        route.fulfill(
            status=200,
            content_type="text/event-stream",
            body=_sse_final({"type": "final", "answer": "no fixture", "thread_id": "t"}),
        )

    page.route("**/api/chat/stream", handler)


def _console_send(page: Page, text: str) -> None:
    page.get_by_test_id("composer-input").fill(text)
    page.get_by_test_id("composer-input").press("Enter")


def _solve_fixture(method: str | None, fallback: bool | None, **extra) -> dict:
    result = {"ok": True, "part": "brake_pedal", "force_n": 500}
    if method is not None:
        result["method"] = method
    if fallback is not None:
        result["fallback"] = fallback
    result.update(extra)
    return {"type": "final", "answer": "Solve done.", "thread_id": "t", "tool_results": [{"name": "apply_load_and_solve", "result": result}]}


def test_console_method_label_precedence(page: Page, test_server_url: str):
    """ADR-017: origin labels follow wire evidence with strict precedence —
    analytical > saved/precomputed > fallback > live — and a fallback flag
    overrides a live-sounding method."""
    errors = _console_errors(page, test_server_url)
    _mock_stream_by_keyword(
        page,
        {
            "live case": _solve_fixture("calculix_ccx", None, max_von_mises_mpa=120.0, safety_factor_vs_yield=2.3),
            "saved case": _solve_fixture("precomputed_demo_estimate", True, max_von_mises_mpa=24.6, safety_factor_vs_yield=11.2),
            "unknown fallback case": _solve_fixture(None, True, max_von_mises_mpa=24.6),
            "override case": _solve_fixture("calculix_ccx", True, max_von_mises_mpa=24.6),
            "analytical case": _solve_fixture("analytical_euler_bernoulli", None, expected_vs_actual={"expected": 120.0, "actual": 120.0, "ratio": 1.0}),
        },
    )

    card = page.get_by_test_id("report-card").last

    _console_send(page, "live case")
    expect(card).to_contain_text("Live simulation")
    expect(card).not_to_contain_text("ESTIMATE")
    expect(card).not_to_contain_text("REFERENCE")
    expect(card).not_to_contain_text("FALLBACK")

    _console_send(page, "saved case")
    expect(card).to_contain_text("Saved reference result")
    expect(card).to_contain_text("REFERENCE")

    _console_send(page, "unknown fallback case")
    expect(card).to_contain_text("Fallback result")
    expect(card).to_contain_text("FALLBACK")

    _console_send(page, "override case")
    expect(card).to_contain_text("Fallback result")
    expect(card).not_to_contain_text("Live simulation")

    _console_send(page, "analytical case")
    expect(card).to_contain_text("Analytical estimate")
    expect(card).to_contain_text("ESTIMATE")

    assert len(errors) == 0


def test_console_execution_status_not_verdict(page: Page, test_server_url: str):
    """ADR-017: the card stamp is the execution outcome (Completed/Failed);
    PASS/FAIL design verdicts are gone from cards."""
    errors = _console_errors(page, test_server_url)
    _mock_stream_by_keyword(
        page,
        {
            "good solve": _solve_fixture("calculix_ccx", None, safety_factor_vs_yield=2.3),
            "bad solve": {
                "type": "final",
                "answer": "Rejected.",
                "thread_id": "t",
                "tool_results": [
                    {
                        "name": "apply_load_and_solve",
                        "result": {"ok": False, "error": "No active geometry", "correction": "Create a part first"},
                    }
                ],
            },
        },
    )

    card = page.get_by_test_id("report-card").last

    _console_send(page, "good solve")
    expect(card.get_by_test_id("exec-status")).to_contain_text("Completed")
    expect(card).not_to_contain_text("PASS")
    expect(card).not_to_contain_text("FAIL")

    _console_send(page, "bad solve")
    expect(card.get_by_test_id("exec-status")).to_contain_text("Failed")
    expect(card).to_contain_text("No active geometry")
    expect(card).to_contain_text("Create a part first")

    assert len(errors) == 0


def test_console_missing_values_and_zeros(page: Page, test_server_url: str):
    """ADR-017: present-but-unavailable values render as em dashes; legitimate
    zeros survive; all displacement variants are covered."""
    errors = _console_errors(page, test_server_url)
    _mock_stream_by_keyword(
        page,
        {
            "gap case": _solve_fixture(
                "calculix_ccx",
                None,
                mass_kg=0.0,
                max_von_mises_mpa=120.0,
                safety_factor_vs_yield=None,
                pad_deflection_mm=None,
                tip_deflection_mm=1.5,
            ),
        },
    )

    _console_send(page, "gap case")
    card = page.get_by_test_id("report-card").last
    expect(card).to_contain_text("0.000 kg")  # legitimate zero preserved
    rows = card.locator("dl > div")
    expect(rows.filter(has_text="SF yield")).to_contain_text("—")
    expect(rows.filter(has_text="δ pad")).to_contain_text("—")
    expect(rows.filter(has_text="δ tip")).to_contain_text("1.500 mm")

    assert len(errors) == 0


def test_console_sf_threshold_colors_and_history(page: Page, test_server_url: str):
    """ADR-017: SF carries the verdict via threshold colors on cards and in
    run history; history rows no longer render pass/fail stamps; divergence
    stays a factual flag."""
    runs_payload = {
        "part": "brake_pedal",
        "runs": [
            {"run_id": "r1", "part": "brake_pedal", "web_type": "solid", "method": "calculix_ccx", "max_von_mises_mpa": 210.0, "safety_factor_vs_yield": 0.8, "ts": "2026-09-06T00:00:00Z"},
            {"run_id": "r2", "part": "brake_pedal", "web_type": "xtruss", "method": "calculix_ccx", "max_von_mises_mpa": 24.6, "safety_factor_vs_yield": 11.2, "ts": "2026-09-06T00:01:00Z"},
            {"run_id": "r3", "part": "brake_pedal", "web_type": "fcc", "method": "precomputed_demo_estimate", "max_von_mises_mpa": 24.6, "safety_factor_vs_yield": 11.2, "divergence_flag": True, "ts": "2026-09-06T00:02:00Z"},
        ],
    }
    page.route("**/api/runs*", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(runs_payload)))
    errors = _console_errors(page, test_server_url)

    history = page.get_by_test_id("run-history")
    expect(history).to_be_visible()
    expect(history).not_to_contain_text("pass")
    stamps = history.locator("span", has_text=re.compile(r"^(pass|caution|fail)$", re.I))
    assert stamps.count() == 0
    # SF 0.8 row colored as failure, both 11.2 rows as pass (divergence is an
    # independent factual flag, not an SF override).
    expect(history.locator(".text-fail")).to_have_count(1)
    expect(history.locator(".text-pass")).to_have_count(2)
    expect(history).to_contain_text("diverged")

    assert len(errors) == 0


def test_console_sources_and_technical_details(page: Page, test_server_url: str):
    """ADR-017: sources stay visible and compact; raw payloads, rankings and
    excerpts collapse under Technical details; friendly names on cards keep
    raw names inspectable."""
    errors = _console_errors(page, test_server_url)
    _mock_stream_by_keyword(
        page,
        {
            "cited case": {
                "type": "final",
                "answer": "Al 6061-T6 yields at 276 MPa.",
                "thread_id": "t",
                "grounding": "strong",
                "citations": [
                    {"source": "docs/reference/materials.md", "text": "Al 6061-T6 yield 276 MPa density 2.70", "tfidf_rank": 1, "bm25_rank": 2, "score": 0.81},
                    {"source": "docs/fea/calculix.md", "text": "Linear static workflow", "tfidf_rank": 3, "bm25_rank": 1, "score": 0.62},
                ],
                "tool_results": [
                    {"name": "query_results", "result": {"ok": True, "method": "precomputed_demo_estimate", "fallback": True, "runs_found": 2}},
                ],
            },
        },
    )

    _console_send(page, "cited case")
    msg = page.get_by_test_id("msg-assistant").last
    sources = msg.get_by_test_id("msg-sources")
    expect(sources).to_be_visible()
    expect(sources).to_contain_text("docs/reference/materials.md")
    expect(sources).to_contain_text("docs/fea/calculix.md")

    details = msg.get_by_test_id("technical-details")
    expect(details).to_be_visible()
    details.locator("summary").click()
    # Raw tool name (not the friendly name) with the verbatim payload.
    expect(msg.get_by_test_id("raw-payloads")).to_contain_text("query_results")
    expect(msg.get_by_test_id("raw-payloads")).to_contain_text('"fallback": true')
    expect(msg.get_by_test_id("retrieval-diagnostics")).to_contain_text("tfidf #1")
    expect(msg.get_by_test_id("retrieval-diagnostics")).to_contain_text("cos 0.810")

    # Report card header shows the friendly mapping, not the raw name.
    card = msg.get_by_test_id("report-card").first
    expect(card).to_contain_text("Run history query")
    assert len(errors) == 0


# =========================================================================
# PART 5: React console session semantics (ADR-017 PR 3) — fresh-on-load,
# runs in this session, saved-runs disclosure, busy protection, obsolete
# responses, missing run ids, convergence sub-runs.
# =========================================================================

def test_console_session_runs_and_saved_history(page: Page, test_server_url: str):
    """Clean launch shows an empty session rail while the saved disclosure
    carries disk history; a solved run lands in the session; New session
    clears it again."""
    runs_payload = {
        "part": "brake_pedal",
        "runs": [
            {"run_id": "old-1", "part": "brake_pedal", "web_type": "solid", "method": "calculix_ccx", "max_von_mises_mpa": 24.6, "safety_factor_vs_yield": 11.2, "ts": "2026-09-01T10:00:00Z"},
            {"run_id": "old-2", "part": "brake_pedal", "web_type": "xtruss", "method": "calculix_ccx", "max_von_mises_mpa": 21.8, "safety_factor_vs_yield": 12.7, "ts": "2026-09-02T10:00:00Z"},
        ],
    }
    page.route("**/api/runs*", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(runs_payload)))
    page.route(
        "**/api/chat/stream",
        lambda route: route.fulfill(
            status=200,
            content_type="text/event-stream",
            body=_sse_final(
                _solve_fixture("calculix_ccx", None, run_id="s1", web_type="solid", max_von_mises_mpa=24.6, safety_factor_vs_yield=11.2)
            ),
        ),
    )
    errors = _console_errors(page, test_server_url)

    session = page.get_by_test_id("session-runs")
    expect(session).to_contain_text("No solves yet in this session")

    saved = page.get_by_test_id("saved-runs")
    saved.locator("summary").click()
    expect(saved).to_contain_text("part: brake_pedal")
    expect(saved).to_contain_text("old-1")
    expect(saved).to_contain_text("old-2")

    _console_send(page, "solve it")
    expect(session).to_contain_text("id s1")

    page.get_by_test_id("new-session").click()
    expect(session).to_contain_text("No solves yet in this session")
    assert page.get_by_test_id("composer-input").input_value() == ""
    assert len(errors) == 0


def test_console_busy_protections_and_obsolete_response(page: Page, test_server_url: str):
    """New session is disabled while busy; a forced reset past the disabled
    guard makes the in-flight response obsolete — it must not land. The hold
    lives inside the page (patched fetch) so the Playwright driver never
    blocks."""
    page.add_init_script(
        """
        (() => {
          const orig = window.fetch;
          window.__holdNext = false;
          window.fetch = async (url, opts) => {
            const res = await orig(url, opts);
            if (String(url).includes("/api/chat/stream") && window.__holdNext) {
              window.__holdNext = false;
              const text = await res.text();
              return new Promise((resolve) => {
                window.__resolveHeld = () =>
                  resolve(new Response(text, { status: 200, headers: { "Content-Type": "text/event-stream" } }));
              });
            }
            return res;
          };
        })();
        """
    )
    stale_payload = _solve_fixture("calculix_ccx", None, run_id="stale-1", max_von_mises_mpa=1.0)
    page.route(
        "**/api/chat/stream",
        lambda route: route.fulfill(status=200, content_type="text/event-stream", body=_sse_final(stale_payload)),
    )
    errors = _console_errors(page, test_server_url)

    page.evaluate("() => { window.__holdNext = true; }")
    _console_send(page, "slow solve")
    new_btn = page.get_by_test_id("new-session")
    expect(new_btn).to_be_disabled()
    expect(page.get_by_test_id("busy-note")).to_contain_text("work continues")

    # Force the reset past the disabled guard (the guard exists for races);
    # the in-flight response now belongs to an obsolete session.
    # Wait until the fetch hold has engaged before forcing the reset.
    page.wait_for_function("() => typeof window.__resolveHeld === 'function'")
    # Invoke the button's real handler directly — a disabled <button> never
    # fires click events, but the guard must stay exercisable for races.
    page.evaluate(
        """
        () => {
          const btn = document.querySelector('[data-testid="new-session"]');
          const key = Object.keys(btn).find((k) => k.startsWith("__reactProps$"));
          btn[key].onClick();
        }
        """
    )
    page.evaluate("() => window.__resolveHeld()")
    page.wait_for_timeout(300)
    assert page.get_by_test_id("msg-user").count() == 0
    assert page.get_by_test_id("msg-assistant").count() == 0
    expect(page.get_by_test_id("session-runs")).to_contain_text("No solves yet in this session")

    # The next send (current generation) lands normally.
    _console_send(page, "fresh solve")
    expect(page.get_by_test_id("msg-user").last).to_contain_text("fresh solve")
    assert len(errors) == 0


def test_console_solve_without_run_id_shows_unrecorded(page: Page, test_server_url: str):
    """A solve whose history write degraded still displays its result with an
    explicit unrecorded marker — no invented persisted identity."""
    page.route(
        "**/api/chat/stream",
        lambda route: route.fulfill(
            status=200,
            content_type="text/event-stream",
            body=_sse_final(
                _solve_fixture(
                    "calculix_ccx",
                    None,
                    max_von_mises_mpa=24.6,
                    safety_factor_vs_yield=11.2,
                    history_write_error="disk full",
                )
            ),
        ),
    )
    errors = _console_errors(page, test_server_url)
    _console_send(page, "solve without history")
    session = page.get_by_test_id("session-runs")
    expect(session).to_contain_text("24.6")
    expect(session).to_contain_text("unrecorded")
    assert len(errors) == 0


def test_console_convergence_subruns_dedup_and_failures(page: Page, test_server_url: str):
    """Convergence sub-runs become session rows in order; replayed run ids
    deduplicate; failed mesh attempts show as failed."""
    payload = {
        "type": "final",
        "answer": "Convergence study complete.",
        "thread_id": "t",
        "tool_results": [
            {
                "name": "run_convergence_study",
                "result": {
                    "ok": True,
                    "method": "calculix_ccx",
                    "run_id": "r10",
                    "max_von_mises_mpa": 120.5,
                    "safety_factor_vs_yield": 2.1,
                    "runs": [
                        {"run_id": "r10", "ok": True, "method": "calculix_ccx", "web_type": "cantilever", "max_von_mises_mpa": 118.0, "safety_factor_vs_yield": 2.2},
                        {"run_id": "r11", "ok": True, "method": "calculix_ccx", "web_type": "cantilever", "max_von_mises_mpa": 120.5, "safety_factor_vs_yield": 2.1},
                        {"ok": False, "error": "mesh generation failed at 1.2 mm", "web_type": "cantilever"},
                    ],
                },
            }
        ],
    }
    page.route(
        "**/api/chat/stream",
        lambda route: route.fulfill(status=200, content_type="text/event-stream", body=_sse_final(payload)),
    )
    errors = _console_errors(page, test_server_url)
    _console_send(page, "run convergence")

    session = page.get_by_test_id("session-runs")
    # r10 appears once (deduplicated across base + sub-run), r11 once, and
    # the failed mesh attempt is visible.
    expect(session.get_by_text("id r10")).to_have_count(1)
    expect(session.get_by_text("id r11")).to_have_count(1)
    expect(session).to_contain_text("failed")
    assert len(errors) == 0
