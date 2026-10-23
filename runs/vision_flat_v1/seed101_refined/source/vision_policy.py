"""GaP execution restricted to RGB estimates and robot proprioception.

The whitelist is enforced at invocation, including late skill registration.
This is an observation boundary for our authored policy, not a security sandbox
for arbitrary hostile Python programs.
"""
from gap_core.tools import ToolRegistry
from robosimstudio_policy_agent import SolutionGraph

from . import vision_planning
from .vision_observer import RGBSensor, VisualObserver, goals


ALLOWED_TOOLS = frozenset({
    'vision.observe', 'puzzle.plan_pose', 'puzzle.plan_path',
    'robot.get_ee_pose', 'robot.grasp_frame', 'robot.set_grip',
    'robot.execute_trajectory', 'robot.wait_steps', 'robot.go_home',
})


class RestrictedRegistry(ToolRegistry):
    def __init__(self, source):
        super().__init__()
        self.source = source
        # Copy only reviewed descriptors. Never retain hidden names in catalog.
        self._tools = {n: d for n, d in source._tools.items() if n in ALLOWED_TOOLS}

    def get(self, name):
        if name not in ALLOWED_TOOLS:
            raise KeyError(f'Not in RGB policy tool contract: {name}')
        return super().get(name)

    def invoke(self, name, ctx=None, **kwargs):
        self.get(name)
        return self.source.invoke(name, ctx, **kwargs)

    def runtime_tools(self):
        return {n: d for n, d in super().runtime_tools().items() if n in ALLOWED_TOOLS}

    def codegen_tools(self):
        return {n: d for n, d in super().codegen_tools().items() if n in ALLOWED_TOOLS}


class VisionGraph(SolutionGraph):
    def __init__(self, env, *, visual_mode='flat', visual_plan='pyramid_robot6_plan.json',
                 observation_dir=None, **kwargs):
        self.sensor = RGBSensor(env)
        self.visual = VisualObserver(self.sensor.capture, self.sensor.cameras,
                                     goals(visual_mode, visual_plan), observation_dir)
        kwargs.update(privileged=False, perception='vision', task_tools=self._register_visual)
        super().__init__(env, **kwargs)

    def _register_visual(self, registry, env, bus):
        vision_planning.register(registry, env, bus)

        def observe(hints: dict = None):
            return bus.call(lambda: self.visual.observe(hints))

        registry.register_callable('vision.observe', observe,
                                   summary='RGB-only calibrated detections, rigid fits and visual goal residuals.',
                                   tags=('vision',))

    def _new_connector(self):
        connector = super()._new_connector()
        connector._tool_registry = RestrictedRegistry(connector.tool_registry)
        # Remove alternate observation/evaluator paths from the connector API.
        connector.get_observation = None
        connector.check_success = None
        connector.facade.compute_reward = lambda: 0.
        connector.facade.task_completed = lambda: False

        def world_snapshot():
            from gap.runtime.verify import World
            # Checkpoints can inspect only the last image-derived observation.
            return World(env_id=0, bodies={}, time_s=0., sim_state={'vision': self.visual.last or {}})

        connector.world_snapshot = world_snapshot
        return connector
