# -*- coding: utf-8 -*-
#
# ,---------,       ____  _ __
# |  ,-^-,  |      / __ )(_) /_______________ _____  ___
# | (  O  ) |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
# | / ,--'  |    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#    +------`   /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
# Copyright (C) 2022 Bitcraze AB
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, in version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
import numpy as np
import numpy.typing as npt

from .ippe_cf import IppeCf
from cflib.localization.lighthouse_types import LhCfPoseSample
from cflib.localization.lighthouse_types import Pose


class LighthouseInitialEstimator:
    """
    Make initial estimates of base station and CF poses useing IPPE (analytical solution).
    The estimates are not good enough to use for flight but is a starting point for further
    Calculations.
    """

    @classmethod
    def estimate(cls, matched_samples: list[LhCfPoseSample], sensor_positions: npt.ArrayLike) -> dict[int, Pose]:
        """
        Make a rough estimate of the poses of all base stations found in the samples.

        The pose of the Crazyflie in the first sample is used as a reference and will define the
        global reference frame.

        :param matched_samples: A list of samples with lihghthouse angles. Note: matched_samples is augmented with
                                more information during the process, including the estimated poses
        :param sensor_positions: An array with the sensor positions on the lighthouse deck (3D, CF ref frame)
        """

        cls._angles_to_poses(matched_samples, sensor_positions)

        # TODO Do not use first sample as reference, pass it in as a parameter

        bs_poses: dict[int, Pose] = {}
        cls._get_reference_bs_poses(matched_samples[0], bs_poses)
        cls._calc_remaining_bs_poses(matched_samples, bs_poses)
        cls._calc_cf_poses(matched_samples, bs_poses)

        return bs_poses

    @classmethod
    def _angles_to_poses(cls, matched_samples: list[LhCfPoseSample], sensor_positions: npt.ArrayLike) -> None:
        for sample in matched_samples:
            poses: dict[int, Pose] = {}
            for bs, angles in sample.angles_calibrated.items():
                Q = angles.projection_pair_list()
                estimate = IppeCf.solve(sensor_positions, Q)

                # Pick the first solution from IPPE and convert to cf ref frame
                R_mat = estimate[0][0].transpose()
                t_vec = np.dot(R_mat, -estimate[0][1])

                poses[bs] = Pose(R_mat, t_vec)
            sample.initial_est_bs_poses = poses

    @classmethod
    def _get_reference_bs_poses(cls, sample: LhCfPoseSample, bs_poses: dict[int, Pose]) -> None:
        """
        The Pose of the CF in this sample is defining the global ref frame.
        Store the poses for the bases stations that are in the sample.
        """
        est_ref_cf = sample.initial_est_bs_poses
        for bs, pose in est_ref_cf.items():
            bs_poses[bs] = pose

    @classmethod
    def _calc_remaining_bs_poses(cls, matched_sampels: list[LhCfPoseSample], bs_poses: dict[int, Pose]) -> None:
        # Find all base stations in the list
        all_bs = set()
        for sample in matched_sampels:
            all_bs.update(sample.initial_est_bs_poses.keys())

        # Remove the reference base stations that we already have the poses for
        to_find = all_bs - bs_poses.keys()

        # run through the list of samples until we manage to find them all
        remaining = len(to_find)
        while remaining > 0:
            for sample in matched_sampels:
                bs_poses_in_sample = sample.initial_est_bs_poses
                unknown = to_find.intersection(bs_poses_in_sample.keys())
                known = set(bs_poses.keys()).intersection(bs_poses_in_sample.keys())

                # We need (at least) one known bs pose to use when transforming the other poses to the global ref frame
                if len(known) > 0:
                    known_bs = list(known)[0]

                    # The known BS pose in the global reference frame
                    known_global = bs_poses[known_bs]
                    # The known BS pose in the CF reference frame (of this sample)
                    known_cf = bs_poses_in_sample[known_bs]

                    for bs in unknown:
                        # The unknown BS pose in the CF reference frame (of this sample)
                        unknown_cf = bs_poses_in_sample[bs]
                        # Finally we can calculate the BS pose in the global reference frame
                        bs_poses[bs] = cls._map_pose_to_ref_frame(known_global, known_cf, unknown_cf)

                to_find = all_bs - bs_poses.keys()
                if len(to_find) == 0:
                    break

            if len(to_find) == remaining:
                raise Exception('Can not link positions between all base stations')

            remaining = len(to_find)

    @classmethod
    def _calc_cf_poses(cls, matched_samples: list[LhCfPoseSample], bs_poses: list[Pose]) -> None:
        for sample in matched_samples:
            # Use the first base station pose as a reference
            est_ref_cf = sample.initial_est_bs_poses
            ref_bs = list(est_ref_cf.keys())[0]

            pose_global = bs_poses[ref_bs]
            pose_cf = est_ref_cf[ref_bs]
            est_ref_global = cls._map_cf_pos_to_cf_pos(pose_global, pose_cf)
            sample.inital_est_pose = est_ref_global

    @classmethod
    def _map_pose_to_ref_frame(cls, pose1_ref1: Pose, pose1_ref2: Pose, pose2_ref2: Pose) -> Pose:
        """
        Express pose2 in reference system 1, given pose1 in both reference system 1 and 2
        """
        R_o2_in_1, t_o2_in_1 = cls._map_cf_pos_to_cf_pos(pose1_ref1, pose1_ref2).matrix_vec

        t = np.dot(R_o2_in_1, pose2_ref2.translation) + t_o2_in_1
        R = np.dot(R_o2_in_1, pose2_ref2.rot_matrix)

        return Pose(R, t)

    @classmethod
    def _map_cf_pos_to_cf_pos(cls, pose1_ref1: Pose, pose1_ref2: Pose) -> Pose:
        """
        Find the rotation/translation from ref1 to ref2 given a pose,
        that is the returned Pose will tell us where the origin in ref2 is,
        expressed in ref1
        """

        R_inv_ref2 = np.matrix.transpose(pose1_ref2.rot_matrix)
        R = np.dot(pose1_ref1.rot_matrix, R_inv_ref2)
        t = pose1_ref1.translation - np.dot(R, pose1_ref2.translation)

        return Pose(R, t)