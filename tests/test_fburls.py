from fbwatch.fburls import is_permalink, normalize_permalink, page_plugin_url, post_id_from_permalink, post_plugin_url


def test_normalize_strips_tracking_and_host():
    assert normalize_permalink("/ertnews/posts/1001?__cft__[0]=abc&__tn__=-R") == "https://www.facebook.com/ertnews/posts/1001"
    assert normalize_permalink("https://m.facebook.com/permalink.php?story_fbid=2002&id=555&__tn__=x") == \
        "https://www.facebook.com/permalink.php?story_fbid=2002&id=555"


def test_post_ids():
    assert post_id_from_permalink("https://www.facebook.com/ertnews/posts/1001") == "post_1001"
    assert post_id_from_permalink("https://www.facebook.com/permalink.php?story_fbid=2002&id=555") == "story_fbid_2002"
    assert post_id_from_permalink("/ertnews/videos/3003/") == "video_3003"
    assert post_id_from_permalink("/ertnews/photos/a.123/4004/") == "photo_4004"
    assert post_id_from_permalink("https://www.facebook.com/photo.php?fbid=99&set=a.1") == "fbid_99"
    assert post_id_from_permalink("https://www.facebook.com/ertnews/something").startswith("h_")


def test_same_post_different_tracking_same_id():
    a = post_id_from_permalink("/ertnews/posts/1001?__cft__[0]=abc")
    b = post_id_from_permalink("https://www.facebook.com/ertnews/posts/1001")
    assert a == b


def test_plugin_urls():
    u = page_plugin_url("https://www.facebook.com/ertnews", "el-GR")
    assert u.startswith("https://www.facebook.com/plugins/page.php?")
    assert "href=https%3A%2F%2Fwww.facebook.com%2Fertnews" in u and "tabs=timeline" in u and "locale=el_GR" in u
    p = post_plugin_url("https://www.facebook.com/ertnews/posts/1001")
    assert p.startswith("https://www.facebook.com/plugins/post.php?") and "show_text=true" in p


def test_is_permalink():
    assert is_permalink("/ertnews/posts/1")
    assert is_permalink("https://www.facebook.com/watch/?v=1")
    assert not is_permalink("https://www.facebook.com/ertnews/")
    assert not is_permalink(None)
