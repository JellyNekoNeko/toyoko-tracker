from toyoko_tracker.desktop import _parser


def test_desktop_parser_defaults():
    args = _parser().parse_args([])
    assert args.port == 4170
    assert args.lan is False
    assert args.local_only is False
    assert args.debug is False


def test_desktop_parser_supports_local_mode_and_port():
    args = _parser().parse_args(["--local-only", "--port", "5180", "--debug"])
    assert args.local_only is True
    assert args.port == 5180
    assert args.debug is True
