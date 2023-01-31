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
import selectors
import socket
import typing
from uuid import uuid4 as uuid
from uuid import UUID

from .errors import TinyProtoError
from .plugins import TinyProtoPlugin
from .connection_details import TinyProtoConnectionDetails
from .connection import TinyProtoConnection


class TinyProtoServer:
    __slots__ = ('shutdown', 'listen_addrs', 'listen_socks', 'active_connections', 'connection_handler', 'connection_limit', 'connection_plugin_list', '_selector')

    def __init__(
        self,
        listen_addresses: typing.List[TinyProtoConnectionDetails],
        connection_handler: TinyProtoConnection = TinyProtoConnection,
        connection_limit: typing.Optional[int] = None,
        connection_plugin_list: typing.List[TinyProtoPlugin] = [],
    ):


        'Whenever this flag is raised to true, server loop will terminate, and shutdown will be initiated'
        self.shutdown=False
        'The list used to hold 2-element-tuples containing ip addr and port on which to listen to for connections'
        self.listen_addrs: typing.List[TinyProtoConnectionDetails]=listen_addresses
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

    def _activate_l(self, connection_details: TinyProtoConnectionDetails):
        listen_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listen_socket.bind( connection_details.socket_connect_details )
        listen_socket.listen(5) # not sure if this value needs to be configurable, so it stays hardcoded for now

        self._selector.register(listen_socket, selectors.EVENT_READ)

        self.listen_socks.append(listen_socket)

    def _activate_listeners(self):
        if len(self.listen_socks) != 0:
            raise TinyProtoError('There are already active listeners')
        if len(self.listen_addrs) == 0:
            raise TinyProtoError('No addresses defined for listening')
        for connection_details in self.listen_addrs:
            self._activate_l(connection_details)

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
