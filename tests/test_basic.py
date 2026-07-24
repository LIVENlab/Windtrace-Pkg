def test_import_windtrace():
    import windtrace
    assert windtrace.__version__ is not None


def test_updater_import():
    from windtrace.ecoinvent_variables_updater import build_parser
    parser = build_parser()
    assert parser is not None