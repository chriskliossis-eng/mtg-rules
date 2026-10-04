import shutil
from pathlib import Path

from fbwatch.cli import main
from fbwatch.storage import PostRecord, Storage


def test_export_with_dotted_source_id(tmp_path, capsys):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("data_dir: ./data\nsources:\n  - {id: in.gr, url: https://www.facebook.com/in.gr}\n", encoding="utf-8")
    with Storage(tmp_path / "data" / "fbwatch.sqlite3") as st:
        st.insert_post(PostRecord(post_id="1", source_id="in.gr", permalink="https://www.facebook.com/in.gr/posts/1",
                                  posted_at="2026-10-01T09:00:00+03:00", first_seen="2026-10-01T10:00:00+03:00",
                                  last_seen="2026-10-01T10:00:00+03:00", text="x"))
    main(["-c", str(cfg), "export", "-s", "in.gr", "-f", "csv"])
    out = capsys.readouterr().out
    files = list((tmp_path / "data" / "exports").iterdir())
    assert len(files) == 1 and files[0].name.startswith("fbwatch_in.gr_") and files[0].suffix == ".csv", out


def test_bad_date_gives_clean_error(tmp_path, capsys):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("sources: []\n", encoding="utf-8")
    import pytest
    with pytest.raises(SystemExit) as e:
        main(["-c", str(cfg), "list", "--from", "χθες"])
    assert "Σφάλμα" in str(e.value)
