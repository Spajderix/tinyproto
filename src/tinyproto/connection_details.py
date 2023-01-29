# -*- coding: utf-8 -*-
# Copyright 2016 - 2023 Spajderix <spajderix@gmail.com>
#
# This library is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this library.  If not, see <http://www.gnu.org/licenses/>.
#
import socket
from .errors import TinyProtoError

TINY_PROTO_SUPPORTED_ADDRESS_FAMILY = (socket.AddressFamily.AF_INET, socket.AddressFamily.AF_INET6)
TINY_PROTO_SUPPORTED_SOCKET_KIND = (socket.SocketKind.SOCK_STREAM, )

class TinyProtoConnectionDetails:
    __slots__ = ('host', 'port', 'socket_connect_details', 'address_family', 'socket_kind', 'socket_proto')

    def __init__(self, host: str, port: int):
        if port < 1 or port > 65535:
            raise TinyProtoError(f'Incorrect port number: {port}. Port number should be between 1 and 65535')
        self.port: int = port

        self.host: str = host

        try:
            res = socket.getaddrinfo(host, port)
        except socket.gaierror as e:
            raise TinyProtoError(f'Could not resolv host/port combination for {host}:{port}, due to error {e}')
        
        res = [d for d in res if d[0] in TINY_PROTO_SUPPORTED_ADDRESS_FAMILY]
        res = [d for d in res if d[1] in TINY_PROTO_SUPPORTED_SOCKET_KIND]

        if len(res) == 0:
            raise TinyProtoError(f'No supported connection details available for host/port combination for {host}:{port}')

        a_family, s_type, s_proto, s_canon, conn_details = res[0]

        self.socket_connect_details = conn_details
        self.address_family: socket.AddressFamily = a_family
        self.socket_kind: socket.SocketKind = s_type
        self.socket_proto = s_proto
