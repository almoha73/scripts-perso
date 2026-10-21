#!/usr/bin/env python3
import base64
import json
import os
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tkinter import font as tkfont, ttk
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BG = "#0f1419"
CARD = "#171f27"
CARD2 = "#1c2630"
ROW_ALT = "#151d25"
TEXT = "#e6edf3"
MUTED = "#8b98a5"
ACCENT = "#4cc2ff"
GEMINI_BLUE = "#7aa2f7"
CLAUDE_CORAL = "#e09f67"
GREEN = "#3ddc84"
ORANGE = "#f5a623"
RED = "#ff5c5c"
TRACK = "#0b0f13"

FONT = "DejaVu Sans"
REFRESH_MS = 60000
API_BASE = "https://opencode.ai/console/api"
CONSOLE_URL = "https://opencode.ai/console"
AUTH_PATH = Path.home() / ".local/share/opencode/auth.json"

AGY_BIN_PATHS = [
    Path.home() / ".local/bin/agy",
    Path.home() / ".local/bin/antigravity",
    Path("/usr/local/bin/agy"),
    Path("/usr/bin/agy"),
]
AGY_TOKEN_PATHS = [
    Path.home() / ".gemini/antigravity-cli/antigravity-oauth-token",
    Path.home() / ".gemini/jetski-standalone-oauth-token",
]
AGY_BRAIN_DIRS = [
    Path.home() / ".gemini/antigravity-cli/brain",
    Path.home() / ".gemini/antigravity/brain",
]

def _load_agy_credentials() -> tuple[str, str]:
    client_id = os.environ.get("AGY_CLIENT_ID", "")
    client_secret = os.environ.get("AGY_CLIENT_SECRET", "")
    if not (client_id and client_secret):
        path = Path(__file__).resolve().parent / "credentials.json"
        try:
            data = json.loads(path.read_text())
            client_id = client_id or data.get("client_id", "")
            client_secret = client_secret or data.get("client_secret", "")
        except (OSError, ValueError):
            pass
    return client_id, client_secret


AGY_CLIENT_ID, AGY_CLIENT_SECRET = _load_agy_credentials()
AGY_API_BASES = [
    "https://daily-cloudcode-pa.googleapis.com",
    "https://cloudcode-pa.googleapis.com",
]

MONTHS = [
    "janv.", "févr.", "mars", "avr.", "mai", "juin",
    "juil.", "août", "sept.", "oct.", "nov.", "déc.",
]

GO_LIMITS = {
    "glm-5.3-flash": 60,
    "glm-5.3": 15,
    "glm-5.2": 60,
    "kimi-k3": 15,
    "kimi-k2.7-code": 60,
    "longcat-2.0": 60,
    "longcat-2.5-preview-free": None,
    "step-5-preview": 60,
    "beam-free": None,
    "mimo-v2.6-flash": 60,
    "mimo-v2.6-pro": 15,
    "mimo-v2.5": 60,
    "mimo-v2.5-pro": 15,
    "minimax-m3.1-flash-free": None,
    "minimax-m3": 60,
    "muse-spark-1.3-contributor": 60,
    "muse-spark-1.2-contributor": 60,
    "qwen3.8-max": 15,
    "qwen3.8-flash": 30,
    "qwen3.7-plus": 60,
    "deepseek-v4.1-flash": 80,
    "deepseek-v4-pro": 15,
    "hy4-preview": 30,
    "hy3": 60,
    "grok-4.7": 15,
    "gpt-6-luna": 15,
    "gpt-5.6-luna": 15,
    "claude-haiku-5-5": 15,
    "gemini-4-argon-contributor": 60,
}

GO_PLUS_LIMITS = {
    "glm-5.3-flash": 180,
    "glm-5.3": 120,
    "glm-5.2": 180,
    "kimi-k3": 60,
    "kimi-k2.7-code": 180,
    "longcat-2.0": 240,
    "longcat-2.5-preview-free": None,
    "step-5-preview": 240,
    "beam-free": None,
    "mimo-v2.6-flash": 120,
    "mimo-v2.6-pro": 60,
    "mimo-v2.5": 120,
    "mimo-v2.5-pro": 60,
    "minimax-m3.1-flash-free": None,
    "minimax-m3": 180,
    "muse-spark-1.3-contributor": 120,
    "muse-spark-1.2-contributor": 120,
    "qwen3.8-max": 60,
    "qwen3.8-flash": 90,
    "qwen3.7-plus": 180,
    "deepseek-v4.1-flash": 160,
    "deepseek-v4-pro": 60,
    "hy4-preview": 120,
    "hy3": 240,
    "grok-4.7": 60,
    "gpt-6-luna": 60,
    "gpt-5.6-luna": 60,
    "claude-haiku-5-5": 60,
    "gemini-4-argon-contributor": 240,
}

MODEL_CHANGE_RE = re.compile(
    r"The user has changed setting `Model Selection` from [A-Za-z0-9 ()._-]+? to ([A-Za-z0-9 ()._-]+)\."
)


class MonitorError(Exception):
    pass


def fr(value, digits=1):
    return f"{value:.{digits}f}".replace(".", ",")


def fr_int(value):
    return f"{int(value):,}".replace(",", " ")


def format_dollars(microcents, digits=2):
    return "$" + fr(int(microcents) / 100000000, digits)


def format_tokens(value):
    value = int(value)
    if value >= 1000000000:
        return fr(value / 1000000000, 2) + " Md"
    if value >= 1000000:
        return fr(value / 1000000, 1) + " M"
    if value >= 1000:
        return fr(value / 1000, 1) + " k"
    return str(value)


def usage_color(fraction):
    if fraction >= 0.85:
        return RED
    if fraction >= 0.60:
        return ORANGE
    return GREEN


def parse_time(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def format_date(value):
    moment = parse_time(value)
    if moment is None:
        return "—"
    local = moment.astimezone()
    return f"{local.day} {MONTHS[local.month - 1]} {local.year}"


def countdown(value):
    moment = parse_time(value)
    if moment is None:
        return ""
    seconds = int((moment - datetime.now(timezone.utc)).total_seconds())
    if seconds <= 0:
        return "imminent"
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        return f"{days} j {hours} h"
    if hours:
        return f"{hours} h {minutes:02d} min"
    return f"{minutes} min"


def pretty_model(model_id):
    special = {
        "gpt": "GPT",
        "glm": "GLM",
        "mimo": "MiMo",
        "kimi": "Kimi",
        "qwen": "Qwen",
        "hy": "Hy",
        "longcat": "LongCat",
        "minimax": "MiniMax",
        "muse": "Muse",
        "deepseek": "DeepSeek",
        "claude": "Claude",
        "gemini": "Gemini",
        "grok": "Grok",
        "step": "Step",
        "beam": "Beam",
    }
    parts = model_id.split("-")
    rendered = []
    for part in parts:
        if part in special:
            rendered.append(special[part])
        elif part and part[0].isdigit():
            rendered.append(part)
        else:
            rendered.append(part.capitalize())
    return " ".join(rendered)


def normalize_gemini_label(label):
    if not label:
        return "Gemini 4 Argon"
    cleaned = re.sub(
        r"\s*\((Low|Medium|High|Max|XHigh|Thinking)\)\s*$",
        "",
        label.strip(),
        flags=re.IGNORECASE,
    )
    return cleaned or label.strip()


def decode_jwt_payload(jwt_token):
    if not jwt_token or "." not in jwt_token:
        return {}
    try:
        parts = jwt_token.split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1]
        payload += "=" * (-len(payload) % 4)
        raw = base64.urlsafe_b64decode(payload.encode("ascii"))
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}


