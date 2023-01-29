import unittest
import unittest.mock
import socket
from tinyproto import TinyProtoConnectionDetails, TinyProtoError


class TestConnectionDetails(unittest.TestCase):
    def test_port_range_verification(self):
        "When port number outside of tcp port range provided, should throw correct error"
        
        incorrect_port_number = 65555
        
        with self.assertRaises(TinyProtoError):
            connection_details = TinyProtoConnectionDetails("localhost", incorrect_port_number)

    @unittest.mock.patch('socket.getaddrinfo')
    def test_tinyproto_exception_for_socket_exception(self, mock_getaddrinfo):
        "When socket.getaddrinfo call throws gaierror, should throw correct error"
        
        mock_getaddrinfo.side_effect = socket.gaierror(5, "dummy error")
        
        with self.assertRaises(TinyProtoError):
            connection_details = TinyProtoConnectionDetails('localhost', 22)
        self.assertGreater(len(mock_getaddrinfo.mock_calls), 0)

    @unittest.mock.patch('socket.getaddrinfo')
    def test_tinyproto_exception_for_address_family_not_supported_details(self, mock_getaddrinfo):
        "When no supported address family connection details returned by socket.getaddrinfo, should throw correct error"
        
        getaddrinfo_return_value = [
            (
                socket.AddressFamily.AF_BLUETOOTH,
                socket.SocketKind.SOCK_STREAM,
                6,
                '',
                ('172.217.16.36', 443)
            )
        ]
        
        mock_getaddrinfo.return_value = getaddrinfo_return_value
        
        with self.assertRaises(TinyProtoError):
            connection_details = TinyProtoConnectionDetails('localhost', 22)
        self.assertGreater(len(mock_getaddrinfo.mock_calls), 0)

    @unittest.mock.patch('socket.getaddrinfo')
    def test_tinyproto_exception_for_socket_kind_not_supported_details(self, mock_getaddrinfo):
        "When no supported socket kind connection details returned by socket.getaddrinfo, should throw correct error"
        
        getaddrinfo_return_value = [
            (
                socket.AddressFamily.AF_INET,
                socket.SocketKind.SOCK_DGRAM,
                17,
                '',
                ('172.217.16.36', 443)
            ),
            (
                socket.AddressFamily.AF_INET,
                socket.SocketKind.SOCK_RAW,
                0,
                '',
                ('172.217.16.36', 443)
            ),
            (
                socket.AddressFamily.AF_INET6,
                socket.SocketKind.SOCK_DGRAM,
                17,
                '',
                ('2a00:1450:401b:805::2004', 443, 0, 0)
            ),
            (
                socket.AddressFamily.AF_INET6,
                socket.SocketKind.SOCK_RAW,
                0,
                '',
                ('2a00:1450:401b:805::2004', 443, 0, 0)
            )
        ]
        
        mock_getaddrinfo.return_value = getaddrinfo_return_value
        
        with self.assertRaises(TinyProtoError):
            connection_details = TinyProtoConnectionDetails('localhost', 22)
        self.assertGreater(len(mock_getaddrinfo.mock_calls), 0)

    @unittest.mock.patch('socket.getaddrinfo')
    def test_tinyproto_exception_for_empty_getaddrinfo_response(self, mock_getaddrinfo):
        "When getaddrinfo returns empty response, should throw correct error"
        
        mock_getaddrinfo.return_value = []
        
        with self.assertRaises(TinyProtoError):
            connection_details = TinyProtoConnectionDetails('localhost', 22)
        self.assertGreater(len(mock_getaddrinfo.mock_calls), 0)

    @unittest.mock.patch('socket.getaddrinfo')
    def test_first_supported_details_picked_from_response(self, mock_getaddrinfo):
        "When supported details returned, picks first and sets correct attributes"
        
        test_socket_address_family = socket.AddressFamily.AF_INET
        test_socket_kind = socket.SocketKind.SOCK_STREAM
        test_socket_proto = 6
        test_socket_connection_details = ('172.217.16.36', 443)
        
        getaddrinfo_return_value = [
            (
                test_socket_address_family,
                test_socket_kind,
                test_socket_proto,
                '',
                test_socket_connection_details
            ),
            (
                socket.AddressFamily.AF_INET,
                socket.SocketKind.SOCK_DGRAM,
                17,
                '',
                ('172.217.16.36', 443)
            ),
            (
                socket.AddressFamily.AF_INET,
                socket.SocketKind.SOCK_RAW,
                0,
                '',
                ('172.217.16.36', 443)
            ),
            (
                socket.AddressFamily.AF_INET6,
                socket.SocketKind.SOCK_STREAM,
                6,
                '',
                ('2a00:1450:401b:805::2004', 443, 0, 0)
            ),
            (
                socket.AddressFamily.AF_INET6,
                socket.SocketKind.SOCK_DGRAM,
                17,
                '',
                ('2a00:1450:401b:805::2004', 443, 0, 0)
            ),
            (
                socket.AddressFamily.AF_INET6,
                socket.SocketKind.SOCK_RAW,
                0,
                '',
                ('2a00:1450:401b:805::2004', 443, 0, 0)
            )
        ]
        
        mock_getaddrinfo.return_value = getaddrinfo_return_value
        
        connection_details = TinyProtoConnectionDetails('localhost', 22)

        self.assertGreater(len(mock_getaddrinfo.mock_calls), 0)        
        self.assertEqual(connection_details.address_family, test_socket_address_family)
        self.assertEqual(connection_details.socket_kind, test_socket_kind)
        self.assertEqual(connection_details.socket_proto, test_socket_proto)
        self.assertEqual(connection_details.socket_connect_details, test_socket_connection_details)
