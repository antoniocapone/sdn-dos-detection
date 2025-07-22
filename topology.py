# topology.py
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController, OVSKernelSwitch, Host
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel, info

class Environment(Topo):
    def build(self):
        h1 = self.addHost('h1', cls = Host, mac = '00:00:00:00:00:01', ip = '10.0.0.1')
        h2 = self.addHost('h2', cls = Host, mac = '00:00:00:00:00:02', ip = '10.0.0.2')
        h3 = self.addHost('h3', cls = Host, mac = '00:00:00:00:00:03', ip = '10.0.0.3')

        s2 = self.addSwitch('s2', cls = OVSKernelSwitch, protocols = 'OpenFlow13')
        s1 = self.addSwitch('s1', cls = OVSKernelSwitch, protocols = 'OpenFlow13')
        s3 = self.addSwitch('s3', cls = OVSKernelSwitch, protocols = 'OpenFlow13')
        s4 = self.addSwitch('s4', cls = OVSKernelSwitch, protocols = 'OpenFlow13')

        self.addLink(h1, s1, bw = 6, delay = '0.0025ms')
        self.addLink(h2, s2, bw = 6, delay = '0.0025ms')
        self.addLink(s1, s3, bw = 3, delay = '25ms')
        self.addLink(s2, s3, bw = 3, delay = '25ms')
        self.addLink(s3, s4, bw = 3, delay = '25ms')
        self.addLink(s4, h3, bw = 6, delay = '0.0025ms')

if __name__ == '__main__':
    setLogLevel('info')
    topology = Environment()
    net = Mininet(topo = topology, link = TCLink, controller = None, switch = OVSKernelSwitch)

    info("*** Adding controller ***\n")
    c0 = net.addController('c0', controller = RemoteController, ip = '127.0.0.1', port = 6633)

    info("*** Starting network ***\n")
    net.start()
    CLI(net)
    net.stop()
