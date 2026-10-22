"""Offline probe socket semantics, not actual ESP forwarding."""
import struct
import unittest
from unittest.mock import patch
import lab_echo

class FakeSocket:
    def __init__(self):self.options=[];self.bound=None;self.token=b'';self.closed=False;self.parts=0
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
    def settimeout(self,n):self.timeout=n
    def setsockopt(self,*args):self.options.append(args)
    def bind(self,a):self.bound=a
    def connect(self,a):self.target=a
    def sendall(self,b):self.token=b
    def send(self,b):self.token=b;return len(b)
    def recv(self,n):
        self.parts+=1
        if self.parts==1:out,self.token=self.token[:7],self.token[7:];return out
        out,self.token=self.token[:n],self.token[n:];return out
    def close(self):self.closed=True

class ProbeTests(unittest.TestCase):
    def test_interface_index_network_order_and_source_bind(self):
        s=FakeSocket()
        with patch.object(lab_echo.sys,'platform','win32'),patch.object(lab_echo.socket,'socket',return_value=s):
            self.assertIs(lab_echo.client_socket('tcp','192.0.2.61',18,1),s)
        self.assertEqual(s.bound,('192.0.2.61',0))
        self.assertEqual(s.options[0][2],struct.pack('!I',18))
    def test_complete_tcp_reply_not_one_recv(self):
        s=FakeSocket()
        with patch.object(lab_echo,'client_socket',return_value=s),patch.object(lab_echo.time,'sleep'):
            self.assertEqual(lab_echo.probe('192.0.2.20:18830','tcp',1),1)
        self.assertGreater(s.parts,1);self.assertTrue(s.closed)
    def test_unsupported_interface_refuses_without_fallback(self):
        s=FakeSocket()
        with patch.object(lab_echo.sys,'platform','linux'),patch.object(lab_echo.socket,'socket',return_value=s):
            with self.assertRaises(ValueError):lab_echo.client_socket('tcp',interface_index=18)
        self.assertTrue(s.closed)

if __name__=='__main__':unittest.main()