def read_api_key():
    env_key = os.environ.get("OPENCODE_GO_API_KEY") or os.environ.get(
        "OPENCODE_CONSOLE_TOKEN"
    )
    if env_key:
        return env_key.strip()
    try:
        with open(AUTH_PATH, encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError:
        raise MonitorError(
            f"Clé introuvable : {AUTH_PATH} n'existe pas."
        )
    except ValueError:
        raise MonitorError(f"Fichier de clés illisible : {AUTH_PATH}")
    entry = data.get("opencode-go") or {}
    key = entry.get("key")
    if not key:
        raise MonitorError(
            "Aucune clé OpenCode Go dans auth.json. Lance opencode puis /connect."
        )
    return key


def load_agy_auth():
    for path in AGY_TOKEN_PATHS:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        token_obj = data.get("token") or {}
        access_token = token_obj.get("access_token")
        refresh_token = token_obj.get("refresh_token")
        expiry_str = token_obj.get("expiry")
        id_claims = decode_jwt_payload(data.get("id_token"))
        email = id_claims.get("email") or ""

        expired = False
        expiry_dt = parse_time(expiry_str)
        if expiry_dt is not None:
            if (expiry_dt - datetime.now(timezone.utc)).total_seconds() < 60:
                expired = True

        if (not access_token or expired) and refresh_token:
            try:
                body = urlencode({
                    "client_id": id_claims.get("azp") or AGY_CLIENT_ID,
                    "client_secret": AGY_CLIENT_SECRET,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                }).encode("utf-8")
                req = Request(
                    "https://oauth2.googleapis.com/token",
                    data=body,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    method="POST",
                )
                with urlopen(req, timeout=10) as resp:
                    refreshed = json.load(resp)
                if refreshed.get("access_token"):
                    access_token = refreshed["access_token"]
                    expires_in = int(refreshed.get("expires_in", 3600))
                    new_expiry = (
                        datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                    ).isoformat()
                    token_obj["access_token"] = access_token
                    token_obj["expiry"] = new_expiry
                    data["token"] = token_obj
                    try:
                        path.write_text(json.dumps(data), encoding="utf-8")
                    except OSError:
                        pass
            except Exception:
                pass

        if access_token:
            return {"access_token": access_token, "email": email}
    return None


def agy_post(access_token, endpoint, payload):
    raw_body = json.dumps(payload).encode("utf-8")
    last_error = None
    for base in AGY_API_BASES:
        url = f"{base}/v1internal:{endpoint}"
        req = Request(
            url,
            data=raw_body,
            headers={
                "Authorization": "Bearer " + access_token,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "antigravity/1.4.4 linux/amd64",
            },
            method="POST",
        )
        try:
            with urlopen(req, timeout=12) as resp:
                return json.load(resp)
        except Exception as err:
            last_error = err
    if last_error:
        raise last_error
    return {}


def scan_local_gemini_transcripts():
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    by_model = {}
    totals = {
        "requests": 0,
        "input": 0,
        "output": 0,
        "cache": 0,
        "conversations": 0,
        "gemini_requests": 0,
        "gemini_input": 0,
        "gemini_output": 0,
        "gemini_cache": 0,
        "claude_requests": 0,
        "claude_input": 0,
        "claude_output": 0,
        "claude_cache": 0,
    }
    seen_transcripts = set()

    for brain_dir in AGY_BRAIN_DIRS:
        if not brain_dir.is_dir():
            continue
        for conv_dir in brain_dir.iterdir():
            if not conv_dir.is_dir():
                continue
            transcript = conv_dir / ".system_generated/logs/transcript.jsonl"
            if not transcript.is_file():
                continue
            real = str(transcript.resolve())
            if real in seen_transcripts:
                continue
            seen_transcripts.add(real)

            current_model = "Gemini 4 Argon"
            conv_counted = False
            try:
                with open(transcript, encoding="utf-8", errors="replace") as handle:
                    for line in handle:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            step = json.loads(line)
                        except ValueError:
                            continue
                        content = step.get("content") or ""
                        if step.get("type") == "USER_INPUT" and "Model Selection" in content:
                            match = MODEL_CHANGE_RE.search(content)
                            if match:
                                current_model = normalize_gemini_label(match.group(1))
                        if step.get("type") != "PLANNER_RESPONSE":
                            continue
                        created = parse_time(step.get("created_at"))
                        if created is not None and created < cutoff:
                            continue
                        inp = int(step.get("input_tokens", 0) or 0)
                        out = int(step.get("output_tokens", 0) or 0)
                        cache = int(step.get("cache_read_tokens", 0) or 0)
                        if inp == 0 and out == 0 and cache == 0:
                            continue
                        if not conv_counted:
                            totals["conversations"] += 1
                            conv_counted = True
                        totals["requests"] += 1
                        totals["input"] += inp
                        totals["output"] += out
                        totals["cache"] += cache

                        is_claude = "claude" in current_model.lower() or "gpt" in current_model.lower()
                        if is_claude:
                            totals["claude_requests"] += 1
                            totals["claude_input"] += inp
                            totals["claude_output"] += out
                            totals["claude_cache"] += cache
                        else:
                            totals["gemini_requests"] += 1
                            totals["gemini_input"] += inp
                            totals["gemini_output"] += out
                            totals["gemini_cache"] += cache

                        entry = by_model.setdefault(
                            current_model,
                            {
                                "name": current_model,
                                "requests": 0,
                                "input": 0,
                                "output": 0,
                                "cache": 0,
                            },
                        )
                        entry["requests"] += 1
                        entry["input"] += inp
                        entry["output"] += out
                        entry["cache"] += cache
            except OSError:
                continue

    return {"totals": totals, "by_model": by_model}


def _find_agy_bin():
    for candidate in AGY_BIN_PATHS:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _parse_bucket(bucket):
    if not isinstance(bucket, dict):
        return None
    rem = bucket.get("remaining_fraction")
    if rem is None:
        rem = bucket.get("remainingFraction")
    reset_time = bucket.get("reset_time") or bucket.get("resetTime") or ""
    if rem is not None:
        rem = float(rem)
    elif reset_time:
        rem = 0.0
    else:
        rem = 1.0
    rem = max(0.0, min(1.0, rem))
    return {
        "id": bucket.get("id") or bucket.get("bucketId") or "",
        "window": bucket.get("window") or "",
        "remaining_fraction": rem,
        "used_fraction": max(0.0, min(1.0, 1.0 - rem)),
        "reset_time": reset_time,
    }


def fetch_gemini_data():
    local = scan_local_gemini_transcripts()
    result = {
        "online": False,
        "email": "",
        "tier": "Google AI Ultra",
        "gemini_5h": None,
        "gemini_weekly": None,
        "claude_5h": None,
        "claude_weekly": None,
        "local": local,
    }

    auth = load_agy_auth()
    if auth:
        result["email"] = auth.get("email") or ""
        token = auth["access_token"]
        try:
            assist = agy_post(token, "loadCodeAssist", {})
            tier_obj = (
                assist.get("paidTier")
                or assist.get("g1Tier")
                or assist.get("currentTier")
                or {}
            )
            if isinstance(tier_obj, dict):
                tier_name = tier_obj.get("name") or tier_obj.get("id")
                if tier_name:
                    result["tier"] = tier_name
        except Exception:
            pass

    # 1. Primary method: call `agy -p /usage --output-format json` which returns
    #    both "Gemini Models" (5h + weekly) and "Claude and GPT models" (5h + weekly)
    agy_bin = _find_agy_bin()
    if agy_bin:
        try:
            proc = subprocess.run(
                [agy_bin, "-p", "/usage", "--output-format", "json"],
                capture_output=True,
                text=True,
                timeout=18,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                payload = json.loads(proc.stdout.strip())
                groups = (
                    (payload.get("command") or {})
                    .get("data", {})
                    .get("groups")
                    or []
                )
                for group in groups:
                    gname = (group.get("name") or group.get("displayName") or "").lower()
                    is_gemini = "gemini" in gname
                    is_claude = "claude" in gname or "gpt" in gname
                    for raw_bucket in group.get("buckets") or []:
                        parsed = _parse_bucket(raw_bucket)
                        if not parsed:
                            continue
                        bid = parsed["id"].lower()
                        win = parsed["window"].lower()
                        is_5h = win == "5h" or "5h" in bid
                        is_week = win == "weekly" or "week" in bid
                        if is_gemini or "gemini" in bid:
                            if is_5h:
                                result["gemini_5h"] = parsed
                            elif is_week:
                                result["gemini_weekly"] = parsed
                        elif is_claude or "3p" in bid:
                            if is_5h:
                                result["claude_5h"] = parsed
                            elif is_week:
                                result["claude_weekly"] = parsed
                if any(result[k] for k in ("gemini_5h", "gemini_weekly", "claude_5h", "claude_weekly")):
                    result["online"] = True
        except Exception:
            pass

    # 2. Fallback / supplement via direct Cloud Code API if any bucket is still missing
    if auth and not all(result[k] for k in ("gemini_5h", "claude_5h", "claude_weekly")):
        token = auth["access_token"]
        try:
            summary_resp = agy_post(token, "retrieveUserQuotaSummary", {})
            for group in summary_resp.get("groups") or []:
                gname = (group.get("displayName") or group.get("name") or "").lower()
                for raw_bucket in group.get("buckets") or []:
                    parsed = _parse_bucket(raw_bucket)
                    if not parsed:
                        continue
                    bid = parsed["id"].lower()
                    win = parsed["window"].lower()
                    if "gemini" in gname or "gemini" in bid:
                        if (win == "5h" or "5h" in bid) and not result["gemini_5h"]:
                            result["gemini_5h"] = parsed
                        elif (win == "weekly" or "week" in bid) and not result["gemini_weekly"]:
                            result["gemini_weekly"] = parsed
                    elif "claude" in gname or "3p" in bid:
                        if (win == "5h" or "5h" in bid) and not result["claude_5h"]:
                            result["claude_5h"] = parsed
                        elif (win == "weekly" or "week" in bid) and not result["claude_weekly"]:
                            result["claude_weekly"] = parsed
            result["online"] = True
        except Exception:
            pass

        try:
            quota_resp = agy_post(token, "retrieveUserQuota", {})
            for b in quota_resp.get("buckets") or []:
                mid = (b.get("modelId") or "").lower()
                parsed = _parse_bucket(b)
                if not parsed:
                    continue
                if "gemini" in mid and not result["gemini_5h"]:
                    result["gemini_5h"] = parsed
                elif "claude" in mid and not result["claude_5h"]:
                    result["claude_5h"] = parsed
            result["online"] = True
        except Exception:
            pass

    return result



CLAUDE_ORANGE = "#d97757"
CLAUDE_CREDENTIALS = Path.home() / ".claude/.credentials.json"
CLAUDE_PROJECTS_DIR = Path.home() / ".claude/projects"
CLAUDE_API = "https://api.anthropic.com/api/oauth"
CLAUDE_USAGE_URL = "https://claude.ai/settings/usage"

_claude_scan_cache = {}
_claude_profile_cache = {}


def pretty_claude_model(model_id):
    # claude-opus-5-5 -> Claude Opus 5.5 ; claude-sonnet-4-5-20250929 -> Claude Sonnet 4.5
    parts = [p for p in model_id.split("-") if not (p.isdigit() and len(p) >= 6)]
    words, digits = [], []
    for part in parts:
        if part.isdigit():
            digits.append(part)
        else:
            words.append(part.capitalize())
    name = " ".join(words)
    if digits:
        name += " " + ".".join(digits)
    return name


def scan_local_claude_transcripts():
    """Agrège les jetons des 30 derniers jours depuis les journaux de Claude Code."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    cutoff_ts = cutoff.timestamp()
    by_model = {}
    totals = {"requests": 0, "input": 0, "output": 0, "cache": 0, "sessions": 0}
    if not CLAUDE_PROJECTS_DIR.is_dir():
        return {"totals": totals, "by_model": by_model}

    for path in CLAUDE_PROJECTS_DIR.rglob("*.jsonl"):
        try:
            stat = path.stat()
        except OSError:
            continue
        if stat.st_mtime < cutoff_ts:
            continue
        key = str(path)
        cached = _claude_scan_cache.get(key)
        if cached and cached[0] == (stat.st_mtime, stat.st_size):
            messages = cached[1]
        else:
            messages = {}
            try:
                with open(path, encoding="utf-8", errors="replace") as handle:
                    for line in handle:
                        if '"usage"' not in line:
                            continue
                        try:
                            entry = json.loads(line)
                        except ValueError:
                            continue
                        message = entry.get("message") or {}
                        usage = message.get("usage")
                        model = message.get("model") or ""
                        if not usage or not model.startswith("claude"):
                            continue
                        msg_id = message.get("id") or entry.get("uuid")
                        messages[msg_id] = (
                            entry.get("timestamp"),
                            model,
                            int(usage.get("input_tokens", 0) or 0)
                            + int(usage.get("cache_creation_input_tokens", 0) or 0),
                            int(usage.get("output_tokens", 0) or 0),
                            int(usage.get("cache_read_input_tokens", 0) or 0),
                        )
            except OSError:
                continue
            _claude_scan_cache[key] = ((stat.st_mtime, stat.st_size), messages)

        counted = False
        for stamp, model, inp, out, cache in messages.values():
            created = parse_time(stamp)
            if created is not None and created < cutoff:
                continue
            if not counted and "subagents" not in path.parts:
                totals["sessions"] += 1
                counted = True
            totals["requests"] += 1
            totals["input"] += inp
            totals["output"] += out
            totals["cache"] += cache
            name = pretty_claude_model(model)
            item = by_model.setdefault(
                name, {"name": name, "requests": 0, "input": 0, "output": 0, "cache": 0}
            )
            item["requests"] += 1
            item["input"] += inp
            item["output"] += out
            item["cache"] += cache
    return {"totals": totals, "by_model": by_model}


def claude_get(token, endpoint):
    req = Request(
        f"{CLAUDE_API}/{endpoint}",
        headers={
            "Authorization": "Bearer " + token,
            "anthropic-beta": "oauth-2025-04-20",
            "Accept": "application/json",
            "User-Agent": "moniteur-ia/1.0",
        },
    )
    with urlopen(req, timeout=15) as resp:
        return json.load(resp)


def claude_limit_label(limit):
    kind = limit.get("kind") or ""
    scope = limit.get("scope") or {}
    model = (scope.get("model") or {}).get("display_name")
    if kind == "session":
        return "Session (5 h)"
    if kind == "weekly_all":
        return "Semaine · tous modèles"
    if kind == "weekly_scoped" and model:
        return f"Semaine · {model}"
    return kind.replace("_", " ").capitalize() or "Limite"


def fetch_claude_data():
    result = {
        "ok": False,
        "error": "",
        "plan": "Claude Max",
        "email": "",
        "limits": [],
        "local": scan_local_claude_transcripts(),
    }
    try:
        creds = json.loads(CLAUDE_CREDENTIALS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        result["error"] = "Claude : identifiants introuvables (connecte-toi dans Claude Code)."
        return result
    oauth = creds.get("claudeAiOauth") or {}
    tier = oauth.get("rateLimitTier") or ""
    match = re.search(r"max_(\d+x)", tier)
    if match:
        result["plan"] = f"Max {match.group(1)}"
    elif oauth.get("subscriptionType"):
        result["plan"] = oauth["subscriptionType"].capitalize()

    token = oauth.get("accessToken")
    expires_at = oauth.get("expiresAt")
    if not token:
        result["error"] = "Claude : aucun jeton, connecte-toi dans Claude Code."
        return result
    # On ne renouvelle pas le jeton nous-mêmes : Claude Code le fait à chaque lancement,
    # et un renouvellement ici invaliderait celui de la session en cours.
    if expires_at and expires_at / 1000 < time.time():
        result["error"] = "Claude : jeton expiré, ouvre Claude Code pour le renouveler."
        return result

    try:
        usage = claude_get(token, "usage")
    except Exception as err:
        text = str(err)
        if "401" in text or "403" in text:
            result["error"] = "Claude : jeton refusé, ouvre Claude Code pour le renouveler."
        else:
            result["error"] = "Claude : " + (text or "erreur inconnue")
        return result

    limits = []
    for raw in usage.get("limits") or []:
        limits.append({
            "label": claude_limit_label(raw),
            "used_fraction": max(0.0, min(1.0, float(raw.get("percent") or 0) / 100)),
            "reset_time": raw.get("resets_at") or "",
        })
    if not limits:
        for key, label in (("five_hour", "Session (5 h)"), ("seven_day", "Semaine · tous modèles"),
                           ("seven_day_opus", "Semaine · Opus"), ("seven_day_sonnet", "Semaine · Sonnet")):
            window = usage.get(key)
            if window:
                limits.append({
                    "label": label,
                    "used_fraction": max(0.0, min(1.0, float(window.get("utilization") or 0) / 100)),
                    "reset_time": window.get("resets_at") or "",
                })
    result["limits"] = limits
    result["ok"] = True

    if token not in _claude_profile_cache:
        try:
            profile = claude_get(token, "profile")
            _claude_profile_cache[token] = (profile.get("account") or {}).get("email") or ""
        except Exception:
            _claude_profile_cache[token] = ""
    result["email"] = _claude_profile_cache[token]
    return result


OPENROUTER_PURPLE = "#a78bfa"
OPENROUTER_API = "https://openrouter.ai/api/v1"
OPENROUTER_URL = "https://openrouter.ai/activity"
OPENROUTER_MGMT_KEY_PATH = Path.home() / ".config/moniteur-ia/openrouter-management.key"
OPENCODE_DB = Path.home() / ".local/share/opencode/opencode.db"


def pretty_openrouter_model(model_id):
    # deepseek/deepseek-v4.1-flash-1017 -> DeepSeek V4.1 Flash
    name = model_id.split("/", 1)[-1].split(":", 1)[0]
    name = re.sub(r"-\d{4,8}$", "", name)
    if name.startswith("claude"):
        return pretty_claude_model(name)
    return pretty_model(name)


def openrouter_get(key, endpoint):
    req = Request(
        f"{OPENROUTER_API}/{endpoint}",
        headers={
            "Authorization": "Bearer " + key,
            "Accept": "application/json",
            "User-Agent": "moniteur-ia/1.0",
        },
    )
    with urlopen(req, timeout=15) as resp:
        return json.load(resp)


def read_openrouter_keys():
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        try:
            data = json.loads(AUTH_PATH.read_text(encoding="utf-8"))
            api_key = (data.get("openrouter") or {}).get("key")
        except (OSError, ValueError):
            api_key = None
    mgmt_key = os.environ.get("OPENROUTER_MANAGEMENT_KEY")
    if not mgmt_key:
        try:
            mgmt_key = OPENROUTER_MGMT_KEY_PATH.read_text(encoding="utf-8").strip() or None
        except OSError:
            mgmt_key = None
    return api_key, mgmt_key


def scan_local_openrouter_usage():
    """Détail par modèle depuis la base d'opencode : uniquement cet ordinateur."""
    import sqlite3

    by_model = {}
    if not OPENCODE_DB.is_file():
        return by_model
    cutoff_ms = int((time.time() - 30 * 86400) * 1000)
    try:
        conn = sqlite3.connect(f"file:{OPENCODE_DB}?mode=ro", uri=True, timeout=5)
        try:
            rows = conn.execute(
                "SELECT data FROM message WHERE time_created >= ? "
                "AND data LIKE '%\"providerID\":\"openrouter\"%'",
                (cutoff_ms,),
            ).fetchall()
        finally:
            conn.close()
    except Exception:
        return by_model
    for (raw,) in rows:
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        if data.get("role") != "assistant" or data.get("providerID") != "openrouter":
            continue
        tokens = data.get("tokens") or {}
        name = pretty_openrouter_model(data.get("modelID") or "?")
        item = by_model.setdefault(
            name, {"name": name, "requests": 0, "input": 0, "output": 0, "cache": 0, "cost": 0.0}
        )
        item["requests"] += 1
        item["input"] += int(tokens.get("input", 0) or 0)
        item["output"] += int(tokens.get("output", 0) or 0) + int(tokens.get("reasoning", 0) or 0)
        item["cache"] += int((tokens.get("cache") or {}).get("read", 0) or 0)
        item["cost"] += float(data.get("cost") or 0)
    return by_model


def fetch_openrouter_activity(mgmt_key):
    """Détail par modèle pour tout le compte (30 derniers jours, clé de gestion requise)."""
    payload = openrouter_get(mgmt_key, "activity")
    by_model = {}
    for entry in payload.get("data") or []:
        name = pretty_openrouter_model(entry.get("model") or entry.get("model_permaslug") or "?")
        item = by_model.setdefault(
            name, {"name": name, "requests": 0, "input": 0, "output": 0, "cache": None, "cost": 0.0}
        )
        item["requests"] += int(entry.get("requests", 0) or 0)
        item["input"] += int(entry.get("prompt_tokens", 0) or 0)
        item["output"] += int(entry.get("completion_tokens", 0) or 0) + int(
            entry.get("reasoning_tokens", 0) or 0
        )
        item["cost"] += float(entry.get("usage", 0) or 0) + float(
            entry.get("byok_usage_inference", 0) or 0
        )
    return by_model


def fetch_openrouter_data():
    result = {
        "ok": False,
        "error": "",
        "credits": None,
        "key": None,
        "by_model": {},
        "scope": "",
    }
    api_key, mgmt_key = read_openrouter_keys()
    if not api_key and not mgmt_key:
        result["error"] = "OpenRouter : aucune clé (ni dans opencode, ni clé de gestion)."
        return result

    errors = []
    try:
        result["credits"] = openrouter_get(mgmt_key or api_key, "credits").get("data") or None
    except Exception as err:
        errors.append(f"crédits indisponibles ({err})")
    if api_key:
        try:
            result["key"] = openrouter_get(api_key, "key").get("data") or None
        except Exception as err:
            errors.append(f"clé opencode refusée ({err})")

    if mgmt_key:
        try:
            result["by_model"] = fetch_openrouter_activity(mgmt_key)
            result["scope"] = "tout le compte"
        except Exception as err:
            text = str(err)
            if "401" in text or "403" in text:
                errors.append("clé de gestion refusée, détail limité à cet ordinateur")
            else:
                errors.append(f"activité indisponible ({text}), détail limité à cet ordinateur")
    if not result["scope"]:
        result["by_model"] = scan_local_openrouter_usage()
        result["scope"] = "cet ordinateur"

    result["ok"] = result["credits"] is not None or result["key"] is not None
    if errors:
        result["error"] = "OpenRouter : " + " · ".join(errors)
    return result


def format_usd(value):
    value = float(value or 0)
    return "$" + fr(value, 2 if value == 0 or value >= 0.1 else 3)


def fit_text(font, text, max_width):
    """Coupe le texte avec une ellipse pour qu'il tienne dans max_width pixels."""
    if max_width <= 0:
        return ""
    if font.measure(text) <= max_width:
        return text
    while text and font.measure(text + "…") > max_width:
        text = text[:-1]
    return (text.rstrip() + "…") if text else ""


class UsageBar(tk.Canvas):
    """Barre sur trois lignes : titre + pourcentage, jauge, détail + reset.

    Les hauteurs viennent des métriques réelles des polices, et chaque texte est
    tronqué pour ne jamais empiéter sur son voisin.
    """

    BAR_HEIGHT = 8

    def __init__(self, master, title):
        self.title_font = tkfont.Font(family=FONT, size=9)
        self.value_font = tkfont.Font(family=FONT, size=9, weight="bold")
        self.small_font = tkfont.Font(family=FONT, size=8)
        self.line1 = max(self.title_font.metrics("linespace"), self.value_font.metrics("linespace"))
        self.line3 = self.small_font.metrics("linespace")
        height = self.line1 + 4 + self.BAR_HEIGHT + 4 + self.line3
        super().__init__(master, height=height, bg=CARD, highlightthickness=0, bd=0)
        self.title = title
        self.fraction = 0.0
        self.value = "—"
        self.detail = ""
        self.caption = ""
        self.color = MUTED
        self.bind("<Configure>", lambda _event: self.redraw())

    def set(self, fraction, value, color, detail="", caption="", title=None):
        if title is not None:
            self.title = title
        self.fraction = max(0.0, min(1.0, fraction))
        self.value = value
        self.color = color
        self.detail = detail
        self.caption = caption
        self.redraw()

    def rounded(self, x1, y1, x2, y2, color):
        radius = (y2 - y1) / 2
        if x2 - x1 < 2 * radius:
            x2 = x1 + 2 * radius
        self.create_oval(x1, y1, x1 + 2 * radius, y2, fill=color, outline=color)
        self.create_oval(x2 - 2 * radius, y1, x2, y2, fill=color, outline=color)
        self.create_rectangle(x1 + radius, y1, x2 - radius, y2, fill=color, outline=color)

    def redraw(self):
        self.delete("all")
        width = self.winfo_width()
        if width <= 2:
            return
        gap = 10

        value_w = self.value_font.measure(self.value)
        self.create_text(width, 0, text=self.value, anchor="ne",
                         fill=self.color if self.color != MUTED else MUTED, font=self.value_font)
        self.create_text(0, 0, text=fit_text(self.title_font, self.title, width - value_w - gap),
                         anchor="nw", fill=TEXT, font=self.title_font)

        top = self.line1 + 4
        self.rounded(0, top, width, top + self.BAR_HEIGHT, TRACK)
        fill_width = width * self.fraction
        if fill_width >= 1:
            self.rounded(0, top, max(fill_width, self.BAR_HEIGHT), top + self.BAR_HEIGHT, self.color)

        y3 = top + self.BAR_HEIGHT + 4
        caption_w = self.small_font.measure(self.caption) if self.caption else 0
        if self.caption:
            self.create_text(width, y3, text=self.caption, anchor="ne", fill=MUTED, font=self.small_font)
        if self.detail:
            self.create_text(0, y3, text=fit_text(self.small_font, self.detail, width - caption_w - gap),
                             anchor="nw", fill=MUTED, font=self.small_font)


class ProviderCard(tk.Frame):
    """Colonne d'un fournisseur : en-tête, grand pourcentage, barres, puis statistiques."""

    def __init__(self, master, name, accent, bar_count, stat_titles):
        super().__init__(master, bg=CARD)
        self.grid_columnconfigure(0, weight=1)
        pad = 16

        top = tk.Frame(self, bg=CARD)
        top.grid(row=0, column=0, sticky="ew", padx=pad, pady=(14, 0))
        top.grid_columnconfigure(0, weight=1)
        tk.Label(top, text=name, bg=CARD, fg=accent, font=(FONT, 9, "bold"),
                 anchor="w").grid(row=0, column=0, sticky="w")
        self.status = tk.Label(top, text="●  chargement", bg=CARD, fg=MUTED,
                               font=(FONT, 8), anchor="e")
        self.status.grid(row=0, column=1, sticky="e")

        head = tk.Frame(self, bg=CARD)
        head.grid(row=1, column=0, sticky="ew", padx=pad, pady=(2, 8))
        head.grid_columnconfigure(0, weight=1)
        self.big = tk.Label(head, text="—", bg=CARD, fg=MUTED, font=(FONT, 26, "bold"), anchor="w")
        self.big.grid(row=0, column=0, sticky="w")
        self.caption = tk.Label(head, text="", bg=CARD, fg=TEXT, font=(FONT, 9),
                                anchor="w", justify="left")
        self.caption.grid(row=1, column=0, sticky="w")
        self.detail = tk.Label(head, text="", bg=CARD, fg=MUTED, font=(FONT, 8),
                               anchor="w", justify="left")
        self.detail.grid(row=2, column=0, sticky="w")
        head.bind("<Configure>", self._wrap_captions)
        self._head = head

        bars = tk.Frame(self, bg=CARD)
        bars.grid(row=2, column=0, sticky="new", padx=pad)
        bars.grid_columnconfigure(0, weight=1)
        self._bars_frame = bars
        self.bars = []
        for index in range(bar_count):
            self._add_bar(index)

        self.grid_rowconfigure(3, weight=1)
        tk.Frame(self, bg=CARD2, height=1).grid(row=4, column=0, sticky="ew", padx=pad, pady=(6, 6))

        stats = tk.Frame(self, bg=CARD)
        stats.grid(row=5, column=0, sticky="ew", padx=pad, pady=(0, 14))
        stats.grid_columnconfigure(1, weight=1)
        self.stats = []
        for row, title in enumerate(stat_titles):
            tk.Label(stats, text=title, bg=CARD, fg=MUTED, font=(FONT, 8),
                     anchor="w").grid(row=row, column=0, sticky="w", pady=2)
            value = tk.Label(stats, text="—", bg=CARD, fg=TEXT, font=(FONT, 9, "bold"),
                             anchor="e")
            value.grid(row=row, column=1, sticky="e", padx=(12, 0), pady=2)
            self.stats.append(value)

    def _add_bar(self, index):
        bar = UsageBar(self._bars_frame, "")
        bar.grid(row=index, column=0, sticky="ew", pady=(0, 7))
        self.bars.append(bar)
        return bar

    def _wrap_captions(self, _event=None):
        available = self._head.winfo_width()
        if available > 40:
            self.caption.configure(wraplength=available)
            self.detail.configure(wraplength=available)

    def set_bars(self, specs):
        """specs : liste de dict(title, fraction, value, color, detail, caption)."""
        while len(self.bars) < len(specs):
            self._add_bar(len(self.bars))
        for index, bar in enumerate(self.bars):
            if index < len(specs):
                spec = specs[index]
                bar.grid()
                bar.set(spec["fraction"], spec["value"], spec["color"],
                        detail=spec.get("detail", ""), caption=spec.get("caption", ""),
                        title=spec["title"])
            else:
                bar.grid_remove()

    def set_headline(self, text, color, caption, detail):
        self.big.configure(text=text, fg=color)
        self.caption.configure(text=caption)
        self.detail.configure(text=detail)
        self.after_idle(self._wrap_captions)

    def set_status(self, ok, text=None):
        if ok:
            self.status.configure(text="●  " + (text or "en direct"), fg=GREEN)
        else:
            self.status.configure(text="●  " + (text or "hors ligne"), fg=RED)

    def set_stats(self, values):
        for label, value in zip(self.stats, values):
            label.configure(text=value)


def reset_caption(value):
    remaining = countdown(value)
    return f"reset dans {remaining}" if remaining and remaining != "imminent" else (
        "reset imminent" if remaining else ""
    )


def quota_spec(title, used, reset_time):
    return {
        "title": title,
        "fraction": used,
        "value": f"{fr(used * 100, 1)} %",
        "color": usage_color(used),
        "detail": f"reste {fr((1 - used) * 100, 0)} %",
        "caption": reset_caption(reset_time),
    }


class GoMonitor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Moniteur IA")
        self._set_icon()
        self.configure(bg=BG)
        self.status = {}
        self.summary = {}
        self.models = []
        self.model_names = {}
        self.go_error = ""
        self.gemini = {}
        self.claude = {}
        self.openrouter = {}
        self.rows = []
        self._after_id = None
        self._loading = False
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *_args: self.populate())
        self._build_style()
        self._build_ui()
        self.update_idletasks()
        width = min(1640, self.winfo_screenwidth() - 40)
        height = min(980, self.winfo_screenheight() - 80)
        self.geometry(f"{width}x{height}")
        self.minsize(1280, 760)
        self._center(width, height)
        self.refresh(initial=True)

    def _set_icon(self):
        icon_path = Path(__file__).with_name("icon.png")
        try:
            self._icon_image = tk.PhotoImage(file=str(icon_path))
            self.iconphoto(True, self._icon_image)
        except Exception:
            pass

    def _center(self, width, height):
        x = max(0, (self.winfo_screenwidth() - width) // 2)
        y = max(0, (self.winfo_screenheight() - height) // 2 - 20)
        self.geometry(f"+{x}+{y}")

    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        self.table_font = tkfont.Font(family=FONT, size=9)
        self.table_head_font = tkfont.Font(family=FONT, size=9, weight="bold")
        row_height = self.table_font.metrics("linespace") + 12

        style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        style.configure(
            "Treeview",
            background=CARD2,
            fieldbackground=CARD2,
            foreground=TEXT,
            borderwidth=0,
            rowheight=row_height,
            font=self.table_font,
        )
        style.map(
            "Treeview",
            background=[("selected", "#2b4354")],
            foreground=[("selected", "#ffffff")],
        )
        style.configure(
            "Treeview.Heading",
            background=CARD,
            foreground=MUTED,
            relief="flat",
            borderwidth=0,
            font=self.table_head_font,
            padding=(8, 6),
        )
        style.map(
            "Treeview.Heading",
            background=[("active", CARD)],
            foreground=[("active", TEXT)],
        )
        style.configure(
            "Vertical.TScrollbar",
            background="#2a3540",
            troughcolor=CARD2,
            bordercolor=CARD2,
            arrowcolor=MUTED,
            darkcolor="#2a3540",
            lightcolor="#2a3540",
            relief="flat",
        )
        style.map("Vertical.TScrollbar", background=[("active", "#3a4855")])
        style.configure(
            "Dark.TEntry",
            fieldbackground=CARD2,
            foreground=TEXT,
            insertcolor=TEXT,
            bordercolor=CARD2,
            lightcolor=CARD2,
            darkcolor=CARD2,
            padding=5,
        )
        style.map(
            "Dark.TEntry",
            bordercolor=[("focus", ACCENT)],
            lightcolor=[("focus", ACCENT)],
            darkcolor=[("focus", ACCENT)],
        )
        style.configure(
            "Ghost.TButton",
            background=CARD2,
            foreground=TEXT,
            borderwidth=0,
            focusthickness=0,
            padding=(12, 5),
            font=(FONT, 9),
        )
        style.map(
            "Ghost.TButton",
            background=[("active", "#25313d"), ("pressed", "#2c3a47")],
        )

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = tk.Frame(self, bg=BG)
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(14, 10))
        header.grid_columnconfigure(0, weight=1)
        tk.Label(
            header, text="Moniteur IA", bg=BG, fg=TEXT,
            font=(FONT, 18, "bold"), anchor="w",
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            header, text="OpenCode Go  ·  Google AI Ultra  ·  Claude Max  ·  OpenRouter",
            bg=BG, fg=MUTED, font=(FONT, 9), anchor="w",
        ).grid(row=1, column=0, sticky="w")
        self.live_label = tk.Label(
            header, text="●  CONNEXION…", bg=BG, fg=MUTED,
            font=(FONT, 9, "bold"), anchor="e",
        )
        self.live_label.grid(row=0, column=1, rowspan=2, sticky="e")

        cards = tk.Frame(self, bg=BG)
        cards.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))
        for column in range(4):
            cards.grid_columnconfigure(column, weight=1, uniform="cards")

        self.go_card = ProviderCard(
            cards, "OPENCODE GO", ACCENT, 3,
            ["Forfait", "Renouvellement", "Coût (30 j)", "Requêtes (30 j)"],
        )
        self.go_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self.ultra_card = ProviderCard(
            cards, "GOOGLE AI ULTRA", GEMINI_BLUE, 4,
            ["Abonnement", "Compte", "Jetons E / S (30 j)", "Requêtes · cache"],
        )
        self.ultra_card.grid(row=0, column=1, sticky="nsew", padx=6)
        self.claude_card = ProviderCard(
            cards, "CLAUDE MAX", CLAUDE_ORANGE, 3,
            ["Forfait", "Compte", "Jetons E / S (30 j)", "Requêtes · cache"],
        )
        self.claude_card.grid(row=0, column=2, sticky="nsew", padx=6)
        self.openrouter_card = ProviderCard(
            cards, "OPENROUTER", OPENROUTER_PURPLE, 2,
            ["Ta clé · aujourd'hui", "Ta clé · ce mois", "Compte · 30 j", "Détail par modèle"],
        )
        self.openrouter_card.grid(row=0, column=3, sticky="nsew", padx=(6, 0))

        # --- Tableau par modèle ---
        models_card = tk.Frame(self, bg=CARD)
        models_card.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 14))
        models_card.grid_columnconfigure(0, weight=1)
        models_card.grid_rowconfigure(1, weight=1)

        toolbar = tk.Frame(models_card, bg=CARD)
        toolbar.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 8))
        toolbar.grid_columnconfigure(1, weight=1)
        tk.Label(
            toolbar, text="Consommation par modèle", bg=CARD, fg=TEXT,
            font=(FONT, 11, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            toolbar, text="30 derniers jours", bg=CARD, fg=MUTED, font=(FONT, 9),
        ).grid(row=0, column=1, sticky="w", padx=(10, 0))
        tk.Label(
            toolbar, text="Filtrer", bg=CARD, fg=MUTED, font=(FONT, 9),
        ).grid(row=0, column=2, sticky="e", padx=(10, 6))
        ttk.Entry(
            toolbar, textvariable=self.filter_var, width=18, style="Dark.TEntry",
        ).grid(row=0, column=3, sticky="e")

        table_frame = tk.Frame(models_card, bg=CARD)
        table_frame.grid(row=1, column=0, sticky="nsew", padx=16)
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)

        columns = ("name", "source", "requests", "input", "output", "cache", "cost", "limit", "pct")
        self.tree = ttk.Treeview(
            table_frame, columns=columns, show="headings", selectmode="browse", height=6,
        )
        # (titre, exemple de valeur la plus large, ancrage)
        headings = {
            "name": ("Modèle", "Muse Spark 1.3 Contributor", "w"),
            "source": ("Offre", "OpenRouter", "w"),
            "requests": ("Requêtes", "12 345", "e"),
            "input": ("Entrée", "888,8 M", "e"),
            "output": ("Sortie", "888,8 M", "e"),
            "cache": ("Cache lu", "888,8 M", "e"),
            "cost": ("Coût", "$888,88", "e"),
            "limit": ("Plafond", "Illimité", "e"),
            "pct": ("Utilisé", "100,0 %", "e"),
        }
        for column, (label, sample, anchor) in headings.items():
            self.tree.heading(column, text=label, anchor=anchor)
            width = max(self.table_head_font.measure(label), self.table_font.measure(sample)) + 28
            self.tree.column(column, width=width, minwidth=width,
                             stretch=(column == "name"), anchor=anchor)
        self.tree.tag_configure("even", background=CARD2)
        self.tree.tag_configure("odd", background=ROW_ALT)
        self.tree.tag_configure("ok", foreground=GREEN)
        self.tree.tag_configure("warn", foreground=ORANGE)
        self.tree.tag_configure("hot", foreground=RED)
        self.tree.tag_configure("muted", foreground=MUTED)
        self.tree.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(
            table_frame, orient="vertical", command=self.tree.yview,
            style="Vertical.TScrollbar",
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)

        footer = tk.Frame(models_card, bg=CARD)
        footer.grid(row=2, column=0, sticky="ew", padx=16, pady=(8, 12))
        footer.grid_columnconfigure(0, weight=1)

        self.status_label = tk.Label(
            footer, text="", bg=CARD, fg=MUTED, font=(FONT, 8),
            anchor="w", justify="left",
        )
        self.status_label.grid(row=0, column=0, sticky="ew")
        footer.bind(
            "<Configure>",
            lambda event: self.status_label.configure(wraplength=max(200, event.width - 600)),
        )
        self.refresh_button = ttk.Button(
            footer, text="Actualiser", style="Ghost.TButton", command=self.refresh,
        )
        self.refresh_button.grid(row=0, column=1, padx=(6, 0))
        ttk.Button(
            footer, text="Console Go", style="Ghost.TButton",
            command=lambda: webbrowser.open(CONSOLE_URL),
        ).grid(row=0, column=2, padx=(6, 0))
        ttk.Button(
            footer, text="Usage Claude", style="Ghost.TButton",
            command=lambda: webbrowser.open(CLAUDE_USAGE_URL),
        ).grid(row=0, column=3, padx=(6, 0))
        ttk.Button(
            footer, text="Activité OpenRouter", style="Ghost.TButton",
            command=lambda: webbrowser.open(OPENROUTER_URL),
        ).grid(row=0, column=4, padx=(6, 0))

    def refresh(self, initial=False):
        if self._loading:
            return
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None
        self._loading = True
        self.refresh_button.state(["disabled"])
        if not initial:
            self.status_label.configure(text="Actualisation…", fg=MUTED)
        threading.Thread(target=self._load_worker, daemon=True).start()

    def _api_get(self, path, params=None):
        key = read_api_key()
        url = API_BASE + path
        if params:
            url += "?" + urlencode(params)
        request = Request(
            url,
            headers={
                "Authorization": "Bearer " + key,
                "Accept": "application/json",
                "User-Agent": "moniteur-opencode-go/1.0",
            },
        )
        with urlopen(request, timeout=20) as response:
            return json.load(response)

    def _fetch_models(self):
        items = []
        page = 1
        while True:
            data = self._api_get(
                "/usage/models",
                {"range": "30d", "page": page, "pageSize": 100},
            )
            items.extend(data.get("items", []))
            page_info = data.get("pageInfo", {})
            page_count = int(page_info.get("pageCount", 1) or 1)
            if page >= page_count:
                break
            page += 1
        return items

    def _fetch_go(self):
        try:
            status = self._api_get("/go/status")
            summary = self._api_get("/usage/summary", {"range": "30d"})
            models = self._fetch_models()
        except MonitorError as error:
            return {"ok": False, "error": str(error)}
        except Exception as error:
            return {"ok": False, "error": self._friendly_error(error)}
        names = {}
        try:
            config = self._api_get("/config")
            provider = config.get("config", {}).get("provider", {}).get("opencode", {})
            for model_id, model in (provider.get("models") or {}).items():
                label = model.get("name")
                if label:
                    names[model_id] = label
        except Exception:
            pass
        return {"ok": True, "status": status, "summary": summary, "models": models, "names": names}

    def _load_worker(self):
        results = {}

        def run(key, func):
            try:
                results[key] = func()
            except Exception as error:
                results[key] = {"ok": False, "error": str(error)}

        threads = [
            threading.Thread(target=run, args=("go", self._fetch_go)),
            threading.Thread(target=run, args=("ultra", fetch_gemini_data)),
            threading.Thread(target=run, args=("claude", fetch_claude_data)),
            threading.Thread(target=run, args=("openrouter", fetch_openrouter_data)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.after(0, self._apply, results)

    def _friendly_error(self, error):
        text = str(error)
        if "401" in text or "403" in text:
            return "Clé refusée par OpenCode (401/403). Reconnecte-toi avec /connect."
        if "timed out" in text.lower():
            return "Délai dépassé : vérifie ta connexion Internet."
        if "URLError" in text or "getaddrinfo" in text:
            return "Impossible de joindre opencode.ai (connexion réseau)."
        return text or "Erreur inconnue."

    def _apply(self, results):
        self._loading = False
        self.refresh_button.state(["!disabled"])
        errors = []

        go = results.get("go") or {}
        if go.get("ok"):
            self.status = go["status"]
            self.summary = go["summary"]
            self.models = go["models"]
            self.model_names = go["names"]
            self._update_go()
            self.go_card.set_status(True)
        else:
            errors.append("OpenCode : " + (go.get("error") or "erreur inconnue"))
            self.go_card.set_status(False)

        ultra = results.get("ultra") or {}
        if "local" in ultra or "online" in ultra:
            self.gemini = ultra
            self._update_ultra()
        if not ultra.get("online"):
            errors.append("Google AI Ultra : quotas indisponibles (agy ou jeton Google).")

        claude = results.get("claude") or {}
        if "local" in claude:
            self.claude = claude
            self._update_claude()
        if not claude.get("ok"):
            errors.append(claude.get("error") or "Claude : erreur inconnue.")

        openrouter = results.get("openrouter") or {}
        if openrouter.get("ok"):
            self.openrouter = openrouter
            self._update_openrouter()
        self.openrouter_card.set_status(bool(openrouter.get("ok")))
        if openrouter.get("error"):
            errors.append(openrouter["error"])

        self.populate()

        sources = (go.get("ok"), ultra.get("online"), claude.get("ok"), openrouter.get("ok"))
        online = sum(1 for flag in sources if flag)
        if online == len(sources):
            self.live_label.configure(text="●  EN DIRECT", fg=GREEN)
        elif online:
            self.live_label.configure(text=f"●  {online}/{len(sources)} EN DIRECT", fg=ORANGE)
        else:
            self.live_label.configure(text="●  HORS LIGNE", fg=RED)

        stamp = time.strftime("%H:%M:%S")
        if errors:
            self.status_label.configure(text=f"{stamp} · " + "  ·  ".join(errors), fg=ORANGE)
        else:
            self.status_label.configure(
                text=f"Actualisé à {stamp} · rafraîchissement toutes les 60 s", fg=MUTED,
            )
        self._after_id = self.after(REFRESH_MS, self.refresh)

    def _limits(self):
        product = self.status.get("product")
        return GO_PLUS_LIMITS if product == "go-plus" else GO_LIMITS

    def _update_go(self):
        access = self.status.get("access") or {}
        meters = access.get("meters") or {}
        product = self.status.get("product")
        plan = "Go Plus" if product == "go-plus" else "Go"

        month = meters.get("month") or {}
        month_limit = float(month.get("limitMicroCents", 0) or 0)
        month_used = float(month.get("usedMicroCents", 0) or 0)
        month_fraction = (month_used / month_limit) if month_limit else 0
        self.go_card.set_headline(
            f"{fr(month_fraction * 100, 0)} %",
            usage_color(month_fraction),
            f"du mois · {format_dollars(month_used)} sur {format_dollars(month_limit)}",
            f"fin du mois dans {countdown(month.get('resetsAt'))}",
        )

        specs = []
        for key, title in (("fiveHour", "Fenêtre glissante (5 h)"),
                           ("week", "Semaine"), ("month", "Mois")):
            meter = meters.get(key) or {}
            limit = float(meter.get("limitMicroCents", 0) or 0)
            used = float(meter.get("usedMicroCents", 0) or 0)
            fraction = (used / limit) if limit else 0
            specs.append({
                "title": title,
                "fraction": fraction,
                "value": f"{fr(fraction * 100, 1)} %",
                "color": usage_color(fraction),
                "detail": f"{format_dollars(used)} / {format_dollars(limit)}",
                "caption": reset_caption(meter.get("resetsAt")),
            })
        self.go_card.set_bars(specs)

        renewal = access.get("endsAt")
        renew_text = "—"
        if renewal:
            moment = parse_time(renewal).astimezone()
            renew_text = f"{moment.day} {MONTHS[moment.month - 1]} · dans {countdown(renewal)}"
        self.go_card.set_stats([
            plan,
            renew_text,
            format_dollars(self.summary.get("totalCostMicroCents", "0")),
            fr_int(self.summary.get("totalRequests", "0")),
        ])

    def _update_ultra(self):
        local = (self.gemini.get("local") or {}).get("totals") or {}
        buckets = [
            ("Gemini · fenêtre 5 h", self.gemini.get("gemini_5h")),
            ("Gemini · semaine", self.gemini.get("gemini_weekly")),
            ("Claude & GPT · fenêtre 5 h", self.gemini.get("claude_5h")),
            ("Claude & GPT · semaine", self.gemini.get("claude_weekly")),
        ]
        specs = []
        for title, bucket in buckets:
            if bucket:
                specs.append(quota_spec(title, bucket["used_fraction"], bucket.get("reset_time")))
            else:
                specs.append({"title": title, "fraction": 0, "value": "—", "color": MUTED,
                              "detail": "indisponible", "caption": ""})
        self.ultra_card.set_bars(specs)

        available = [(title, b) for title, b in buckets if b]
        if available:
            title, top = max(available, key=lambda item: item[1]["used_fraction"])
            used = top["used_fraction"]
            self.ultra_card.set_headline(
                f"{fr(used * 100, 0)} %", usage_color(used),
                f"quota le plus entamé", title,
            )
            self.ultra_card.set_status(True)
        else:
            self.ultra_card.set_headline(
                format_tokens(int(local.get("input", 0)) + int(local.get("output", 0))),
                GEMINI_BLUE, "jetons sur 30 jours", "quotas indisponibles",
            )
            self.ultra_card.set_status(False)

        self.ultra_card.set_stats([
            self.gemini.get("tier") or "Google AI Ultra",
            self.gemini.get("email") or "—",
            f"{format_tokens(local.get('input', 0))} / {format_tokens(local.get('output', 0))}",
            f"{fr_int(local.get('requests', 0))} · {format_tokens(local.get('cache', 0))}",
        ])

    def _update_claude(self):
        local = (self.claude.get("local") or {}).get("totals") or {}
        limits = self.claude.get("limits") or []
        if limits:
            self.claude_card.set_bars([
                quota_spec(limit["label"], limit["used_fraction"], limit["reset_time"])
                for limit in limits
            ])
            top = max(limits, key=lambda limit: limit["used_fraction"])
            used = top["used_fraction"]
            self.claude_card.set_headline(
                f"{fr(used * 100, 0)} %", usage_color(used),
                "quota le plus entamé", top["label"],
            )
        else:
            self.claude_card.set_bars([
                {"title": title, "fraction": 0, "value": "—", "color": MUTED,
                 "detail": "indisponible", "caption": ""}
                for title in ("Session (5 h)", "Semaine · tous modèles")
            ])
            self.claude_card.set_headline(
                format_tokens(int(local.get("input", 0)) + int(local.get("output", 0))),
                CLAUDE_ORANGE, "jetons sur 30 jours", "quotas indisponibles",
            )
        self.claude_card.set_status(bool(self.claude.get("ok")))
        self.claude_card.set_stats([
            self.claude.get("plan") or "Claude Max",
            self.claude.get("email") or "—",
            f"{format_tokens(local.get('input', 0))} / {format_tokens(local.get('output', 0))}",
            f"{fr_int(local.get('requests', 0))} · {format_tokens(local.get('cache', 0))}",
        ])

    def _update_openrouter(self):
        credits = self.openrouter.get("credits") or {}
        key = self.openrouter.get("key") or {}
        by_model = self.openrouter.get("by_model") or {}
        specs = []

        if credits:
            total = float(credits.get("total_credits", 0) or 0)
            used = float(credits.get("total_usage", 0) or 0)
            remaining = max(0.0, total - used)
            fraction = (used / total) if total else 0
            self.openrouter_card.set_headline(
                format_usd(remaining), usage_color(fraction),
                f"restants sur {format_usd(total)}",
                f"consommé depuis le début : {format_usd(used)}",
            )
            specs.append({
                "title": "Crédits du compte",
                "fraction": fraction,
                "value": f"{fr(fraction * 100, 1)} %",
                "color": usage_color(fraction),
                "detail": f"{format_usd(used)} / {format_usd(total)}",
                "caption": f"reste {format_usd(remaining)}",
            })
        else:
            self.openrouter_card.set_headline("—", MUTED, "crédits indisponibles", "")

        if key.get("limit"):
            limit = float(key["limit"])
            remaining = key.get("limit_remaining")
            if remaining is not None:
                key_used = max(0.0, limit - float(remaining))
            else:
                key_used = float(key.get("usage", 0) or 0)
            fraction = min(1.0, key_used / limit) if limit else 0
            reset = key.get("limit_reset")
            periods = {"daily": "Plafond du jour", "weekly": "Plafond de la semaine",
                       "monthly": "Plafond du mois"}
            now = datetime.now(timezone.utc)
            if reset == "monthly":
                next_month = (now.month % 12) + 1
                caption = f"reset le 1er {MONTHS[next_month - 1]}"
            elif reset in ("daily", "weekly"):
                caption = "reset chaque jour" if reset == "daily" else "reset chaque lundi"
            else:
                caption = f"reste {format_usd(max(0.0, limit - key_used))}"
            specs.append({
                "title": periods.get(reset, "Plafond de la clé"),
                "fraction": fraction,
                "value": f"{fr(fraction * 100, 1)} %",
                "color": usage_color(fraction),
                "detail": f"{format_usd(key_used)} / {format_usd(limit)}",
                "caption": caption,
            })
        free = key.get("free_model_daily_requests") or {}
        if free.get("limit"):
            fraction = float(free.get("used", 0) or 0) / float(free["limit"])
            specs.append({
                "title": "Requêtes gratuites (jour)",
                "fraction": fraction,
                "value": f"{fr(fraction * 100, 1)} %",
                "color": usage_color(fraction),
                "detail": f"{fr_int(free.get('used', 0))} / {fr_int(free['limit'])}",
                "caption": f"reste {fr_int(free.get('remaining', 0))}",
            })
        self.openrouter_card.set_bars(specs)

        model_cost = sum(item["cost"] for item in by_model.values())
        self.openrouter_card.set_stats([
            format_usd(key.get("usage_daily")) if key else "—",
            format_usd(key.get("usage_monthly")) if key else "—",
            f"{format_usd(model_cost)} · {len(by_model)} modèle" + ("s" if len(by_model) > 1 else ""),
            self.openrouter.get("scope") or "—",
        ])

    def _build_rows(self):
        limits = self._limits()
        rows = []

        for item in self.models:
            model_id = item.get("model", "?")
            cost = int(item.get("totalCostMicroCents", 0) or 0)
            limit = limits.get(model_id)
            rows.append({
                "id": "go:" + model_id,
                "name": self.model_names.get(model_id) or pretty_model(model_id),
                "source": "OpenCode",
                "requests": int(item.get("totalRequests", 0) or 0),
                "input": int(item.get("totalInputTokens", 0) or 0),
                "output": int(item.get("totalOutputTokens", 0) or 0),
                "cache": int(item.get("totalCacheReadTokens", 0) or 0),
                "cost": format_dollars(cost),
                "limit": "Illimité" if (model_id in limits and limit is None) else (
                    "$" + fr(limit, 0) if limit else "—"),
                "fraction": ((cost / 100000000) / limit) if limit else None,
                "order": (0, cost),
            })

        for source, prefix, data in (("Ultra", "ultra:", self.gemini), ("Claude", "max:", self.claude)):
            for entry in ((data.get("local") or {}).get("by_model") or {}).values():
                rows.append({
                    "id": prefix + entry["name"],
                    "name": entry["name"],
                    "source": source,
                    "requests": entry["requests"],
                    "input": entry["input"],
                    "output": entry["output"],
                    "cache": entry["cache"],
                    "cost": "inclus",
                    "limit": "forfait",
                    "fraction": None,
                    "order": (1 if source == "Ultra" else 2, entry["input"] + entry["output"]),
                })

        for entry in (self.openrouter.get("by_model") or {}).values():
            rows.append({
                "id": "openrouter:" + entry["name"],
                "name": entry["name"],
                "source": "OpenRouter",
                "requests": entry["requests"],
                "input": entry["input"],
                "output": entry["output"],
                "cache": entry["cache"],
                "cost": format_usd(entry["cost"]),
                "limit": "crédits",
                "fraction": None,
                "order": (3, entry["cost"]),
            })

        # Par offre, puis du plus consommé au moins consommé
        rows.sort(key=lambda row: (row["order"][0], -(row["fraction"] or 0), -row["order"][1],
                                   -row["requests"]))
        return rows

    def _filtered_rows(self):
        query = self.filter_var.get().strip().lower()
        if not query:
            return self.rows
        return [
            row for row in self.rows
            if query in row["name"].lower() or query in row["source"].lower()
        ]

    def populate(self):
        self.rows = self._build_rows()
        rows = self._filtered_rows()
        existing = set(self.tree.get_children(""))
        seen = set()
        selected = self.tree.selection()
        for index, row in enumerate(rows):
            iid = row["id"]
            seen.add(iid)
            fraction = row["fraction"]
            if fraction is None:
                pct_text = "—"
                state = "muted" if row["limit"] == "Illimité" else ""
            else:
                pct_text = fr(fraction * 100, 1) + " %"
                state = "hot" if fraction >= 0.85 else "warn" if fraction >= 0.60 else "ok"
            values = (
                row["name"],
                row["source"],
                fr_int(row["requests"]),
                format_tokens(row["input"]),
                format_tokens(row["output"]),
                format_tokens(row["cache"]) if row["cache"] is not None else "—",
                row["cost"],
                row["limit"],
                pct_text,
            )
            tags = ("even" if index % 2 == 0 else "odd",) + ((state,) if state else ())
            if iid in existing:
                self.tree.item(iid, values=values, tags=tags)
            else:
                self.tree.insert("", "end", iid=iid, values=values, tags=tags)
            self.tree.move(iid, "", index)

        for iid in existing - seen:
            self.tree.delete(iid)

        if selected and selected[0] in seen:
            self.tree.selection_set(selected[0])


if __name__ == "__main__":
    if "--test-gemini" in sys.argv:
        print(json.dumps(fetch_gemini_data(), indent=2))
        sys.exit(0)
    if "--test-openrouter" in sys.argv:
        print(json.dumps(fetch_openrouter_data(), indent=2, default=str))
        sys.exit(0)
    if "--test-claude" in sys.argv:
        print(json.dumps(fetch_claude_data(), indent=2, default=str))
        sys.exit(0)
    app = GoMonitor()
    app.mainloop()
