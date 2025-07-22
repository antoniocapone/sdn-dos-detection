# dos_protector_controller.py

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, CONFIG_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types
from ryu.lib import hub

import time
import threading
from flask import Flask, jsonify, request

class DoSProtector(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(DoSProtector, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.datapaths = {}
        self.port_stats = {}  # {dpid: {port_no: (last_rx_bytes, last_timestamp)}}
        self.threshold = 1_000_000  # Default: 1 MB/s
        self.monitor_interval = 2  # more reactive
        self.alarmed_ports = {}  # (dpid, port_no): bool
        self.monitor_thread = None
        self.expected_dpids = {1, 2, 3, 4}

        # REST API state
        self.status_snapshot = {}  # {(dpid, port): {throughput, alarmed, timestamp}}

        # Flask server in background
        self.api_thread = threading.Thread(target=self._start_rest_server)
        self.api_thread.daemon = True
        self.api_thread.start()

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath

        if datapath.id not in self.expected_dpids:
            self.logger.warning("Ignoring unknown datapath: %s", datapath.id)
            return

        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

    def add_flow(self, datapath, priority, match, actions, buffer_id=None):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]

        if buffer_id:
            mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id,
                                     priority=priority, match=match, instructions=inst)
        else:
            mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                     match=match, instructions=inst)
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, CONFIG_DISPATCHER])
    def _state_change_handler(self, ev):
        datapath = ev.datapath

        if ev.state == MAIN_DISPATCHER:
            if datapath.id not in self.expected_dpids:
                self.logger.info("Unknown datapath %s ignored.", datapath.id)
                return

            if datapath.id not in self.datapaths:
                self.logger.info("Register datapath: %016x", datapath.id)
                self.datapaths[datapath.id] = datapath

            if self.monitor_thread is None and len(self.datapaths) >= len(self.expected_dpids):
                self.logger.info("Starting monitor thread (all switches registered)")
                self.monitor_thread = hub.spawn(self._monitor)

        elif ev.state == 'DEAD':
            if datapath.id in self.datapaths:
                self.logger.info("Unregister datapath: %016x", datapath.id)
                del self.datapaths[datapath.id]

    def _monitor(self):
        while True:
            for dp in self.datapaths.values():
                self._request_stats(dp)
            hub.sleep(self.monitor_interval)

    def _request_stats(self, datapath):
        parser = datapath.ofproto_parser
        req = parser.OFPPortStatsRequest(datapath, 0, datapath.ofproto.OFPP_ANY)
        datapath.send_msg(req)

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def _port_stats_reply_handler(self, ev):
        body = ev.msg.body
        dpid = ev.msg.datapath.id
        now = time.time()

        for stat in body:
            port_no = stat.port_no
            rx_bytes = stat.rx_bytes

            if port_no >= 0xffffff00:
                continue

            key = (dpid, port_no)
            old_rx_bytes, old_time = self.port_stats.get(key, (0, now))
            delta_bytes = rx_bytes - old_rx_bytes
            delta_time = now - old_time if now > old_time else 1
            throughput = delta_bytes / delta_time

            self.logger.info("DPID %s Port %s Throughput: %.2f B/s", dpid, port_no, throughput)

            if throughput > self.threshold:
                if not self.alarmed_ports.get(key, False):
                    self.logger.warning("!!! ALERT: High traffic on DPID %s port %s. Blocking...", dpid, port_no)
                    self._block_port(ev.msg.datapath, port_no)
                    self.alarmed_ports[key] = True
            else:
                if self.alarmed_ports.get(key, False):
                    self.logger.info("Traffic normalized on DPID %s port %s. Unblocking...", dpid, port_no)
                    self._unblock_port(ev.msg.datapath, port_no)
                    self.alarmed_ports[key] = False

            self.port_stats[key] = (rx_bytes, now)
            self.status_snapshot[key] = {
                'throughput': throughput,
                'alarmed': self.alarmed_ports.get(key, False),
                'timestamp': now
            }

    def _block_port(self, datapath, port_no):
        parser = datapath.ofproto_parser
        match = parser.OFPMatch(in_port=port_no)
        actions = []
        self.add_flow(datapath, priority=100, match=match, actions=actions)

    def _unblock_port(self, datapath, port_no):
        parser = datapath.ofproto_parser
        match = parser.OFPMatch(in_port=port_no)
        mod = parser.OFPFlowMod(datapath=datapath,
                                command=datapath.ofproto.OFPFC_DELETE,
                                out_port=datapath.ofproto.OFPP_ANY,
                                out_group=datapath.ofproto.OFPG_ANY,
                                priority=100,
                                match=match)
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        dst = eth.dst
        src = eth.src
        dpid = datapath.id

        if dpid not in self.expected_dpids:
            return

        self.mac_to_port.setdefault(dpid, {})
        self.mac_to_port[dpid][src] = in_port

        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]
        match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)

        if msg.buffer_id != ofproto.OFP_NO_BUFFER:
            self.add_flow(datapath, 1, match, actions, msg.buffer_id)
            return
        else:
            self.add_flow(datapath, 1, match, actions)

        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                  in_port=in_port, actions=actions, data=msg.data)
        datapath.send_msg(out)

    def _start_rest_server(self):
        app = Flask(__name__)

        @app.route('/api/status')
        def status():
            output = {
                'threshold': self.threshold,
                'ports': []
            }
            for key, val in self.status_snapshot.items():
                dpid, port = key
                output['ports'].append({
                    'dpid': dpid,
                    'port': port,
                    'throughput': val['throughput'],
                    'alarmed': val['alarmed'],
                    'timestamp': val['timestamp']
                })
            return jsonify(output)

        @app.route('/api/threshold', methods=['POST'])
        def update_threshold():
            data = request.get_json()
            if 'threshold' in data:
                try:
                    new_thresh = int(data['threshold'])
                    self.threshold = new_thresh
                    return jsonify({"status": "ok", "threshold": self.threshold})
                except Exception as e:
                    return jsonify({"status": "error", "message": str(e)}), 400
            return jsonify({"status": "error", "message": "Missing threshold"}), 400

        app.run(port=5001, host='0.0.0.0')