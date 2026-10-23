"""RSS policy with immutable, owner-thread snapshots for GaP checkpoints."""
import numpy as np
from robosimstudio_policy_agent import SolutionGraph
from .task import poses, beads, grade


class VerifiedGraph(SolutionGraph):
    def _new_connector(self):
        connector = super()._new_connector()

        def world_snapshot():
            def read():
                from gap.runtime.verify import Body, World
                bodies = {}
                for name, pose in poses(self.env).items():
                    points = beads(pose, name) if name != 'board' else pose[None, :3]
                    velocity = np.asarray(self.env[name].velocity).copy()
                    bodies[name] = Body(
                        name=name, position=pose[:3].copy(),
                        quaternion_wxyz=pose[[6, 3, 4, 5]].copy(),
                        aabb_lower=points.min(axis=0) - .0125,
                        aabb_upper=points.max(axis=0) + .0125,
                        linear_velocity=velocity[:3], angular_velocity=velocity[3:],
                        contacts=frozenset())
                return World(env_id=0, bodies=bodies,
                             time_s=self.env.step_count / self.env.pipeline.control_hz,
                             sim_state={'puzzle_grade': grade(self.env)})
            return self.bus.call(read)

        connector.world_snapshot = world_snapshot
        return connector
