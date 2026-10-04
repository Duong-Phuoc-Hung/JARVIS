"""Unavailable market feeds must never become fabricated live quotes."""
from unittest.mock import patch

import pytest

from jarvis.web.finance import FinanceTracker
from jarvis.web.hub import WebIntelligenceHub


@pytest.mark.parametrize('method,args', [
    ('get_exchange_rate', ('USD', 'VND')),
    ('_fetch_crypto_quote', ('BTC', 25000.0)),
    ('get_stock_quote', ('AAPL',)),
])
def test_offline_finance_raises_instead_of_fabricating(method, args):
    tracker = FinanceTracker()
    with patch('jarvis.web.finance.REQUESTS_AVAILABLE', False), patch(
        'urllib.request.urlopen', side_effect=OSError('offline')
    ):
        with pytest.raises(RuntimeError, match='MARKET_DATA_UNAVAILABLE'):
            getattr(tracker, method)(*args)


def test_briefing_retains_available_sections_without_market_data():
    from jarvis.web.weather import WeatherData

    hub = WebIntelligenceHub()
    with patch.object(hub.weather, 'get_weather', return_value=WeatherData(
        city='Test', temp_c=20, feels_like_c=20, condition='Clear', humidity=50, wind_kph=0
    )), patch.object(hub.news, 'get_top_news', return_value=[]), patch.object(
        hub.finance, 'get_exchange_rate', side_effect=RuntimeError('MARKET_DATA_UNAVAILABLE')
    ):
        result = hub.generate_morning_briefing()
    assert result['status'] == 'LIMITED'
    assert result['success'] is False
    assert result['crypto'] == {}
    assert result['usd_vnd_rate'] is None
    assert '20' in result['spoken_summary']
