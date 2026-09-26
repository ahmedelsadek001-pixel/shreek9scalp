from __future__ import annotations
import os
from dataclasses import dataclass

def _bool(name:str,default:bool)->bool:
    raw=os.getenv(name)
    return default if raw is None else raw.strip().lower() in {"1","true","yes","on"}

@dataclass(frozen=True)
class RuntimeConfig:
    environment:str=os.getenv("SHREEK_ENV","production")
    scanner_enabled:bool=_bool("SCANNER_ENABLED",True)
    scanner_interval_seconds:float=float(os.getenv("SCANNER_INTERVAL_SECONDS","5"))
    symbols:tuple[str,...]=tuple(s.strip().upper() for s in os.getenv("SCANNER_SYMBOLS","XAUUSD").split(",") if s.strip())
    closed_bars_only:bool=_bool("CLOSED_BARS_ONLY",True)
    notify_only_new_signals:bool=_bool("NOTIFY_ONLY_NEW_SIGNALS",True)
    telegram_notify_chat_id:str|None=os.getenv("TELEGRAM_NOTIFY_CHAT_ID") or None
    allow_unauthenticated_dev:bool=_bool("ALLOW_UNAUTHENTICATED_DEV",False)
    max_scanner_errors_before_backoff:int=int(os.getenv("MAX_SCANNER_ERRORS_BEFORE_BACKOFF","3"))
    scanner_backoff_seconds:float=float(os.getenv("SCANNER_BACKOFF_SECONDS","30"))
    @property
    def is_production(self)->bool:return self.environment.lower()=="production"
RUNTIME=RuntimeConfig()
