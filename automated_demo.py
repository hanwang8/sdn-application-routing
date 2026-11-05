#!/usr/bin/env python3
"""One-command Mininet demonstration and automatic path verification."""

import argparse
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time

from mininet.log import setLogLevel
from mininet.net import Mininet
from mininet.node import OVSSwitch, RemoteController
from mininet.topo import Topo


PROJECT_DIR = Path(__file__).resolve().parent
RESULTS_DIR = PROJECT_DIR / "results"


class ApplicationRoutingTopology(Topo):
    def build(self):
        h1 = self.addHost("h1", ip="10.0.0.1/24", mac="00:00:00:00:00:01")
        h2 = self.addHost("h2", ip="10.0.0.2/24", mac="00:00:00:00:00:02")
        s1 = self.addSwitch("s1", dpid="0000000000000001", protocols="OpenFlow13")
        s2 = self.addSwitch("s2", dpid="0000000000000002", protocols="OpenFlow13")
        s3 = self.addSwitch("s3", dpid="0000000000000003", protocols="OpenFlow13")
        s4 = self.addSwitch("s4", dpid="0000000000000004", protocols="OpenFlow13")

        self.addLink(h1, s1, port2=1)
        self.addLink(h2, s4, port2=1)
        self.addLink(s1, s2, port1=2, port2=1)
        self.addLink(s1, s3, port1=3, port2=1)
        self.addLink(s2, s4, port1=2, port2=2)
        self.addLink(s3, s4, port1=2, port2=3)


def require_environment():
    if os.geteuid() != 0:
        raise SystemExit("Run this demonstration with sudo.")
    required = ["ryu-manager", "ovs-vsctl", "curl"]
    missing = [command for command in required if shutil.which(command) is None]
    if missing:
        raise SystemExit("Missing required commands: {}".format(", ".join(missing)))


def wait_for_controller(port=6653, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.25)
    raise RuntimeError("Ryu controller did not start; inspect results/ryu.log")


def interface_bytes(interface):
    base = Path("/sys/class/net") / interface / "statistics"
    return int((base / "rx_bytes").read_text()) + int((base / "tx_bytes").read_text())


def snapshot_paths():
    return {
        "upper_s2": interface_bytes("s2-eth2"),
        "lower_s3": interface_bytes("s3-eth2"),
    }


def difference(before, after):
    return {key: after[key] - before[key] for key in before}


def maybe_pause(enabled, message):
    if enabled:
        input("\n{} Press Enter to continue... ".format(message))


def run_demo(pause=False):
    require_environment()
    RESULTS_DIR.mkdir(exist_ok=True)
    log_handle = open(str(RESULTS_DIR / "ryu.log"), "w")
    controller = subprocess.Popen(
        [
            "ryu-manager",
            "--ofp-tcp-listen-port",
            "6653",
            str(PROJECT_DIR / "application_router.py"),
        ],
        stdout=log_handle,
        stderr=subprocess.STDOUT,
    )
    net = None
    try:
        wait_for_controller()
        print("[1/5] Ryu controller is ready.")
        net = Mininet(
            topo=ApplicationRoutingTopology(),
            controller=None,
            switch=OVSSwitch,
        )
        net.addController(
            "c0", controller=RemoteController, ip="127.0.0.1", port=6653
        )
        net.start()
        time.sleep(3)
        print("[2/5] Topology started: h1--s1--{s2,s3}--s4--h2")

        h1, h2 = net.get("h1", "h2")
        http_pid = h2.cmd(
            "python3 -m http.server 80 --bind 10.0.0.2 "
            "> /tmp/demo-http.log 2>&1 & echo $!"
        ).strip()
        bulk_pid = h2.cmd(
            "python3 {} > /tmp/demo-bulk.log 2>&1 & echo $!".format(
                PROJECT_DIR / "bulk_server.py"
            )
        ).strip()
        time.sleep(1)

        print("[3/5] Verifying basic connectivity and learning ARP...")
        ping_result = h1.cmd("ping -c 3 -W 2 10.0.0.2")
        if "0% packet loss" not in ping_result:
            raise RuntimeError("Basic h1-to-h2 connectivity failed")

        maybe_pause(pause, "HTTP traffic will now use the upper path.")
        before_http = snapshot_paths()
        http_output = h1.cmd("curl --max-time 5 -s http://10.0.0.2/")
        after_http = snapshot_paths()
        http_delta = difference(before_http, after_http)
        http_passed = bool(http_output) and http_delta["upper_s2"] > http_delta["lower_s3"]
        print(
            "[4/5] HTTP: upper={:,} bytes, lower={:,} bytes [{}]".format(
                http_delta["upper_s2"],
                http_delta["lower_s3"],
                "PASS" if http_passed else "FAIL",
            )
        )

        maybe_pause(pause, "Bulk TCP traffic will now use the lower path.")
        before_bulk = snapshot_paths()
        bulk_output = h1.cmd(
            "python3 {} 10.0.0.2 8".format(PROJECT_DIR / "bulk_client.py")
        )
        after_bulk = snapshot_paths()
        bulk_delta = difference(before_bulk, after_bulk)
        bulk_passed = (
            "server received 8388608 bytes" in bulk_output
            and bulk_delta["lower_s3"] > bulk_delta["upper_s2"]
        )
        print(bulk_output.strip())
        print(
            "[5/5] BULK: upper={:,} bytes, lower={:,} bytes [{}]".format(
                bulk_delta["upper_s2"],
                bulk_delta["lower_s3"],
                "PASS" if bulk_passed else "FAIL",
            )
        )

        print("Overall result: {}".format("PASS" if http_passed and bulk_passed else "FAIL"))

        h2.cmd("kill {} {} 2>/dev/null".format(http_pid, bulk_pid))
        return 0 if http_passed and bulk_passed else 1
    finally:
        if net is not None:
            net.stop()
        controller.terminate()
        try:
            controller.wait(timeout=5)
        except subprocess.TimeoutExpired:
            controller.kill()
        log_handle.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pause", action="store_true", help="pause between demo stages")
    arguments = parser.parse_args()
    setLogLevel("warning")
    sys.exit(run_demo(arguments.pause))


if __name__ == "__main__":
    main()
