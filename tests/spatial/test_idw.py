import numpy as np
import pytest
from scripts.spatial_pipeline import haversine_km, idw_logodds


def test_haversine_same_point():
    """Distance from a point to itself should be 0."""
    d = haversine_km(38.9, -77.0, 38.9, -77.0)
    assert abs(d) < 1e-6


def test_haversine_known_distance():
    """DCA to IAD is roughly 37km."""
    d = haversine_km(38.8521, -77.0377, 38.9531, -77.4565)
    assert 33 < d < 41, f"Unexpected DCA-IAD distance: {d:.1f} km"


def test_idw_at_station_location():
    """
    At a station's exact location, the output should be very close
    to that station's prediction.
    """
    station_probs = np.array([0.10, 0.80, 0.30, 0.20, 0.15, 0.25, 0.35, 0.40])
    station_lats  = np.array([38.8521, 38.9531, 39.1754, 39.1683,
                               39.4175, 38.7217, 38.8108, 38.5803])
    station_lons  = np.array([-77.0377, -77.4565, -76.6683, -77.1660,
                               -77.3743, -77.5155, -76.8694, -76.9228])

    # Query at station 0 (KDCA, p=0.10)
    grid_lats = np.array([38.8521])
    grid_lons = np.array([-77.0377])

    prob, low_conf = idw_logodds(station_probs, station_lats, station_lons,
                                  grid_lats, grid_lons)
    # Should be very close to 0.10 (small epsilon for numerical precision)
    assert abs(prob[0] - 0.10) < 0.02, f"Expected ~0.10, got {prob[0]:.4f}"


def test_idw_uniform_input():
    """If all stations have the same probability, every cell gets that probability."""
    p = 0.35
    station_probs = np.full(8, p)
    station_lats  = np.array([38.85, 38.95, 39.17, 39.16, 39.41, 38.72, 38.81, 38.58])
    station_lons  = np.array([-77.04, -77.46, -76.67, -77.17, -77.37, -77.52, -76.87, -76.92])

    grid_lats = np.array([39.0, 39.1, 38.9])
    grid_lons = np.array([-77.2, -77.0, -76.9])

    prob, _ = idw_logodds(station_probs, station_lats, station_lons,
                           grid_lats, grid_lons)
    np.testing.assert_allclose(prob, p, atol=1e-4)


def test_idw_output_in_01():
    """IDW output should always be in [0, 1]."""
    rng = np.random.default_rng(42)
    station_probs = rng.uniform(0.05, 0.95, 8)
    station_lats  = np.array([38.85, 38.95, 39.17, 39.16, 39.41, 38.72, 38.81, 38.58])
    station_lons  = np.array([-77.04, -77.46, -76.67, -77.17, -77.37, -77.52, -76.87, -76.92])

    grid_lats = np.linspace(38.2, 39.6, 20)
    grid_lons = np.linspace(-78.0, -76.1, 20)
    glat, glon = np.meshgrid(grid_lats, grid_lons)

    prob, _ = idw_logodds(station_probs, station_lats, station_lons,
                           glat.ravel(), glon.ravel())
    assert np.all(prob >= 0.0) and np.all(prob <= 1.0)


def test_apply_terrain_output_range():
    """Final probability after terrain offset must be in [0, 1]."""
    from scripts.spatial_pipeline import apply_terrain_offset
    rng = np.random.default_rng(0)
    idw_prob     = rng.uniform(0.05, 0.95, (10, 10))
    terrain_off  = rng.uniform(-0.5, 0.5, (10, 10))
    result = apply_terrain_offset(idw_prob, terrain_off)
    assert result.shape == (10, 10)
    assert np.all(result >= 0.0) and np.all(result <= 1.0)


def test_apply_terrain_neutral_offset():
    """A terrain offset of 0 everywhere should return the IDW probability unchanged."""
    from scripts.spatial_pipeline import apply_terrain_offset
    idw_prob = np.array([[0.1, 0.4, 0.7]])
    terrain_off = np.zeros_like(idw_prob)
    result = apply_terrain_offset(idw_prob, terrain_off)
    np.testing.assert_allclose(result, idw_prob, atol=1e-5)
