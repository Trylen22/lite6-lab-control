"""Fixed-height visual servo math, in pixels and robot-base millimeters.

A stationary marker moves in the IMAGE when the wrist camera moves in XY.
J maps camera/arm displacement to that image displacement. Its signs are
measured, never guessed from how the picture looks. This local approximation
is valid only for the sampled plane, camera settings, height and orientation.
"""

import numpy as np


def fit_response(offsets_mm, centers_px):
    """Fit p = aim + J @ XY using an overdetermined least-squares system."""
    xy = np.asarray(offsets_mm, dtype=float)
    pixels = np.asarray(centers_px, dtype=float)
    if xy.ndim != 2 or xy.shape[1] != 2 or pixels.shape != xy.shape or len(xy) < 5:
        raise ValueError("Need at least five paired XY/pixel observations")
    if not np.isfinite(xy).all() or not np.isfinite(pixels).all():
        raise ValueError("Nonfinite calibration data")
    design = np.column_stack([np.ones(len(xy)), xy])
    if np.linalg.matrix_rank(design) != 3:
        raise ValueError("Samples must span both robot axes")
    coefficients = np.linalg.lstsq(design, pixels, rcond=None)[0]
    jacobian = coefficients[1:].T
    singular = np.linalg.svd(jacobian, compute_uv=False)
    residual = np.linalg.norm(design @ coefficients - pixels, axis=1)
    if singular[-1] < 0.25 or singular[0] / singular[-1] > 5:
        raise ValueError("Image response is too weak or ill-conditioned")
    if max(residual) > 2:
        raise ValueError("Calibration residual exceeds two pixels")
    return {
        "aim_px": coefficients[0].tolist(),
        "jacobian_px_per_mm": jacobian.tolist(),
        "max_residual_px": float(max(residual)),
        "condition": float(singular[0] / singular[-1]),
    }


def correction_mm(model, center_px, gain=0.6, max_step_mm=2):
    """Solve J*dXY = aim-current; damp and cap the EUCLIDEAN step length."""
    matrix = np.asarray(model["jacobian_px_per_mm"], dtype=float)
    error = np.asarray(model["aim_px"]) - np.asarray(center_px)
    delta = np.linalg.solve(matrix, error) * gain
    if not np.isfinite(delta).all():
        raise ValueError("Nonfinite visual correction")
    length = np.linalg.norm(delta)
    if length > max_step_mm:
        delta *= max_step_mm / length
    return delta.tolist()
