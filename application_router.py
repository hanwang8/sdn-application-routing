#!/usr/bin/env python3
"""OpenFlow 1.3 application-aware router.

TCP/80 (HTTP) uses the upper path s1-s2-s4.
TCP/5001 (bulk transfer) uses the lower path s1-s3-s4.
ARP and all other IPv4 traffic use the upper path.
"""

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3


class ApplicationRouter(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        self.logger.info("Configuring s%s", datapath.id)
        self.install_switch_rules(datapath)

    def add_flow(self, datapath, priority, match_fields, output_port):
        parser = datapath.ofproto_parser
        match = parser.OFPMatch(**match_fields)
        actions = [parser.OFPActionOutput(output_port)]
        instructions = [
            parser.OFPInstructionActions(
                datapath.ofproto.OFPIT_APPLY_ACTIONS, actions
            )
        ]
        message = parser.OFPFlowMod(
            datapath=datapath,
            priority=priority,
            match=match,
            instructions=instructions,
        )
        datapath.send_msg(message)

    def add_bidirectional_link(self, datapath, port_a, port_b, priority=100):
        self.add_flow(datapath, priority, {"in_port": port_a}, port_b)
        self.add_flow(datapath, priority, {"in_port": port_b}, port_a)

    def install_switch_rules(self, datapath):
        switch_id = datapath.id

        # Intermediate switches simply forward between their two ports.
        if switch_id in (2, 3):
            self.add_bidirectional_link(datapath, 1, 2)
            return

        if switch_id == 1:
            self.install_s1_rules(datapath)
            return

        if switch_id == 4:
            self.install_s4_rules(datapath)
            return

        self.logger.warning("Unknown switch DPID %s; no forwarding rules installed", switch_id)

    def install_s1_rules(self, datapath):
        # Port map: 1=h1, 2=s2 (upper), 3=s3 (lower).
        # Application-specific rules have the highest priority.
        self.add_flow(
            datapath,
            300,
            {"in_port": 1, "eth_type": 0x0800, "ip_proto": 6, "tcp_dst": 80},
            2,
        )
        self.add_flow(
            datapath,
            300,
            {"in_port": 2, "eth_type": 0x0800, "ip_proto": 6, "tcp_src": 80},
            1,
        )
        self.add_flow(
            datapath,
            300,
            {"in_port": 1, "eth_type": 0x0800, "ip_proto": 6, "tcp_dst": 5001},
            3,
        )
        self.add_flow(
            datapath,
            300,
            {"in_port": 3, "eth_type": 0x0800, "ip_proto": 6, "tcp_src": 5001},
            1,
        )

        # ARP and ordinary IPv4 traffic use the upper path.
        self.add_flow(datapath, 200, {"in_port": 1, "eth_type": 0x0806}, 2)
        self.add_flow(datapath, 200, {"in_port": 2, "eth_type": 0x0806}, 1)
        self.add_flow(datapath, 100, {"in_port": 1, "eth_type": 0x0800}, 2)
        self.add_flow(datapath, 100, {"in_port": 2, "eth_type": 0x0800}, 1)
        self.add_flow(datapath, 100, {"in_port": 3, "eth_type": 0x0800}, 1)

    def install_s4_rules(self, datapath):
        # Port map: 1=h2, 2=s2 (upper), 3=s3 (lower).
        self.add_flow(
            datapath,
            300,
            {"in_port": 2, "eth_type": 0x0800, "ip_proto": 6, "tcp_dst": 80},
            1,
        )
        self.add_flow(
            datapath,
            300,
            {"in_port": 1, "eth_type": 0x0800, "ip_proto": 6, "tcp_src": 80},
            2,
        )
        self.add_flow(
            datapath,
            300,
            {"in_port": 3, "eth_type": 0x0800, "ip_proto": 6, "tcp_dst": 5001},
            1,
        )
        self.add_flow(
            datapath,
            300,
            {"in_port": 1, "eth_type": 0x0800, "ip_proto": 6, "tcp_src": 5001},
            3,
        )

        self.add_flow(datapath, 200, {"in_port": 1, "eth_type": 0x0806}, 2)
        self.add_flow(datapath, 200, {"in_port": 2, "eth_type": 0x0806}, 1)
        self.add_flow(datapath, 100, {"in_port": 1, "eth_type": 0x0800}, 2)
        self.add_flow(datapath, 100, {"in_port": 2, "eth_type": 0x0800}, 1)
        self.add_flow(datapath, 100, {"in_port": 3, "eth_type": 0x0800}, 1)
