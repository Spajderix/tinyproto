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
from threading import Thread, RLock
import socket
import selectors
import typing
import logging

from .errors import TinyProtoError
from .plugins import TinyProtoPlugin
from .connection_details import TinyProtoConnectionDetails

log = logging.getLogger(__name__)

SC_OK=0xff
SC_GENERIC_ERROR=0x00
SC_CONLIMIT=0xfe
SC_CONFLICT=0xfd

MSG_MAX_SIZE=0xf0ffffff # 4 byte size, never change this value!!!
# Above limit will make sure, that size is not mixed up with
# SC_OK signal, which is 0xff, or any other current or future
# signal
# It also sets a reasonably high one time transfer limit of
# a little over 3854 MB, which no sane person would ever reach


class TinyProtoConnection:
    __slots__ = (
        'shutdown',
        'socket_o',
        'is_socket_up',
        'remote_details',
        'plugin_list',
        'connection_lock',
        'peername_details',
        '_selector',
        '_connection_loop_thread'
    )

    def __init__(
        self,
        socket_object: socket.socket,
        socket_already_up: bool = True,
        remote_details: typing.Optional[TinyProtoConnectionDetails] = None,
        connection_plugin_list: typing.List[TinyProtoPlugin] = []
    ):
        self.shutdown: bool = False
        self.connection_lock = RLock()
        self.peername_details = None
        self._selector = selectors.DefaultSelector()

        self.socket_o: socket.socket = socket_object
        self.is_socket_up = socket_already_up

        self.remote_details: typing.Optional[TinyProtoConnectionDetails] = remote_details

        self.plugin_list = []
        for connection_plugin in connection_plugin_list:
            self.register_plugin(connection_plugin)

        self._connection_loop_thread: Thread = Thread(target=self._connection_thread_runner, daemon=True)

    def __del__(self):
        self.shutdown = True

    def _ba_to_s(self, size_ba):
        'Always 4 byte size!!!'
        if type(size_ba) is not bytearray:
            raise ValueError('Must be a byte array')
        s = 0
        s += (size_ba[0] << 24 )
        s += (size_ba[1] << 16 )
        s += (size_ba[2] << 8 )
        s += size_ba[3]
        return s

    def _s_to_ba(self, s):
        'Always 4 byte size!!!'
        if type(s) is not int:
            raise ValueError('Must be an integer')
        ba = bytearray()
        ba.append(   ( (s >> 24 ) & 0xff )   )
        ba.append(   ( (s >> 16 ) & 0xff )   )
        ba.append(   ( (s >> 8 ) & 0xff )   )
        ba.append(   ( s & 0xff )   )
        return ba

    def _prep_for_transmit(self, msg):
        if type(msg) is int:
            ba = bytearray()
            ba.append(msg)
        else:
            ba = bytearray(msg)
        return ba

    def _process_plugins_transmit(self, msg):
        for p in self.plugin_list:
            msg = p.msg_transmit(msg)
        return msg

    def _process_plugins_receive(self, msg):
        for x in range(len(self.plugin_list)-1, -1, -1):
            msg =  self.plugin_list[x].msg_receive(msg)
        return msg

    def _raw_transmit(self, msg):
        msg_a = self._prep_for_transmit(msg)
        transmit_count = len(msg_a)
        while transmit_count > 0:
            res = self.socket_o.send(msg_a[(transmit_count * -1):])
            transmit_count -= res

    def _raw_receive(self, size):
        msg_a = bytearray()
        recv_count = size
        while recv_count > 0:
            tmp = self.socket_o.recv(recv_count)

            # if the connection dies for some reason
            # then socket will return 0 byte string
            # this is the moment to close the connection
            if len(tmp) == 0:
                self.shutdown = True
                msg_a.append(0)
                msg_a.append(0)
                msg_a.append(0)
                msg_a.append(0)
                return msg_a

            msg_a.extend(tmp)
            recv_count -= len(tmp)
        return msg_a

    def _receive(self):
        with self.connection_lock:
            # first get a 4 byte size of a transmission
            size_ba = self._raw_receive(4)
            recv_count = self._ba_to_s(size_ba)
            if recv_count > MSG_MAX_SIZE:
                self._raw_transmit(SC_GENERIC_ERROR)
                raise TinyProtoError(f'Remote end trying to send message of size {recv_count} which is bigger then supported max size of {MSG_MAX_SIZE}')
            elif recv_count == 0 and self.shutdown:
                # this will happen if the connection is dropped on the other side
                raise TinyProtoError(f'Received zero bytes from remote end. Most probably remote end dropped connection.')
            self._raw_transmit(SC_OK)
            msg_a = self._raw_receive(recv_count)
            # as the last step, push message through all plugins
            msg_a = self._process_plugins_receive(msg_a)
            return msg_a

    def _transmit(self, msg):
        with self.connection_lock:
            # before we can even begin calculating anything, we have to process all plugins
            # because the size might change in the process
            msg = self._process_plugins_transmit(msg)
            # first prepare and send 4 byte size of a transmission
            size_ba = self._s_to_ba(len(msg))
            self._raw_transmit(size_ba)
            # check if return code is OK
            tx_status = self._raw_receive(1)
            if tx_status[0] != SC_OK:
                raise TinyProtoError('Transmission rejected: {0}'.format(tx_status))
            self._raw_transmit(msg)

    def receive(self):
        try:
            return self._receive()
        except OSError as e:
            self.shutdown = True
            log.error('Shutting down connection on receive due to error {}'.format(e))
            return bytearray()

    def transmit(self, msg):
        try:
            self._transmit(msg)
        except OSError as e:
            log.error('Shutting down connection on transmit due to error {}'.format(e))
            self.shutdown = True

    def _initialise_connection(self):
        if not self.is_socket_up and self.remote_details is not None:
            self.socket_o.connect( self.remote_details.socket_connect_details )
            self.is_socket_up = True
        self._raw_transmit(SC_OK)
        res = self._raw_receive(1)
        if res[0] != SC_OK:
            raise TinyProtoError('Initialisation error: {0}'.format(res))
        self.peername_details = self.socket_o.getpeername()
        self._selector.register(self.socket_o, selectors.EVENT_READ)

    def _connection_loop(self):
        while not self.shutdown:
            with self.connection_lock:
                selected_keys = self._selector.select(0.03)
                if len(selected_keys) > 0 and selected_keys[0][0].fileobj == self.socket_o:
                    msg_a = self.receive()
                    if msg_a is not False:
                        self.transmission_received(msg_a)
                self.loop_pass()

    def _cleanup_connection(self):
        self.socket_o.close()
        self._selector.close()

    def register_plugin(self, plugin):
        try:
            if issubclass(plugin, TinyProtoPlugin):
                self.plugin_list.append(plugin())
            else:
                raise ValueError('Not a subclass of TinyProtoPlugin')
        except TypeError as e:
            if isinstance(plugin, TinyProtoPlugin):
                self.plugin_list.append(plugin)
            else:
                raise ValueError('Not a subclass of TinyProtoPlugin')

    def _connection_thread_runner(self):
        self._initialise_connection()
        self.pre_loop()
        self._connection_loop()
        self.post_loop()
        self._cleanup_connection()

    def is_alive(self) -> bool:
        return self._connection_loop_thread.is_alive()

    def start(self):
        self._connection_loop_thread.start()

    def pre_loop(self):
        pass
    def post_loop(self):
        pass
    def loop_pass(self):
        pass
    def transmission_received(self, msg):
        pass
