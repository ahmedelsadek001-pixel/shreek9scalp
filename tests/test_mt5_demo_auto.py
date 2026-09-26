from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

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
    api.account = Account(trade_mode=2)
    refused = scan_and_submit_demo(api, CONFIG, tmp_path / "demo.sqlite3", execute=True,
                                   kill_switch_off=True, now=clock)
    assert not refused.sent and not api.sends


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


def test_local_stop_file_prevents_auto_submission(monkeypatch, tmp_path):
    api, clock, bars = _api(datetime.now(timezone.utc))
    monkeypatch.setattr(mt5_demo_auto, "detect_breakout_retest",
                        lambda *args, **kwargs: (_signal(bars),))
    (tmp_path / "demo.stop").write_text("stop", encoding="utf-8")
    result = scan_and_submit_demo(api, CONFIG, tmp_path / "demo.sqlite3",
                                  execute=True, kill_switch_off=True, now=clock)
    assert result.signal_detected and not result.sent and not api.sends


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
