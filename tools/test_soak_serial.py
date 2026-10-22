"""Offline log evidence checks; never import pyserial, open COM or reset hardware."""
import unittest
from soak_serial import summarise

class SoakEvidenceTests(unittest.TestCase):
    def test_interrupted_log_is_not_hour_soak(self):
        r=summarise('[+0.5] rst:0x15 (USB_UART_CHIP_RESET)\n[+2570.0] heap_internal_free=7847 stack_free=5296\n')
        self.assertEqual(r['last_capture_marker_seconds'],2570)
        self.assertLess(r['last_capture_marker_seconds'],3600)
        self.assertEqual(r['reboot'],1)
        self.assertEqual(r['heap_internal_min'],7847)
        self.assertFalse(r['largest_free_block_measured'])
        self.assertFalse(r['unexpected_resets_proven_absent'])
    def test_empty_log_and_explicit_failures(self):
        self.assertIsNone(summarise('')['last_capture_marker_seconds'])
        r=summarise('[+1] heap_internal_free=12\n[+2] heap_internal_free=9\nESP_ERR_NO_MEM\nTask watchdog got triggered\nBacktrace:')
        self.assertEqual((r['heap_internal_min'],r['heap_internal_max'],r['heap_internal_last']),(9,12,9))
        self.assertEqual((r['alloc_fail'],r['watchdog'],r['panic']),(1,1,1))
        self.assertEqual(r['largest_capture_marker_gap_seconds'],1)

if __name__=='__main__':unittest.main()
