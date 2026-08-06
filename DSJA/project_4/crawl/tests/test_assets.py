from p4_crawl.assets import is_linkareer_hosted


def test_asset_host_policy() -> None:
    assert is_linkareer_hosted("https://cdn.linkareer.com/a.png")
    assert is_linkareer_hosted("https://linkareer.com/a.png")
    assert not is_linkareer_hosted("https://linkareer.com.evil.example/a.png")
    assert not is_linkareer_hosted("http://linkareer.com/a.png")
