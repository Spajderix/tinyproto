import unittest
import unittest.mock
import socket
from tinyproto import TinyProtoConnection, TinyProtoError
from tinyproto.connection import SC_OK, SC_GENERIC_ERROR


class TestConnection(unittest.TestCase):
    def test_s_to_ba_correctly_calculates_byte_array(self):
        "_s_to_ba should correctly split integer with size into 4 separate bytes"
        socket_mock = unittest.mock.MagicMock(spec=socket.socket)

        connection_object = TinyProtoConnection(socket_mock)
        
        test_size = 939574096
        expected_size_bytearray = bytearray([56, 0, 195, 80])
        
        size_bytearray = connection_object._s_to_ba(test_size)
        
        self.assertEqual(size_bytearray, expected_size_bytearray)
        
    def test_ba_to_s_correctly_calculates_size(self):
        "_ba_to_s should correctly compile 4 byte bytearray into int size"
        socket_mock = unittest.mock.MagicMock(spec=socket.socket)
        
        connection_object = TinyProtoConnection(socket_mock)
        
        test_size_bytearray = bytearray([185, 192, 0, 0])
        expected_size = 3116367872
        
        size = connection_object._ba_to_s(test_size_bytearray)
        
        self.assertEqual(size, expected_size)

    def test_raw_receive_will_obtain_data_up_to_provided_size_in_bytes(self):
        "_raw_receive should correctly receive raw bytes from socket up to specified size"
        socket_mock = unittest.mock.MagicMock(spec=socket.socket)
        
        connection_object = TinyProtoConnection(socket_mock)
        
        test_data = 'My life amounts to no more than one drop in a limitless ocean. Yet what is any ocean, but a multitude of drops?'.encode()
        test_data_size = len(test_data)
        
        socket_mock.recv.return_value = test_data
        
        result = connection_object._raw_receive(test_data_size)
        
        self.assertEqual(result, test_data)
        socket_mock.recv.assert_called_once()

    def test_raw_receive_will_keep_obtaining_data_in_loop_until_socket_returns_complete_set(self):
        "_raw_receive should continue requesting data from socket untill entire byte size is obtained"
        socket_mock = unittest.mock.MagicMock(spec=socket.socket)
        
        connection_object = TinyProtoConnection(socket_mock)
        
        test_data = 'Travel far enough, you meet yourself.'.encode()
        test_data_size = len(test_data)
        
        def socket_recv_side_effect(receive_size):
            if receive_size == test_data_size:
                return test_data[:4]
            else:
                return test_data[-receive_size:]
            
        socket_mock.recv.side_effect = socket_recv_side_effect
        
        result = connection_object._raw_receive(test_data_size)
        
        self.assertEqual(result, test_data)
        self.assertEqual(len(socket_mock.recv.mock_calls), 2)

    def test_raw_receive_will_return_zero_bytearray_on_receiving_empty_response(self):
        "_raw_receive, when receiving empty byte response, should return 4 zero bytes"
        socket_mock = unittest.mock.MagicMock(spec=socket.socket)
        
        connection_object = TinyProtoConnection(socket_mock)
        
        socket_mock.recv.return_value = bytes()
        
        result = connection_object._raw_receive(5)
        
        self.assertEqual(len(result), 4)
        self.assertEqual(result, bytearray((0,0,0,0)))
        socket_mock.recv.assert_called_once()

    def test_raw_transmit_will_push_data_through_socket_object(self):
        "_raw_transmit should correctly send data over socket object"
        socket_mock = unittest.mock.MagicMock(spec=socket.socket)
        
        connection_object = TinyProtoConnection(socket_mock)
        
        test_data = "I believe there is another world waiting for us. A better world. And I'll be waiting for you there.".encode()
        
        socket_mock.send.return_value = len(test_data)

        connection_object._raw_transmit(test_data)

        socket_mock.send.assert_called_once()
        mock_send_captured_data = socket_mock.send.mock_calls[0][1][0]
        self.assertEqual(mock_send_captured_data, test_data)
        
    def test_raw_transmit_will_keep_pushing_untill_full_data_set_sent(self):
        "_raw_transmit should continue sending data in a loop until complete size is pushed"
        socket_mock = unittest.mock.MagicMock(spec=socket.socket)
        
        connection_object = TinyProtoConnection(socket_mock)
        
        test_data = "Truth is singular. Its 'versions' are mistruths.".encode()
        def socket_send_side_effect(send_data):
            if len(send_data) == len(test_data):
                return 3
            elif len(send_data) == len(test_data) - 3:
                return 4
            else:
                return len(send_data)
        socket_mock.send.side_effect = socket_send_side_effect

        connection_object._raw_transmit(test_data)
        
        self.assertEqual(len(socket_mock.send.mock_calls), 3)
        captured_send_data = [c[1][0] for c in socket_mock.send.mock_calls]
        self.assertEqual(captured_send_data[0], test_data)
        self.assertEqual(captured_send_data[1], test_data[3:])
        self.assertEqual(captured_send_data[2], test_data[7:])

    def test_transmit_will_send_size_followed_by_message(self):
        "transmit should send 4 byte size of message followed by the actual message"
        socket_mock = unittest.mock.MagicMock(spec=socket.socket)
        
        connection_object = TinyProtoConnection(socket_mock)
        
        test_data = "...now I'm a spent firework; but at least I've been a firework.".encode()
        
        socket_mock.send.side_effect = [4, len(test_data)]
        socket_mock.recv.return_value = bytes((SC_OK,))
        
        connection_object.transmit(test_data)
        
        self.assertEqual(len(socket_mock.send.mock_calls), 2)
        self.assertEqual(len(socket_mock.recv.mock_calls), 1)
        
        first_send_argument = socket_mock.send.mock_calls[0][1][0]
        second_send_argument = socket_mock.send.mock_calls[1][1][0]
        recv_argument = socket_mock.recv.mock_calls[0][1][0]
        
        self.assertEqual(first_send_argument, bytearray((0, 0, 0, len(test_data) )))
        self.assertEqual(second_send_argument, test_data)
        self.assertEqual(recv_argument, 1)
        
    def test_transmit_will_raise_on_nonok_signal(self):
        "transmit should raise TinyProtoError when remote end sends non ok signal"
        socket_mock = unittest.mock.MagicMock(spec=socket.socket)
        
        connection_object = TinyProtoConnection(socket_mock)
        
        test_data = "One fine day a predatory world shall consume itself.".encode()
        
        socket_mock.send.side_effect = [4, len(test_data)]
        socket_mock.recv.return_value = bytes((SC_GENERIC_ERROR,))
        
        with self.assertRaises(TinyProtoError):
            connection_object.transmit(test_data)
            
        self.assertEqual(len(socket_mock.send.mock_calls), 1)
        self.assertEqual(len(socket_mock.recv.mock_calls), 1)
        
    def test_receive_will_retrieve_size_followed_by_data(self):
        "receive should acquire 4 byte message size, reply with 1 byte signal ok, followed by retrieval of full message"
        socket_mock = unittest.mock.MagicMock(spec=socket.socket)
        
        connection_object = TinyProtoConnection(socket_mock)
        
        test_data = "By each crime and every kindness, we birth our future.".encode()
        
        socket_mock.recv.side_effect = [
            bytes((0,0,0, len(test_data))),
            test_data
        ]
        socket_mock.send.return_value = 1
        
        result = connection_object.receive()
        
        self.assertEqual(result, test_data)
        self.assertEqual(len(socket_mock.recv.mock_calls), 2)
        self.assertEqual(len(socket_mock.send.mock_calls), 1)
        
        first_recv_argument = socket_mock.recv.mock_calls[0][1][0]
        second_recv_argument = socket_mock.recv.mock_calls[1][1][0]
        send_argument = socket_mock.send.mock_calls[0][1][0]
        
        self.assertEqual(first_recv_argument, 4)
        self.assertEqual(second_recv_argument, len(test_data))
        self.assertEqual(send_argument, bytes((SC_OK,)))
        
    @unittest.mock.patch('tinyproto.connection.MSG_MAX_SIZE', 5)
    def test_receive_will_throw_on_too_big_message(self):
        "receive should throw TinyProtoError on oversize message"
        socket_mock = unittest.mock.MagicMock(spec=socket.socket)
        
        connection_object = TinyProtoConnection(socket_mock)
        
        socket_mock.recv.return_value = bytes((0,0,0, 42))
        socket_mock.send.return_value = 1 # because it sends an error signal on too big message
        
        with self.assertRaises(TinyProtoError):
            connection_object.receive()
            
    def test_receive_will_throw_on_empty_response(self):
        "receive should throw TinyProtoError on empty response"
        socket_mock = unittest.mock.MagicMock(spec=socket.socket)
        
        connection_object = TinyProtoConnection(socket_mock)
        
        socket_mock.recv.return_value = bytes()
        
        with self.assertRaises(TinyProtoError):
            connection_object.receive()
