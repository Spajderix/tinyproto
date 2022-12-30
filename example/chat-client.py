import tinyproto as tp
from threading import Lock, Thread

class ChatClientConnection(tp.TinyProtoConnection):
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



class ChatClient(tp.TinyProtoClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        t = Thread(target = self.start)
        t.start()

    def loop_pass(self):
        for conn_id, conn_o in self.active_connections.items():
            pending_msgs = conn_o.Inbox
            for m in pending_msgs:
                print(m)




if __name__ == '__main__':
    c = ChatClient(
        connection_handler = ChatClientConnection,
        timeout = 3,
    )

    print('Connecting ... ')
    cuid = c.connect_to('127.0.0.1', 8088)
    conn = c.active_connections[cuid]
    print('Connection established!')

    buff = "abc"
    while buff != 'quit' and conn.is_alive():
        buff = input('')
        conn.Outbox = buff
    conn.shutdown = True
    c.shutdown = True
