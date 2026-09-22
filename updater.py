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
CURRENT_FALLBACK_VERSION = "1.0.53"

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

def parse_version(ver_str: str) -> tuple:
    """
    Converte qualquer formato de versão ('1.0.53', 'v1.0.53', ' 1.0.53\n')
    em uma tupla numérica confiável (1, 0, 53). Imune a erros de parse.
    """
    try:
        if not ver_str:
            return (0,)
        clean = str(ver_str).strip().lstrip("vV")
        partes = []
        for x in clean.split("."):
            num = ""
            for ch in x:
                if ch.isdigit():
                    num += ch
                else:
                    break
            if num:
                partes.append(int(num))
        return tuple(partes) if partes else (0,)
    except Exception:
        return (0,)

def get_local_version() -> str:
    """
    Localiza a versão local procurando em múltiplos locais possíveis e garante
    que nunca retorne versão zerada ou antiga como fallback.
    """
    candidatos = [
        LOCAL_VERSION_FILE,
        BASE_DIR / "dist" / "PokasStoreMobile" / "version.json",
        BASE_DIR.parent / "version.json"
    ]
    melhor_ver = CURRENT_FALLBACK_VERSION
    for cand in candidatos:
        if cand.exists():
            try:
                with open(cand, "r", encoding="utf-8-sig") as f:
                    v = json.load(f).get("version", "")
                    if v and parse_version(v) > parse_version(melhor_ver):
                        melhor_ver = str(v).strip()
            except Exception:
                pass
    return melhor_ver

def set_local_version(version: str):
    try:
        for v_path in [LOCAL_VERSION_FILE, BASE_DIR / "dist" / "PokasStoreMobile" / "version.json"]:
            try:
                with open(v_path, "w", encoding="utf-8") as f:
                    json.dump({"version": version}, f, indent=4)
            except Exception:
                pass
    except Exception:
        pass

def check_for_updates() -> tuple[bool, dict]:
    """
    Retorna (has_update: bool, remote_manifest: dict).
    REGRA ESTRITA: NUNCA avisa nem aplica versões menores ou iguais (passadas).
    Somente versões ESTRITAMENTE MAIORES (futuras) são disparadas.
    """
    try:
        url = f"{GITHUB_RAW_VERSION_URL}?t={int(time.time())}"
        resp = requests.get(url, headers=_get_headers(), timeout=6)
        if resp.status_code != 200:
            return False, {}

        remote_data = resp.json()
        remote_version = str(remote_data.get("version", "")).strip()
        local_version = get_local_version().strip()

        parsed_remote = parse_version(remote_version)
        parsed_local = parse_version(local_version)

        # Apenas atualizações estritamente futuras
        if remote_version and parsed_remote > parsed_local and parsed_remote != (0,):
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
            if final_path.name.lower().endswith(".exe"):
                new_exe = BASE_DIR / f"{final_path.name}.new"
                try:
                    if new_exe.exists(): new_exe.unlink()
                except Exception:
                    pass
                try:
                    tmp_path.replace(new_exe)
                except Exception:
                    try:
                        import shutil
                        shutil.move(str(tmp_path), str(new_exe))
                    except Exception:
                        pass
                continue

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
    Reinicia o aplicativo (suporta substituição segura de executável congelado .exe e script .py).
    """
    try:
        new_exe = BASE_DIR / "PokasStoreMobile.exe.new"
        cur_exe = BASE_DIR / "PokasStoreMobile.exe"
        if new_exe.exists():
            bat_path = BASE_DIR / "_restart_updater.bat"
            bat_script = f"""@echo off
timeout /t 1 /nobreak >nul
move /y "{new_exe}" "{cur_exe}" >nul 2>&1
start "" "{cur_exe}"
del "%~f0"
"""
            with open(bat_path, "w", encoding="utf-8") as f:
                f.write(bat_script)
            import subprocess
            subprocess.Popen(["cmd.exe", "/c", str(bat_path)])
            os._exit(0)

        import subprocess
        if getattr(sys, 'frozen', False):
            subprocess.Popen([sys.executable] + sys.argv[1:])
        else:
            subprocess.Popen([sys.executable] + sys.argv)
        os._exit(0)
    except Exception:
        os._exit(0)
        os.execl(python_exe, python_exe, *sys.argv)
