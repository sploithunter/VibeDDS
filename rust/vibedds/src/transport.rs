/// UDP multicast and unicast transport for RTPS.
///
/// Provides socket management for SPDP multicast, metatraffic unicast,
/// and user data unicast.

use std::io;
use std::net::{Ipv4Addr, SocketAddr, SocketAddrV4, UdpSocket};

use socket2::{Domain, Protocol, Socket, Type};

use crate::constants::{spdp_multicast_port, spdp_unicast_port, user_unicast_port, SPDP_MULTICAST_ADDRESS};

/// A UDP packet received from the network.
#[derive(Debug)]
pub struct ReceivedPacket {
    pub data: Vec<u8>,
    pub source_addr: SocketAddr,
    pub dest_socket: SocketType,
}

/// Identifies which socket received a packet.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SocketType {
    SpdpMulticast,
    MetatrafficUnicast,
    UserUnicast,
}

/// Manages UDP sockets for RTPS communication.
pub struct UdpTransport {
    domain_id: u16,
    participant_id: u16,
    local_ip: Ipv4Addr,
    spdp_mc_port: u16,
    meta_uc_port: u16,
    user_uc_port: u16,
    spdp_mc_sock: Option<UdpSocket>,
    meta_uc_sock: Option<UdpSocket>,
    user_uc_sock: Option<UdpSocket>,
    send_sock: Option<UdpSocket>,
}

impl UdpTransport {
    pub fn new(domain_id: u16, participant_id: u16) -> Self {
        Self {
            domain_id,
            participant_id,
            local_ip: get_local_ip(),
            spdp_mc_port: spdp_multicast_port(domain_id),
            meta_uc_port: spdp_unicast_port(domain_id, participant_id),
            user_uc_port: user_unicast_port(domain_id, participant_id),
            spdp_mc_sock: None,
            meta_uc_sock: None,
            user_uc_sock: None,
            send_sock: None,
        }
    }

    pub fn local_ip(&self) -> Ipv4Addr {
        self.local_ip
    }

    pub fn metatraffic_unicast_port(&self) -> u16 {
        self.meta_uc_port
    }

    pub fn user_unicast_port(&self) -> u16 {
        self.user_uc_port
    }

    pub fn spdp_multicast_port(&self) -> u16 {
        self.spdp_mc_port
    }

    pub fn open(&mut self) -> io::Result<()> {
        self.spdp_mc_sock = Some(self.open_spdp_multicast()?);
        self.meta_uc_sock = Some(self.open_unicast(self.meta_uc_port)?);
        self.user_uc_sock = Some(self.open_unicast(self.user_uc_port)?);
        self.send_sock = Some(self.open_send_socket()?);

        log::info!(
            "Transport opened: local_ip={}, spdp_mc={}, meta_uc={}, user_uc={}",
            self.local_ip,
            self.spdp_mc_port,
            self.meta_uc_port,
            self.user_uc_port
        );
        Ok(())
    }

    fn open_spdp_multicast(&self) -> io::Result<UdpSocket> {
        let socket = Socket::new(Domain::IPV4, Type::DGRAM, Some(Protocol::UDP))?;
        socket.set_reuse_address(true)?;
        #[cfg(target_os = "macos")]
        socket.set_reuse_port(true)?;

        let addr = SocketAddrV4::new(Ipv4Addr::UNSPECIFIED, self.spdp_mc_port);
        socket.bind(&addr.into())?;

        // Join multicast group
        let mcast_addr: Ipv4Addr = SPDP_MULTICAST_ADDRESS.parse().unwrap();
        socket.join_multicast_v4(&mcast_addr, &Ipv4Addr::UNSPECIFIED)?;
        socket.set_nonblocking(true)?;

        Ok(socket.into())
    }

    fn open_unicast(&self, port: u16) -> io::Result<UdpSocket> {
        let socket = Socket::new(Domain::IPV4, Type::DGRAM, Some(Protocol::UDP))?;
        socket.set_reuse_address(true)?;
        #[cfg(target_os = "macos")]
        socket.set_reuse_port(true)?;

        let addr = SocketAddrV4::new(Ipv4Addr::UNSPECIFIED, port);
        socket.bind(&addr.into())?;
        socket.set_nonblocking(true)?;

        Ok(socket.into())
    }

