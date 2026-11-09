from pathlib import Path

from streamlit.testing.v1 import AppTest


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def test_dashboard_client_selection_filters_and_downloads():
    app = AppTest.from_file(str(APP_PATH), default_timeout=30).run()
    assert not app.exception
    assert len(app.tabs) == 4
    assert app.metric[0].value == "5"
    assert app.metric[1].value == "425"
    assert len(app.get("plotly_chart")) == 3
    app.selectbox[0].select("C005").run()
    assert not app.exception
    assert any("Harbor Collective" in heading.value for heading in app.subheader)
    assert app.metric[7].value.endswith("%")
    app.multiselect[0].select("CedarWorks").run()
    app.multiselect[1].select("Medium").run()
    assert not app.exception
    findings = app.dataframe[1].value
    assert findings["Client"].tolist() == ["CedarWorks"]
    assert findings["Detected issue"].tolist() == ["Low engagement"]
    downloads = app.get("download_button")
    assert len(downloads) == 2
    assert all(button.proto.url for button in downloads)
    app.multiselect[1].unselect("Medium").select("High").run()
    assert not app.exception
    assert any("No findings match" in message.value for message in app.success)
