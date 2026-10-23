"""Regression: a piece at 4.036 mm settled before an unnecessary regrasp."""
import unittest

from puzzler.controller import place


class RecheckContext:
    def __init__(self, readings):
        self.readings = iter(readings)
        self.calls = []

    def tool(self, name, **kwargs):
        self.calls.append((name, kwargs))
        if name == 'puzzle.observe':
            error, speed = next(self.readings)
            return {'grade': {'bead_error_m': {'navy': error}, 'speed_mps': {'navy': speed}}}
        if name == 'robot.wait_steps':
            return {}
        raise RuntimeError('new grasp required')


class TestSeatedRecheck(unittest.TestCase):
    def test_settling_can_avoid_a_second_grasp(self):
        ctx = RecheckContext([(.004036, .0001), (.002094, .0001)])
        result = place(ctx, 'navy', {'reuse_seated': True, 'full_task': True})
        self.assertEqual(result['route'], 'placed')
        self.assertTrue(result['reused_seated'])
        self.assertEqual([name for name, _ in ctx.calls],
                         ['puzzle.observe', 'robot.wait_steps', 'puzzle.observe'])

    def test_nearby_piece_is_not_accepted_outside_the_strict_gate(self):
        ctx = RecheckContext([(.006, .0001)] * 3)
        with self.assertRaisesRegex(RuntimeError, 'new grasp required'):
            place(ctx, 'navy', {'reuse_seated': True, 'full_task': True})

    def test_seated_but_moving_piece_is_not_accepted(self):
        ctx = RecheckContext([(.002, .04)] * 3)
        with self.assertRaisesRegex(RuntimeError, 'new grasp required'):
            place(ctx, 'navy', {'reuse_seated': True, 'full_task': True})


if __name__ == '__main__':
    unittest.main()
