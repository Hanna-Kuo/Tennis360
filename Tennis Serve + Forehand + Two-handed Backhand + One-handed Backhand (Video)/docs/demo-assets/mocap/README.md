# Optical Tennis Motion-Capture Teaching Samples

Two unmodified serve BVHs from [Tennis-MoCap](https://github.com/jdpulgarin/Tennis-MoCap),
upstream commit `9af88bb4df4e78b22127719744fdca993ced2733`, are redistributed under
[CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/). Preserve the
[upstream license](UPSTREAM-LICENSE.md), [manifest](manifest.json), source credits
and this citation with the data and derived trajectories:

Pulgarin-Giraldo J.D., Alvarez-Meza A.M., Melo-Betancourt L.G., Ramos-Bermudez S.,
Castellanos-Dominguez G. (2017). *A Similarity Indicator for Differentiating
Kinematic Performance Between Qualified Tennis Players*. LNCS 10125, 309–317.
[DOI](https://doi.org/10.1007/978-3-319-52277-7_38).

| File | Descriptive participant tier | Motion |
|---|---|---|
| adorozco_Servicio.bvh | RP, regular performance | 3,000 frames; 100 Hz |
| jarua_Servicio.bvh | HP, high performance | 3,000 frames; 100 Hz |

The study used optical Optitrack markers, then Arena skeleton reconstruction.
These are measured-motion-derived joint trajectories, not MediaPipe predictions
or raw marker centers. RP is not an incorrect-pose label; HP is not a correct-pose
label. Neither file contains paired RGB, Trophy Pose timestamps or coach ratings.
Do not treat a rendered skeleton as a real-photo test.

Use LeftShoulder/LeftElbow/LeftWrist and their right equivalents; Collar is a
separate proximal joint. The declared intrinsic channel order is Z-X-Y. For
column vectors, local rotation is Rz @ Rx @ Ry; the child offset is transformed
by its parent's rotation. Source coordinate units are preserved, never assumed
to be meters. Angles are invariant under uniform scale and rigid transforms.

```bash
.venv/bin/python scripts/evaluate_mocap.py --report-dir archive/class-mocap
```

Choose a new report directory; the script refuses to overwrite an existing CSV
or summary. It validates input hashes, records missing/degenerate arms and
compares the application's acos geometry to an independent atan2/cross-product
formula on every frame. This checks numerical geometry, not photo-model accuracy.
