# simulation/scripts/traffic_demo.py
"""
traffic_demo.py — Main simulation loop for the SUMO traffic environment.
"""

import os
import sys
import time
import random
import logging
import argparse
import threading
import asyncio
from pathlib import Path
from typing import Dict, List, Optional

import traci
import httpx
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
from rich.console import Console

from config import CFG, STATE, GEN_DIR, NET_FILE, ROU_FILE, CFG_FILE
from publisher import VehicleCountPublisher

# ─────────────────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("traffic_demo")


# ─────────────────────────────────────────────────────────────────────────────
# SETUP & TOOLS
# ─────────────────────────────────────────────────────────────────────────────
def check_sumo():
    """Ensure SUMO_HOME is set and traci is installed."""
    if "SUMO_HOME" not in os.environ:
        logger.error("SUMO_HOME environment variable not set.")
        sys.exit(1)


def generate_network(force=False):
    """Create a 4-way intersection using netgenerate."""
    if not os.path.exists(GEN_DIR):
        os.makedirs(GEN_DIR)

    if force or not os.path.exists(NET_FILE):
        logger.info("Generating %s …", NET_FILE)
        import subprocess
        cmd = [
            "netgenerate",
            "--grid",
            "--grid.number", "1",
            "--grid.length", "200",
            "--output-file", NET_FILE,
            "--no-internal-links", "false",
            "--no-turnarounds", "true",
            "--all-junctions.greedy", "true"
        ]
        subprocess.run(cmd, check=True, capture_output=True)


def generate_routes(force=False):
    """Write static route file with passenger, bus, and motorcycle types."""
    if force or not os.path.exists(ROU_FILE):
        logger.info("Writing %s …", ROU_FILE)
        
        passenger_prob = CFG.vtype_dist.get("passenger",  0.75)
        bus_prob       = CFG.vtype_dist.get("bus",        0.10)
        moto_prob      = CFG.vtype_dist.get("motorcycle", 0.15)
        
        Path(ROU_FILE).write_text(
            f"""<routes>
    <vType id="passenger"        vClass="passenger"  guiShape="passenger"            length="5.0" minGap="2.5" maxSpeed="50.0" probability="{passenger_prob * 0.4}"/>
    <vType id="passenger_sedan"  vClass="passenger"  guiShape="passenger/sedan"      length="4.5" minGap="2.5" maxSpeed="50.0" probability="{passenger_prob * 0.3}"/>
    <vType id="passenger_hatch"  vClass="passenger"  guiShape="passenger/hatchback"  length="4.0" minGap="2.5" maxSpeed="50.0" probability="{passenger_prob * 0.2}"/>
    <vType id="passenger_wagon"  vClass="passenger"  guiShape="passenger/wagon"      length="5.2" minGap="2.5" maxSpeed="50.0" probability="{passenger_prob * 0.1}"/>
    <vType id="bus"              vClass="bus"        guiShape="bus"                  length="12.0" minGap="3.0" maxSpeed="30.0" probability="{bus_prob}"/>
    <vType id="motorcycle"       vClass="motorcycle" guiShape="motorcycle"           length="2.2"  minGap="1.5" maxSpeed="60.0" probability="{moto_prob}"/>
    <vType id="emergency"        vClass="emergency"  guiShape="emergency"            length="6.5"  minGap="2.5" maxSpeed="80.0" color="255,255,0"/>
    <vType id="flagged"          vClass="passenger"  guiShape="passenger"            length="5.0"  minGap="2.5" maxSpeed="50.0" color="255,0,0"/>
    
    <route id="n_s" edges="n2c c2s"/>
    <route id="s_n" edges="s2c c2n"/>
    <route id="e_w" edges="e2c c2w"/>
    <route id="w_e" edges="w2c c2e"/>
</routes>"""
        )


