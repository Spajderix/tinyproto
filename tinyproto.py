# -*- coding: utf-8 -*-
from threading import Thread
import socket
from select import select

SC_OK=0x00
SC_GENERIC_ERROR=0xff
SC_CONLIMIT=0x01

class TinyProtoError(Exception):
    pass

class TinyProtoConnection(Thread, object):
    __slots__ = ('socket_o')

    def set_socket(self, so):
        self.socket_o = so

    def on_receive(self):
        pass #??????



class TinyProtoServer(object):
    __slots__ = ('shutdown', 'listen_addrs', 'listen_socks', 'active_connections', 'connection_handler', 'connection_limit')

    def __init__(self):
        self.shutdown=False
        'Whenever this flag is raised to true, server loop will terminate, and shutdown will be initiated'
        self.listen_addrs=[]
        'Above list will be used to hold 2-element-tuples containing ip addr and port on which to listen to for connections'
        self.listen_socks=[]
        'Above list used to store listening sockets currently in use'
        self.active_connections = []
        'Above list wil be used to store connection objects based on TinyProtoConnection class, as well as socket objects - 2 element tuples'
        self.connection_handler=TinyProtoConnection
        'connection_handler will hold a base class, which will be used to handle incoming connections'
        self.connection_limit=None # can be either None or int

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
            conn_o.set_socket(con)
            conn_o.start()
            self.active_connections.append( (conn_o, con) )

    def _server_loop(self):
        while not self.shutdown:
            rs,ws,es = select(self.listen_socks, [], [], 0.1)
            if len(rs) > 0:
                for active_s in rs:
                    new_sock, new_addr = active_s.accept()
                    self._initialise_connection(new_sock, new_addr)
            # cleanup closed connections
            for x in xrange(len(self.active_connections)):
                conn_o, sock_o = self.active_connections.pop(0)
                if conn_o.is_alive():
                    self.active_connections.append( (conn_o, sock_o) )
                else:
                    # if it is not alive, then let's clean up the socket
                    sock_o.close()
            self.loop_pass()

    def _shutdown_active_cons(self):
        for x in xrange(len(self.active_connections)):
            conn_o, sock_o self.active_connections.pop(0)
            # !!!!this part needs to be rewritten as soon as connection class is completed!!!!!!!
            del(conn_o)
            sock_o.close()
            del(sock_o)

    def _close_listeners(self):
        for x in xrange(len(self.listen_socks)):
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

    def start(self):
        self._activate_listeners()
        self.pre_loop()
        self._server_loop()
        self._post_loop()
        self._shutdown_active_cons()
        self._close_listeners()


    def pre_loop(self):
        pass
    def post_loop(self):
        pass
    def loop_pass(self):
        pass



class TinyProtoClient(object):
    pass
