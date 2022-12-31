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

class TinyProtoConnectionDetails:
    __slots__ = ('host', 'ipaddr', 'port')

    def __init__(self, host: str, port: int):
        if port < 1 or port > 65535:
            raise TinyProtoError(f'Incorrect port number: {port}. Port number should be between 1 and 65535')
        self.port: int = port

        self.host: str = host

        try:
            self.ipaddr: str = socket.gethostbyname(host)
        except socket.gaierror:
            raise TinyProtoError(f'Incorrect host: {host}')
