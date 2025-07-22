# topology.py
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController, OVSKernelSwitch
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel, info

class CustomTopo(Topo):
    def build(self):
        # Hosts
        h1 = self.addHost('h1', ip='10.0.0.1')  # Attacker
        h2 = self.addHost('h2', ip='10.0.0.2')  # Legitimate user
        h3 = self.addHost('h3', ip='10.0.0.3')  # Target server

        # Switches
        s1 = self.addSwitch('s1')
        s2 = self.addSwitch('s2')
        s3 = self.addSwitch('s3')
        s4 = self.addSwitch('s4')

        # Links
        self.addLink(h1, s1, bw=10, delay='1ms')
        self.addLink(h2, s2, bw=10, delay='1ms')
        self.addLink(h3, s4, bw=10, delay='1ms')

        self.addLink(s1, s3, bw=10, delay='10ms')
        self.addLink(s2, s3, bw=10, delay='10ms')
        self.addLink(s3, s4, bw=10, delay='10ms')

if __name__ == '__main__':
    setLogLevel('info')
    topo = CustomTopo()
    net = Mininet(topo=topo, link=TCLink, controller=None, switch=OVSKernelSwitch)

    info("*** Adding controller\n")
    c0 = net.addController('c0', controller=RemoteController, ip='127.0.0.1', port=6633)

    info("*** Starting network\n")
    net.start()
    CLI(net)
    net.stop()
