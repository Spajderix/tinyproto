# DISCLAIMER
This library is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Lesser General Public License for more details.

# Purpose
This library was built as a learning experience to understand how sockets work on the low level. Main purpose is to serve as a framework to build small client/server TCP/IP applications. It handles sending and receiving transmission, makes sure everything that goes in on one end will get received on the other.

# Components
There are a few components to this library. Basic operation with this library is to import those components and create subclasses which will inherit from the library classes, overwriting a few of methods.

There is a simple example inside `example` directory, for the more advanced example please look into [tpft](https://github.com/Spajderix/tpft)

## TinyProtoConnection
This class handles everything that happens within a connection. It's designed to become a separate thread upon established connection. Once the connection is created and an instance of this class starts a thread, the main function of this thread will initiate a sequence of methods. First of them is `pre_loop`, which will get executed only once, right after connection is established, but before the main connection loop. After that a connection loop will start which will check for any message that can be received, and will execute `loop_pass` on every loop pass. After the loop ends ( when the connection is being closed ), `post_loop` will be executed, which is also executed only once. Whenever any transmission is sent to a connection, and the transmission is detected within a loop, method `transmission_received` will be called, with the transmitted message as it's first parameter.

`pre_loop`, `post_loop`, `loop_pass` and `transmission_received` can be overridden with a connection subclass to define the behavior of the connection within certain actions. In addition, 2 methods of this class can be used to either transmit message or directly receive message without waiting for connection loop to catch it.

`transmit` will take any message of size up to almost 4GB and send it to the other end of the connection. In a same way `receive` will wait for a transmission from the other end, of any size of up to almost 4GB, and return it as soon as entire message is received.

What happens within the connection ( upon running transmit, or receive ) is first the overall size of the message is calculated. After the size is known, the sending end of the connection will send 4 byte size message, informing receiving end of how much data will be coming down the socket. Once the receiving end is ok with the size of the message, it will send one byte OK message. After the sending end received the OK message, it will start transmitting the message, and the receiving end will try to receive. If the socket won't send the message in full ( for any reason, turns out sockets are weirdos ), the sending end will retry sending the missing part, and receiving end will try to get data from a socket in a loop until entire message is received.

## TinyProtoServer
This class is used as a main server process. It's main task is to listen for connection, initialize new connection sockets and new threads, and possibly communicate between connection threads, if needed. It works based on entering main execution loop, which will handle listening and creating new connections.

As it was with previous class, there are a few methods which can be overridden within a server subclass. `pre_loop` will be executed only once, before entering main loop. `post_loop` will be executed only once right after main loop ends. `loop_pass` will be executed every time main loop passes. `conn_init` will be executed every time a connection is established, before a new thread is created. `conn_shutdown` will be executed every time a connection is closed.

In addition, `add_addr` method can be used to add another ipaddress/port combination to listen on. `set_conn_handler` sets the subclass of TinyProtoConnection class, which will be used to handle each new connection opened. In order to start a server `start` method is used, but connection handler and at least one listening address needs to be set before.

All of new connections are added to `active_connections` property.

## TinyProtoClient
This class is used to handle client applications. Just like the server, this class operates based on main loop, but with client applications, starting main loop is not necessary.

If main loop is used, a few methods can be overridden. `pre_loop` will be executed once, before main loop starts, `post_loop` will be executed once, right after main loop stops and `loop_pass` will be executed every main loop execution pass.

In order to connect to a server, `connect_to` method can be used. It accepts ip address and port as it's parameters. Upon establishing connection, it will return an index to an active connection list, on which the connection is placed. `set_timeout` method will set default timeout on each created connection. `set_conn_handler` method will set a subclass of TinyProtoConnection class, which will be a base for every new connection.