def generate_config(force=False):
    """Write the main .sumocfg file."""
    if force or not os.path.exists(CFG_FILE):
        logger.info("Writing %s …", CFG_FILE)
        Path(CFG_FILE).write_text(
            f"""<configuration>
    <input>
        <net-file value="{os.path.basename(NET_FILE)}"/>
        <route-files value="{os.path.basename(ROU_FILE)}"/>
    </input>
    <time>
        <begin value="0"/>
        <step-length value="{CFG.step_length}"/>
    </time>
    <report>
        <no-step-log value="true"/>
    </report>
</configuration>"""
        )


# ─────────────────────────────────────────────────────────────────────────────
# SIMULATION LOGIC
# ─────────────────────────────────────────────────────────────────────────────
_arm_map = {"north": "n2c", "south": "s2c", "east": "e2c", "west": "w2c"}
_publisher: Optional[VehicleCountPublisher] = None


def spawn_vehicles():
    """Inject random vehicles into the network."""
    p = STATE.spawn_rate / 100.0
    routes = ["n_s", "s_n", "e_w", "w_e"]
    
    for rid in routes:
        if random.random() < p:
            vid = f"veh_{STATE.sim_time}_{rid}"
            vtype = random.choice(["passenger", "passenger_sedan", "bus", "motorcycle"])
            
            # Special case for emergency vehicle trigger
            if STATE.trigger_emergency:
                vtype = "emergency"
                STATE.trigger_emergency = False
                STATE.alert_msg = f"EMERGENCY VEHICLE INJECTED on {rid}"
                STATE.alert_expires = STATE.sim_time + 10
            
            # Special case for flagged vehicle
            if STATE.trigger_flagged:
                vtype = "flagged"
                STATE.trigger_flagged = False
            
            traci.vehicle.add(vid, rid, typeID=vtype)


def update_queues():
    """Calculate queue length for each arm."""
    for arm, eid in _arm_map.items():
        STATE.queues[arm] = traci.edge.getLastStepVehicleNumber(eid)
        
        # Track waiting time for metrics
        current_wait = sum(traci.vehicle.getWaitingTime(v) for v in traci.edge.getLastStepVehicleIDs(eid))
        if STATE.mode == "FIXED":
            STATE.total_wait_fixed += current_wait
            STATE.steps_fixed      += 1
        elif STATE.mode == "ADAPTIVE":
            STATE.total_wait_adaptive += current_wait
            STATE.steps_adaptive      += 1


def request_rl_signal(queues: dict, waits: dict, sim_time: int):
    """Request a binary decision (Stay/Switch) from the RL backend."""
    url = f"{CFG.ai_service_url}/ai/rl/predict"
    payload = {
        "counts": [queues["north"], queues["south"], queues["east"], queues["west"]],
        "waits": [waits["north"], waits["south"], waits["east"], waits["west"]],
        "sim_time": sim_time
    }
    try:
        resp = httpx.post(url, json=payload, timeout=0.5)
        if resp.is_success:
            STATE.last_rl_decision = resp.json()
    except:
        pass


def manage_signals():
    """Handle signal transition logic based on mode."""
    # Logic for switching modes based on time is inside the main loop
    # This function is for periodic check/update
    pass


def run_sim(nogui=False, steps=1000):
    """Primary simulation execution loop."""
    global _publisher
    _publisher = VehicleCountPublisher(CFG.ai_service_url)
    
    sumo_bin = "sumo" if nogui else "sumo-gui"
    logger.info("Starting %s on port %d …", sumo_bin, CFG.traci_port)
    
    traci.start([sumo_bin, "-c", CFG_FILE, "--start", "--quit-on-end", "--port", str(CFG.traci_port)])
    
    try:
        while traci.simulation.getMinExpectedNumber() > 0:
            traci.simulationStep()
            STATE.sim_time = int(traci.simulation.getTime())
            
            if steps and STATE.sim_time >= steps:
                break
                
            update_queues()
            spawn_vehicles()
            
            # Switch to RL or Adaptive after threshold
            if STATE.sim_time >= STATE.rl_mode_start_time:
                STATE.mode = "RL"
            elif STATE.sim_time >= CFG.adaptive_start_time:
                STATE.mode = "ADAPTIVE"

            # ── RL Mode Decision ──────────────────────────────────────────────────
            if STATE.mode == "RL" and STATE.sim_time % 5 == 0:
                # Construct arm_waits for model
                arm_waits = {arm: sum(traci.vehicle.getWaitingTime(v) 
                                     for v in traci.edge.getLastStepVehicleIDs(eid))
                             for arm, eid in _arm_map.items()}
                
                request_rl_signal(STATE.queues, arm_waits, STATE.sim_time)

            # ── Periodic Publishing ─────────────────────────────────────────────
            if STATE.sim_time % CFG.publish_interval == 0:
                _publisher.publish(STATE.queues, STATE.sim_time, STATE.mode)
                
            time.sleep(0.01) # Small throttle for dashboard visibility
                
    finally:
        traci.close()
        _publisher.close()


# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────
def generate_dashboard() -> Layout:
    """Create a rich TUI for the traffic simulation."""
    layout = Layout()
    
    alert_active = STATE.alert_msg and STATE.sim_time < STATE.alert_expires
    alert_panel  = Panel(f"[bold white on red] ⚠ {STATE.alert_msg} [/]", justify="center") if alert_active else ""

    layout.split_column(
        Layout(
            Panel(Text("🚦 Traffic Control Dashboard", style="bold cyan", justify="center")),
            size=3,
        ),
        Layout(alert_panel, size=3 if alert_active else 0),
        Layout(name="main", ratio=1)
    )

    # Main area columns
    layout["main"].split_row(
        Layout(name="status", ratio=1),
        Layout(name="queues", ratio=2),
    )

    # Status Table
    st_table = Table.grid(padding=1)
    st_table.add_column(style="dim")
    st_table.add_column(style="bold")
    st_table.add_row("Sim Time", f": {STATE.sim_time} s")
    st_table.add_row("Control Mode", f": {STATE.mode}")
    st_table.add_row("Active Veh", f": {traci.vehicle.getIDCount()}")
    st_table.add_row("Spawn Rate", f": {STATE.spawn_rate}%")
    
    layout["status"].update(Panel(st_table, title="[bold blue]Simulation Specs[/]"))

    # Queues Table
    q_table = Table(header_style="bold magenta", expand=True, box=None)
    q_table.add_column("ARM", ratio=1)
    q_table.add_column("VEH", ratio=1)
    q_table.add_column("LOAD", ratio=3)

    for arm, count in STATE.queues.items():
        bar = "█" * min(count, 30)
        color = "green" if count < 5 else "yellow" if count < 12 else "red"
        q_table.add_row(arm.upper(), str(count), f"[{color}]{bar}[/]")

    layout["queues"].update(Panel(q_table, title="[bold magenta]Queue Analysis (Real-time)[/]"))

    return layout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--nogui", action="store_true", help="Run without sumo-gui")
    parser.add_argument("--steps", type=int, default=1000, help="Max simulation steps")
    parser.add_argument("--force-regen", action="store_true", help="Force network regeneration")
    args = parser.parse_args()

    check_sumo()
    generate_network(args.force_regen)
    generate_routes(args.force_regen)
    generate_config(args.force_regen)

    sim_thread = threading.Thread(target=run_sim, args=(args.nogui, args.steps), daemon=True)
    sim_thread.start()

    console = Console()
    with Live(generate_dashboard(), refresh_per_second=CFG.refresh_rate) as live:
        try:
            while sim_thread.is_alive():
                live.update(generate_dashboard())
                time.sleep(1 / CFG.refresh_rate)
        except KeyboardInterrupt:
            STATE.running = False
            logger.info("Stopping simulation…")

    print("\n── Shutting down ─────────────────────────────────────────────")
    print(f"  Simulated time    : {STATE.sim_time} s")
    print(f"  Avg wait FIXED    : {STATE.total_wait_fixed/max(1, STATE.steps_fixed):.2f} s/step")
    print(f"  Avg wait ADAPTIVE : {STATE.total_wait_adaptive/max(1, STATE.steps_adaptive):.2f} s/step")
    print(f"  Last backend resp : {STATE.last_rl_decision}")
    print("─────────────────────────────────────────────────────────────\n")


if __name__ == "__main__":
    main()