    fn open_send_socket(&self) -> io::Result<UdpSocket> {
        let socket = Socket::new(Domain::IPV4, Type::DGRAM, Some(Protocol::UDP))?;
        // Enable multicast loopback for single-host testing
        socket.set_multicast_loop_v4(true)?;
        socket.set_multicast_ttl_v4(1)?;

        Ok(socket.into())
    }

    pub fn close(&mut self) {
        self.spdp_mc_sock = None;
        self.meta_uc_sock = None;
        self.user_uc_sock = None;
        self.send_sock = None;
    }

    /// Send data to the SPDP multicast group.
    pub fn send_multicast(&self, data: &[u8]) -> io::Result<()> {
        if let Some(sock) = &self.send_sock {
            let mcast_addr: Ipv4Addr = SPDP_MULTICAST_ADDRESS.parse().unwrap();
            let dest = SocketAddrV4::new(mcast_addr, self.spdp_mc_port);
            sock.send_to(data, dest)?;
        }
        Ok(())
    }

    /// Send data to a specific unicast address:port.
    pub fn send_unicast(&self, data: &[u8], addr: Ipv4Addr, port: u16) -> io::Result<()> {
        if let Some(sock) = &self.send_sock {
            let dest = SocketAddrV4::new(addr, port);
            sock.send_to(data, dest)?;
        }
        Ok(())
    }

    /// Try to receive a packet from the SPDP multicast socket.
    pub fn try_recv_spdp_multicast(&self) -> io::Result<Option<ReceivedPacket>> {
        self.try_recv(&self.spdp_mc_sock, SocketType::SpdpMulticast)
    }

    /// Try to receive a packet from the metatraffic unicast socket.
    pub fn try_recv_metatraffic(&self) -> io::Result<Option<ReceivedPacket>> {
        self.try_recv(&self.meta_uc_sock, SocketType::MetatrafficUnicast)
    }

    /// Try to receive a packet from the user unicast socket.
    pub fn try_recv_user(&self) -> io::Result<Option<ReceivedPacket>> {
        self.try_recv(&self.user_uc_sock, SocketType::UserUnicast)
    }

    fn try_recv(
        &self,
        sock: &Option<UdpSocket>,
        sock_type: SocketType,
    ) -> io::Result<Option<ReceivedPacket>> {
        let sock = match sock {
            Some(s) => s,
            None => return Ok(None),
        };

        let mut buf = [0u8; 65536];
        match sock.recv_from(&mut buf) {
            Ok((len, addr)) => Ok(Some(ReceivedPacket {
                data: buf[..len].to_vec(),
                source_addr: addr,
                dest_socket: sock_type,
            })),
            Err(e) if e.kind() == io::ErrorKind::WouldBlock => Ok(None),
            Err(e) => Err(e),
        }
    }

    /// Get file descriptors for use with select/poll.
    #[cfg(unix)]
    pub fn get_fds(&self) -> Vec<i32> {
        use std::os::unix::io::AsRawFd;
        let mut fds = Vec::new();
        if let Some(s) = &self.spdp_mc_sock {
            fds.push(s.as_raw_fd());
        }
        if let Some(s) = &self.meta_uc_sock {
            fds.push(s.as_raw_fd());
        }
        if let Some(s) = &self.user_uc_sock {
            fds.push(s.as_raw_fd());
        }
        fds
    }
}

