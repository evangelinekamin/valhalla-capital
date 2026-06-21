import os
from unittest.mock import MagicMock, patch


@patch("scraper.core.pipeline.get_engine")
@patch("scraper.core.pipeline.TriageEngine")
@patch("scraper.core.pipeline.PreFilter")
def test_pipeline_uses_local_miniflux_default(mock_prefilter, mock_triage, mock_get_engine):
    """Pipeline should default to host-mapped Miniflux port when MINIFLUX_URL is unset."""
    from scraper.core.pipeline import ProcessingPipeline

    mock_get_engine.return_value = MagicMock()

    with patch.dict(os.environ, {"MINIFLUX_API_KEY": "test-key"}, clear=True):
        pipeline = ProcessingPipeline()

    assert pipeline.miniflux_url == "http://localhost:8081"


@patch("scraper.core.pipeline.get_engine")
@patch("scraper.core.pipeline.TriageEngine")
@patch("scraper.core.pipeline.PreFilter")
def test_pipeline_miniflux_url_env_override(mock_prefilter, mock_triage, mock_get_engine):
    """Pipeline should use MINIFLUX_URL when it is provided."""
    from scraper.core.pipeline import ProcessingPipeline

    mock_get_engine.return_value = MagicMock()

    with patch.dict(
        os.environ,
        {
            "MINIFLUX_API_KEY": "test-key",
            "MINIFLUX_URL": "http://miniflux:8080",
        },
        clear=True,
    ):
        pipeline = ProcessingPipeline()

    assert pipeline.miniflux_url == "http://miniflux:8080"
