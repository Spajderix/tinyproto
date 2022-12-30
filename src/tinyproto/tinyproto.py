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
import queue
import typing
from uuid import uuid4 as uuid
from uuid import UUID
from time import sleep
import logging

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

class TinyProtoError(Exception):
    pass

class TinyProtoPlugin(object):
    def msg_transmit(self, msg):
        return msg
    def msg_receive(self, msg):
        return msg

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
        remote_host: typing.Optional[str] = None,
        remote_port: typing.Optional[int] = None,
        connection_plugin_list: typing.List[TinyProtoPlugin] = []
    ):
        self.shutdown: bool = False
        self.connection_lock = RLock()
        self.peername_details = None
        self._selector = selectors.DefaultSelector()

        self.socket_o: socket.socket = socket_object
        self.is_socket_up = socket_already_up

        if remote_host is not None and remote_port is not None:
            self.remote_details = (remote_host, remote_port)
        else:
            self.remote_details = None

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
                return False
            elif recv_count == 0 and self.shutdown:
                # this will happen if the connection is dropped on the other side
                return False
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
            self.socket_o.connect( self.remote_details)
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


class TinyProtoServer:
    __slots__ = ('shutdown', 'listen_addrs', 'listen_socks', 'active_connections', 'connection_handler', 'connection_limit', 'connection_plugin_list', '_selector')

    def __init__(
        self,
        connection_handler: TinyProtoConnection = TinyProtoConnection,
        connection_limit: typing.Optional[int] = None,
        connection_plugin_list: typing.List[TinyProtoPlugin] = [],
        listen_addressess: typing.List[typing.Tuple] = [("0.0.0.0", 8899)]
    ):


        'Whenever this flag is raised to true, server loop will terminate, and shutdown will be initiated'
        self.shutdown=False
        'The list used to hold 2-element-tuples containing ip addr and port on which to listen to for connections'
        self.listen_addrs: typing.List[typing.Tuple]=[]
        for l_host, l_port in listen_addressess:
            self.add_addr(l_host, l_port)
        'The list used to store listening sockets currently in use'
        self.listen_socks: typing.List[socket.socket]=[]
        'The dictionary used to store connection objects based on TinyProtoConnection class by their UUID'
        self.active_connections: typing.Dict[UUID, TinyProtoConnection] = {}

        self.set_conn_handler(connection_handler)

        self.connection_limit: typing.Optional[int]=connection_limit

        self.connection_plugin_list: typing.List[TinyProtoPlugin]=[]
        for connection_plugin in connection_plugin_list:
            self.register_connection_plugin(connection_plugin)

        self._selector = selectors.DefaultSelector()

    def _activate_l(self, addr, port):
        listen_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listen_socket.bind( (addr, port) )
        listen_socket.listen(5) # not sure if this value needs to be configurable, so it stays hardcoded for now

        self._selector.register(listen_socket, selectors.EVENT_READ)

        self.listen_socks.append(listen_socket)

    def _activate_listeners(self):
        if len(self.listen_socks) != 0:
            raise TinyProtoError('There are already active listeners')
        if len(self.listen_addrs) <= 0:
            raise TinyProtoError('No addresses defined for listening')
        for addr, port in self.listen_addrs:
            self._activate_l(addr,port)

    def _is_limit_exceeded(self):
        if self.connection_limit == None:
            return False
        if len(self.active_connections) >= self.connection_limit:
            return True
        return False

    def _respond_with_limit_exceeded_code(self, socket_object: socket.socket):
        socket_object.send(bytearray(SC_CONLIMIT))
        socket_object.close()

    def _initialise_connection(self, con, addr):
        if self._is_limit_exceeded():
            self._respond_with_limit_exceeded_code(con)
        else:
            connection_id = uuid()
            connection_object = self.connection_handler(
                socket_object=con,
                socket_already_up=True,
                connection_plugin_list=self.connection_plugin_list,
            )

            self.conn_init(connection_id, connection_object)

            connection_object.start()

            self.active_connections[connection_id] = connection_object

    def _server_loop(self):
        while not self.shutdown:
            selected_keys = self._selector.select(0.03)
            if len(selected_keys) > 0:
                for active_socket_key, key_mask in selected_keys:
                    new_socket, new_addr = active_socket_key.fileobj.accept()
                    self._initialise_connection(new_socket, new_addr)
            # cleanup closed connections
            conn_uids = tuple(self.active_connections.keys())
            for conn_id in conn_uids:
                conn_o = self.active_connections.pop(conn_id)
                if conn_o.is_alive():
                    self.active_connections[conn_id] = conn_o
                else:
                    self.conn_shutdown(conn_id, conn_o)
            self.loop_pass()

    def _shutdown_active_cons(self):
        conn_uids = tuple(self.active_connections.keys())
        for cuid in conn_uids:
            conn_o = self.active_connections.pop(cuid)
            # !!!!this part needs to be rewritten as soon as connection class is completed!!!!!!!
            conn_o.shutdown = True
            del(conn_o)

    def _close_listeners(self):
        for x in range(len(self.listen_socks)):
            ls = self.listen_socks.pop(0)
            ls.close()
            del(ls)

    def set_conn_handler(self, handler: TinyProtoConnection):
        if not issubclass(handler, TinyProtoConnection):
            raise ValueError('Connection handler must be a subclass of TinyProtoConnection')
        self.connection_handler = handler

    def add_addr(self, ipaddr: str, port: int):
        port=int(port)
        if port < 1 or port > 65535:
            raise ValueError('Incorrect port number: {}. Port number should be between 1 and 65535'.format(port))
        try:
            socket.inet_aton(ipaddr)
        except socket.error as e:
            raise ValueError('Incorrect ip address {}'.format(ipaddr))
        self.listen_addrs.append((ipaddr, port))

    def register_connection_plugin(self, plugin: TinyProtoPlugin):
        try:
            if issubclass(plugin, TinyProtoPlugin):
                self.connection_plugin_list.append(plugin())
            else:
                raise ValueError('Not a subclass of TinyProtoPlugin')
        except TypeError as e:
            if isinstance(plugin, TinyProtoPlugin):
                self.connection_plugin_list.append(plugin)
            else:
                raise ValueError('Not a subclass of TinyProtoPlugin')

    def start(self):
        self._activate_listeners()
        self.pre_loop()
        self._server_loop()
        self.post_loop()
        self._shutdown_active_cons()
        self._close_listeners()
        self._selector.close()


    def pre_loop(self):
        pass
    def post_loop(self):
        pass
    def loop_pass(self):
        pass
    def conn_init(self, conn_id: UUID, conn_o: TinyProtoConnection):
        pass
    def conn_shutdown(self, conn_id: UUID, conn_o: TinyProtoConnection):
        pass



