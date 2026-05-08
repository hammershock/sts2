import pytest

from sts2_bridge.macos_screenshot import WindowInfo, select_game_window, window_click_coordinates
from sts2_bridge.models import BridgeError


def test_select_game_window_uses_largest_visible_layer_zero_window() -> None:
    windows = [
        WindowInfo(1, "Slay the Spire 2", None, 0, 0, 1512, 33, 0),
        WindowInfo(2, "Slay the Spire 2", None, 0, 482, 64, 64, 0),
        WindowInfo(3, "Slay the Spire 2", None, 0, 33, 1512, 949, 0),
        WindowInfo(4, "Slay the Spire 2", None, 0, 0, 1512, 33, 26),
    ]

    selected = select_game_window(windows)

    assert selected.window_id == 3


def test_window_click_coordinates_support_pixel_and_normalized_positions() -> None:
    window = WindowInfo(3, "Slay the Spire 2", None, 100, 200, 800, 600, 0)

    assert window_click_coordinates(window, 40, 50) == (140, 250)
    assert window_click_coordinates(window, 0.5, 0.25, normalized=True) == (500, 350)


def test_window_click_coordinates_reject_out_of_bounds_positions() -> None:
    window = WindowInfo(3, "Slay the Spire 2", None, 100, 200, 800, 600, 0)

    with pytest.raises(BridgeError) as exc_info:
        window_click_coordinates(window, 1.2, 0.5, normalized=True)

    assert exc_info.value.code == "invalid_click_coordinates"
