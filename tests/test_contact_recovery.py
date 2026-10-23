"""A failed lift may seat a part; acceptance still needs release and strict checks."""
import unittest
from unittest.mock import patch, MagicMock
import numpy as np
from puzzler import controller


def reading(error, speed=0., support=.001):
    return dict(poses={'yellow':[0.,0.,.76,0.,0.,0.,1.]},
                grade=dict(bead_error_m={'yellow':error,'orange':support},
                           speed_mps={'yellow':speed,'orange':0.}))


class TestContactRecovery(unittest.TestCase):
    def recover(self, confirmed, enabled=True):
        initial=reading(.006)
        lifted=reading(.001)
        pl=dict(body=np.array([0.,0.,.76,0.,0.,0.,1.]),
                grasp=np.array([0.,0.,.76]),rotation={},s=initial)
        ctx=MagicMock()
        with patch.object(controller,'state',side_effect=[initial,lifted,confirmed]), \
             patch.object(controller,'plan',return_value=pl), \
             patch.object(controller,'move'),patch.object(controller,'grip') as grip:
            result=controller.place(ctx,'yellow',dict(preserve_placed=True,
                recover_contact_seated=enabled))
            return result,grip,ctx

    def test_seated_contact_recovery_releases_and_rechecks(self):
        result,grip,ctx=self.recover(reading(.00076))
        self.assertEqual(result['route'],'placed')
        self.assertTrue(result['contact_seated'])
        self.assertEqual(grip.call_args.args[2],.04)
        ctx.tool.assert_called_once_with('robot.wait_steps',steps=50)

    def test_rejects_error_moving_or_disturbed_support(self):
        for confirmed in [reading(.004),reading(.001,speed=.015),reading(.001,support=.004)]:
            with self.subTest(confirmed=confirmed):
                result,_,_=self.recover(confirmed)
                self.assertEqual(result['route'],'retry')

    def test_recovery_is_explicitly_enabled(self):
        result,_,ctx=self.recover(reading(.001),enabled=False)
        self.assertEqual(result['failure'],'grasp_miss')
        ctx.tool.assert_not_called()


if __name__=='__main__':unittest.main()
