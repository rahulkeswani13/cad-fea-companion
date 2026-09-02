"""Browser UI automation tests using Playwright against mocked CAD/FEA companion server.

Tests all 36 demo prompts + 9 multi-turn feature journeys (45 total tests).
"""

from __future__ import annotations

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
