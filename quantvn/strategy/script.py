"""Check a strategy file against the rules of the place where QuantVN runs it, without running it.

Uploaded strategies run in a sandbox: no network, no secrets, a few seconds of CPU, and a fresh process for
every bar, so top-level code runs on every bar and nothing is remembered between two calls. `validate_script`
reads the source and reports what will not work there. `load_script` loads a file the way the sandbox does,
so the same file can be passed to `quantvn.strategy.check`.
"""
from __future__ import annotations

import ast
import os
from dataclasses import dataclass, field
from typing import Callable, List

# Modules that need a network, a database or another process: none of them can do anything in the sandbox.
_NETWORK = {"requests", "urllib", "urllib3", "http", "httpx", "aiohttp", "socket", "websocket", "websockets",
            "yfinance", "vnstock", "ftplib", "smtplib", "boto3", "botocore", "psycopg2", "pymongo", "redis",
            "sqlalchemy", "telegram"}
_PROCESS = {"subprocess", "multiprocessing", "threading", "concurrent"}
_SDK_DATA = {"get_hist", "get_stock_hist", "get_derivatives_hist", "get_crypto_hist", "get_us_hist"}
_SDK_LIVE = {"list_liquid_asset", "Macro", "Quote", "Trading", "Finance", "Company", "Fund", "Listing", "WorldIndex"}


@dataclass
class ScriptReport:
    """``errors``: the file will fail in the sandbox. ``warnings``: it runs, but not the way it may seem."""
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        head = "script: " + ("OK" if self.ok else "NOT OK")
        return "\n".join([head] + [f"  ERROR   {e}" for e in self.errors] + [f"  warning {w}" for w in self.warnings])

    def __repr__(self) -> str:
        return self.summary()


def _source(path_or_source: str) -> str:
    if "\n" not in path_or_source and os.path.exists(path_or_source):
        with open(path_or_source, encoding="utf-8") as f:
            return f.read()
    return path_or_source


def _name(node) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def validate_script(path_or_source: str) -> ScriptReport:
    """Static check of a strategy file (a path, or the source text itself)."""
    rep = ScriptReport()
    try:
        tree = ast.parse(_source(path_or_source))
    except SyntaxError as e:
        rep.errors.append(f"syntax error on line {e.lineno}: {e.msg}")
        return rep

    fn = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "gen_position"), None)
    if fn is None:
        rep.errors.append("no top-level function gen_position(df)")
    else:
        required = len(fn.args.args) - len(fn.args.defaults)
        if required != 1:
            rep.errors.append(f"gen_position is called with one argument (the candles); it requires {required}")

    in_function = set()
    for f in ast.walk(tree):
        if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            for n in ast.walk(f):
                in_function.add(id(n))

    imported = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            imported |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            imported.add(n.module.split(".")[0])
    net = sorted(imported & _NETWORK)
    if net:
        rep.errors.append(f"imports {', '.join(net)}: there is no network in the sandbox, every call will fail. "
                          "Use the candles passed to gen_position")
    proc = sorted(imported & _PROCESS)
    if proc:
        rep.warnings.append(f"imports {', '.join(proc)}: a call may start at most a few processes and all of them "
                            "are killed when it returns")

    top_calls, live_calls, data_calls, waits = [], set(), set(), set()
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        name = _name(n.func)
        short = name.rsplit(".", 1)[-1]
        if short in ("input", "getpass"):
            waits.add(short)
        if short in _SDK_LIVE:
            live_calls.add(short)
        if short in _SDK_DATA:
            data_calls.add(short)
        if id(n) not in in_function and short not in ("client", "filterwarnings", "load_dotenv", "getenv", "print"):
            if isinstance(n.func, (ast.Name, ast.Attribute)) and short[:1].islower() and short not in ("Timestamp",):
                top_calls.append(short)
    if waits:
        rep.errors.append(f"calls {', '.join(sorted(waits))}(): nobody can type an answer in the sandbox")
    if live_calls:
        rep.errors.append(f"uses {', '.join(sorted(live_calls))} from the SDK: these fetch live data over the network, "
                          "which the sandbox does not have")
    if data_calls:
        rep.warnings.append(f"calls {', '.join(sorted(data_calls))}: in the sandbox these return the same candles "
                            "gen_position receives (previous day and today of the strategy's own instrument), and an "
                            "empty frame for any other symbol. Use the df argument instead")
    heavy = sorted(set(top_calls) - {"time", "Timedelta", "to_datetime", "set_option", "seterr", "simplefilter",
                                     "basicConfig", "getLogger", "dataclass", "namedtuple", "compile"})
    if heavy:
        rep.warnings.append(f"top-level code calls {', '.join(heavy[:6])}: everything outside functions runs again on "
                            "every bar. Keep backtests and plots under  if __name__ == '__main__':")
    return rep


def load_script(path: str) -> Callable:
    """Load a strategy file as the sandbox does and return its gen_position.

    The file is executed with ``__name__ == "extracted_function"``, so a block under
    ``if __name__ == "__main__":`` does not run. Unlike the sandbox, this runs on your machine with your
    network and your files: only load code you trust.
    """
    with open(path, encoding="utf-8") as f:
        source = f.read()
    scope = {"__name__": "extracted_function", "__file__": path}
    exec(compile(source, path, "exec"), scope)
    fn = scope.get("gen_position")
    if not callable(fn):
        raise ValueError(f"{path} defines no gen_position function")
    return fn
