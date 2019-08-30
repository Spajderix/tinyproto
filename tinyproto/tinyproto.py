# -*- coding: utf-8 -*-
# Copyright 2016 - 2019 Spajderix <spajderix@gmail.com>
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
from threading import Thread, Lock
import socket
from select import select
import queue
from uuid import uuid4 as uuid
from time import sleep

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

class TinyProtoConnection(Thread, object):
    __slots__ = ('shutdown', 'socket_o', 'is_socket_up', 'remote_details', 'plugin_list', 'connection_lock', 'peername_details')

    def __init__(self, *args, **kwargs):
        super(TinyProtoConnection, self).__init__(*args, **kwargs)
        self.shutdown = False
        self.socket_o = None
        self.is_socket_up = False
        self.remote_details = None # address and port in case connection needs to be initialised inside thread
        self.plugin_list = []
        self.connection_lock = Lock()
        self.peername_details = None

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

    def _initialise_connection(self):
        if not self.is_socket_up and self.remote_details is not None:
            self.socket_o.connect( self.remote_details)
            self.is_socket_up = True
        self._raw_transmit(SC_OK)
        res = self._raw_receive(1)
        if res[0] != SC_OK:
            raise TinyProtoError('Initialisation error: {0}'.format(res))
        self.peername_details = self.socket_o.getpeername()

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
            return bytearray()

    def transmit(self, msg):
        try:
            self._transmit(msg)
        except OSError as e:
            self.shutdown = True

    def _connection_loop(self):
        while not self.shutdown:
            rs,ws,es = select([self.socket_o], [], [], 0.1)
            if len(rs) > 0 and rs[0] is self.socket_o:
                msg_a = self.receive()
                if msg_a is not False:
                    self.transmission_received(msg_a)
            self.loop_pass()
            sleep(0.01)

    def _cleanup_connection(self):
        self.socket_o.close()

    def set_socket(self, so, is_up=True, conn_details=None):
        self.socket_o = so
        self.is_socket_up = is_up
        self.remote_details = conn_details

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

    def run(self):
        self._initialise_connection()
        self.pre_loop()
        self._connection_loop()
        self.post_loop()
        self._cleanup_connection()

    def pre_loop(self):
        pass
    def post_loop(self):
        pass
    def loop_pass(self):
        pass
    def transmission_received(self, msg):
        pass


class TinyProtoServer(object):
    __slots__ = ('shutdown', 'listen_addrs', 'listen_socks', 'active_connections', 'connection_handler', 'connection_limit', 'connection_plugin_list')

    def __init__(self):
        self.shutdown=False
        'Whenever this flag is raised to true, server loop will terminate, and shutdown will be initiated'
        self.listen_addrs=[]
        'Above list will be used to hold 2-element-tuples containing ip addr and port on which to listen to for connections'
        self.listen_socks=[]
        'Above list used to store listening sockets currently in use'
        self.active_connections = {}
        'Above list wil be used to store connection objects based on TinyProtoConnection class'
        self.connection_handler=TinyProtoConnection
        'connection_handler will hold a base class, which will be used to handle incoming connections'
        self.connection_limit=None # can be either None or int
        self.connection_plugin_list=[]

    def _activate_l(self, addr, port):
        listen_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listen_socket.bind( (addr, port) )
        listen_socket.listen(5) # not sure if this value needs to be configurable, so it stays hardcoded for now

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

    def _limit_exceeded(self, con):
        con.send(bytearray(SC_CONLIMIT))
        con.close()

    def _initialise_connection(self, con, addr):
        if self._is_limit_exceeded():
            self._limit_exceeded(con)
        else:
            conn_o = self.connection_handler()
            conn_id = uuid()
            conn_o.set_socket(con)
            for p in self.connection_plugin_list:
                conn_o.register_plugin(p)
            self.conn_init(conn_id, conn_o)
            conn_o.start()
            self.active_connections[conn_id] = conn_o

    def _server_loop(self):
        while not self.shutdown:
            rs,ws,es = select(self.listen_socks, [], [], 0.1)
            if len(rs) > 0:
                for active_s in rs:
                    new_sock, new_addr = active_s.accept()
                    self._initialise_connection(new_sock, new_addr)
            # cleanup closed connections
            conn_uids = tuple(self.active_connections.keys())
            for conn_id in conn_uids:
                conn_o = self.active_connections.pop(conn_id)
                if conn_o.is_alive():
                    self.active_connections[conn_id] = conn_o
                else:
                    self.conn_shutdown(conn_id, conn_o)
            self.loop_pass()
            sleep(0.01)

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

    def set_conn_handler(self, handler):
        if not issubclass(handler, TinyProtoConnection):
            raise ValueError('Connection handler must be a subclass of TinyProtoConnection')
        self.connection_handler = handler

    def add_addr(self, ipaddr, port):
        port=int(port)
        if port < 1 or port > 65535:
            raise ValueError('Port number should be between 1 and 65535')
        try:
            socket.inet_aton(ipaddr)
        except socket.error as e:
            raise ValueError('Incorrect ip address')
        self.listen_addrs.append((ipaddr, port))

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

    def start(self):
        self._activate_listeners()
        self.pre_loop()
        self._server_loop()
        self.post_loop()
        self._shutdown_active_cons()
        self._close_listeners()


    def pre_loop(self):
        pass
    def post_loop(self):
        pass
    def loop_pass(self):
        pass
    def conn_init(self, conn_id, conn_o):
        pass
    def conn_shutdown(self, conn_id, conn_o):
        pass



class TinyProtoClient(object):
    __slots__ = ('shutdown', 'active_connections', 'connection_handler', 'connection_plugin_list', 'socket_timeout')

    def __init__(self):
        self.shutdown = False
        self.active_connections = {}
        self.connection_handler = TinyProtoConnection
        self.connection_plugin_list = []
        self.socket_timeout = 5

    def set_conn_handler(self, handler):
        if not issubclass(handler, TinyProtoConnection):
            raise ValueError('Connection handler must be a subclass of TinyProtoConnection')
        self.connection_handler = handler

    def set_timeout(self, t):
        if type(t) is not int:
            raise ValueError('Timeout value is not integer')
        self.socket_timeout = t

    def _shutdown_active_cons(self):
        conn_uids = tuple(self.active_connections.keys())
        for cuid in conn_uids:
            conn_o = self.active_connections.pop(cuid)
            # !!!!this part needs to be rewritten as soon as connection class is completed!!!!!!!
            conn_o.shutdown = True

    def _client_loop(self):
        while not self.shutdown:
            self.loop_pass()
            sleep(0.01)

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

    def connect_to(self, host, port):
        conn_o = self.connection_handler()
        socket_o = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        socket_o.settimeout(self.socket_timeout)
        conn_o.set_socket(socket_o, False, (host, port))
        for p in self.connection_plugin_list:
            conn_o.register_plugin(p)
        conn_o.start()
        cuid = uuid()
        self.active_connections[cuid] = conn_o
        return cuid


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
