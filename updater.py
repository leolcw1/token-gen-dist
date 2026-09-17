import os
import sys
import json
import time
import requests
from pathlib import Path

# ===================================================================
#  CONFIGURACAO DO GITHUB PARA O GN ROC (POKASSTORE MOBILE)
# ===================================================================
GITHUB_RAW_VERSION_URL = "https://raw.githubusercontent.com/leolcw1/token-gen-dist/main/version.json"

# Se o repositorio for PRIVADO, insira o seu token aqui. Se for PUBLICO, deixe None.
GITHUB_TOKEN = None

if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent.resolve()
else:
    BASE_DIR = Path(__file__).parent.resolve()

LOCAL_VERSION_FILE = BASE_DIR / "version.json"
CURRENT_FALLBACK_VERSION = "1.0.0"

def _get_headers() -> dict:
    headers = {
        "User-Agent": "PokasStore-AutoUpdater",
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0"
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    return headers

def get_local_version() -> str:
    if LOCAL_VERSION_FILE.exists():
        try:
            with open(LOCAL_VERSION_FILE, "r", encoding="utf-8") as f:
                return json.load(f).get("version", CURRENT_FALLBACK_VERSION)
        except Exception:
            pass
    return CURRENT_FALLBACK_VERSION

def set_local_version(version: str):
    try:
        with open(LOCAL_VERSION_FILE, "w", encoding="utf-8") as f:
            json.dump({"version": version}, f, indent=4)
    except Exception:
        pass

def check_for_updates() -> tuple[bool, dict]:
    """
    Retorna (has_update: bool, remote_manifest: dict)
    """
    try:
        url = f"{GITHUB_RAW_VERSION_URL}?t={int(time.time())}"
        resp = requests.get(url, headers=_get_headers(), timeout=6)
        if resp.status_code != 200:
            return False, {}

        remote_data = resp.json()
        remote_version = str(remote_data.get("version", "")).strip()
        local_version = get_local_version().strip()

        if remote_version and remote_version != local_version:
            return True, remote_data
    except Exception:
        pass

    return False, {}

def apply_update(remote_data: dict) -> bool:
    """
    Baixa os arquivos listados no manifesto e substitui com seguranca.
    """
    files = remote_data.get("files", {})
    if not files:
        return False

    temp_files = []
    try:
        for filename, url in files.items():
            cache_bust_url = f"{url}?t={int(time.time())}"
            resp = requests.get(cache_bust_url, headers=_get_headers(), timeout=30)
            if resp.status_code != 200:
                for t, _ in temp_files:
                    try: t.unlink()
                    except: pass
                return False

            tmp_path = BASE_DIR / f"{filename}.update_tmp"
            with open(tmp_path, "wb") as f:
                f.write(resp.content)
            temp_files.append((tmp_path, BASE_DIR / filename))

        for tmp_path, final_path in temp_files:
            try:
                if final_path.exists():
                    final_path.unlink()
            except Exception:
                pass
            try:
                tmp_path.replace(final_path)
            except Exception:
                try:
                    import shutil
                    shutil.move(str(tmp_path), str(final_path))
                except Exception:
                    pass

            # Limpa qualquer resíduo .old
            old_f = BASE_DIR / f"{final_path.name}.old"
            if old_f.exists():
                try: old_f.unlink()
                except Exception: pass

        set_local_version(remote_data.get("version", "1.0.0"))
        return True

    except Exception:
        return False

def restart_process():
    """
    Reinicia o aplicativo (suporta executável congelado .exe e script .py).
    """
    try:
        import subprocess
        if getattr(sys, 'frozen', False):
            subprocess.Popen([sys.executable] + sys.argv[1:])
        else:
            subprocess.Popen([sys.executable] + sys.argv)
        os._exit(0)
    except Exception:
        python_exe = sys.executable
        os.execl(python_exe, python_exe, *sys.argv)
