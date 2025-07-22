# dos_protector_controller.py

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, CONFIG_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types
from ryu.lib import hub

import time

class DoSProtector(app_manager.RyuApp):
    # Specifica la versione OpenFlow usata (1.3)
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(DoSProtector, self).__init__(*args, **kwargs)
        # Mappa MAC → porta per ogni switch (usato per apprendimento L2)
        self.mac_to_port = {}
        # Switch attivi
        self.datapaths = {}
        # Statistiche per ogni porta (usate per throughput)
        self.port_stats = {}  # {dpid: {port_no: (last_rx_bytes, last_timestamp)}}
        # Soglia oltre la quale consideriamo un attacco (in Byte/s)
        self.threshold = 1_000_000  # 1 MB/s
        # Ogni quanti secondi leggere le statistiche
        self.monitor_interval = 2  # più reattivo
        # Mappa per tenere traccia delle porte già bloccate
        self.alarmed_ports = {}  # (dpid, port_no): bool
        # Thread per il monitoraggio
        self.monitor_thread = None
        # DPID attesi (topologia conosciuta)
        self.expected_dpids = {1, 2, 3, 4}

    # Gestisce evento iniziale: installa flow-table di default
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath

        if datapath.id not in self.expected_dpids:
            self.logger.warning("Ignoring unknown datapath: %s", datapath.id)
            return

        # Flow table di default: invia tutto al controller
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

    # Funzione per aggiungere una nuova regola di flusso (flow)
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

    # Registra o rimuove switch nel controller
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

            # Avvia thread di monitoraggio solo se tutti gli switch sono online
            if self.monitor_thread is None and len(self.datapaths) >= len(self.expected_dpids):
                self.logger.info("Starting monitor thread (all switches registered)")
                self.monitor_thread = hub.spawn(self._monitor)

        elif ev.state == 'DEAD':
            if datapath.id in self.datapaths:
                self.logger.info("Unregister datapath: %016x", datapath.id)
                del self.datapaths[datapath.id]

    # Thread che chiede regolarmente le statistiche
    def _monitor(self):
        while True:
            for dp in self.datapaths.values():
                self._request_stats(dp)
            hub.sleep(self.monitor_interval)

    # Invia richiesta di statistiche porta a uno switch
    def _request_stats(self, datapath):
        parser = datapath.ofproto_parser
        req = parser.OFPPortStatsRequest(datapath, 0, datapath.ofproto.OFPP_ANY)
        datapath.send_msg(req)

    # Analizza la risposta con le statistiche e valuta il throughput
    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def _port_stats_reply_handler(self, ev):
        body = ev.msg.body
        dpid = ev.msg.datapath.id
        now = time.time()

        for stat in body:
            port_no = stat.port_no
            rx_bytes = stat.rx_bytes

            # Ignora le porte speciali come LOCAL (4294967294)
            if port_no >= 0xffffff00:
                continue

            key = (dpid, port_no)
            old_rx_bytes, old_time = self.port_stats.get(key, (0, now))
            delta_bytes = rx_bytes - old_rx_bytes
            delta_time = now - old_time if now > old_time else 1
            throughput = delta_bytes / delta_time

            self.logger.info("DPID %s Port %s Throughput: %.2f B/s", dpid, port_no, throughput)

            # Se supera la soglia, blocca
            if throughput > self.threshold:
                if not self.alarmed_ports.get(key, False):
                    self.logger.warning("!!! ALERT: High traffic on DPID %s port %s. Blocking...", dpid, port_no)
                    self._block_port(ev.msg.datapath, port_no)
                    self.alarmed_ports[key] = True
            else:
                # Se ritorna sotto la soglia, sblocca
                if self.alarmed_ports.get(key, False):
                    self.logger.info("Traffic normalized on DPID %s port %s. Unblocking...", dpid, port_no)
                    self._unblock_port(ev.msg.datapath, port_no)
                    self.alarmed_ports[key] = False

            # Aggiorna stato attuale
            self.port_stats[key] = (rx_bytes, now)

    # Blocca una porta: aggiunge regola drop
    def _block_port(self, datapath, port_no):
        parser = datapath.ofproto_parser
        match = parser.OFPMatch(in_port=port_no)
        actions = []
        self.add_flow(datapath, priority=100, match=match, actions=actions)

    # Sblocca una porta: rimuove regola drop
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

    # Gestione pacchetti in ingresso (packet-in)
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
            return  # Ignora pacchetti LLDP (usati per discovery)

        dst = eth.dst
        src = eth.src
        dpid = datapath.id

        if dpid not in self.expected_dpids:
            return

        # Impara la porta sorgente
        self.mac_to_port.setdefault(dpid, {})
        self.mac_to_port[dpid][src] = in_port

        # Se conosce il MAC di destinazione, invia direttamente
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
