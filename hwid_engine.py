import os
import json
import ctypes
import hashlib
import subprocess
import winreg

_VAULT_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "PokasStore")
_VAULT_FILE = os.path.join(_VAULT_DIR, "hwid.vault")

def _obter_uuid_placa_mae():
    # 1. PowerShell (CIM - rápido, moderno e padrão no Windows 10/11)
    try:
        cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", "(Get-CimInstance Win32_ComputerSystemProduct).UUID"]
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=4).decode("utf-8", errors="ignore").strip()
        if out and len(out) > 5 and "UUID" not in out.upper():
            return out
    except Exception:
        pass

    # 2. WMIC (legado como fallback)
    try:
        out = subprocess.check_output(
            "wmic csproduct get uuid",
            shell=True,
            stderr=subprocess.DEVNULL,
            timeout=5
        ).decode("utf-8", errors="ignore")
        linhas = [l.strip() for l in out.splitlines() if l.strip() and "UUID" not in l.upper()]
        if linhas and len(linhas[0]) > 5:
            return linhas[0]
    except Exception:
        pass

    # 3. Fallback estável direto no Registro do Windows (BIOS / Motherboard)
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\BIOS") as k:
            mfg, _ = winreg.QueryValueEx(k, "SystemManufacturer")
            prod, _ = winreg.QueryValueEx(k, "SystemProductName")
            if mfg or prod:
                return f"{mfg}:{prod}".strip()
    except Exception:
        pass

    return ""

def _obter_serial_volume():
    try:
        vol_serial = ctypes.c_ulong(0)
        res = ctypes.windll.kernel32.GetVolumeInformationW(
            "C:\\", None, 0, ctypes.byref(vol_serial), None, None, None, 0
        )
        if res and vol_serial.value != 0:
            return str(vol_serial.value)
    except Exception:
        pass
    return ""

def _obter_machine_guid():
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as k:
            val, _ = winreg.QueryValueEx(k, "MachineGuid")
            if val:
                return str(val).strip()
    except Exception:
        pass
    return ""

def obter_hwid():
    """
    Combina múltiplos identificadores de hardware em um digest único e ultra-estável.
    Utiliza cache local ancorado em hardware para impedir oscilações temporárias de subprocessos.
    Formato retornado: GNROC-XXXX-XXXX-XXXX-XXXX
    """
    guid_atual = _obter_machine_guid()
    vol_atual = _obter_serial_volume()

    # ── 1. Verificação de Cache Ancorado ─────────────────────────────────────
    if os.path.exists(_VAULT_FILE):
        try:
            with open(_VAULT_FILE, "r", encoding="utf-8") as f:
                cached = json.load(f)
            cached_hwid = cached.get("hwid", "")
            cached_guid = cached.get("guid", "")
            cached_vol = cached.get("vol", "")

            # Valida que o cache pertence comprovadamente a este hardware
            if cached_hwid and ((guid_atual and cached_guid == guid_atual) or (vol_atual and cached_vol == vol_atual)):
                return cached_hwid
        except Exception:
            pass

    # ── 2. Cálculo Determinístico ────────────────────────────────────────────
    uuid_atual = _obter_uuid_placa_mae()
    comp = [uuid_atual, vol_atual, guid_atual]
    dados = [c for c in comp if c]
    if not dados:
        dados = ["GNROC-FALLBACK-SYS-NODE"]

    raw = "|".join(dados)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()
    hwid = f"GNROC-{digest[0:4]}-{digest[4:8]}-{digest[8:12]}-{digest[12:16]}"

    # ── 3. Salva no Cache Local Ancorado ─────────────────────────────────────
    try:
        os.makedirs(_VAULT_DIR, exist_ok=True)
        with open(_VAULT_FILE, "w", encoding="utf-8") as f:
            json.dump({"hwid": hwid, "guid": guid_atual, "vol": vol_atual}, f)
    except Exception:
        pass

    return hwid

if __name__ == "__main__":
    print(f"HWID Detectado: {obter_hwid()}")
