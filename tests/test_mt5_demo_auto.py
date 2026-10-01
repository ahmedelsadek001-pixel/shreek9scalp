from datetime import datetime, timezone
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.enums import Direction
from execution.mt5_demo_auto import scan_and_submit_demo
from execution import mt5_demo_auto, mt5_demo_auto_cli
from test_mt5_demo_transport import CONFIG, Account, FakeMT5


def _bars(now):
    last_start = int((now.timestamp() - 330) // 300) * 300
    bar_time = datetime.fromtimestamp(last_start + 330, timezone.utc)
    return bar_time, [dict(time=last_start - 300 * (79 - i), open=4000.0,
                           high=4001.0, low=3999.0, close=4000.0,
                           tick_volume=100) for i in range(80)]


def _api(now):
    api = FakeMT5()
    api.TIMEFRAME_M5 = 5
    clock, bars = _bars(now)
    api.copy_rates_from_pos = lambda symbol, timeframe, start, count: (
        bars if (symbol, timeframe, start, count) == ("XAUUSD.s", 5, 1, 80) else None)
    return api, clock, bars


def _signal(bars):
    return SimpleNamespace(direction=Direction.BUY,
                           signal_time=datetime.fromtimestamp(bars[-1]["time"], timezone.utc),
                           breakout_time=datetime.fromtimestamp(bars[-2]["time"], timezone.utc),
                           entry_price=4000.0, sl_price=3998.0, tp1=4002.0)


def test_market_closed_or_real_account_never_sends(tmp_path):
    now = datetime.now(timezone.utc)
    api, clock, bars = _api(now)
    old_clock = clock.replace(year=clock.year - 1)
    stale = scan_and_submit_demo(api, CONFIG, tmp_path / "demo.sqlite3", execute=True,
                                 kill_switch_off=True, now=old_clock)
    assert not stale.sent and not api.sends
    assert stale.reason == "last completed M5 candle is stale or not yet closed"
    api.account = Account(trade_mode=2)
    refused = scan_and_submit_demo(api, CONFIG, tmp_path / "demo.sqlite3", execute=True,
                                   kill_switch_off=True, now=clock)
    assert not refused.sent and not api.sends


def test_last_based_or_missing_chart_mode_never_trades(tmp_path):
    api, clock, bars = _api(datetime.now(timezone.utc))
    api.symbol.chart_mode = 1
    result = scan_and_submit_demo(api, CONFIG, tmp_path / "demo.sqlite3",
                                  execute=True, kill_switch_off=True, now=clock)
    assert not result.sent and not api.sends


def test_missing_completed_candles_and_failed_shutdown_never_send(monkeypatch, tmp_path):
    api, clock, bars = _api(datetime.now(timezone.utc))
    api.copy_rates_from_pos = lambda *args: None
    missing = scan_and_submit_demo(api, CONFIG, tmp_path / "demo.sqlite3", now=clock)
    assert missing.reason == "80 completed M5 bars unavailable"
    api, clock, bars = _api(datetime.now(timezone.utc))
    monkeypatch.setattr(mt5_demo_auto, "detect_breakout_retest",
                        lambda *args, **kwargs: (_signal(bars),))

    def broken_shutdown():
        raise RuntimeError("terminal failure")

    api.shutdown = broken_shutdown
    result = scan_and_submit_demo(api, CONFIG, tmp_path / "demo.sqlite3",
                                  execute=True, kill_switch_off=True, now=clock)
    assert result.reason == "automatic DEMO session shutdown failed"
    assert not result.sent and not api.sends


def test_failed_shutdown_overrides_an_early_no_bar_result(tmp_path):
    api, clock, _ = _api(datetime.now(timezone.utc))
    api.copy_rates_from_pos = lambda *args: None
    api.shutdown = lambda: (_ for _ in ()).throw(RuntimeError("terminal failure"))
    result = scan_and_submit_demo(api, CONFIG, tmp_path / "demo.sqlite3", now=clock)
    assert result.reason == "automatic DEMO session shutdown failed"
    assert not result.sent and not result.signal_detected and not api.sends


def test_shifted_m5_bars_use_explicit_utc_mapping_and_broker_quote(monkeypatch, tmp_path):
    api, clock, bars = _api(datetime.now(timezone.utc))
    api.copy_rates_from_pos = lambda *args: [dict(row, time=row["time"] + 10800) for row in bars]
    api.tick_ms += 10_800_000
    config = replace(CONFIG, server_utc_offset_seconds=10800)

    def current_signal(rows, *_args, **_kwargs):
        assert rows[-1].timestamp == datetime.fromtimestamp(bars[-1]["time"], timezone.utc)
        return (SimpleNamespace(direction=Direction.BUY, signal_time=rows[-1].timestamp,
                                breakout_time=rows[-2].timestamp, entry_price=4000.0,
                                sl_price=3998.0, tp1=4002.0),)

    monkeypatch.setattr(mt5_demo_auto, "detect_breakout_retest", current_signal)
    ledger = tmp_path / "demo.sqlite3"
    assert not scan_and_submit_demo(api, CONFIG, ledger, now=clock).signal_detected
    dry = scan_and_submit_demo(api, config, ledger, now=clock)
    assert dry.signal_detected and not dry.sent and not ledger.exists()
    sent = scan_and_submit_demo(api, config, ledger, execute=True,
                                kill_switch_off=True, now=clock)
    assert sent.accepted and sent.signal_id == dry.signal_id and len(api.sends) == 1


def test_real_last_bar_retest_reaches_fake_fok_demo_transport_on_shifted_feed(tmp_path):
    api, clock, bars = _api(datetime.now(timezone.utc))
    bars[-2].update(open=4000.0, high=4002.0, low=3999.9,
                    close=4001.8, tick_volume=200)
    bars[-1].update(open=4001.0, high=4001.7, low=4000.5,
                    close=4001.5, tick_volume=100)
    api.copy_rates_from_pos = lambda *args: [dict(row, time=row["time"] + 10800) for row in bars]
    api.tick_ms += 10_800_000
    api.symbol.filling_mode = 1
    config = replace(CONFIG, server_utc_offset_seconds=10800)
    original_tick = api.symbol_info_tick

    def matching_tick(symbol):
        tick = original_tick(symbol)
        tick.bid, tick.ask = 4001.5, 4001.6
        return tick

    def broker_check(request):
        assert request["sl"] == 4000.0 and request["tp"] == 4003.75
        assert request["type_filling"] == api.ORDER_FILLING_FOK
        return SimpleNamespace(retcode=0)

    api.symbol_info_tick = matching_tick
    api.order_check = broker_check
    ledger = tmp_path / "demo.sqlite3"
    dry = scan_and_submit_demo(api, config, ledger, now=clock)
    assert dry.signal_detected and not dry.sent and not ledger.exists()
    submitted = scan_and_submit_demo(api, config, ledger, execute=True,
                                     kill_switch_off=True, now=clock)
    assert submitted.accepted and submitted.signal_id == dry.signal_id
    assert len(api.sends) == 1 and api.sends[0]["price"] == 4001.6


def test_shifted_m5_bars_with_unshifted_quote_never_send(monkeypatch, tmp_path):
    api, clock, bars = _api(datetime.now(timezone.utc))
    api.copy_rates_from_pos = lambda *args: [dict(row, time=row["time"] + 10800) for row in bars]
    config = replace(CONFIG, server_utc_offset_seconds=10800)
    monkeypatch.setattr(mt5_demo_auto, "detect_breakout_retest", lambda rows, *args, **kwargs: (
        SimpleNamespace(direction=Direction.BUY, signal_time=rows[-1].timestamp,
                        breakout_time=rows[-2].timestamp, entry_price=4000.0,
                        sl_price=3998.0, tp1=4002.0),))
    result = scan_and_submit_demo(api, config, tmp_path / "demo.sqlite3",
                                  execute=True, kill_switch_off=True, now=clock)
    assert result.signal_detected and not result.sent and not api.sends


def test_only_last_completed_bar_can_generate_demo_order(monkeypatch, tmp_path):
    api, clock, bars = _api(datetime.now(timezone.utc))
    strategy = _signal(bars)
    monkeypatch.setattr(mt5_demo_auto, "detect_breakout_retest", lambda rows, pip, config, **kwargs: (
        (strategy,) if kwargs["min_signal_index"] == 79 and pip == 0.1 else ()))
    ledger = tmp_path / "demo.sqlite3"
    dry = scan_and_submit_demo(api, CONFIG, ledger, now=clock)
    assert dry.signal_detected and not dry.sent and not ledger.exists()
    done = scan_and_submit_demo(api, CONFIG, ledger, execute=True, kill_switch_off=True, now=clock)
    assert done.accepted and done.signal_id == dry.signal_id and len(api.sends) == 1
    import sqlite3
    with sqlite3.connect(ledger) as db:
        assert db.execute("SELECT source_kind FROM attempts").fetchone() == ("strategy_experiment",)
    assert api.sends[0]["price"] == 4000.1
    replay = scan_and_submit_demo(api, CONFIG, ledger, execute=True, kill_switch_off=True, now=clock)
    assert not replay.sent and len(api.sends) == 1


def test_buy_signal_compares_bid_candle_and_pays_ask(monkeypatch, tmp_path):
    api, clock, bars = _api(datetime.now(timezone.utc))
    monkeypatch.setattr(mt5_demo_auto, "detect_breakout_retest",
                        lambda *args, **kwargs: (_signal(bars),))
    original_tick = api.symbol_info_tick

    def spread_tick(symbol):
        tick = original_tick(symbol)
        tick.ask = 4000.18
        return tick

    api.symbol_info_tick = spread_tick
    done = scan_and_submit_demo(api, CONFIG, tmp_path / "demo.sqlite3",
                                execute=True, kill_switch_off=True, now=clock)
    assert done.accepted and api.sends[0]["price"] == 4000.18


def test_old_signal_gap_changed_price_and_active_kill_switch_block(monkeypatch, tmp_path):
    api, clock, bars = _api(datetime.now(timezone.utc))
    signal = _signal(bars)
    monkeypatch.setattr(mt5_demo_auto, "detect_breakout_retest", lambda *args, **kwargs: (signal,))
    api.copy_rates_from_pos = lambda *args: bars[:-2] + [dict(bars[-2], time=bars[-2]["time"] - 600)] + bars[-1:]
    assert not scan_and_submit_demo(api, CONFIG, tmp_path / "demo.sqlite3",
                                    execute=True, kill_switch_off=True, now=clock).sent
    api, clock, bars = _api(datetime.now(timezone.utc))
    signal = _signal(bars)
    assert not scan_and_submit_demo(api, CONFIG, tmp_path / "demo.sqlite3",
                                    execute=True, kill_switch_off=False, now=clock).sent
    signal.entry_price = 3999.0
    assert not scan_and_submit_demo(api, CONFIG, tmp_path / "demo.sqlite3",
                                    execute=True, kill_switch_off=True, now=clock).sent
    assert not api.sends


def test_gap_inside_complete_strategy_lookback_blocks_even_when_latest_33_are_clean(
        monkeypatch, tmp_path):
    api, clock, bars = _api(datetime.now(timezone.utc))
    assert mt5_demo_auto.CONTEXT_BARS == 39
    # A gap just before the latest 35 bars used to pass the 33-bar check.
    for row in bars[:-35]:
        row["time"] -= 300
    monkeypatch.setattr(mt5_demo_auto, "detect_breakout_retest",
                        lambda *a, **k: (_signal(bars),))
    result = scan_and_submit_demo(api, CONFIG, tmp_path / "demo.sqlite3",
                                  execute=True, kill_switch_off=True, now=clock)
    assert result.reason == "M5 context has a session gap"
    assert not result.signal_detected and not result.sent and not api.sends


def test_gap_older_than_complete_strategy_lookback_does_not_block_current_signal(
        monkeypatch, tmp_path):
    api, clock, bars = _api(datetime.now(timezone.utc))
    for row in bars[:-mt5_demo_auto.CONTEXT_BARS]:
        row["time"] -= 300
    monkeypatch.setattr(mt5_demo_auto, "detect_breakout_retest",
                        lambda *a, **k: (_signal(bars),))
    result = scan_and_submit_demo(api, CONFIG, tmp_path / "demo.sqlite3", now=clock)
    assert result.signal_detected and not result.sent
    assert not api.sends


def test_local_stop_file_prevents_auto_submission(monkeypatch, tmp_path):
    api, clock, bars = _api(datetime.now(timezone.utc))
    monkeypatch.setattr(mt5_demo_auto, "detect_breakout_retest",
                        lambda *args, **kwargs: (_signal(bars),))
    (tmp_path / "demo.stop").write_text("stop", encoding="utf-8")
    result = scan_and_submit_demo(api, CONFIG, tmp_path / "demo.sqlite3",
                                  execute=True, kill_switch_off=True, now=clock)
    assert result.signal_detected and not result.sent and not api.sends


def test_dangling_stop_marker_prevents_auto_submission(monkeypatch, tmp_path):
    api, clock, bars = _api(datetime.now(timezone.utc))
    monkeypatch.setattr(mt5_demo_auto, "detect_breakout_retest",
                        lambda *args, **kwargs: (_signal(bars),))
    marker = tmp_path / "demo.stop"
    try:
        marker.symlink_to(tmp_path / "missing-stop-target")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    result = scan_and_submit_demo(api, CONFIG, tmp_path / "demo.sqlite3",
                                  execute=True, kill_switch_off=True, now=clock)
    assert result.reason == "automatic DEMO stop file active"
    assert result.signal_detected and not result.sent and not api.sends


def test_unreadable_stop_marker_prevents_auto_submission(monkeypatch, tmp_path):
    api, clock, bars = _api(datetime.now(timezone.utc))
    monkeypatch.setattr(mt5_demo_auto, "detect_breakout_retest",
                        lambda *args, **kwargs: (_signal(bars),))
    ledger = tmp_path / "demo.sqlite3"
    original_lstat = Path.lstat

    def unreadable_stop(path):
        if path == ledger.with_suffix(".stop"):
            raise PermissionError("private filesystem details")
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", unreadable_stop)
    result = scan_and_submit_demo(api, CONFIG, ledger,
                                  execute=True, kill_switch_off=True, now=clock)
    assert result.reason == "automatic DEMO stop file active"
    assert result.signal_detected and not result.sent and not api.sends
    assert "private" not in str(result)


def test_cli_never_enables_automation_without_both_opt_ins(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("SHREEK_DEMO_LOGIN", "123456")
    monkeypatch.setenv("SHREEK_DEMO_TERMINAL_PATH", CONFIG.terminal_path)
    monkeypatch.setenv("SHREEK_DEMO_SERVER", CONFIG.expected_server)
    monkeypatch.setenv("SHREEK_DEMO_SYMBOL", CONFIG.symbol)
    monkeypatch.delenv("SHREEK_DEMO_AUTO_ACK", raising=False)
    monkeypatch.setenv("SHREEK_DEMO_KILL_SWITCH", "OFF")
    api, clock, bars = _api(datetime.now(timezone.utc))
    monkeypatch.setattr(mt5_demo_auto, "detect_breakout_retest", lambda *args, **kwargs: (_signal(bars),))
    monkeypatch.setattr(mt5_demo_auto_cli, "demo_only_mt5_runtime", lambda: api)
    args = ["--ledger", str(Path(tmp_path) / "demo.sqlite3")]
    assert mt5_demo_auto_cli.main(args) == 2
    assert mt5_demo_auto_cli.main(["--execute-demo-auto"] + args) == 2
    assert not api.sends
    assert "123456" not in capsys.readouterr().out
