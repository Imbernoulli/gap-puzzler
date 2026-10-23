"""The explicit hardware variant must retain the stock collisions and drive."""
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import robosimstudio
from robosimstudio.robots.registry import get_embodiment, get_gripper

from puzzler.hardware import register


class TestPrecisionHardware(unittest.TestCase):
    def test_stock_contacts_and_actuators_are_retained(self):
        source = Path(robosimstudio.__file__).resolve().parent.parent / 'assets/embodiments/yam/yam_bimanual_arms.xml'
        stock = ET.parse(source).getroot()
        name = register('yam_bimanual_precision20v1')
        spec = get_embodiment(name)
        modified = ET.parse(spec.asset.path).getroot()
        for section in ['default', 'actuator', 'equality']:
            self.assertEqual(ET.tostring(stock.find(section)), ET.tostring(modified.find(section)))
        for old in stock.findall('.//body'):
            new = modified.find(f'.//body[@name="{old.get("name")}"]')
            self.assertIsNotNone(new)
            self.assertEqual(old.attrib, new.attrib)
            for tag in ['geom', 'joint', 'inertial']:
                self.assertEqual([ET.tostring(e) for e in old.findall(tag)],
                                 [ET.tostring(e) for e in new.findall(tag)])
        self.assertEqual(len(modified.findall('.//geom')) - len(stock.findall('.//geom')), 12)
        self.assertAlmostEqual(get_gripper(spec.arms[0].gripper).tcp_offset[2], .150)
        self.assertFalse(spec.enable_self_collisions)  # Same upstream hardware setting.


if __name__ == '__main__':
    unittest.main()
