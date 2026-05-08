from sts2_bridge.macos_screenshot import WindowInfo, select_game_window


def test_select_game_window_uses_largest_visible_layer_zero_window() -> None:
    windows = [
        WindowInfo(1, "Slay the Spire 2", None, 0, 0, 1512, 33, 0),
        WindowInfo(2, "Slay the Spire 2", None, 0, 482, 64, 64, 0),
        WindowInfo(3, "Slay the Spire 2", None, 0, 33, 1512, 949, 0),
        WindowInfo(4, "Slay the Spire 2", None, 0, 0, 1512, 33, 26),
    ]

    selected = select_game_window(windows)

    assert selected.window_id == 3
