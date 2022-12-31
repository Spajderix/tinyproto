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
import typing
from uuid import uuid4 as uuid
from uuid import UUID
from time import sleep

from .plugins import TinyProtoPlugin
from .connection_details import TinyProtoConnectionDetails
from .connection import TinyProtoConnection


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

    def connect_to(self, connection_details: TinyProtoConnectionDetails) -> UUID:
        socket_object = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        socket_object.settimeout(self.socket_timeout)

        connection_id = uuid()
        connection_object = self.connection_handler(
            socket_object = socket_object,
            socket_already_up = False,
            remote_details = connection_details,
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
