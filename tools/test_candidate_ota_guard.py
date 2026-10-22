"""Offline backup-slot protection tests; does not open a device or install."""
import copy
import unittest
from test_candidate_ota import ota_target


def layout(running='ota_1'):
    return {'partitions':[dict(name=name,offset=offset,size=0x1e0000,
                               running=name==running,bootnext=name==running)
                          for name,offset in (('ota_0',0x20000),('ota_1',0x200000))]}


class Guard(unittest.TestCase):
    def test_stable_boot_allows_only_other_slot(self):
        self.assertEqual(ota_target(layout(), 'ota_1','ota_1',1800000),'ota_0')

    def test_candidate_boot_cannot_overwrite_stable(self):
        with self.assertRaises(AssertionError): ota_target(layout('ota_0'),'ota_0','ota_1',1800000)

    def test_refuses_unknown_pending_layout_or_size(self):
        baseline = layout()
        cases = []
        for field,value in (('size',0x200000),('offset',0x10000),('bootnext',True)):
            changed = copy.deepcopy(baseline)
            changed['partitions'][0][field] = value
            cases.append(changed)
        cases.extend(({'partitions':[]}, {'partitions':baseline['partitions']*2}))
        for data in cases:
            with self.assertRaises(AssertionError): ota_target(data,'ota_1','ota_1',1800000)
        for size in (0,0x1e0001):
            with self.assertRaises(AssertionError): ota_target(baseline,'ota_1','ota_1',size)
        with self.assertRaises(AssertionError): ota_target(baseline,'ota_0','ota_1',1800000)


if __name__ == '__main__': unittest.main()
