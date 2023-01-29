import unittest
import unittest.mock
import socket
from tinyproto import TinyProtoConnection, TinyProtoError


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
        
        test_data = 'This is a test message'.encode()
        test_data_size = len(test_data)
        
        socket_mock.recv.return_value = test_data
        
        result = connection_object._raw_receive(test_data_size)
        
        self.assertEqual(result, test_data)
        socket_mock.recv.assert_called_once()

    def test_raw_receive_will_keep_obtaining_data_in_loop_until_socket_returns_complete_set(self):
        "_raw_receive should continue requesting data from socket untill entire byte size is obtained"
        socket_mock = unittest.mock.MagicMock(spec=socket.socket)
        
        connection_object = TinyProtoConnection(socket_mock)
        
        test_data = 'This is a test message'.encode()
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
        
        test_data = 'Tihs is a test message'.encode()
        
        socket_mock.send.return_value = len(test_data)

        connection_object._raw_transmit(test_data)

        socket_mock.send.assert_called_once()
        mock_send_captured_data = socket_mock.send.mock_calls[0][1][0]
        self.assertEqual(mock_send_captured_data, test_data)
        
    def test_raw_transmit_will_keep_pushing_untill_full_data_set_sent(self):
        "_raw_transmit should continue sending data in a loop until complete size is pushed"
        socket_mock = unittest.mock.MagicMock(spec=socket.socket)
        
        connection_object = TinyProtoConnection(socket_mock)
        
        test_data = 'This is a test message'.encode()
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

    # TODO: transmit send size followed by message
    # TODO: transmit raise error on status not OK
    # TODO: receive retrieves 4 byte size followed by actual message
    # TODO: 