class TinyProtoClient:
    __slots__ = ('shutdown', 'active_connections', 'connection_handler', 'connection_plugin_list', 'socket_timeout')

    def __init__(
        self,
        connection_handler: TinyProtoConnection = TinyProtoConnection,
        connection_plugin_list: typing.List[TinyProtoPlugin] = [],
        timeout: int = 5
    ):
        self.shutdown = False
        self.active_connections: typing.Dict[UUID, TinyProtoConnection] = {}

        self.set_conn_handler(connection_handler)

        self.connection_plugin_list: typing.List[TinyProtoPlugin] = []
        for connection_plugin in connection_plugin_list:
            self.register_connection_plugin(connection_plugin)
        self.socket_timeout: int = timeout

    def set_conn_handler(self, handler: TinyProtoConnection):
        if not issubclass(handler, TinyProtoConnection):
            raise ValueError('Connection handler must be a subclass of TinyProtoConnection')
        self.connection_handler: TinyProtoConnection = handler

    def _shutdown_active_cons(self):
        conn_uids = tuple(self.active_connections.keys())
        for cuid in conn_uids:
            conn_o = self.active_connections.pop(cuid)
            # !!!!this part needs to be rewritten as soon as connection class is completed!!!!!!!
            conn_o.shutdown = True

    def _client_loop(self):
        while not self.shutdown:
            self.loop_pass()
            sleep(0.03)

    def register_connection_plugin(self, plugin):
        try:
            if issubclass(plugin, TinyProtoPlugin):
                self.connection_plugin_list.append(plugin())
            else:
                raise ValueError('Not a subclass of TinyProtoPlugin')
        except TypeError as e:
            if isinstance(plugin, TinyProtoPlugin):
                self.connection_plugin_list.append(plugin)
            else:
                raise ValueError('Not a subclass of TinyProtoPlugin')

    def connect_to(self, host: str, port: int) -> UUID:
        socket_object = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        socket_object.settimeout(self.socket_timeout)

        connection_id = uuid()
        connection_object = self.connection_handler(
            socket_object = socket_object,
            socket_already_up = False,
            remote_host = host,
            remote_port = port,
            connection_plugin_list = self.connection_plugin_list
        )

        connection_object.start()
        self.active_connections[connection_id] = connection_object
        return connection_id


    def start(self):
        self.pre_loop()
        self._client_loop()
        self.post_loop()
        self._shutdown_active_cons()


    def pre_loop(self):
        pass
    def post_loop(self):
        pass
    def loop_pass(self):
        pass
