"""UDP multicast and unicast transport for RTPS.

Provides socket management for SPDP multicast, metatraffic unicast,
and user data unicast.
"""

from __future__ import annotations

import socket
import struct
import sys
import logging
from dataclasses import dataclass

from vibedds.constants import (
    SPDP_MULTICAST_ADDRESS,
    spdp_multicast_port, spdp_unicast_port, user_unicast_port, user_multicast_port,
)

logger = logging.getLogger(__name__)


def get_local_ip() -> str:
    """Detect the local IP address used for outbound connections."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


@dataclass
class ReceivedPacket:
    """A UDP packet received from the network."""
    data: bytes
    source_addr: str
    source_port: int
    dest_socket: str  # "spdp_multicast", "metatraffic_unicast", "user_unicast"


class UdpTransport:
    """Manages UDP sockets for RTPS communication.

    Opens three sockets:
    - SPDP multicast receiver (239.255.0.1 on SPDP port)
    - Metatraffic unicast receiver (for SEDP and builtin endpoints)
    - User data unicast receiver (for user DataWriter/DataReader)
    """

    def __init__(self, domain_id: int = 0, participant_id: int = 0):
        self.domain_id = domain_id
        self.participant_id = participant_id
        self.local_ip = get_local_ip()

        self._spdp_multicast_port = spdp_multicast_port(domain_id)
        self._metatraffic_unicast_port = spdp_unicast_port(domain_id, participant_id)
        self._user_unicast_port = user_unicast_port(domain_id, participant_id)
        self._user_multicast_port = user_multicast_port(domain_id)

        self._spdp_mc_sock: socket.socket | None = None
        self._meta_uc_sock: socket.socket | None = None
        self._user_uc_sock: socket.socket | None = None
        self._user_mc_sock: socket.socket | None = None
        self._send_sock: socket.socket | None = None

    @property
    def metatraffic_unicast_port(self) -> int:
        return self._metatraffic_unicast_port

    @property
    def user_unicast_port(self) -> int:
        return self._user_unicast_port

    @property
    def spdp_multicast_port_value(self) -> int:
        return self._spdp_multicast_port

    def open(self) -> None:
        """Open all sockets."""
        self._open_spdp_multicast()
        self._open_metatraffic_unicast()
        self._open_user_unicast()
        self._open_user_multicast()
        self._open_send_socket()
        logger.info(
            "Transport opened: local_ip=%s, spdp_mc=%d, meta_uc=%d, user_uc=%d",
            self.local_ip, self._spdp_multicast_port,
            self._metatraffic_unicast_port, self._user_unicast_port,
        )

    def _open_spdp_multicast(self) -> None:
        """Open SPDP multicast receive socket."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if sys.platform == "darwin":
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        sock.bind(("", self._spdp_multicast_port))

        # Join multicast group
        mreq = struct.pack(
            "4s4s",
            socket.inet_aton(SPDP_MULTICAST_ADDRESS),
            socket.inet_aton("0.0.0.0"),
        )
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        sock.setblocking(False)
        self._spdp_mc_sock = sock

    def _open_metatraffic_unicast(self) -> None:
        """Open metatraffic unicast receive socket."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if sys.platform == "darwin":
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        sock.bind(("", self._metatraffic_unicast_port))
        sock.setblocking(False)
        self._meta_uc_sock = sock

    def _open_user_unicast(self) -> None:
        """Open user data unicast receive socket."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if sys.platform == "darwin":
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        sock.bind(("", self._user_unicast_port))
        sock.setblocking(False)
        self._user_uc_sock = sock

    def _open_user_multicast(self) -> None:
        """Open user data multicast receive socket."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if sys.platform == "darwin":
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        sock.bind(("", self._user_multicast_port))

        mreq = struct.pack(
            "4s4s",
            socket.inet_aton(SPDP_MULTICAST_ADDRESS),
            socket.inet_aton("0.0.0.0"),
        )
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        sock.setblocking(False)
        self._user_mc_sock = sock

    def _open_send_socket(self) -> None:
        """Open a socket for sending (multicast and unicast)."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        # Enable multicast loopback for single-host testing
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
        # Set multicast TTL
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
        self._send_sock = sock

    def close(self) -> None:
        """Close all sockets."""
        for sock in [self._spdp_mc_sock, self._meta_uc_sock,
                     self._user_uc_sock, self._user_mc_sock, self._send_sock]:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass
        self._spdp_mc_sock = None
        self._meta_uc_sock = None
        self._user_uc_sock = None
        self._user_mc_sock = None
        self._send_sock = None

    def send_multicast(self, data: bytes, port: int | None = None) -> None:
        """Send data to the SPDP multicast group."""
        if port is None:
            port = self._spdp_multicast_port
        if self._send_sock:
            self._send_sock.sendto(data, (SPDP_MULTICAST_ADDRESS, port))

    def send_unicast(self, data: bytes, addr: str, port: int) -> None:
        """Send data to a specific unicast address:port."""
        if self._send_sock:
            self._send_sock.sendto(data, (addr, port))

    def get_sockets(self) -> dict[str, socket.socket]:
        """Return dict of name -> socket for select() usage."""
        result = {}
        if self._spdp_mc_sock:
            result["spdp_multicast"] = self._spdp_mc_sock
        if self._meta_uc_sock:
            result["metatraffic_unicast"] = self._meta_uc_sock
        if self._user_uc_sock:
            result["user_unicast"] = self._user_uc_sock
        if self._user_mc_sock:
            result["user_multicast"] = self._user_mc_sock
        return result

    def recv_from(self, sock_name: str, bufsize: int = 65536) -> ReceivedPacket | None:
        """Try to receive a packet from the named socket. Non-blocking."""
        sockets = self.get_sockets()
        sock = sockets.get(sock_name)
        if not sock:
            return None
        try:
            data, (addr, port) = sock.recvfrom(bufsize)
            return ReceivedPacket(data=data, source_addr=addr,
                                 source_port=port, dest_socket=sock_name)
        except BlockingIOError:
            return None
