# Sumo_simulation/scripts/traffic_demo.py
"""
traffic_demo.py — Production rewrite (SUMO → ai-services pipeline integrated).
Run with: python traffic_demo.py [--nogui] [--port PORT] [--steps N] [--force-regen] [--verbose]
"""

# ==============================================================================
# 1. IMPORTS
# ==============================================================================
import argparse
import json
import logging
import os
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

try:
    import traci
except ImportError:
    print("Error: traci not found. Activate the project venv and re-run.")
    sys.exit(1)

try:
    from rich.layout import Layout
    from rich.live import Live
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
except ImportError:
    print("Error: rich not found. Run: pip install rich")
    sys.exit(1)

try:
    from pynput import keyboard as pynput_keyboard
    _HAS_PYNPUT = True
except ImportError:
    _HAS_PYNPUT = False

from config import CFG, STATE, GEN_DIR, NET_FILE, ROU_FILE, CFG_FILE, LOG_FILE
from publisher import VehicleCountPublisher

try:
    import httpx as _httpx
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False
    logger_stub = logging.getLogger("traffic_demo")
    logger_stub.warning("httpx not installed — backend polling disabled.")

logging.basicConfig(
    level=logging.DEBUG if os.getenv("VERBOSE") else logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("traffic_demo")


# ==============================================================================
# 2. NETWORK GENERATION  (files go to Sumo_simulation/scripts/generated/)
# ==============================================================================
def generate_all(force: bool = False) -> None:
    """Generate net, routes, and SUMO config into the GEN_DIR folder."""
    os.makedirs(GEN_DIR, exist_ok=True)

    # ── Net file ──────────────────────────────────────────────────────────────
    if force or not os.path.exists(NET_FILE):
        netgen = shutil.which("netgenerate") or shutil.which("netgenerate.exe")
        if netgen:
            logger.info("Generating %s …", NET_FILE)
            subprocess.run(
                [
                    netgen,
                    "--cross", "true",
                    "--cross.number", "1",
                    "--default.lanenumber", str(CFG.num_lanes),
                    "--default.speed", str(CFG.speed_limit),
                    "--cross.x", "0",
                    "--cross.y", "0",
                    "--street-length", str(CFG.street_length),
                    "--tls.guess", "true",
                    "--output-file", NET_FILE,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            logger.warning("netgenerate not found; skipping net generation.")

    # ── Route file ────────────────────────────────────────────────────────────
    if force or not os.path.exists(ROU_FILE):
        logger.info("Writing %s …", ROU_FILE)
        passenger_prob = CFG.vtype_dist.get("passenger",  0.75)
        bus_prob       = CFG.vtype_dist.get("bus",        0.10)
        moto_prob      = CFG.vtype_dist.get("motorcycle", 0.15)
        Path(ROU_FILE).write_text(
            f"""<routes>
    <vType id="passenger"  vClass="passenger"  guiShape="passenger"  length="5.0"  minGap="2.5" maxSpeed="50.0" probability="{passenger_prob}"/>
    <vType id="bus"        vClass="bus"        guiShape="bus"        length="12.0" minGap="3.0" maxSpeed="30.0" probability="{bus_prob}"/>
    <vType id="motorcycle" vClass="motorcycle" guiShape="motorcycle" length="2.2"  minGap="1.5" maxSpeed="60.0" probability="{moto_prob}"/>
    <vType id="emergency"  vClass="emergency"  guiShape="emergency"  length="6.5"  minGap="2.5" maxSpeed="80.0" color="255,255,0"/>
    <vType id="flagged"    vClass="passenger"  guiShape="passenger"  length="5.0"  minGap="2.5" maxSpeed="50.0" color="255,0,0"/>
</routes>"""
        )

    # ── SUMO config ───────────────────────────────────────────────────────────
    if force or not os.path.exists(CFG_FILE):
        logger.info("Writing %s …", CFG_FILE)
        Path(CFG_FILE).write_text(
            f"""<configuration>
    <input>
        <net-file value="{NET_FILE}"/>
        <route-files value="{ROU_FILE}"/>
    </input>
    <time>
        <begin value="0"/>
        <step-length value="{CFG.step_length}"/>
    </time>
</configuration>"""
        )


# ==============================================================================
# 3. VEHICLE SPAWNER
# ==============================================================================
_arm_map:    dict[str, str] = {}   # {"north": edgeId, ...}
_exit_edges: list[str]      = []


def init_edge_map() -> None:
    """Map intersection edges to cardinal arm names (must be called after traci.start)."""
    global _arm_map, _exit_edges
    tls_ids = traci.trafficlight.getIDList()
    if not tls_ids:
        logger.warning("No traffic lights found in simulation.")
        return
    tls_id = tls_ids[0]
    links  = traci.trafficlight.getControlledLinks(tls_id)
    entries = list(set(traci.lane.getEdgeID(lnk[0][0]) for lnk in links if lnk))
    exits   = list(set(traci.lane.getEdgeID(lnk[0][1]) for lnk in links if lnk))
    arms    = ["north", "south", "east", "west"]
    _arm_map    = {arms[i % 4]: e for i, e in enumerate(entries[:4])}
    _exit_edges = exits


def _generate_plate(flagged: bool = False) -> str:
    if flagged:
        return CFG.flagged_plate
    chars  = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    digits = "0123456789"
    return f"WB{''.join(random.choices(chars, k=2))}{''.join(random.choices(digits, k=4))}"


def _spawn_vehicle(veh_id: str, vtype: str, plate: str,
                   entry_edge: str, exit_edge: str) -> None:
    route_id = f"route_{veh_id}"
    try:
        if route_id not in traci.route.getIDList():
            traci.route.add(route_id, [entry_edge, exit_edge])
        traci.vehicle.add(veh_id, route_id, typeID=vtype)
        STATE.plate_map[veh_id] = plate
        if vtype == "emergency":
            traci.vehicle.setSpeedMode(veh_id, 0)
            traci.vehicle.setSpeed(veh_id, 25.0)
    except traci.exceptions.TraCIException:
        pass


def handle_spawning() -> None:
    """Spawn random traffic + triggered specialty vehicles each step."""
    if not _arm_map or not _exit_edges:
        return

    entries = list(_arm_map.values())

    # ── Hotkey-triggered vehicles ─────────────────────────────────────────────
    if STATE.trigger_emergency:
        STATE.trigger_emergency = False
        _spawn_vehicle(
            f"emg_{STATE.sim_time}", "emergency", "EMERGENCY",
            random.choice(entries), random.choice(_exit_edges),
        )

    if STATE.trigger_flagged:
        STATE.trigger_flagged = False
        _spawn_vehicle(
            f"veh_{STATE.sim_time}_flagged", "flagged",
            _generate_plate(flagged=True),
            random.choice(entries), random.choice(_exit_edges),
        )

    if STATE.trigger_reset:
        STATE.trigger_reset = False
        STATE.spawn_rate    = CFG.default_spawn_rate

    # ── Procedural traffic ────────────────────────────────────────────────────
    spawn_prob = STATE.spawn_rate / 60.0
    if random.random() < spawn_prob:
        entry = random.choice(entries)
        other_exits = [e for e in _exit_edges if e != entry] or _exit_edges
        exit_e = random.choice(other_exits)

        r = random.random()
        cumulative = 0.0
        vtype = "passenger"
        for vt, prob in CFG.vtype_dist.items():
            cumulative += prob
            if r < cumulative:
                vtype = vt
                break

        veh_id = f"veh_{STATE.sim_time}_{random.randint(1000, 9999)}"
        _spawn_vehicle(veh_id, vtype, _generate_plate(), entry, exit_e)


# ==============================================================================
# 4. SIGNAL CONTROLLER  (fixed / adaptive + emergency preemption)
# ==============================================================================
def manage_signal(tls_id: str) -> None:
    """Update signal timing based on current mode and queue lengths."""
    # Update per-arm queue lengths
    for arm, edge_id in _arm_map.items():
        STATE.queues[arm] = traci.edge.getLastStepHaltingNumber(edge_id)

    # Accumulate wait stats
    current_wait = sum(float(traci.vehicle.getWaitingTime(v))
                       for v in traci.vehicle.getIDList())

    if STATE.mode == "FIXED":
        STATE.total_wait_fixed += current_wait
        STATE.steps_fixed      += 1
    else:
        STATE.total_wait_adaptive += current_wait
        STATE.steps_adaptive      += 1

    # Switch to adaptive after threshold
    if STATE.sim_time >= CFG.adaptive_start_time:
        STATE.mode = "ADAPTIVE"

    # ── Emergency preemption ──────────────────────────────────────────────────
    for vid in traci.vehicle.getIDList():
        if "emg" in vid.lower() or "emergency" in traci.vehicle.getTypeID(vid).lower():
            try:
                traci.trafficlight.setPhase(tls_id, 0)   # force green phase
            except traci.exceptions.TraCIException:
                pass
            break

    # ── Adaptive extension ────────────────────────────────────────────────────
    if (STATE.mode == "ADAPTIVE"
            and STATE.sim_time % CFG.adaptive_check_every == 0
            and STATE.queues):
        max_q = max(STATE.queues.values())
        if max_q > 0:
            extension = min(15, max_q * CFG.adaptive_ext_step)
            new_dur   = CFG.fixed_green + extension
            if new_dur <= CFG.max_green:
                try:
                    traci.trafficlight.setPhaseDuration(tls_id, new_dur)
                except traci.exceptions.TraCIException:
                    pass


# ==============================================================================
# 5. ANPR LOGGER
# ==============================================================================
def check_anpr() -> None:
    """Detect slow/stopped vehicles and log ANPR events to detections.log."""
    already_seen = {d["vehicle_id"] for d in STATE.recent_detections}

    for arm, edge_id in _arm_map.items():
        for vid in traci.edge.getLastStepVehicleIDs(edge_id):
            speed = traci.vehicle.getSpeed(vid)
            if speed >= CFG.detection_speed_threshold:
                continue
            plate = STATE.plate_map.get(vid)
            if not plate or vid in already_seen:
                continue
            flagged = plate == CFG.flagged_plate
            rec = {
                "timestamp":  STATE.sim_time,
                "plate":      plate,
                "vehicle_id": vid,
                "speed":      round(speed, 2),
                "arm":        arm,
                "flagged":    flagged,
            }
            with open(LOG_FILE, "a") as lf:
                lf.write(json.dumps(rec) + "\n")

            STATE.recent_detections.insert(0, rec)
            if len(STATE.recent_detections) > 5:
                STATE.recent_detections.pop()
            STATE.total_plates += 1

            if flagged:
                STATE.alert_msg     = (
                    f"[bold red blink]!! ANPR ALERT: SUSPECT VEHICLE "
                    f"{plate} DETECTED AT {arm.upper()} ARM !![/]"
                )
                STATE.alert_expires = STATE.sim_time + 15


# ==============================================================================
# 6. PUBLISHER INTEGRATION
# ==============================================================================
_publisher: VehicleCountPublisher | None = None


def init_publisher() -> None:
    global _publisher
    _publisher = VehicleCountPublisher(CFG.ai_service_url)
    logger.info("Publisher ready → %s", CFG.ai_service_url)


def maybe_publish() -> None:
    """Publish vehicle counts every CFG.publish_interval steps."""
    if _publisher is None:
        return
    if STATE.sim_time > 0 and STATE.sim_time % CFG.publish_interval == 0:
        _publisher.publish(dict(STATE.queues), STATE.sim_time, STATE.mode)


# ==============================================================================
# 7. DASHBOARD  (5 panels including Backend Status)
# ==============================================================================
def _backend_status_text() -> Text:
    t = Text()
    resp = STATE.last_backend_response
    if not resp:
        t.append("Waiting for first publish …\n", style="dim")
        return t

    mc  = resp.get("most_congested_arm", "—")
    # recommended_green_extension lives in the arm_analysis list
    arm_analysis = resp.get("arm_analysis", [])
    rec_ext = 0
    for a in arm_analysis:
        if isinstance(a, dict) and a.get("arm") == mc:
            rec_ext = a.get("recommended_green_extension", 0)

    notified = resp.get("backend_notified", False)
    pub_t    = STATE.last_publish_time

    t.append(f"Last publish t :  {pub_t} s\n",     style="cyan")
    t.append(f"Most congested :  {mc.upper()}\n",   style="yellow")
    t.append(f"Rec. extension :  {rec_ext} s\n",    style="green")
    t.append(
        f"Backend saved  :  {'✓ YES' if notified else '✗ NO'}\n",
        style="green" if notified else "red",
    )
    return t


def generate_dashboard() -> Layout:
    """Compose and return the full Rich layout."""
    STATE.active_vehicles = traci.vehicle.getIDCount()

    # ── Queue bar chart ───────────────────────────────────────────────────────
    q_text = Text()
    for arm in ("north", "south", "east", "west"):
        count = STATE.queues[arm]
        bar   = "█" * min(count, 20)
        q_text.append(f"{arm.upper():<5} | {count:<2} | {bar}\n", style="cyan")

    # ── ANPR log ──────────────────────────────────────────────────────────────
    plates_text = Text()
    if not STATE.recent_detections:
        plates_text.append("Waiting for detections …\n", style="dim")
    for p in STATE.recent_detections:
        style  = "red bold" if p["flagged"] else "green"
        marker = "[!] "     if p["flagged"] else ""
        plates_text.append(
            f"{p['timestamp']}s  {marker}{p['plate']}  ({p['arm']})\n",
            style=style,
        )

    # ── Alert management ──────────────────────────────────────────────────────
    alert_active = STATE.alert_msg and STATE.sim_time < STATE.alert_expires
    if not alert_active:
        STATE.alert_msg = ""
    alert_panel = (
        Panel(STATE.alert_msg, style="red", title="SECURITY EVENT")
        if alert_active
        else Text("")
    )

    # ── Status ────────────────────────────────────────────────────────────────
    avg_fixed = (
        STATE.total_wait_fixed / STATE.steps_fixed
        if STATE.steps_fixed else 0.0
    )
    avg_adap  = (
        STATE.total_wait_adaptive / STATE.steps_adaptive
        if STATE.steps_adaptive else 0.0
    )
    info_str = (
        f"Sim Time     : {STATE.sim_time} s\n"
        f"Control Mode : [bold white]{STATE.mode}[/]\n"
        f"Spawn Rate   : {STATE.spawn_rate} veh/min\n"
        f"Active Veh   : {STATE.active_vehicles}\n"
        f"Plates Logged: {STATE.total_plates} total\n"
        f"Avg Wait(F)  : {avg_fixed:.1f} s\n"
        f"Avg Wait(A)  : {avg_adap:.1f} s"
    )

    controls = (
        "[yellow]+ / =   Increase spawn rate (+5/min)\n"
        "-       Decrease spawn rate (-5/min)\n"
        "e       Spawn Emergency Vehicle\n"
        "f       Spawn Flagged Vehicle\n"
        "r       Reset spawn rate\n"
        "q       Quit simulation[/]"
    )

    # ── Grid assembly ─────────────────────────────────────────────────────────
    grid = Table.grid(expand=True)
    grid.add_column()
    grid.add_column()
    grid.add_row(
        Panel(info_str, title="Simulation Status", border_style="blue"),
        Panel(q_text,   title="Queue Analyser",    border_style="magenta"),
    )
    grid.add_row(
        Panel(plates_text,          title="Live ANPR Log",    border_style="green"),
        Panel(controls,             title="Key Bindings",     border_style="yellow"),
    )
    grid.add_row(
        Panel(_backend_status_text(), title="Backend Status", border_style="cyan"),
        Text(""),
    )

    layout = Layout()
    layout.split_column(
        Layout(
            Panel("[bold cyan]🚦 Traffic Control Dashboard[/bold cyan]", justify="center"),
            size=3,
        ),
        Layout(alert_panel, size=3 if alert_active else 0),
        Layout(grid),
    )
    return layout


# ==============================================================================
# 8. KEYBOARD HANDLER
# ==============================================================================
def _handle_key(char: str) -> None:
    if char in ("+", "="):
        STATE.spawn_rate = min(CFG.max_spawn_rate, STATE.spawn_rate + 5)
    elif char == "-":
        STATE.spawn_rate = max(CFG.min_spawn_rate, STATE.spawn_rate - 5)
    elif char == "e":
        STATE.trigger_emergency = True
    elif char == "f":
        STATE.trigger_flagged   = True
    elif char == "r":
        STATE.trigger_reset     = True
    elif char == "q":
        STATE.running = False


def start_keyboard_listener() -> None:
    """Start a pynput daemon listener for hotkeys (graceful no-op if unavailable)."""
    if not _HAS_PYNPUT:
        print("Note: pynput not found — hotkeys disabled. pip install pynput to enable.")
        return

    def on_press(key) -> None:
        try:
            ch = key.char.lower() if hasattr(key, "char") and key.char else None
            if ch:
                _handle_key(ch)
        except Exception:
            pass

    listener = pynput_keyboard.Listener(on_press=on_press)
    listener.daemon = True
    listener.start()



# ==============================================================================
# 8b. BACKEND COMMAND POLLING & RL SIGNAL REQUEST
# ==============================================================================

import threading as _threading

_MODE_CYCLE = ["FIXED", "ADAPTIVE", "RL"]


def _do_poll_commands() -> None:
    """Runs in a daemon thread — polls backend for simulation commands."""
    if not _HAS_HTTPX:
        return
    try:
        url = f"{CFG.backend_url}/api/sim/commands/latest"
        resp = _httpx.get(url, timeout=2.0)
        if resp.status_code == 204:
            return  # no pending command
        if not resp.is_success:
            logger.debug("Command poll returned HTTP %d", resp.status_code)
            return

        cmd = resp.json()
        action = cmd.get("action", "")

        if action == "SET_SPAWN_RATE":
            rate = cmd.get("value")
            if rate is not None:
                STATE.spawn_rate = int(rate)
                logger.info("Backend → SET_SPAWN_RATE=%d", STATE.spawn_rate)

        elif action == "SPAWN_EMERGENCY":
            STATE.trigger_emergency = True
            logger.info("Backend → SPAWN_EMERGENCY")

        elif action == "SPAWN_FLAGGED":
            STATE.trigger_flagged = True
            logger.info("Backend → SPAWN_FLAGGED")

        elif action == "RESET_SPAWN_RATE":
            STATE.trigger_reset = True
            logger.info("Backend → RESET_SPAWN_RATE")

        elif action == "SET_MODE":
            new_mode = cmd.get("stringValue", "")
            if new_mode in _MODE_CYCLE:
                STATE.mode = new_mode
                logger.info("Backend → SET_MODE=%s", STATE.mode)

        else:
            return  # unknown action — don't acknowledge

        # Acknowledge (DELETE) so the command isn't picked up again
        _httpx.delete(url, timeout=2.0)

    except Exception as exc:
        logger.debug("Command poll error (non-fatal): %s", exc)


def _poll_backend_commands_async() -> None:
    """Fire-and-forget: spawn a daemon thread to poll backend commands."""
    t = _threading.Thread(target=_do_poll_commands, daemon=True,
                          name=f"cmd-poll-t{STATE.sim_time}")
    t.start()


def request_rl_signal(arm_counts: dict, arm_waits: dict, sim_time: int) -> dict | None:
    """
    POST to ai-services /ai/rl/predict and return the parsed decision dict,
    or None on any error. Runs synchronously — TraCI step is paused while
    we decide, so a 2s timeout is acceptable.
    """
    if not _HAS_HTTPX:
        return None
    try:
        url = f"{CFG.ai_service_url}/ai/rl/predict"
        payload = {
            "intersection_id": "SIM_JUNCTION_001",
            "timestamp": sim_time,
            "north_count": arm_counts.get("north", 0),
            "south_count": arm_counts.get("south", 0),
            "east_count":  arm_counts.get("east",  0),
            "west_count":  arm_counts.get("west",  0),
            "north_wait":  arm_waits.get("north", 0.0),
            "south_wait":  arm_waits.get("south", 0.0),
            "east_wait":   arm_waits.get("east",  0.0),
            "west_wait":   arm_waits.get("west",  0.0),
            "mode": "RL",
            "source": "sumo_simulation",
        }
        resp = _httpx.post(url, json=payload, timeout=2.0)
        if resp.is_success:
            decision = resp.json()
            STATE.last_rl_decision = decision
            return decision
        logger.debug("RL predict returned HTTP %d", resp.status_code)
    except Exception as exc:
        logger.debug("RL signal request error (non-fatal): %s", exc)
    return None


# ==============================================================================
# 9. MAIN
# ==============================================================================
def main() -> None:
    parser = argparse.ArgumentParser(
        description="SUMO Smart Traffic Simulation — SUMO→ai-services→MongoDB pipeline"
    )
    parser.add_argument("--nogui",       action="store_true",  help="Run headless (sumo, not sumo-gui)")
    parser.add_argument("--port",        type=int, default=CFG.traci_port, help="TraCI port")
    parser.add_argument("--steps",       type=int, default=0,  help="Max simulation steps (0 = unlimited)")
    parser.add_argument("--force-regen", action="store_true",  help="Regenerate network files even if they exist")
    parser.add_argument("--verbose",     action="store_true",  help="Enable debug logging")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        os.environ["VERBOSE"] = "1"

    # ── Locate SUMO binary (never import sumolib) ──────────────────────────────
    binary_name = "sumo" if args.nogui else "sumo-gui"
    sumo_binary = shutil.which(binary_name)
    if sumo_binary is None:
        # Fallback: search the project venv
        venv_bin = Path(__file__).parents[2] / "venv" / "bin" / binary_name
        if venv_bin.exists():
            sumo_binary = str(venv_bin)
    if sumo_binary is None:
        print(f"Error: '{binary_name}' not found. Set SUMO_HOME or activate the venv.")
        sys.exit(1)

    # ── Generate simulation files ──────────────────────────────────────────────
    generate_all(force=args.force_regen)

    # ── Reset ANPR log ─────────────────────────────────────────────────────────
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)

    # ── Build SUMO command ─────────────────────────────────────────────────────
    sumo_cmd = [
        sumo_binary,
        "-c", CFG_FILE,
        "--step-length", str(CFG.step_length),
        "--waiting-time-memory", "10000",
        "--start",           # sumo-gui: begin simulation immediately
        "--quit-on-end",     # sumo-gui: close when simulation ends
    ]

    print(f"Starting {binary_name} on port {args.port} …")

    try:
        traci.start(sumo_cmd, port=args.port)
    except Exception as exc:
        print(f"Failed to start TraCI: {exc}")
        sys.exit(1)

    # ── Post-start initialisation ─────────────────────────────────────────────
    init_edge_map()
    init_publisher()
    tls_ids = traci.trafficlight.getIDList()
    tls_id  = tls_ids[0] if tls_ids else None
    start_keyboard_listener()

    max_steps = args.steps or float("inf")

    # ── Main loop ─────────────────────────────────────────────────────────────
    try:
        with Live(generate_dashboard(), refresh_per_second=CFG.refresh_rate) as live:
            while STATE.running and STATE.sim_time < max_steps:
                traci.simulationStep()
                STATE.sim_time += 1

                handle_spawning()

                if tls_id:
                    manage_signal(tls_id)

                check_anpr()
                maybe_publish()         # ← pipeline integration

                # Poll backend for dashboard commands every N steps
                if STATE.sim_time % CFG.command_poll_interval == 0:
                    _poll_backend_commands_async()

                live.update(generate_dashboard())
                time.sleep(0.05)

    except KeyboardInterrupt:
        pass
    except traci.exceptions.FatalTraCIError:
        pass
    finally:
        print("\n── Shutting down ─────────────────────────────────────────────")
        try:
            traci.close()
        except Exception:
            pass

        # ── Final report ──────────────────────────────────────────────────────
        avg_f = (STATE.total_wait_fixed    / STATE.steps_fixed   ) if STATE.steps_fixed    else 0
        avg_a = (STATE.total_wait_adaptive / STATE.steps_adaptive) if STATE.steps_adaptive else 0
        print(f"  Simulated time    : {STATE.sim_time} s")
        print(f"  Total ANPR events : {STATE.total_plates}")
        print(f"  Avg wait FIXED    : {avg_f:.2f} s/step")
        print(f"  Avg wait ADAPTIVE : {avg_a:.2f} s/step")
        print(f"  Last backend resp : {STATE.last_backend_response.get('most_congested_arm', 'N/A')}")
        print("─────────────────────────────────────────────────────────────\n")


if __name__ == "__main__":
    main()
