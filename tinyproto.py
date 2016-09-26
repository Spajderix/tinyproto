# -*- coding: utf-8 -*-
from threading import Thread
import socket
from select import select
import Queue

SC_OK=0x00
SC_GENERIC_ERROR=0xff
SC_CONLIMIT=0x01

MSG_MAX_SIZE=0xffffffff # 4 byte size, never change this value!!!

class TinyProtoError(Exception):
    pass

class TinyProtoConnection(Thread, object):
    __slots__ = ('shutdown', 'socket_o', 'q_to_parent', 'q_to_child')

    def __init__(self, *args, **kwargs):
        super(TinyProtoConnection, self).__init__(*args, **kwargs)
        self.shutdown = False
        self.socket_o = None

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

    def _raw_transmit(self, msg):
        msg_a = self._prep_for_transmit(msg)
        transmit_count = len(msg_a)
        while transmit_count > 0:
            res = self.socket_o.send(msg_a)
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
        self._raw_transmit(SC_OK)
        res = self._raw_receive(1)
        if res[0] != SC_OK:
            raise TinyProtoError('Initialisation error: {0}'.format(res))

    def receive(self):
        # first get a 4 byte size of a transmission
        size_ba = self._raw_receive(4)
        recv_count = self._ba_to_s(size_ba)
        if recv_count > MSG_MAX_SIZE:
            self._raw_transmit(SC_GENERIC_ERROR)
            return False
        self._raw_transmit(SC_OK)
        msg_a = self._raw_receive(recv_count)
        return msg_a

    def transmit(self, msg):
        # first prepare and send 4 byte size of a transmission
        size_ba = self._s_to_ba(len(msg))
        self._raw_transmit(size_ba)
        # check if return code is OK
        tx_status = self._raw_receive(1)
        if tx_status[0] != SC_OK:
            raise TinyProtoError('Transmission rejected: {0}'.format(tx_status))
        self._raw_transmit(msg)

    def _connection_loop(self):
        while not self.shutdown:
            rs,ws,es = select([self.socket_o], [], [], 0.1)
            if len(rs) > 0 and rs[0] is self.socket_o:
                msg_a = self.receive()
                self.transmission_received(msg_a)
            self.loop_pass()

    def _cleanup_connection(self):
        self.socket_o.close()

    def _set_queues(self, qtp, qtc):
        self.q_to_parent = qtp
        self.q_to_child = qtc

    def msg_to_parent(self, msg):
        self.q_to_parent.put(msg)

    def msg_from_parent(self):
        msgs=[]
        empty=False
        while not empty:
            try:
                tmp = self.q_to_child.get(False)
            except Queue.Empty as e:
                empty = True
            else:
                msgs.append(tmp)
        return msgs

    def set_socket(self, so):
        self.socket_o = so

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


class TinyProtoConnectionHelper(object):
    __slots__ = ('conn_o', 'socket_o', 'q_to_parent', 'q_to_child')

    def __init__(self,co,so):
        self.conn_o = co
        self.socket_o = so
        self.q_to_parent = Queue.Queue()
        self.q_to_child = Queue.Queue()

        self.conn_o._set_queues(self.q_to_parent, self.q_to_child)
        self.conn_o.start()

    def is_alive(self):
        return self.conn_o.is_alive()

    def cleanup(self):
        self.socket_o.close()

    def msg_to_child(self, m):
        self.q_to_child.put(m)

    def msg_from_child(self):
        msgs = []
        empty = False
        while not empty:
            try:
                tmp = self.q_to_parent.get(False)
            except Queue.Empty as e:
                empty = True
            else:
                msgs.append(tmp)
        return msgs


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
            conn_h = TinyProtoConnectionHelper(conn_o, con)
            self.active_connections.append(conn_h)

    def _server_loop(self):
        while not self.shutdown:
            rs,ws,es = select(self.listen_socks, [], [], 0.1)
            if len(rs) > 0:
                for active_s in rs:
                    new_sock, new_addr = active_s.accept()
                    self._initialise_connection(new_sock, new_addr)
            # cleanup closed connections
            for x in xrange(len(self.active_connections)):
                conn_h = self.active_connections.pop(0)
                if conn_h.is_alive():
                    self.active_connections.append(conn_h)
                else:
                    conn_h.cleanup()
            self.loop_pass()

    def _shutdown_active_cons(self):
        for x in xrange(len(self.active_connections)):
            conn_h = self.active_connections.pop(0)
            # !!!!this part needs to be rewritten as soon as connection class is completed!!!!!!!
            conn_h.cleanup()
            del(conn_h)

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


    def pre_loop(self):
        pass
    def post_loop(self):
        pass
    def loop_pass(self):
        pass