/// Detect the local IP address used for outbound connections.
fn get_local_ip() -> Ipv4Addr {
    // Create a UDP socket and connect to a public address (doesn't send data)
    if let Ok(socket) = UdpSocket::bind("0.0.0.0:0") {
        if socket.connect("8.8.8.8:80").is_ok() {
            if let Ok(local_addr) = socket.local_addr() {
                if let SocketAddr::V4(v4) = local_addr {
                    return *v4.ip();
                }
            }
        }
    }
    Ipv4Addr::LOCALHOST
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_get_local_ip() {
        let ip = get_local_ip();
        // Should return a valid IPv4 address
        assert!(!ip.is_unspecified());
    }

    #[test]
    fn test_transport_new() {
        let transport = UdpTransport::new(0, 0);
        assert_eq!(transport.spdp_multicast_port(), 7400);
        assert_eq!(transport.metatraffic_unicast_port(), 7410);
        assert_eq!(transport.user_unicast_port(), 7401);
    }

    #[test]
    fn test_transport_new_participant_1() {
        let transport = UdpTransport::new(0, 1);
        assert_eq!(transport.metatraffic_unicast_port(), 7412);
        assert_eq!(transport.user_unicast_port(), 7403);
    }

    #[test]
    fn test_transport_domain_1() {
        let transport = UdpTransport::new(1, 0);
        assert_eq!(transport.spdp_multicast_port(), 7650); // 7400 + 250*1
        assert_eq!(transport.metatraffic_unicast_port(), 7660); // 7410 + 250*1
        assert_eq!(transport.user_unicast_port(), 7651); // 7401 + 250*1
    }

    #[test]
    fn test_transport_local_ip() {
        let transport = UdpTransport::new(0, 0);
        let ip = transport.local_ip();
        assert!(!ip.is_unspecified());
    }

    #[test]
    fn test_transport_open_close() {
        // Use unique participant_id to avoid port conflicts with other tests
        let mut transport = UdpTransport::new(0, 20);

        // Open should succeed
        let result = transport.open();
        assert!(result.is_ok(), "Failed to open transport: {:?}", result.err());

        // Close should not panic
        transport.close();
    }

    #[test]
    fn test_transport_try_recv_before_open() {
        let transport = UdpTransport::new(0, 21);

        // try_recv before open should return None (not error)
        let result = transport.try_recv_spdp_multicast();
        assert!(result.is_ok());
        assert!(result.unwrap().is_none());

        let result = transport.try_recv_metatraffic();
        assert!(result.is_ok());
        assert!(result.unwrap().is_none());

        let result = transport.try_recv_user();
        assert!(result.is_ok());
        assert!(result.unwrap().is_none());
    }

    #[test]
    fn test_transport_send_before_open() {
        let transport = UdpTransport::new(0, 22);

        // send_multicast before open should succeed (just does nothing)
        let result = transport.send_multicast(b"test");
        assert!(result.is_ok());

        // send_unicast before open should succeed (just does nothing)
        let result = transport.send_unicast(b"test", Ipv4Addr::LOCALHOST, 12345);
        assert!(result.is_ok());
    }

    #[test]
    fn test_transport_send_multicast_after_open() {
        let mut transport = UdpTransport::new(0, 23);
        transport.open().unwrap();

        // Send should succeed
        let result = transport.send_multicast(b"RTPS test message");
        assert!(result.is_ok());

        transport.close();
    }

    #[test]
    fn test_transport_try_recv_empty() {
        let mut transport = UdpTransport::new(0, 24);
        transport.open().unwrap();

        // No messages pending, should return None
        let result = transport.try_recv_spdp_multicast();
        assert!(result.is_ok());
        assert!(result.unwrap().is_none());

        transport.close();
    }

    #[cfg(unix)]
    #[test]
    fn test_transport_get_fds_before_open() {
        let transport = UdpTransport::new(0, 25);
        let fds = transport.get_fds();
        assert!(fds.is_empty());
    }

    #[cfg(unix)]
    #[test]
    fn test_transport_get_fds_after_open() {
        let mut transport = UdpTransport::new(0, 26);
        transport.open().unwrap();

        let fds = transport.get_fds();
        // Should have 3 file descriptors (spdp_mc, meta_uc, user_uc)
        assert_eq!(fds.len(), 3);

        transport.close();
    }

    #[test]
    fn test_socket_type_debug() {
        // Ensure SocketType derives work
        let st = SocketType::SpdpMulticast;
        assert_eq!(format!("{:?}", st), "SpdpMulticast");

        let st2 = st.clone();
        assert_eq!(st, st2);
    }

    #[test]
    fn test_received_packet_debug() {
        let pkt = ReceivedPacket {
            data: vec![1, 2, 3],
            source_addr: "127.0.0.1:1234".parse().unwrap(),
            dest_socket: SocketType::UserUnicast,
        };
        // Ensure Debug derive works
        let debug_str = format!("{:?}", pkt);
        assert!(debug_str.contains("ReceivedPacket"));
    }
}
