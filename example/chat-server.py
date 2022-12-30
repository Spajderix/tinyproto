import tinyproto as tp
from threading import Lock


class ChatSrvConnection(tp.TinyProtoConnection):
    __slots__ = (
        '__msg_inbox', '__msg_inbox_lock',
        '__msg_outbox', '__msg_outbox_lock',
        '__transaction_lock',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.__msg_inbox = []
        self.__msg_outbox = []
        self.__msg_inbox_lock = Lock()
        self.__msg_outbox_lock = Lock()
        self.__transaction_lock = Lock()

    @property
    def Inbox(self):
        with self.__msg_inbox_lock:
            res = self.__msg_inbox
            self.__msg_inbox = []
            return res
    @Inbox.setter
    def Inbox(self, newval):
        with self.__msg_inbox_lock:
            self.__msg_inbox.append(newval)

    @property
    def Outbox(self):
        with self.__msg_outbox_lock:
            res = self.__msg_outbox
            self.__msg_outbox = []
            return res
    @Outbox.setter
    def Outbox(self, newval):
        with self.__msg_outbox_lock:
            self.__msg_outbox.append(newval)

    def transmission_received(self, msg):
        self.Inbox = msg.decode()

    def loop_pass(self):
        with self.__transaction_lock:
            pending_msgs = self.Outbox
            for msg in pending_msgs:
                self.transmit(msg.encode())



class ChatSrv(tp.TinyProtoServer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def conn_init(self, conn_id, conn_o):
        print('[INFO] New connection opened from {}'.format(conn_o.socket_o.getpeername()))
        self.broadcast_msgs(conn_id, ('**joined the chat', ))
    def conn_shutdown(self, conn_id, conn_o):
        print('[INFO] Connection closed from {}'.format(conn_o.peername_details))
        self.broadcast_msgs(conn_id, ('**left the chat', ))

    def loop_pass(self):
        for conn_id, conn_o in self.active_connections.items():
            pending_msgs = conn_o.Inbox
            self.broadcast_msgs(conn_id, pending_msgs)

    def broadcast_msgs(self, originating_conn_id, msgs):
        for conn_id, conn_o in self.active_connections.items():
            if conn_id == originating_conn_id:
                continue

            for m in msgs:
                formatted_m = '[{}] {}'.format(originating_conn_id, m)
                conn_o.Outbox = formatted_m



if __name__ == '__main__':
    print('Loading server ... ')
    srv = ChatSrv(
        connection_handler = ChatSrvConnection,
        listen_addressess = [('0.0.0.0', 8088)]
    )
    srv.start()
