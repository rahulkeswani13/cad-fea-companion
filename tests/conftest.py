"""Pytest fixtures for browser UI automation and mock server."""

from __future__ import annotations

import os
import socket
import threading
import time
from pathlib import Path
from typing import Any, Generator

import pytest
import uvicorn
from fastapi import FastAPI
from langgraph.checkpoint.memory import MemorySaver

from companion.agent.graph import build_graph
from companion.llm.providers import AgentTurn, LLMProvider, ToolCallSpec
from tests.fakes import StubTools, tc


class SmartDemoMockLLM(LLMProvider):
    """Deterministic LLM Mock capable of handling all 36 demo prompts + multi-turn journeys."""

    def __init__(self) -> None:
        self.turn_count = 0

    def complete(self, system: str, user: str) -> str:
        return self.complete_messages([]).content

    def complete_messages(
        self,
        messages: list[Any],
        tools: list[Any] | None = None,
    ) -> AgentTurn:
        # Extract the text of the latest user message
        user_text = ""
        for m in reversed(messages):
            role = getattr(m, "type", None) or getattr(m, "role", None)
            content = getattr(m, "content", "")
            if not user_text and (role in ("human", "user") or type(m).__name__ == "HumanMessage"):
                user_text = str(content).lower()
                break

        # Exact prompt matching priority
        # F01 RAG
        if "al 6061-t6" in user_text or "al 6061" in user_text:
            return AgentTurn(content="**Aluminum 6061-T6**: Yield strength is **276 MPa**, density is **2.70 g/cm³**, and Young's modulus is **69.0 GPa** [docs/reference/materials.md].")
        if "bending stress formula" in user_text or "formula" in user_text:
            return AgentTurn(content="The analytical bending stress formula for a rectangular cantilever beam under tip load is:\n$$\\sigma = \\frac{6FL}{bh^2}$$\nwhere $F$ is tip load, $L$ is length, $b$ is width, and $h$ is height [docs/reference/materials.md].")
        if "structural steel" in user_text or "steel" in user_text:
            return AgentTurn(content="For structural steel in this demo, assume **Young's modulus E = 210 GPa**, Poisson's ratio &nu; = 0.30, and density = 7850 kg/m³ [docs/reference/materials.md].")
        if "ti-6al-4v" in user_text and "allowable" in user_text:
            return AgentTurn(content="**Titanium Ti-6Al-4V**: Yield strength is **880 MPa**, ultimate tensile strength is **950 MPa**, and density is **4.43 g/cm³** [docs/reference/materials.md].")

        # F02 Outcome Envelope
        if "without creating any geometry" in user_text:
            return AgentTurn(content="**Error**: No active geometry found. Call `create_brake_pedal` or `create_cantilever` first.")
        if "nonexistent_cad_generator" in user_text:
            return AgentTurn(content="**Error**: Unknown tool `nonexistent_cad_generator`. Available tools: `create_brake_pedal`, `create_uav_arm`.")
        if "-50" in user_text:
            return AgentTurn(content="**Rejected**: Dimensions must be strictly positive (> 0 mm).")
        if "-5" in user_text:
            return AgentTurn(content="**Rejected**: Cell size -5 mm is invalid. Allowed range: `[5.0, 40.0] mm`.")

        # F03 B-Rep Gate
        if "strut radius 8" in user_text or "radius 8" in user_text:
            return AgentTurn(content="**B-Rep Rejected**: Strut radius 8.0 mm exceeds cell radius 3.0 mm (self-intersecting solid).")
        if "height 0" in user_text:
            return AgentTurn(content="**B-Rep Rejected**: Cantilever height 0 mm results in a degenerated zero-volume solid.")
        if "voronoi" in user_text:
            return AgentTurn(content="**Invalid Web Type**: 'voronoi' is unsupported. Valid web types: `solid`, `xtruss`, `fcc`.")
        if "validate the current" in user_text or "validate" in user_text:
            return AgentTurn(content="**CAD Geometry Validation**: PASS. Solid is **watertight** with 0 self-intersections (Volume: 58,000 mm³).")

        # F04 Design Programs
        if "without applying" in user_text or "dry_run" in user_text or "preview" in user_text:
            return AgentTurn(content="**Dry-Run Preview**: Parameters are valid. Proposed hash `a1b2c3d4` without modifying disk.")
        if "again" in user_text:
            return AgentTurn(content="**No-Op Update**: Cell size is already 12.0 mm (`changed: false`). Active revision 2 retained.")
        if "cell size to 12 mm" in user_text and ("pedal" in user_text or "re-solve" in user_text):
            return AgentTurn(content="Updated brake pedal cell size to **12 mm** (rev 2). Solved under 500 N: Max von Mises **24.6 MPa**.")
        if "15 mm cells" in user_text and "pedal" in user_text:
            return AgentTurn(content="Created **X-truss brake pedal** with 15 mm cells (rev 1). Solved under 500 N: Max von Mises **21.8 MPa**, SF **6.2**.")

        # F06 Spatial History
        if "where is it located" in user_text or "peak stress in the latest" in user_text:
            return AgentTurn(content="Latest solve **Peak von Mises: 44.6 MPa** located at coordinate **(X: 12.4 mm, Y: -8.1 mm, Z: 5.0 mm)** on the root clamp fillet.")
        if "list all simulation runs" in user_text or "runs in this session" in user_text:
            return AgentTurn(content="| Run ID | Part | Rev | Mesh Size | Max Stress | Status |\n|---|---|---|---|---|---|\n| run_01 | cantilever | 1 | 3.5 mm | 120.0 MPa | COMPLETED |\n| run_02 | uav_arm | 1 | 5.0 mm | 44.6 MPa | COMPLETED |")
        if "compare run 1" in user_text or "compare run" in user_text:
            return AgentTurn(content="**Run Comparison (Run 1 vs Run 2)**:\n* Part: `cantilever` (0.027 kg) &rarr; `uav_arm` (0.157 kg)\n* Peak Stress: 120.0 MPa &rarr; 44.6 MPa\n* Solver: CalculiX CCX static linear elastic.")
        if "coordinate of the maximum von mises" in user_text or "hotspot" in user_text:
            return AgentTurn(content="Maximum von Mises stress on the brake pedal is **21.8 MPa**, situated at the pivot ring interior radius **(X: 0.0 mm, Y: 0.0 mm, Z: 12.5 mm)**.")

        # F07 Analytical
        if "expected analytical bending stress" in user_text or "expected analytical" in user_text:
            return AgentTurn(content="Expected analytical stress for a 100x20x5 mm beam under 100 N:\n$$\\sigma = \\frac{6 \\cdot 100 \\cdot 100}{20 \\cdot 5^2} = 120.0\\text{ MPa}$$")
        if "estimate for a brake pedal" in user_text:
            return AgentTurn(content="Estimated simplified cantilever bending stress for the brake pedal arm under 500 N is **~23.4 MPa** (approximate beam envelope).")
        if "compare to the beam theory" in user_text or "fea stress compare" in user_text:
            return AgentTurn(content="The 3D CalculiX FEA result (**120.0 MPa**) matches 1D Euler-Bernoulli beam theory (**120.0 MPa**) with **0.0% divergence**.")
        if "cantilever beam 100x20x5" in user_text or ("cantilever" in user_text and "100 n" in user_text):
            return AgentTurn(content="Created cantilever beam 100x20x5 mm. Solved under 100 N: **Max von Mises: 120.0 MPa**, matching `analytical_reference_mpa: 120.0`.")

        # F08 Convergence
        if "convergence" in user_text:
            if "fcc" in user_text:
                return AgentTurn(content="**Refused**: FCC lattice pedal uses precomputed demo KPIs that do not vary with mesh size. Live solves required.")
            return AgentTurn(content="| Mesh Size | Max von Mises | Tip Deflection |\n|---|---|---|\n| 5.0 mm | 118.0 MPa | 1.62 mm |\n| 3.5 mm | 119.5 MPa | 1.66 mm |\n| 2.5 mm | 120.5 MPa | 1.69 mm |\n\n**Recommended Mesh**: 2.5 mm (Asymptotic delta: 2.8%).")
        if "tip deflection change" in user_text:
            return AgentTurn(content="Tip deflection converges smoothly across mesh steps:\n* 5.0 mm: **1.62 mm**\n* 3.5 mm: **1.66 mm**\n* 2.5 mm: **1.69 mm** (+4.3% displacement convergence).")

        # F09 Materials
        if "titanium vs aluminum 7075" in user_text or ("compare" in user_text and "titanium" in user_text):
            return AgentTurn(content="| Material | Mass | Max Stress | Safety Factor |\n|---|---|---|---|\n| Al 6061-T6 | 0.25 kg | 24.6 MPa | 11.2 |\n| **Al 7075-T6** | **0.25 kg** | **24.6 MPa** | **20.4** |\n| Ti-6Al-4V | 0.40 kg | 24.6 MPa | 35.8 |\n| PA12 | 0.09 kg | 24.6 MPa | 1.95 (*NOT VERIFIED*) |\n\n**Recommendation**: Al 7075-T6 offers highest strength-to-weight ratio meeting SF &ge; 1.5.")
        if "pa12" in user_text:
            return AgentTurn(content="Switching to **PA12 Nylon** drops mass to **0.09 kg** (SF: 1.95). **Caveat**: Deflection is **NOT VERIFIED** because linear elastic solvers under-predict large polymer viscoelastic deformations.")
        if "vibranium" in user_text:
            return AgentTurn(content="**Rejected**: Unknown material 'Vibranium-X'. Supported: `al6061t6`, `al7075t6`, `ti6al4v`, `pa12`, `steel`.")
        if "7075" in user_text:
            return AgentTurn(content="Updated brake pedal material to **Al 7075-T6** (rev 2, Yield: 503 MPa). Solved under 500 N.")

        # F26 UAV Arm
        if "0.8 mm" in user_text or "0.8" in user_text:
            return AgentTurn(content="**Preflight Rejected**: Strut radius 0.8 mm is below the 1.5 mm meshable floor. Active revision preserved.")
        if "220 mm" in user_text or "220" in user_text:
            return AgentTurn(content="Updated UAV arm length to **220 mm** (rev 3). Mass and peak stress increase with the longer moment arm (no committed golden at 220 mm).")
        if "x-truss lattice" in user_text or "xtruss" in user_text or ("12 mm" in user_text and "uav" in user_text):
            return AgentTurn(content="Updated UAV arm to **X-truss lattice** with 12 mm cells (rev 2). Mass reduced by **~17%** (157 g &rarr; 130 g, SF: 2.9).")
        if "uav arm" in user_text or "uav" in user_text:
            return AgentTurn(content="Created **solid aluminum UAV arm** (157 g). Solved under 120 N thrust: **Peak von Mises: 44.6 MPa**, Safety Factor **6.2** vs Al 6061-T6 yield [docs/reference/materials.md].")

        # Brake Pedal default
        if "brake pedal" in user_text or "pedal" in user_text:
            return AgentTurn(content="Created **X-truss brake pedal** with 15 mm cells (rev 1). Solved under 500 N: Max von Mises **21.8 MPa**, SF **6.2**.")

        # Out of domain
        if "weather" in user_text or "tokyo" in user_text:
            return AgentTurn(content="I do not have access to live weather data or external search. I am a specialized CAD/FEA engineering companion.")

        return AgentTurn(content="I understand your request. Ready to create geometry or run FEA simulations.")


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def test_server_url() -> Generator[str, None, None]:
    """Spawns an in-process FastAPI server with MockLLM and StubTools on an ephemeral port."""
    import companion.agent.graph as c_graph
    from companion.main import app

    port = get_free_port()
    host = "127.0.0.1"

    # Inject mock graph into agent.graph module
    stub_tools = StubTools()
    mock_llm = SmartDemoMockLLM()
    mock_graph = build_graph(
        llm=mock_llm,
        call_tool_fn=stub_tools,
        checkpointer=MemorySaver(),
        require_tool_confirm=False,
    )
    c_graph._GRAPH = mock_graph
    c_graph.get_graph = lambda: mock_graph

    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait for server to become responsive
    url = f"http://{host}:{port}"
    for _ in range(30):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.2)
                if s.connect_ex((host, port)) == 0:
                    break
        except Exception:
            pass
        time.sleep(0.1)

    yield url
    server.should_exit = True
    thread.join(timeout=2)


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Configures Playwright viewport and options."""
    return {
        **browser_context_args,
        "viewport": {"width": 1280, "height": 850},
    }
