import os
import re
import sys
import json
import time
import hmac
import uuid
import shutil
import tempfile
import base64
import random
import string
import struct
import hashlib
import calendar
import threading
import subprocess
import unicodedata
import urllib.parse
import urllib.request
import urllib.error
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from datetime import datetime
from PIL import Image, ImageTk
import ctypes
from ctypes import wintypes

# Ativa Per-Monitor DPI Awareness no Windows para escala perfeita em qualquer monitor/notebook
try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)
except Exception:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

import pyautogui
import pyperclip

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try: user32.SetProcessDPIAware()
    except Exception: pass

from playwright.sync_api import sync_playwright

# ============================================================================
# CONFIGURAÇÕES E DIRETÓRIOS
# ============================================================================

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    # ── Hot-Reload Dinâmico para Distribuição Compilada (.exe) ───────────────────
    # Permite que atualizações baixadas pelo updater (.py) sejam executadas diretamente
    if not os.environ.get("_POKAS_DYNAMIC_LOADED"):
        _dynamic_script = os.path.join(BASE_DIR, "app_mobile.py")
        if os.path.exists(_dynamic_script):
            try:
                with open(_dynamic_script, "rb") as _f:
                    _src = _f.read()
                if len(_src) > 5000:
                    os.environ["_POKAS_DYNAMIC_LOADED"] = "1"
                    import runpy
                    runpy.run_path(_dynamic_script, run_name="__main__")
                    sys.exit(0)
            except Exception:
                pass
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONTAS_DIR = os.path.join(BASE_DIR, "contas")
os.makedirs(CONTAS_DIR, exist_ok=True)

OUTLOOK_FILE = os.path.join(CONTAS_DIR, "outlook.txt")
CRIAR_FILE = OUTLOOK_FILE  # Alias de compatibilidade
ROCKSTAR_FILE = os.path.join(CONTAS_DIR, "rockstar.txt")
FEITAS_FILE = ROCKSTAR_FILE  # Alias de compatibilidade
ERRO_FILE = os.path.join(CONTAS_DIR, "erro.txt")
CODIGOS_FILE = os.path.join(CONTAS_DIR, "codigos.txt")
PRONTAS_FILE = os.path.join(CONTAS_DIR, "prontas.txt")

for fpath in [OUTLOOK_FILE, ROCKSTAR_FILE, ERRO_FILE, CODIGOS_FILE, PRONTAS_FILE]:
    if not os.path.exists(fpath):
        with open(fpath, "w", encoding="utf-8") as f:
            pass

# Garante que as pastas com adb.exe e scrcpy.exe estejam no PATH do processo
diretorios_bin = [
    BASE_DIR,
    os.path.join(BASE_DIR, "dist", "PokasStoreMobile"),
    os.path.join(BASE_DIR, "_internal", "adbutils", "binaries"),
    os.path.join(BASE_DIR, "adbutils", "binaries"),
]
try:
    import adbutils
    diretorios_bin.append(os.path.dirname(adbutils.adb_path()))
except Exception:
    pass

for d in diretorios_bin:
    if os.path.isdir(d) and d not in os.environ["PATH"]:
        os.environ["PATH"] = d + os.pathsep + os.environ["PATH"]

# Resolução dinâmica do Scrcpy
SCRCPY_PATH = "scrcpy"
candidatos_scrcpy = [
    os.path.join(BASE_DIR, "scrcpy.exe"),
    os.path.join(BASE_DIR, "_internal", "adbutils", "binaries", "scrcpy.exe"),
    r"C:\Users\leoc\AppData\Local\Microsoft\WinGet\Packages\Genymobile.scrcpy_Microsoft.Winget.Source_8wekyb3d8bbwe\scrcpy-win64-v4.1\scrcpy.exe",
]
try:
    import adbutils
    candidatos_scrcpy.insert(1, os.path.join(os.path.dirname(adbutils.adb_path()), "scrcpy.exe"))
except Exception:
    pass

for c in candidatos_scrcpy:
    if os.path.exists(c):
        SCRCPY_PATH = c
        break

_lock_contas = threading.Lock()
_contas_em_uso = set()
_falhas_consecutivas_graph = {}

def gerar_senha_rockstar_dinamica():
    """Gera uma senha forte e única para cada conta Rockstar (13-15 chars, maiúsculas, minúsculas, números e símbolos)."""
    letras_maiusculas = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    letras_minusculas = "abcdefghjkmnpqrstuvwxyz"
    numeros = "23456789"
    simbolos = "!@#$*&"

    parte_obrigatoria = [
        random.choice(letras_maiusculas),
        random.choice(letras_minusculas),
        random.choice(numeros),
        random.choice(simbolos),
        random.choice(letras_maiusculas),
        random.choice(numeros)
    ]

    todos = letras_maiusculas + letras_minusculas + numeros + simbolos
    tamanho_total = random.randint(13, 15)
    restante = [random.choice(todos) for _ in range(tamanho_total - len(parte_obrigatoria))]

    senha_lista = parte_obrigatoria + restante
    random.shuffle(senha_lista)
    return "".join(senha_lista)

def tratar_resultado_conta_graph(conta, sucesso, status, secret_key, email_final, senha_final, nome, log_cb=None):
    email = conta.get("email", "").strip().lower()
    if sucesso:
        _falhas_consecutivas_graph.pop(email, None)
        senha_gravar = senha_final or conta.get("password", "") or gerar_senha_rockstar_dinamica()
        salvar_feita(email_final, senha_gravar, secret_key, log_cb)
        remover_conta_criar(conta)
        _contas_em_uso.discard(conta.get("email", "").strip())
        return True
    else:
        tentativas = _falhas_consecutivas_graph.get(email, 0) + 1
        _falhas_consecutivas_graph[email] = tentativas
        if tentativas < 2:
            _contas_em_uso.discard(conta.get("email", "").strip())
            if log_cb:
                log_cb(f"⚠️ {nome}: Rate limit/falha na conta ({tentativas}/2). Conta MANTIDA em outlook.txt para 2ª tentativa após intervalo/novo IP!")
        else:
            _falhas_consecutivas_graph.pop(email, None)
            salvar_erro(conta, f"{status} (2x falhas)", log_cb)
            _contas_em_uso.discard(conta.get("email", "").strip())
            if log_cb:
                log_cb(f"❌ {nome}: Conta falhou duas vezes seguidas. Salva em erro.txt e removida da fila.")
        return False

# ============================================================================
# IMPORT MHMDO (OPCIONAL — FALLBACK SE NÃO DISPONÍVEL)
# ============================================================================

_MHMDO_DISPONIVEL = False
try:
    from mhmdo_mail import MhmdoClient, obter_ou_gerar_email_mhmdo, marcar_email_mhmdo_consumido, descartar_email_mhmdo_invalido, aguardar_codigo_mhmdo
    from config import ROCKSTAR_DEFAULT_PASSWORD, PROXY_DATAIMPULSE
    _mhmdo_client_global = MhmdoClient()
    _MHMDO_DISPONIVEL = True
except ImportError:
    try:
        from config import PROXY_DATAIMPULSE, ROCKSTAR_DEFAULT_PASSWORD
    except ImportError:
        PROXY_DATAIMPULSE = {
            "server": "http://gw.dataimpulse.com:823",
            "username": "c9324c6bbdf5a1717a1c__cr.br",
            "password": "8c7a29423e9f74a1",
        }
        ROCKSTAR_DEFAULT_PASSWORD = "M@ik2025Roc!"
    _mhmdo_client_global = None

def consultar_saldo_mhmdo():
    """Consulta saldo mhmdo e retorna dict com info de cada tipo de email."""
    if not _MHMDO_DISPONIVEL or not _mhmdo_client_global:
        return None
    try:
        quota = _mhmdo_client_global.get_quota()
        if not quota:
            return None
        balance = quota.get('balance_usd', 0)
        return {
            'balance_usd': balance,
            'remaining': quota.get('remaining', 0),
            'used': quota.get('used', 0),
            'custom': int(balance / 0.001),   # $1 / 1.000
            'short': int(balance / 0.002),     # $2 / 1.000
            'full': int(balance / 0.006),      # $6 / 1.000
        }
    except Exception:
        return None

# ============================================================================
# GERADORES
# ============================================================================

def gerar_data_nascimento():
    ano = random.randint(1970, 2005)
    mes = random.randint(1, 12)
    dia = random.randint(1, calendar.monthrange(ano, mes)[1])
    return mes, dia, ano

def gerar_nickname():
    """Gera um nickname limpo, natural e 100% livre de bloqueios/profanidade da Rockstar."""
    prefixos = [
        "Shadow", "Vortex", "Falcon", "Krono", "Raptor", "Apex", "Titan", "Specter",
        "Strike", "Blaze", "Frost", "Pulse", "Cyber", "Drift", "Storm", "Volt",
        "Hyper", "Alpha", "Bravo", "Delta", "Echo", "Ghost", "Matrix", "Nexus",
        "Phantom", "Quantum", "Razor", "Savage", "Solar", "Turbo", "Viper", "Zero"
    ]
    sufixos = [
        "Pro", "Max", "Fox", "Wolf", "Hawk", "Rex", "Sky", "Jet", "Star", "Core",
        "Prime", "Tech", "Wave", "Gamer", "Force", "Fire", "Nova", "Knight"
    ]
    p = random.choice(prefixos)
    s = random.choice(sufixos)
    num = random.randint(100, 9999)
    nick = f"{p}{s}{num}"
    if len(nick) > 16:
        nick = f"{p}{num}"
    return nick

def gerar_totp(secret):
    secret = secret.replace(' ', '').replace('-', '').upper()
    padding = 8 - (len(secret) % 8)
    if padding != 8:
        secret += '=' * padding
    key = base64.b32decode(secret)
    counter = int(time.time()) // 30
    msg = struct.pack('>Q', counter)
    h = hmac.new(key, msg, hashlib.sha1).digest()
    offset = h[-1] & 0x0F
    code = struct.unpack('>I', h[offset:offset + 4])[0]
    code = (code & 0x7FFFFFFF) % 1000000
    return f"{code:06d}"

def _normalizar_texto(texto):
    if not texto:
        return ""
    texto = unicodedata.normalize('NFKD', str(texto))
    texto = ''.join(ch for ch in texto if not unicodedata.combining(ch))
    return texto.lower()

def _limpar_html(texto):
    if not texto:
        return ""
    import html as html_module
    texto = html_module.unescape(str(texto))
    texto = re.sub(r'(?is)<(script|style).*?>.*?</\1>', ' ', texto)
    texto = re.sub(r'(?is)<br\s*/?>', '\n', texto)
    texto = re.sub(r'(?is)</p\s*>', '\n', texto)
    texto = re.sub(r'(\d)\s*</\w+>\s*<\w+[^>]*>\s*(\d)', r'\1\2', texto)
    texto = re.sub(r'(?is)<[^>]+>', ' ', texto)
    texto = re.sub(r'[\t\r\f\v]+', ' ', texto)
    texto = re.sub(r'(\d)\s+(?=\d)', r'\1', texto)
    return texto.strip()

# ============================================================================
# GERENCIAMENTO DE CONTAS (CRIAR.TXT — MODO GRAPH API)
# ============================================================================

def parse_conta_linha(linha_s):
    """Interpreta linha JSON ou formato tabular email:senha:... com refresh_token para Graph API."""
    if not linha_s:
        return None
    linha_s = linha_s.strip()
    if not linha_s or linha_s.startswith("#"):
        return None
    try:
        obj = json.loads(linha_s)
        if isinstance(obj, dict) and obj.get("email"):
            return obj
    except Exception:
        pass

    if ":" in linha_s:
        partes = [p.strip() for p in linha_s.split(":")]
        email = partes[0]
        senha = partes[1] if len(partes) > 1 else ""
        client_id = "9e5f94bc-e8a4-4e73-b8be-63364c29d753"
        refresh_token = ""

        for p in partes[2:]:
            if re.match(r"^[0-9a-fA-F-]{32,36}$", p):
                client_id = p
            elif len(p) > 50:
                refresh_token = p
            elif not senha and p:
                senha = p

        return {
            "email": email,
            "password": senha,
            "graph_refresh_token": refresh_token,
            "thunderbird_client_id": client_id,
            "raw": linha_s
        }
    return None

def carregar_proxima_conta():
    with _lock_contas:
        if not os.path.exists(CRIAR_FILE):
            return None
        with open(CRIAR_FILE, "r", encoding="utf-8") as f:
            todas = f.readlines()
        for linha in todas:
            linha_s = linha.strip()
            if not linha_s or linha_s.startswith("#"):
                continue
            obj = parse_conta_linha(linha_s)
            if obj:
                email = obj.get("email", "").strip()
                if email and email not in _contas_em_uso:
                    _contas_em_uso.add(email)
                    return obj
        return None

def remover_conta_criar(conta):
    with _lock_contas:
        if not os.path.exists(CRIAR_FILE):
            return
        email_alvo = conta.get("email", "").strip().lower()
        if not email_alvo:
            return
        linhas_restantes = []
        removida = False
        with open(CRIAR_FILE, "r", encoding="utf-8") as f:
            todas = f.readlines()
        for linha in todas:
            linha_s = linha.strip()
            if not linha_s:
                continue
            if not removida:
                obj = parse_conta_linha(linha_s)
                if obj and obj.get("email", "").strip().lower() == email_alvo:
                    removida = True
                    continue
            linhas_restantes.append(linha)
        with open(CRIAR_FILE, "w", encoding="utf-8") as f:
            f.writelines(linhas_restantes)

def salvar_erro(conta, motivo="Erro", log_cb=None):
    with _lock_contas:
        with open(ERRO_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(conta, ensure_ascii=False) + "\n")
    remover_conta_criar(conta)
    if log_cb:
        log_cb(f"❌ Conta salva em erro.txt ({motivo})")

def salvar_feita(email, senha, secret_key, log_cb=None):
    with _lock_contas:
        secret_limpa = secret_key.replace(' ', '').replace('-', '')
        linha = f"{email}:{senha}:{secret_limpa}"
        with open(ROCKSTAR_FILE, "a", encoding="utf-8") as f:
            f.write(linha + "\n")
    if log_cb:
        log_cb(f"✅ Salvo em rockstar.txt: {linha}")
    return linha

_cache_contagem = {}

def contar_linhas(caminho):
    try:
        if not os.path.exists(caminho):
            return 0
        mtime = os.path.getmtime(caminho)
        cached = _cache_contagem.get(caminho)
        if cached and cached[0] == mtime:
            return cached[1]
        with open(caminho, "r", encoding="utf-8") as f:
            total = sum(1 for l in f if l.strip() and not l.startswith("#"))
        _cache_contagem[caminho] = (mtime, total)
        return total
    except Exception:
        return 0

_cache_rockstar = {"mtime": 0, "res": (0, 0, 0, 0)}

def contar_contas_rockstar():
    """Retorna (pendentes, prontas, erros, total) de contas em rockstar.txt."""
    try:
        if not os.path.exists(ROCKSTAR_FILE):
            return 0, 0, 0, 0
        mtime = os.path.getmtime(ROCKSTAR_FILE)
        if _cache_rockstar["mtime"] == mtime:
            return _cache_rockstar["res"]
        with open(ROCKSTAR_FILE, "r", encoding="utf-8") as f:
            linhas = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        prontas = sum(1 for l in linhas if "pronta" in l.lower())
        erros = sum(1 for l in linhas if "erro" in l.lower() and "pronta" not in l.lower())
        pendentes = sum(1 for l in linhas if "pronta" not in l.lower() and "erro" not in l.lower())
        res = (pendentes, prontas, erros, len(linhas))
        _cache_rockstar["mtime"] = mtime
        _cache_rockstar["res"] = res
        return res
    except Exception:
        return 0, 0, 0, 0

def carregar_proxima_conta_feita():
    """Lê a primeira conta disponível em rockstar.txt sem marcação de | pronta ou | erro."""
    with _lock_contas:
        if not os.path.exists(ROCKSTAR_FILE):
            return None
        with open(ROCKSTAR_FILE, "r", encoding="utf-8") as f:
            linhas = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        
        for linha in linhas:
            l_lower = linha.lower()
            if "| pronta" in l_lower or "| erro" in l_lower or "pronta" in l_lower:
                continue
            
            conteudo = linha.split("|")[0].strip()
            if ":" in conteudo:
                partes = conteudo.split(":")
                if len(partes) >= 3:
                    return {
                        "email": partes[0].strip(),
                        "password": partes[1].strip(),
                        "secret_key": partes[2].strip(),
                        "raw": linha
                    }
            try:
                obj = json.loads(conteudo)
                obj["raw"] = linha
                return obj
            except Exception:
                return {"email": conteudo, "password": "", "secret_key": "", "raw": linha}
        return None

def marcar_conta_pronta(conta, log_cb=None):
    """Marca a conta como '| pronta' em rockstar.txt."""
    with _lock_contas:
        if not os.path.exists(ROCKSTAR_FILE):
            return
        with open(ROCKSTAR_FILE, "r", encoding="utf-8") as f:
            linhas = f.readlines()
        
        raw = conta.get("raw", "")
        email = conta.get("email", "")
        novas_linhas = []
        marcou = False

        for l in linhas:
            l_strip = l.strip()
            if (raw and l_strip == raw) or (email and email in l_strip and "| pronta" not in l_strip.lower()):
                if not marcou:
                    base = l_strip.split("|")[0].strip()
                    novas_linhas.append(f"{base} | pronta\n")
                    marcou = True
                else:
                    novas_linhas.append(l)
            else:
                novas_linhas.append(l)
        
        if not marcou and raw:
            base = raw.split("|")[0].strip()
            novas_linhas.append(f"{base} | pronta\n")

        with open(ROCKSTAR_FILE, "w", encoding="utf-8") as f:
            f.writelines(novas_linhas)

    if log_cb:
        log_cb(f"🏷️ Conta {email} marcada como | pronta em rockstar.txt")

def marcar_conta_erro(conta, log_cb=None):
    """Marca a conta como '| erro' em rockstar.txt."""
    with _lock_contas:
        if not os.path.exists(ROCKSTAR_FILE):
            return
        with open(ROCKSTAR_FILE, "r", encoding="utf-8") as f:
            linhas = f.readlines()
        
        raw = conta.get("raw", "")
        email = conta.get("email", "")
        novas_linhas = []
        marcou = False

        for l in linhas:
            l_strip = l.strip()
            if (raw and l_strip == raw) or (email and email in l_strip and "| erro" not in l_strip.lower() and "| pronta" not in l_strip.lower()):
                if not marcou:
                    base = l_strip.split("|")[0].strip()
                    novas_linhas.append(f"{base} | erro\n")
                    marcou = True
                else:
                    novas_linhas.append(l)
            else:
                novas_linhas.append(l)

        with open(ROCKSTAR_FILE, "w", encoding="utf-8") as f:
            f.writelines(novas_linhas)

    if log_cb:
        log_cb(f"⚠️ Conta {email} marcada como | erro em rockstar.txt")

def carregar_proximo_codigo():
    """Lê o primeiro código de licença disponível em codigos.txt."""
    with _lock_contas:
        if not os.path.exists(CODIGOS_FILE):
            return None
        with open(CODIGOS_FILE, "r", encoding="utf-8") as f:
            linhas = [l.strip() for l in f if l.strip()]
        for linha in linhas:
            l_lower = linha.lower()
            if linha.startswith("#") or "| resgatado" in l_lower or "| erro" in l_lower or "resgatado" in l_lower:
                continue
            codigo = linha.split("|")[0].split(";")[0].strip()
            if codigo:
                return codigo
        return None

def marcar_codigo_resgatado(codigo, log_cb=None):
    """Marca o código como '| resgatado' em codigos.txt."""
    with _lock_contas:
        if not os.path.exists(CODIGOS_FILE):
            return
        with open(CODIGOS_FILE, "r", encoding="utf-8") as f:
            linhas = f.readlines()
        
        novas_linhas = []
        marcou = False
        codigo_limpo = codigo.strip()

        for l in linhas:
            l_strip = l.strip()
            if codigo_limpo in l_strip and "| resgatado" not in l_strip.lower() and not marcou:
                base = l_strip.split("|")[0].strip()
                novas_linhas.append(f"{base} | resgatado\n")
                marcou = True
            else:
                novas_linhas.append(l)

        if not marcou:
            novas_linhas.append(f"{codigo_limpo} | resgatado\n")

        with open(CODIGOS_FILE, "w", encoding="utf-8") as f:
            f.writelines(novas_linhas)
    
    if log_cb:
        log_cb(f"🏷️ Código {codigo_limpo} marcado como | resgatado em codigos.txt")

def marcar_codigo_erro(codigo, log_cb=None):
    """Marca o código como '| erro' em codigos.txt."""
    with _lock_contas:
        if not os.path.exists(CODIGOS_FILE):
            return
        with open(CODIGOS_FILE, "r", encoding="utf-8") as f:
            linhas = f.readlines()
        
        novas_linhas = []
        marcou = False
        codigo_limpo = codigo.strip()

        for l in linhas:
            l_strip = l.strip()
            if codigo_limpo in l_strip and "| erro" not in l_strip.lower() and "| resgatado" not in l_strip.lower() and not marcou:
                base = l_strip.split("|")[0].strip()
                novas_linhas.append(f"{base} | erro\n")
                marcou = True
            else:
                novas_linhas.append(l)

        with open(CODIGOS_FILE, "w", encoding="utf-8") as f:
            f.writelines(novas_linhas)

    if log_cb:
        log_cb(f"⚠️ Código {codigo_limpo} marcado como | erro em codigos.txt")

_cache_codigos = {"mtime": 0, "res": (0, 0)}

def contar_codigos_disponiveis():
    """Retorna a contagem de códigos em tempo real (disponíveis, resgatados)."""
    try:
        if not os.path.exists(CODIGOS_FILE):
            return 0, 0
        mtime = os.path.getmtime(CODIGOS_FILE)
        if _cache_codigos["mtime"] == mtime:
            return _cache_codigos["res"]
        with open(CODIGOS_FILE, "r", encoding="utf-8") as f:
            linhas = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        disp = 0
        resg = 0
        for l in linhas:
            l_lower = l.lower()
            if "resgatado" in l_lower or "usado" in l_lower:
                resg += 1
            elif "erro" not in l_lower:
                disp += 1
        res = (disp, resg)
        _cache_codigos["mtime"] = mtime
        _cache_codigos["res"] = res
        return res
    except Exception:
        return 0, 0

def salvar_pronta(email, senha, secret_key, codigo=None, log_cb=None):
    """Salva conta ativada com sucesso em prontas.txt no formato exato."""
    with _lock_contas:
        with open(PRONTAS_FILE, "a", encoding="utf-8") as f:
            linha = f"{email}:{senha}:{secret_key} - PRONTA"
            f.write(linha + "\n")
    if log_cb:
        log_cb(f"🏆 Conta ATIVADA e salva em prontas.txt: {email} - PRONTA")
    return linha

def limpar_cache_profundo_rockstar(log_cb=None):
    """Realiza limpeza profunda de caches, sessões, cookies e identificadores locais do Rockstar Games Launcher."""
    if log_cb: log_cb("🧹 Iniciando limpeza profunda do Rockstar Games Launcher...")
    
    # 1. Encerra todos os processos do Launcher e Social Club
    procs = ["Launcher.exe", "LauncherPatcher.exe", "SocialClubHelper.exe", "RockstarService.exe", "RockstarErrorHandler.exe"]
    for proc in procs:
        try:
            subprocess.run(f"taskkill /F /IM {proc} /T", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
    time.sleep(1.0)
    
    # 2. Diretórios completos de cache, CEF, AppData e dados de sessão
    dirs_para_limpar = [
        os.path.expandvars(r"%APPDATA%\Rockstar Games"),
        os.path.expandvars(r"%LOCALAPPDATA%\Rockstar Games"),
        os.path.expandvars(r"%USERPROFILE%\Documents\Rockstar Games"),
    ]
    
    import shutil
    removidos = 0
    for d in dirs_para_limpar:
        if os.path.exists(d):
            try:
                shutil.rmtree(d, ignore_errors=True)
                removidos += 1
            except Exception:
                pass

    # 3. Limpar chaves de registro HKCU da Rockstar
    try:
        subprocess.run(r'reg delete "HKCU\Software\Rockstar Games" /f', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
                
    # 4. Limpar DNS local
    try:
        subprocess.run("ipconfig /flushdns", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

    if log_cb: log_cb(f"✨ Limpeza profunda estilo Revo concluída! ({removidos} pastas e registros HKCU resetados)")
    return True

# ============================================================================
# RELAY LOCAL DE PROXY DATAIMPULSE (CRIAÇÃO & RESGATE) COM ROTAÇÃO DE IP
# ============================================================================

LOCAL_PROXY_PORT = 18899
_local_proxy_started = False
_local_proxy_lock = threading.Lock()
_proxy_session_lock = threading.Lock()

def rotacionar_ip_dataimpulse(log_cb=None):
    """Proxy desativado."""
def fechar_rockstar_launcher(log_cb=None):
    """Encerra todos os processos do Rockstar Games Launcher de forma limpa."""
    if log_cb: log_cb("🚪 Fechando Rockstar Games Launcher...")
    procs = ["Launcher.exe", "LauncherPatcher.exe", "SocialClubHelper.exe", "RockstarService.exe", "RockstarErrorHandler.exe"]
    for proc in procs:
        try:
            subprocess.run(f"taskkill /F /IM {proc} /T", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
    time.sleep(1.5)

def abrir_rockstar_launcher(log_cb=None):
    """Localiza e abre o executável oficial do Rockstar Games Launcher via shell do Windows."""
    caminhos = [
        os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Rockstar Games\Rockstar Games Launcher.lnk"),
        r"C:\Program Files\Rockstar Games\Launcher\LauncherPatcher.exe",
        r"C:\Program Files\Rockstar Games\Launcher\Launcher.exe",
        r"C:\Program Files (x86)\Rockstar Games\Launcher\LauncherPatcher.exe",
        r"C:\Program Files (x86)\Rockstar Games\Launcher\Launcher.exe",
        r"D:\Rockstar Games\Launcher\LauncherPatcher.exe",
        r"D:\Rockstar Games\Launcher\Launcher.exe",
    ]
    for p in caminhos:
        if os.path.exists(p):
            if log_cb: log_cb("🚀 Abrindo Rockstar Games Launcher...")
            try:
                os.startfile(p)
                return True
            except Exception:
                try:
                    subprocess.Popen([p], cwd=os.path.dirname(p))
                    return True
                except Exception:
                    pass
    if log_cb: log_cb("⚠️ Rockstar Games Launcher não encontrado nas pastas padrão!")
    return False

import pyautogui
import pyperclip
pyautogui.FAILSAFE = False

def obter_hwnd_launcher():
    """Localiza a janela principal do Rockstar Games Launcher (tela de login ou dashboard), descartando janelas de fundo fullscreen."""
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    melhor_hwnd = None
    max_score = -1

    screen_w = user32.GetSystemMetrics(0)
    screen_h = user32.GetSystemMetrics(1)

    # 1. PIDs do ecossistema Rockstar via snapshot (funciona mesmo com Launcher como Administrador)
    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ('dwSize', wintypes.DWORD),
            ('cntUsage', wintypes.DWORD),
            ('th32ProcessID', wintypes.DWORD),
            ('th32DefaultHeapID', ctypes.c_size_t),
            ('th32ModuleID', wintypes.DWORD),
            ('cntThreads', wintypes.DWORD),
            ('th32ParentProcessID', wintypes.DWORD),
            ('pcPriClassBase', ctypes.c_long),
            ('dwFlags', wintypes.DWORD),
            ('szExeFile', ctypes.c_char * 260)
        ]

    pids_rockstar = {}
    hSnap = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    if hSnap != -1:
        pe = PROCESSENTRY32()
        pe.dwSize = ctypes.sizeof(PROCESSENTRY32)
        if kernel32.Process32First(hSnap, ctypes.byref(pe)):
            while True:
                name = pe.szExeFile.decode('latin1', errors='ignore').lower()
                if name in ['launcher.exe', 'socialclubhelper.exe', 'launcherpatcher.exe'] or 'rockstar' in name:
                    pids_rockstar[pe.th32ProcessID] = name
                if not kernel32.Process32Next(hSnap, ctypes.byref(pe)):
                    break
        kernel32.CloseHandle(hSnap)

    # 2. Busca direta por títulos padrão do Rockstar Launcher
    for tit in ["Rockstar Games Launcher", "Rockstar Games", "Social Club"]:
        h = user32.FindWindowW(None, tit)
        if h and user32.IsWindowVisible(h) and not user32.IsIconic(h):
            r = wintypes.RECT()
            user32.GetWindowRect(h, ctypes.byref(r))
            w = r.right - r.left
            h_len = r.bottom - r.top
            if 400 < w < (screen_w - 50) and 300 < h_len < (screen_h - 50):
                return h

    # 3. Varredura com EnumWindows
    def _f_cb(h, l):
        nonlocal melhor_hwnd, max_score
        if user32.IsWindowVisible(h) and not user32.IsIconic(h):
            cls_buf = ctypes.create_unicode_buffer(260)
            user32.GetClassNameW(h, cls_buf, 260)
            cls_name = cls_buf.value.lower()
            if cls_name in ["progman", "workerw", "shell_traywnd"]:
                return True

            r = wintypes.RECT()
            user32.GetWindowRect(h, ctypes.byref(r))
            w = r.right - r.left
            h_len = r.bottom - r.top

            # Descarta janelas minúsculas e a janela preta host que cobre a tela inteira
            if w > 400 and h_len > 300:
                if w >= (screen_w - 50) and h_len >= (screen_h - 50):
                    return True

                length = user32.GetWindowTextLengthW(h)
                title = ""
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(h, buff, length + 1)
                    title = buff.value.lower()

                # Ignora a janela do próprio painel
                if "pokas ideia" in title:
                    return True

                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
                pname = pids_rockstar.get(pid.value, "")

                is_launcher = bool(pname)
                if not is_launcher and title:
                    if ("rockstar" in title or "social club" in title) and "chrome" not in title and "visual studio" not in title:
                        is_launcher = True

                if is_launcher:
                    # Checa se esta janela possui o logo amarelo da Rockstar (dashboard)
                    tem_logo = False
                    try:
                        from PIL import ImageGrab
                        im_l = ImageGrab.grab(bbox=(r.left + 5, r.top + 15, r.left + 75, r.top + 75))
                        yellows = sum(1 for y in range(im_l.height) for x in range(im_l.width) if im_l.getpixel((x, y))[0] > 200 and im_l.getpixel((x, y))[1] > 130 and im_l.getpixel((x, y))[2] < 50)
                        if yellows > 25:
                            tem_logo = True
                    except Exception:
                        pass

                    score = w * h_len
                    if tem_logo:
                        score += 50000000
                    if pname == "launcher.exe":
                        score += 20000000
                    elif pname == "socialclubhelper.exe":
                        score += 15000000
                    if "rockstar games launcher" in title:
                        score += 10000000

                    if score > max_score:
                        max_score = score
                        melhor_hwnd = h
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(_f_cb), 0)
    return melhor_hwnd

def trazer_janela_frente(hwnd=None):
    """Força a janela do Rockstar Games Launcher ao primeiro plano sem tirar o foco de campos de texto."""
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    if not hwnd:
        hwnd = obter_hwnd_launcher()

    if hwnd:
        try:
            fore_hwnd = user32.GetForegroundWindow()
            if fore_hwnd == hwnd:
                return

            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            else:
                user32.ShowWindow(hwnd, 5)  # SW_SHOW

            curr_tid = kernel32.GetCurrentThreadId()
            fore_tid = user32.GetWindowThreadProcessId(fore_hwnd, None)
            target_tid = user32.GetWindowThreadProcessId(hwnd, None)

            if fore_tid != curr_tid:
                try: user32.AttachThreadInput(curr_tid, fore_tid, True)
                except Exception: pass
            if target_tid != curr_tid:
                try: user32.AttachThreadInput(curr_tid, target_tid, True)
                except Exception: pass

            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)

            if fore_tid != curr_tid:
                try: user32.AttachThreadInput(curr_tid, fore_tid, False)
                except Exception: pass
            if target_tid != curr_tid:
                try: user32.AttachThreadInput(curr_tid, target_tid, False)
                except Exception: pass
        except Exception:
            pass

def aguardar_janela_launcher(log_cb=None, timeout=30, manager=None):
    """Aguarda até que a janela do Rockstar Games Launcher esteja visível e pronta."""
    if log_cb: log_cb("🔍 Aguardando carregamento do Rockstar Games Launcher...")
    
    inicio = time.time()
    while time.time() - inicio < timeout:
        if manager and not manager.redeem_running:
            return None
            
        launcher_hwnd = obter_hwnd_launcher()
        if launcher_hwnd:
            trazer_janela_frente(launcher_hwnd)
            time.sleep(0.5)
            if log_cb: log_cb("🖥️ Rockstar Games Launcher detectado e focado!")
            return launcher_hwnd

        time.sleep(0.5)

    if log_cb: log_cb("⚠️ Prosseguindo para preenchimento...")
    return None

def aguardar_campo_email_launcher(launcher_hwnd, log_cb=None, timeout=30, manager=None):
    """Garante que a janela está na frente e pronta para receber digitação."""
    trazer_janela_frente(launcher_hwnd)
    time.sleep(0.5)
    return True

def checar_rate_limit_login(log_cb=None):
    """Verifica com máxima cautela se a faixa vermelha de erro #1.000.7 apareceu na área de notificação do Launcher."""
    try:
        from PIL import ImageGrab
        launcher_hwnd = obter_hwnd_launcher()
        if not launcher_hwnd:
            return False
            
        user32 = ctypes.windll.user32
        rect = wintypes.RECT()
        user32.GetWindowRect(launcher_hwnd, ctypes.byref(rect))
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        if w < 300 or h < 300:
            return False

        # Captura apenas a área interna central do formulário do Launcher (evitando banners de jogos e bordas)
        x1 = max(0, rect.left + int(w * 0.15))
        y1 = max(0, rect.top + int(h * 0.10))
        x2 = max(0, rect.left + int(w * 0.85))
        y2 = max(0, rect.top + int(h * 0.28))  # Notificação no topo (evita falsos positivos em campos de senha/2fa)
        
        im = ImageGrab.grab(bbox=(x1, y1, x2, y2))
        
        # Varredura horizontal por faixa vermelha larga e contínua do erro oficial #1.000.7
        for y in range(0, im.height, 4):
            consecutive = 0
            for x in range(0, im.width, 3):
                p = im.getpixel((x, y))
                # Vermelho característico da faixa de alerta da Rockstar
                if p[0] > 145 and p[1] < 35 and p[2] < 35:
                    consecutive += 1
                    if consecutive >= 40:  # ~120px contínuos de faixa de alerta
                        if log_cb: log_cb("🚨 Erro #1.000.7 detectado no Launcher! Acionando pausa de 2 minutos, limpeza profunda e troca de IP...")
                        return True
                else:
                    consecutive = 0
    except Exception:
        pass
    return False

def localizar_tela_login(launcher_hwnd=None):
    """
    Localiza os elementos da tela de login do Launcher (campo de e-mail, senha e botão amarelo 'Iniciar sessão').
    Retorna (is_login: bool, coords_dict: dict).
    """
    coords_padrao = None
    try:
        user32 = ctypes.windll.user32
        if not launcher_hwnd:
            launcher_hwnd = obter_hwnd_launcher()
        if not launcher_hwnd:
            return False, None

        rect = wintypes.RECT()
        user32.GetWindowRect(launcher_hwnd, ctypes.byref(rect))
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        if w < 300 or h < 300:
            return False, None

        # Coordenadas calibradas seguras baseadas na geometria do Launcher
        coords_padrao = {
            "btn_login": (rect.left + int(w * 0.72), rect.top + int(h * 0.66)),
            "campo_email": (rect.left + int(w * 0.50), rect.top + int(h * 0.38)),
            "campo_senha": (rect.left + int(w * 0.50), rect.top + int(h * 0.50))
        }

        from PIL import ImageGrab
        x1 = max(0, rect.left)
        y1 = max(0, rect.top)
        x2 = max(0, rect.right)
        y2 = max(0, rect.bottom)
        im = ImageGrab.grab(bbox=(x1, y1, x2, y2))

        white_card = 0
        yellow_xs, yellow_ys = [], []

        # Varre a área central onde o card branco de login e o botão amarelo residem
        for y in range(int(h * 0.25), int(h * 0.85), 3):
            for x in range(int(w * 0.25), int(w * 0.85), 3):
                p = im.getpixel((x, y))
                # Fundo branco puro do card de login da Rockstar
                if p[0] > 245 and p[1] > 245 and p[2] > 245:
                    white_card += 1
                # Botão amarelo/laranja 'Iniciar sessão'
                elif p[0] > 200 and 130 < p[1] < 220 and p[2] < 70:
                    yellow_xs.append(x1 + x)
                    yellow_ys.append(y1 + y)

        if len(yellow_xs) >= 8:
            coords_padrao["btn_login"] = (sum(yellow_xs) // len(yellow_xs), sum(yellow_ys) // len(yellow_ys))

        # A tela de login tem o card branco central E o botão amarelo
        is_login = (white_card > 400 and len(yellow_xs) >= 8)
        return is_login, coords_padrao
    except Exception:
        pass
    return False, coords_padrao

def checar_tela_login_ativa(log_cb=None, launcher_hwnd=None):
    """Verifica se o botão amarelo/laranja 'Iniciar sessão' da Rockstar está ativo na tela do Launcher."""
    is_login, _ = localizar_tela_login(launcher_hwnd=launcher_hwnd)
    return is_login

def focar_janela_launcher(log_cb=None):
    return aguardar_janela_launcher(log_cb=log_cb, timeout=15)

def _sleep_check(segundos, manager=None):
    """Aguarda em intervalos de 100ms, abortando imediatamente se redeem_running for False."""
    passos = int(max(0.1, segundos) * 10)
    for _ in range(passos):
        if manager and not manager.redeem_running:
            return False
        time.sleep(0.1)
    return True

def localizar_avatar_launcher(launcher_hwnd):
    """Localiza o centro do círculo do avatar no canto superior direito do Launcher."""
    try:
        from PIL import ImageGrab
        user32 = ctypes.windll.user32
        rect = wintypes.RECT()
        user32.GetWindowRect(launcher_hwnd, ctypes.byref(rect))
        
        # Área restrita ao topo direito onde o avatar reside
        x1 = rect.right - 110
        y1 = rect.top + 35
        x2 = rect.right - 20
        y2 = rect.top + 95

        im = ImageGrab.grab(bbox=(x1, y1, x2, y2))
        xs, ys = [], []
        for y in range(im.height):
            for x in range(im.width):
                p = im.getpixel((x, y))
                # Círculo branco do avatar sobre o fundo escuro/vermelho do header
                if p[0] > 190 and p[1] > 190 and p[2] > 190:
                    xs.append(x)
                    ys.append(y)

        if len(xs) > 30:
            cx = x1 + sum(xs) // len(xs)
            cy = y1 + sum(ys) // len(ys)
            return cx, cy
    except Exception:
        pass
    
    # Ponto geométrico padrão calibrado
    rect = wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(launcher_hwnd, ctypes.byref(rect))
    return (rect.right - 58, rect.top + 65)

def aguardar_conclusao_2fa(launcher_hwnd, timeout=45, log_cb=None, manager=None):
    """Aguarda até que a tela/modal de 2FA desapareça por completo após o envio do código."""
    if log_cb: log_cb("⏳ Aguardando autenticação do código 2FA e resposta dos servidores da Rockstar...")
    user32 = ctypes.windll.user32
    inicio = time.time()
    
    if launcher_hwnd:
        trazer_janela_frente(launcher_hwnd)

    time.sleep(1.5)
    
    while time.time() - inicio < timeout:
        if manager and not manager.redeem_running:
            return False

        if checar_rate_limit_login(log_cb=log_cb):
            return False

        try:
            from PIL import ImageGrab
            active_h = obter_hwnd_launcher() or launcher_hwnd
            rect = wintypes.RECT()
            user32.GetWindowRect(active_h, ctypes.byref(rect))
            w = rect.right - rect.left
            h = rect.bottom - rect.top

            x1 = max(0, rect.left)
            y1 = max(0, rect.top)
            x2 = max(0, rect.right)
            y2 = max(0, rect.bottom)
            im = ImageGrab.grab(bbox=(x1, y1, x2, y2))

            orange_center = 0
            for y in range(int(h * 0.78), int(h * 0.98), 2):
                for x in range(int(w * 0.38), int(w * 0.62), 2):
                    p = im.getpixel((x, y))
                    if p[0] > 180 and 100 < p[1] < 180 and p[2] < 50:
                        orange_center += 1

            # Quando o modal de 2FA fecha, o link 'Voltar para o início de sessão' desaparece
            if orange_center < 10:
                if log_cb: log_cb("🎉 Autenticação 2FA concluída! Modal encerrado pelos servidores.")
                time.sleep(1.0)
                return True

        except Exception:
            pass

        time.sleep(0.5)

    if log_cb: log_cb("⚠️ Timeout aguardando validação do 2FA.")
    return False

def aguardar_resposta_login(launcher_hwnd, tem_2fa=True, timeout=45, log_cb=None, manager=None):
    """
    Aguarda ativamente a resposta e transição de tela após submeter o login.
    Monitora até o surgimento do modal de 2FA, do Dashboard ou de erro/rate limit.
    """
    if log_cb: log_cb("⏳ Aguardando processamento e resposta dos servidores da Rockstar...")
    user32 = ctypes.windll.user32
    inicio = time.time()
    
    # Dá 1.5s inicial para o envio ser despachado
    time.sleep(1.5)

    while time.time() - inicio < timeout:
        if manager and not manager.redeem_running:
            return None

        # 1. Monitora erro de rate limit (#1.000.7) no topo
        if checar_rate_limit_login(log_cb=log_cb):
            return "rate_limit"

        active_h = obter_hwnd_launcher() or launcher_hwnd
        if active_h:
            try:
                from PIL import ImageGrab
                rect = wintypes.RECT()
                user32.GetWindowRect(active_h, ctypes.byref(rect))
                w = rect.right - rect.left
                h = rect.bottom - rect.top

                if w > 300 and h > 300:
                    x1 = max(0, rect.left)
                    y1 = max(0, rect.top)
                    x2 = max(0, rect.right)
                    y2 = max(0, rect.bottom)
                    im = ImageGrab.grab(bbox=(x1, y1, x2, y2))

                    # 2. Verifica se a tela de 2FA apareceu (Modal branco com link centralizado 'Voltar para o início de sessão')
                    if tem_2fa:
                        orange_center = 0
                        for y in range(int(h * 0.78), int(h * 0.98), 2):
                            for x in range(int(w * 0.38), int(w * 0.62), 2):
                                p = im.getpixel((x, y))
                                if p[0] > 180 and 100 < p[1] < 180 and p[2] < 50:
                                    orange_center += 1

                        if orange_center >= 20:
                            if log_cb: log_cb("🔐 Tela de autenticação 2FA carregada com sucesso!")
                            time.sleep(1.0)
                            return "2fa"

                    # 3. Verifica se logou direto no Dashboard (avatar presente no topo direito)
                    av_x1 = max(0, int(w * 0.85))
                    av_y1 = int(h * 0.04)
                    av_x2 = max(0, int(w * 0.98))
                    av_y2 = int(h * 0.15)
                    xs, ys = [], []
                    for y in range(av_y1, min(h, av_y2)):
                        for x in range(av_x1, min(w, av_x2)):
                            p = im.getpixel((x, y))
                            if p[0] > 190 and p[1] > 190 and p[2] > 190:
                                xs.append(x)
                                ys.append(y)
                    if len(xs) > 30:
                        cx = rect.left + sum(xs) // len(xs)
                        cy = rect.top + sum(ys) // len(ys)
                        if log_cb: log_cb(f"✅ Dashboard carregado diretamente sem 2FA! Avatar detectado ({cx}, {cy}).")
                        return "dashboard"

                    # 4. Verifica se surgiu faixa vermelha de erro de formulário na tela de login
                    red_form = 0
                    for y in range(int(h * 0.30), int(h * 0.65), 3):
                        for x in range(int(w * 0.20), int(w * 0.80), 3):
                            p = im.getpixel((x, y))
                            if p[0] > 160 and p[1] < 40 and p[2] < 40:
                                red_form += 1
                    if red_form > 40:
                        if log_cb: log_cb("❌ Erro no formulário de login (e-mail inválido ou senha incorreta).")
                        return "form_error"

            except Exception:
                pass

        time.sleep(0.5)

    if log_cb: log_cb("⚠️ Timeout aguardando resposta da Rockstar. Prosseguindo...")
    return "timeout"

def aguardar_avatar_launcher(launcher_hwnd, timeout=35, log_cb=None, manager=None):
    """Aguarda ativamente até que o avatar branco do perfil apareça no topo direito do Launcher pós-login."""
    user32 = ctypes.windll.user32
    inicio = time.time()
    
    # Foca uma única vez antes de iniciar o loop de detecção
    if launcher_hwnd:
        trazer_janela_frente(launcher_hwnd)

    while time.time() - inicio < timeout:
        if manager and not manager.redeem_running:
            return None

        # Checa se deu erro de rate limit durante o login
        if checar_rate_limit_login(log_cb=log_cb):
            return None

        try:
            from PIL import ImageGrab
            active_h = obter_hwnd_launcher() or launcher_hwnd
            rect = wintypes.RECT()
            user32.GetWindowRect(active_h, ctypes.byref(rect))

            # Área do avatar no canto superior direito
            x1 = rect.right - 120
            y1 = rect.top + 30
            x2 = rect.right - 15
            y2 = rect.top + 100

            im = ImageGrab.grab(bbox=(x1, y1, x2, y2))
            xs, ys = [], []
            for y in range(im.height):
                for x in range(im.width):
                    p = im.getpixel((x, y))
                    if p[0] > 190 and p[1] > 190 and p[2] > 190:
                        xs.append(x)
                        ys.append(y)

            # Avatar branco renderizado com nitidez
            if len(xs) > 30:
                cx = x1 + sum(xs) // len(xs)
                cy = y1 + sum(ys) // len(ys)
                if log_cb: log_cb(f"✅ Dashboard carregado! Avatar do perfil detectado ({cx}, {cy}). Estabilizando (2s)...")
                if not _sleep_check(2.0, manager): return None
                return cx, cy
        except Exception:
            pass

        time.sleep(0.4)

    # Se atingiu o timeout, usa a geometria padrão calibrada
    rect = wintypes.RECT()
    user32.GetWindowRect(launcher_hwnd, ctypes.byref(rect))
    if log_cb: log_cb("⚠️ Timeout aguardando renderização do avatar. Prosseguindo com coordenadas calibradas...")
    return (rect.right - 58, rect.top + 65)

def executar_fluxo_resgate_codigo(pw, conta, codigo, log_cb=None, manager=None, precisa_fechar_popup=False, is_primeira_conta=False):
    """Realiza login automático com 2FA TOTP e ativa o código de jogo diretamente pelo Launcher oficial."""
    email = conta.get("email", "")
    senha = conta.get("password", "")
    secret_key = conta.get("secret_key", "")
    nome = email.split("@")[0]

    if log_cb: log_cb(f"🔑 [Resgate Launcher] Iniciando ativação para {email} | Chave: {codigo}")

    try:
        # Garante que a janela do Launcher está aberta (abrindo do zero se necessário)
        hwnd = obter_hwnd_launcher()
        if not hwnd:
            if log_cb: log_cb("🚀 Abrindo Rockstar Games Launcher para nova conta...")
            abrir_rockstar_launcher(log_cb)
            hwnd = aguardar_janela_launcher(log_cb=log_cb, timeout=45, manager=manager)
        if hwnd:
            trazer_janela_frente(hwnd)
            time.sleep(0.5)

        # Aguarda a tela de login carregar por completo
        if log_cb: log_cb(f"⏳ {nome}: Aguardando tela de login carregar...")
        is_login, _ = localizar_tela_login(hwnd)
        if not is_login:
            for _ in range(30):
                if manager and not manager.redeem_running: return False
                time.sleep(0.5)
                is_login, _ = localizar_tela_login(hwnd)
                if is_login:
                    time.sleep(1.0)
                    break

        trazer_janela_frente(hwnd)
        time.sleep(0.3)

        # Preenchimento estritamente via teclado conforme especificado:
        # O Launcher abriu do zero: o campo de E-mail já vem selecionado nativamente!
        if log_cb: log_cb(f"✍️ {nome}: Digitando e-mail ({email})...")
        pyautogui.write(email, interval=0.01)
        if not _sleep_check(0.2, manager): return False

        # 1x TAB e insere a senha
        if log_cb: log_cb(f"🔑 {nome}: Pressionando TAB e digitando senha...")
        pyautogui.press('tab')
        time.sleep(0.2)
        pyautogui.write(senha, interval=0.01)
        if not _sleep_check(0.2, manager): return False

        # 4x TAB para alcançar o botão 'Iniciar sessão' e confirma com ENTER
        if log_cb: log_cb("⚡ Navegando até 'Iniciar sessão' (4x TAB) e enviando (ENTER)...")
        for _ in range(4):
            if not manager or manager.redeem_running:
                pyautogui.press('tab')
                time.sleep(0.15)
        pyautogui.press('enter')

        # Aguarda dinamicamente os servidores responderem e a tela de 2FA ou Dashboard carregar
        status_login = aguardar_resposta_login(
            hwnd, 
            tem_2fa=bool(secret_key), 
            timeout=45, 
            log_cb=log_cb, 
            manager=manager
        )
        if not status_login or status_login in ["rate_limit", "form_error", "timeout"]:
            if log_cb: log_cb(f"❌ {nome}: Login não prosseguiu ({status_login}). Abortando resgate desta conta.")
            return False

        # 7. Resolver 2FA TOTP (somente após o modal de 2FA estar completamente carregado)
        if status_login == "2fa":
            if not secret_key:
                if log_cb: log_cb(f"❌ {nome}: Modal 2FA exigido, mas a conta não possui secret_key em rockstar.txt!")
                return False
            totp = gerar_totp(secret_key)

            # O campo de código de verificação já está selecionado: apenas digita o código e prossegue
            if log_cb: log_cb(f"🔢 {nome}: Digitando código de verificação 2FA ({totp})...")
            time.sleep(0.2)
            pyautogui.write(totp, interval=0.02)
            if not _sleep_check(0.3, manager): return False

            # Navega 2x TAB até o botão 'Enviar' e confirma com ENTER
            if log_cb: log_cb("➡️ Navegando até o botão de envio 2FA (2x TAB)...")
            for _ in range(2):
                if not manager or manager.redeem_running:
                    pyautogui.press('tab')
                    time.sleep(0.2)
            if log_cb: log_cb("⚡ Enviando código 2FA (ENTER)...")
            pyautogui.press('enter')

            # Aguarda a validação do 2FA pelo servidor da Rockstar até o modal sumir por completo
            if not aguardar_conclusao_2fa(hwnd, timeout=45, log_cb=log_cb, manager=manager):
                return False

            # Monitora se após o 2FA surgiu o erro #1.000.7
            if checar_rate_limit_login(log_cb=log_cb):
                return False

        # Garante que o Launcher está em primeiro plano absoluto
        launcher_hwnd = obter_hwnd_launcher()
        if launcher_hwnd:
            trazer_janela_frente(launcher_hwnd)
            time.sleep(0.5)

        # Checagem de segurança antes de tentar resgatar código
        if checar_rate_limit_login(log_cb=log_cb):
            return False

        # 9. Aguarda o dashboard carregar por completo e o avatar estar visível
        if log_cb: log_cb("⏳ Aguardando carregamento completo do painel da Rockstar pós-login...")
        av_coords = aguardar_avatar_launcher(launcher_hwnd, timeout=35, log_cb=log_cb, manager=manager)
        if not av_coords:
            if log_cb: log_cb("❌ Não foi possível carregar o dashboard do Launcher a tempo.")
            return False
        av_x, av_y = av_coords

        if log_cb: log_cb(f"👤 Abrindo menu do perfil clicando no avatar ({av_x}, {av_y})...")
        pyautogui.moveTo(av_x, av_y, duration=0.2)
        pyautogui.click()
        if not _sleep_check(1.0, manager): return False

        # 10. Entrar na tela de Resgate de Código (1x TAB + ENTER)
        if log_cb: log_cb("➡️ Selecionando 'RESGATAR CÓDIGO' no menu suspenso (1x TAB + ENTER)...")
        pyautogui.press('tab')
        time.sleep(0.25)
        pyautogui.press('enter')
        if not _sleep_check(2.5, manager): return False

        # 11. Inserir código de resgate (2x TAB -> digitar código -> 1x TAB -> ENTER)
        if log_cb: log_cb(f"🔑 {nome}: Inserindo código de ativação ({codigo})...")
        pyautogui.press('tab')
        time.sleep(0.15)
        pyautogui.press('tab')
        time.sleep(0.2)
        pyautogui.press('backspace', presses=30, interval=0.005)
        time.sleep(0.1)
        pyautogui.write(codigo, interval=0.01)
        if not _sleep_check(0.3, manager): return False

        if log_cb: log_cb("➡️ Clicando em VERIFICAR (1x TAB + ENTER)...")
        pyautogui.press('tab')
        time.sleep(0.2)
        pyautogui.press('enter')
        if not _sleep_check(3.0, manager): return False

        # 12. Marcar Checkbox de vinculação (1x TAB -> SPACE -> 1x TAB -> ENTER)
        if log_cb: log_cb("➡️ Focando e marcando checkbox de vinculação (1x TAB + SPACE)...")
        pyautogui.press('tab')
        time.sleep(0.3)
        pyautogui.press('space')
        if not _sleep_check(0.4, manager): return False

        if log_cb: log_cb("⚡ Confirmando resgate final do jogo (1x TAB + ENTER)...")
        pyautogui.press('tab')
        time.sleep(0.3)
        pyautogui.press('enter')
        if not _sleep_check(3.5, manager): return False

        # 13. Fechar tela de sucesso (1x TAB -> ENTER / ESC)
        if log_cb: log_cb("➡️ Fechando modal de confirmação (1x TAB + ENTER)...")
        pyautogui.press('tab')
        time.sleep(0.3)
        pyautogui.press('enter')
        time.sleep(0.5)
        pyautogui.press('esc')
        if not _sleep_check(1.5, manager): return False

        # 14. Salvar e Marcar
        salvar_pronta(email, senha, secret_key, codigo=codigo, log_cb=log_cb)
        marcar_codigo_resgatado(codigo, log_cb=log_cb)
        marcar_conta_pronta(conta, log_cb=log_cb)
        if log_cb: log_cb(f"🏆 {nome}: Conta salva em prontas.txt e código {codigo} resgatado com sucesso!")

        # 15. Fecha o Launcher diretamente conforme solicitado (sem necessidade de encerrar sessão manual)
        fechar_rockstar_launcher(log_cb)
        time.sleep(1.0)

        return True

    except Exception as e:
        if log_cb: log_cb(f"❌ {nome}: Erro no fluxo do Launcher: {e}")
        return False

# ============================================================================
# GRAPH API — BUSCAR CÓDIGO DE VERIFICAÇÃO (MODO GRAPH)
# ============================================================================

def extrair_codigo_rockstar(texto):
    texto = _normalizar_texto(texto)
    texto = re.sub(r'(\d)[\s\u00a0\u200b]+(?=\d)', r'\1', texto)
    padroes = [
        r'verification\s*code\s*[:#\-]?\s*(\d{4,8})\b',
        r'\bcode\s*[:#\-]?\s*(\d{4,8})\b',
        r'codigo\s*[:#\-]?\s*(\d{4,8})\b',
        r'\bis\s*[:\-]?\s*(\d{4,8})\b',
        r'\b(\d{6})\b',
        r'\b(\d{8})\b',
    ]
    for padrao in padroes:
        match = re.search(padrao, texto, re.IGNORECASE)
        if match:
            return match.group(1)
    return None

def _graph_refresh_token(refresh_token, client_id):
    url = 'https://login.microsoftonline.com/common/oauth2/v2.0/token'
    data = urllib.parse.urlencode({
        'client_id': client_id,
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
        'scope': 'https://graph.microsoft.com/Mail.Read offline_access',
    }).encode('utf-8')
    req = urllib.request.Request(url, data=data, method='POST')
    req.add_header('Content-Type', 'application/x-www-form-urlencoded')
    with urllib.request.urlopen(req, timeout=15) as resp:
        resultado = json.loads(resp.read().decode('utf-8'))
    return resultado.get('access_token'), resultado.get('refresh_token', refresh_token)

def _graph_buscar_emails(access_token, top=30):
    url = f'https://graph.microsoft.com/v1.0/me/messages?$top={top}&$orderby=receivedDateTime%20desc&$select=subject,from,body,receivedDateTime'
    req = urllib.request.Request(url, method='GET')
    req.add_header('Authorization', f'Bearer {access_token}')
    with urllib.request.urlopen(req, timeout=15) as resp:
        resultado = json.loads(resp.read().decode('utf-8'))
    return resultado.get('value', [])

def buscar_codigo_graph(conta, nome, log_cb=None, timeout=90):
    graph_rt = conta.get('graph_refresh_token', '').strip()
    client_id = conta.get('thunderbird_client_id', '9e5f94bc-e8a4-4e73-b8be-63364c29d753').strip()
    if not graph_rt:
        if log_cb: log_cb(f"❌ {nome}: Sem graph_refresh_token na conta!")
        return None

    filtros = ['rockstar', 'rockstargames', 'verification', 'code', 'codigo']
    inicio = time.time()
    corte_ts = inicio - 180
    access_token = None
    erros_400 = 0

    while time.time() - inicio < timeout:
        try:
            if access_token is None:
                if log_cb: log_cb(f"   🔄 {nome}: Renovando token Graph API...")
                access_token, _ = _graph_refresh_token(graph_rt, client_id)
                if log_cb: log_cb(f"   ✅ {nome}: Token renovado!")

            emails = _graph_buscar_emails(access_token)
            if not emails:
                time.sleep(3)
                continue

            for msg in emails:
                received_str = msg.get('receivedDateTime', '')
                if received_str:
                    try:
                        parts = received_str.rstrip('Z').split('.')[0]
                        t_struct = time.strptime(parts, '%Y-%m-%dT%H:%M:%S')
                        email_ts = calendar.timegm(t_struct)
                        if email_ts < corte_ts:
                            continue
                    except Exception:
                        pass
                subject = msg.get('subject', '') or ''
                from_obj = msg.get('from', {}) or {}
                from_email = ''
                if from_obj.get('emailAddress'):
                    from_email = from_obj['emailAddress'].get('address', '')
                texto_filtro = _normalizar_texto(from_email + ' ' + subject)
                if not any(f in texto_filtro for f in filtros):
                    continue
                body_obj = msg.get('body', {}) or {}
                body_content = body_obj.get('content', '') or ''
                content_type = body_obj.get('contentType', 'text')
                if content_type.lower() == 'html':
                    body_text = _limpar_html(body_content)
                else:
                    body_text = body_content
                codigo = extrair_codigo_rockstar(subject + ' ' + body_text)
                if codigo:
                    return codigo
            time.sleep(3)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                access_token = None
                time.sleep(1)
            elif e.code == 400:
                erros_400 += 1
                if log_cb: log_cb(f"   ⚠️ {nome}: Erro Graph API HTTP 400 ({erros_400}/3)")
                if erros_400 >= 3:
                    if log_cb: log_cb(f"   ❌ {nome}: Token inválido/expirado!")
                    salvar_erro(conta, "Graph API HTTP 400", log_cb)
                    return "ERRO_400"
                access_token = None
                time.sleep(3)
            else:
                if log_cb: log_cb(f"   ⚠️ {nome}: Erro Graph API HTTP {e.code}")
                time.sleep(3)
        except Exception as e:
            if log_cb: log_cb(f"   ⚠️ {nome}: Erro Graph API: {str(e)[:80]}")
            time.sleep(3)
    return None

# ============================================================================
# PLAYWRIGHT HELPERS (FORMULÁRIO — MESMO FLUXO py.py)
# ============================================================================

def _pausa_humana(min_s=0.5, max_s=1.8):
    time.sleep(random.uniform(min_s, max_s))

def _mover_mouse_aleatorio(page):
    x = random.randint(100, 400)
    y = random.randint(100, 500)
    page.mouse.move(x, y)
    time.sleep(random.uniform(0.2, 0.6))

def _aceitar_cookies(page, nome, log_cb=None):
    try:
        botao = page.query_selector(
            'button[data-ui-name="acceptAllButton"], '
            '#onetrust-accept-btn-handler, '
            'button:has-text("Accept All"), '
            'button:has-text("Aceitar tudo"), '
            'button:has-text("Aceitar todos")'
        )
        if botao and botao.is_visible():
            botao.click()
            if log_cb: log_cb(f"🍪 {nome}: Cookies aceitos!")
            time.sleep(1)
    except Exception:
        pass

def _preencher_campo_fluido(page, seletor, valor, delay_range=(30, 60), limpar=False):
    """Preenchimento limpo, fluido e direto sem colar-e-apagar."""
    try:
        campo = page.wait_for_selector(seletor, timeout=8000)
        if not campo:
            return

        try:
            campo.scroll_into_view_if_needed(timeout=1500)
        except Exception:
            pass

        # Só limpa se solicitado E se o campo tiver conteúdo anterior
        if limpar:
            try:
                val_atual = campo.input_value()
            except Exception:
                val_atual = ""
            if val_atual and val_atual != valor:
                try:
                    campo.fill("")
                except Exception:
                    pass

        # Preenchimento direto atômico via Playwright
        sucesso = False
        try:
            campo.fill(valor)
            sucesso = True
        except Exception:
            try:
                campo.click(timeout=1500, force=True)
                campo.type(valor, delay=random.randint(delay_range[0], delay_range[1]))
                sucesso = True
            except Exception:
                pass

        # Sincroniza eventos sintéticos do React se necessário
        if sucesso:
            try:
                page.evaluate("""(sel, val) => {
                    const el = document.querySelector(sel);
                    if (el && el.value !== val) {
                        const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
                        if (nativeSetter) {
                            nativeSetter.call(el, val);
                        } else {
                            el.value = val;
                        }
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                }""", seletor, valor)
            except Exception:
                pass

    except Exception:
        try:
            page.fill(seletor, valor)
        except Exception:
            pass

def _preencher_campo_robusto(page, seletor, valor, delay_range=(30, 60), limpar=False):
    _preencher_campo_fluido(page, seletor, valor, delay_range, limpar=limpar)

def gerar_senha_rockstar_dinamica():
    """Gera uma senha forte e única para cada conta Rockstar (13-15 chars, maiúsculas, minúsculas, números e símbolos)."""
    letras_maiusculas = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    letras_minusculas = "abcdefghjkmnpqrstuvwxyz"
    numeros = "23456789"
    simbolos = "!@#$*&"

    parte_obrigatoria = [
        random.choice(letras_maiusculas),
        random.choice(letras_minusculas),
        random.choice(numeros),
        random.choice(simbolos),
        random.choice(letras_maiusculas),
        random.choice(numeros)
    ]

    todos = letras_maiusculas + letras_minusculas + numeros + simbolos
    tamanho_total = random.randint(13, 15)
    restante = [random.choice(todos) for _ in range(tamanho_total - len(parte_obrigatoria))]

    senha_lista = parte_obrigatoria + restante
    random.shuffle(senha_lista)
    return "".join(senha_lista)

def sanitizar_senha_rockstar(senha_original):
    """Garante que a senha satisfaça todos os critérios da Rockstar (maiúscula, minúscula, número, caractere especial e 10+ chars)."""
    if not senha_original or len(str(senha_original).strip()) < 8 or str(senha_original).strip() == ROCKSTAR_DEFAULT_PASSWORD:
        return gerar_senha_rockstar_dinamica()
    s = str(senha_original).strip()
    if not any(c.isdigit() for c in s):
        s += str(random.randint(10, 99))
    if not any(c.isupper() for c in s):
        s = random.choice("ABCDEFGHJKLMNPQRSTUVWXYZ") + s
    if not any(c.islower() for c in s):
        s += random.choice("abcdefghjkmnpqrstuvwxyz")
    if not any(c in "!@#$%*&" for c in s):
        s += random.choice("!@#$*")
    return s

def _preencher_cadastro(page, email, senha, nickname, nome, log_cb=None, limpar=False):
    # 1. E-mail
    _preencher_campo_fluido(page, 'input[data-ui-name="emailInput"]', email, (30, 60), limpar=limpar)
    try:
        page.evaluate("() => { if (document.activeElement) document.activeElement.blur(); }")
    except Exception:
        pass
    _pausa_humana(0.2, 0.4)

    # 2. Senha Sanitizada
    senha_ajustada = sanitizar_senha_rockstar(senha)
    _preencher_campo_fluido(page, 'input[data-ui-name="passwordInput"]', senha_ajustada, (45, 80), limpar=limpar)
    # Remove foco da senha para fechar balão de requisitos e liberar a tela no mobile
    try:
        page.evaluate("() => { if (document.activeElement) document.activeElement.blur(); }")
    except Exception:
        pass
    _pausa_humana(0.2, 0.4)

    # 3. Nickname
    _preencher_campo_fluido(page, 'input[data-ui-name="nicknameInput"]', nickname, (45, 80), limpar=limpar)
    try:
        page.evaluate("() => { if (document.activeElement) document.activeElement.blur(); }")
    except Exception:
        pass
    _pausa_humana(0.3, 0.5)

    # Verificação rápida de restrição/profanidade
    erro_inline = page.query_selector('[data-ui-name="validationError"], div[class*="error"], span[class*="error"], p[class*="error"]')
    if erro_inline and erro_inline.is_visible():
        txt = _normalizar_texto(erro_inline.inner_text())
        if any(k in txt for k in ["profanity", "profanidade", "ofensiv", "palavras", "invalid", "invalido", "reserved", "taken", "ja esta em uso", "nickname"]):
            novo_nick = gerar_nickname()
            if log_cb: log_cb(f"⚠️ {nome}: Nickname restrito ('{txt[:40]}'). Corrigindo para: {novo_nick}")
            _preencher_campo_fluido(page, 'input[data-ui-name="nicknameInput"]', novo_nick, (35, 70), limpar=True)
            nickname = novo_nick

    if log_cb: log_cb(f"✅ {nome}: Email={email} | User={nickname}")
    return senha_ajustada

def _rotacionar_ip_direto(log_cb=None, serial=None):
    """Executa a rotação de IP 4G via dados móveis sem derrubar o vínculo USB/tethering."""
    try:
        adb_prefix = f"adb -s {serial} " if serial else "adb "
        out = ""
        for tentativa in range(2):
            try:
                out = subprocess.check_output(f"{adb_prefix}get-state", shell=True, stderr=subprocess.DEVNULL).decode()
                if "device" in out:
                    break
            except Exception:
                pass
            subprocess.run(f"{adb_prefix}reconnect", shell=True, timeout=3, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1)

        if "device" in out:
            if log_cb: log_cb("🔄 Rotacionando IP 4G no celular (Modo Avião)...")
            
            # Acorda o celular se estiver em suspensão
            subprocess.run(f"{adb_prefix}shell input keyevent 224", shell=True, timeout=3, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # Ativa Modo Avião (desconecta rádio da operadora para forçar novo IP)
            subprocess.run(f"{adb_prefix}shell cmd connectivity airplane-mode enable", shell=True, timeout=5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(f"{adb_prefix}shell settings put global airplane_mode_on 1", shell=True, timeout=5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(3.0)

            # Desativa Modo Avião e reativa dados
            subprocess.run(f"{adb_prefix}shell cmd connectivity airplane-mode disable", shell=True, timeout=5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(f"{adb_prefix}shell settings put global airplane_mode_on 0", shell=True, timeout=5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1.0)
            subprocess.run(f"{adb_prefix}shell svc data disable", shell=True, timeout=5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(0.5)
            subprocess.run(f"{adb_prefix}shell svc data enable", shell=True, timeout=5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # Valida restabelecimento da conectividade 4G e resolução DNS
            import socket
            conectado = False
            for _ in range(12):
                time.sleep(1.0)
                try:
                    socket.gethostbyname("prod.ros.rockstargames.com")
                    conectado = True
                    break
                except Exception:
                    pass

            try:
                subprocess.run("ipconfig /flushdns", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

            if conectado:
                if log_cb: log_cb("✅ IP 4G renovado e conexão validada com sucesso!")
            else:
                if log_cb: log_cb("✅ IP 4G renovado com sucesso (Vínculo USB mantido ativo)!")
            return True
        else:
            if log_cb: log_cb("⚠️ Celular não detectado via USB/ADB para rotação do 4G.")
    except Exception as e:
        if log_cb: log_cb(f"⚠️ Falha ao rotacionar 4G: {e}")
    return False


def _submeter_cadastro(page, nickname, nome, log_cb=None, max_tentativas=20, rotacionar_ip_fn=None, senha_ref=None):
    tentativas_verificacao_detalhes = 0
    for tentativa in range(max_tentativas):
        # 1. Fechar o teclado virtual do Android removendo o foco de qualquer input
        try:
            page.evaluate("() => { if (document.activeElement) document.activeElement.blur(); }")
        except Exception:
            pass
        _pausa_humana(0.3, 0.8)

        # 2. Clicar no botão Next com coordenadas nativas de mouse
        if log_cb: log_cb(f"➡️ {nome}: Next (cadastro)! Aguardando resposta...")
        try:
            btn_next = page.wait_for_selector('button[data-ui-name="nextButton"]', timeout=5000)
            if btn_next and btn_next.is_visible():
                btn_next.scroll_into_view_if_needed()
                _pausa_humana(0.2, 0.5)
                btn_next.hover()
                _pausa_humana(0.1, 0.3)
                btn_next.click()
            else:
                page.click('button[data-ui-name="nextButton"]', timeout=5000)
        except Exception:
            try:
                page.click('button[data-ui-name="nextButton"]', timeout=5000)
            except Exception:
                pass

        # 3. Loop ativo de espera de resposta com desengasgo automático de botão travado em spinner
        inicio_espera = time.time()
        respondeu = False
        tentou_destravar = False

        while time.time() - inicio_espera < 35:
            # A. Campo de verificação apareceu (sucesso!)
            if page.query_selector('input[data-ui-name="evCodeInput"], input[name="evCode"]'):
                if log_cb: log_cb(f"✅ {nome}: Campo de verificação apareceu!")
                return nickname, "OK"

            # B. Alerta de erro ou erro de validação visível
            alerta_visivel = page.query_selector('[data-ui-name="alertText"], [data-ui-name="validationError"], [role="alert"], div[class*="alert" i], div[class*="error" i]')
            if not alerta_visivel:
                try:
                    txt_dom = page.evaluate("() => (document.body ? document.body.innerText : '').toLowerCase()")
                    if any(k in txt_dom for k in ["unable to handle", "handle your request", "1.500.7", "1.500", "sorry, we are unable", "too many requests"]):
                        respondeu = True
                        break
                except Exception:
                    pass
            if alerta_visivel and alerta_visivel.is_visible():
                respondeu = True
                break

            # C. Desengasgo de botão travado em spinner / loading após 8s
            elapsed = time.time() - inicio_espera
            if elapsed > 8 and not tentou_destravar:
                tentou_destravar = True
                if log_cb: log_cb(f"🔄 {nome}: Botão Next travado em carregamento ({int(elapsed)}s). Re-disparando envio para destravar...")
                try:
                    page.evaluate("""() => {
                        const btn = document.querySelector('button[data-ui-name="nextButton"]');
                        if (btn) btn.click();
                        const form = document.querySelector('form');
                        if (form) form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
                    }""")
                except Exception:
                    try:
                        page.keyboard.press("Enter")
                    except Exception:
                        pass

            time.sleep(0.8)

        # Checagem prioritária de sucesso (se o campo de código estiver na tela, ignorar qualquer alerta residual)
        if page.query_selector('input[data-ui-name="evCodeInput"], input[name="evCode"]'):
            if log_cb: log_cb(f"✅ {nome}: Campo de verificação apareceu!")
            return nickname, "OK"

        if not respondeu:
            if log_cb: log_cb(f"⚠️ {nome}: Formulário sem resposta após 35s ({tentativa + 1}/{max_tentativas}). Tentando reenviar...")
            try:
                page.keyboard.press("Enter")
            except Exception:
                pass
            time.sleep(2)
            continue

        alerta = page.query_selector('[data-ui-name="alertText"], [role="alert"], div[class*="alert" i], div[class*="error" i]')
        texto_alerta = ""
        if alerta and alerta.is_visible():
            try:
                texto_alerta = _normalizar_texto(alerta.inner_text())
            except Exception:
                pass

        if not texto_alerta:
            try:
                texto_alerta = _normalizar_texto(page.evaluate("() => document.body ? document.body.innerText : ''"))
            except Exception:
                pass

        if texto_alerta:
            if any(k in texto_alerta for k in [
                "ja tenha uma conta com este", "ja tem uma conta com este", "already have an account with this",
                "account with this email", "already registered with this"
            ]):
                if log_cb: log_cb(f"⚠️ {nome}: E-mail já tem conta!")
                return nickname, "EMAIL_EXISTENTE"

            # Detecção de rate-limit / bloqueio de IP da Rockstar (#1.500.7 / unable to handle)
            if any(k in texto_alerta for k in [
                "unable to handle", "handle your request", "1.500.7", "1.500", "sorry, we are unable",
                "nao e possivel resolver", "nao foi possivel atender sua solicitacao"
            ]):
                if log_cb: log_cb(f"🛑 {nome}: Bloqueio #1.500.7 detectado ('Sorry, we are unable to handle your request at this time')!")
                return nickname, "IP_BLOQUEADO"

            # Detecção de "Too many requests in too short a time" (#3.000.2 / #3.0)
            if any(k in texto_alerta for k in [
                "too many requests", "too short a time", "come back later", "3.000.2", "muitas solicitacoes", "tente mais tarde", "#3.0"
            ]):
                if log_cb: log_cb(f"⚠️ {nome}: Rate limit no envio (#3.000.2). Trocando e-mail e continuando...")
                return nickname, "EMAIL_EXISTENTE"

            # Detecção de "Unable to proceed, the required parameters are missing." (#1.000.2)
            if any(k in texto_alerta for k in [
                "required parameters are missing", "1.000.2", "unable to proceed", "parameters are missing", "parametros obrigatorios"
            ]):
                if log_cb: log_cb(f"⚠️ {nome}: Parâmetros ausentes / sessão expirada (#1.000.2). Pulando de e-mail...")
                return nickname, "EMAIL_EXISTENTE"
            
            # Detecção de "Your details could not be verified at this time. Please refresh and try again." (#1.1900.1)
            if any(k in texto_alerta for k in [
                "could not be verified", "nao foi possivel verificar", "not be verified", 
                "1.1900", "please refresh", "refresh and try again"
            ]):
                tentativas_verificacao_detalhes += 1
                if log_cb: log_cb(f"⚠️ {nome}: Detalhes não puderam ser verificados (#1.1900.1). Aguardando alguns segundos e tentando Next novamente ({tentativas_verificacao_detalhes}/5)...")
                time.sleep(random.uniform(4.0, 6.5))
                if tentativas_verificacao_detalhes >= 5:
                    if log_cb: log_cb(f"⚠️ {nome}: Limite de tentativas #1.1900.1 atingido. Bloqueio de IP/Sessão!")
                    return nickname, "IP_BLOQUEADO"
                continue

            # Detecção de profanidade / apelido inválido no alerta principal
            if any(k in texto_alerta for k in ["profanity", "profanidade", "nickname", "apelido", "offensive", "ofensiv", "invalid"]):
                sugestao = page.query_selector('a[data-ui-name*="suggestion"], div[class*="Suggestion"] a, div[class*="suggestion"] a, ul[class*="suggestion"] a, .suggestions a')
                if sugestao and sugestao.is_visible():
                    novo_nick = sugestao.inner_text().strip()
                    try:
                        sugestao.click()
                        if log_cb: log_cb(f"⚠️ {nome}: Nickname recusado. Clicou na sugestão da Rockstar: {novo_nick}")
                        nickname = novo_nick
                        _pausa_humana(0.3, 0.6)
                        continue
                    except Exception:
                        pass
                
                novo_nick = gerar_nickname()
                if log_cb: log_cb(f"⚠️ {nome}: Nickname recusado ('{texto_alerta[:40]}')! Trocando para: {novo_nick}")
                _preencher_campo_fluido(page, 'input[data-ui-name="nicknameInput"]', novo_nick, (35, 70), limpar=True)
                try:
                    page.evaluate("() => { if (document.activeElement) document.activeElement.blur(); }")
                except Exception:
                    pass
                nickname = novo_nick
                _pausa_humana(0.3, 0.5)
                continue

            # Detecção de senha inválida / sem números / muito fraca no alerta principal
            if any(k in texto_alerta for k in [
                "password must contain", "password is too weak", "senha deve conter", 
                "senha fraca", "senha muito fraca", "least one number", "least one uppercase", 
                "least one lowercase", "characters long"
            ]):
                nova_senha = sanitizar_senha_rockstar(senha_ref[0] if senha_ref else ROCKSTAR_DEFAULT_PASSWORD)
                if senha_ref and nova_senha == senha_ref[0]:
                    nova_senha = ROCKSTAR_DEFAULT_PASSWORD
                if senha_ref:
                    senha_ref[0] = nova_senha
                if log_cb: log_cb(f"🔑 {nome}: Senha inválida/fraca detectada no alerta ('{texto_alerta[:45]}'). Corrigida automaticamente para: {nova_senha}")
                _preencher_campo_fluido(page, 'input[data-ui-name="passwordInput"]', nova_senha, (40, 75), limpar=True)
                try:
                    page.evaluate("() => { if (document.activeElement) document.activeElement.blur(); }")
                except Exception:
                    pass
                _pausa_humana(0.3, 0.6)
                continue

            if log_cb: log_cb(f"⚠️ {nome}: Alerta servidor: {texto_alerta[:80]}")
            time.sleep(5)
            continue

        erros_validacao = []
        for erro_val in page.query_selector_all('[data-ui-name="validationError"]'):
            try:
                if erro_val.is_visible():
                    texto_erro = _normalizar_texto(erro_val.inner_text())
                    if texto_erro and texto_erro not in erros_validacao:
                        erros_validacao.append(texto_erro)
            except Exception:
                pass

        if erros_validacao:
            texto_erros = " | ".join(erros_validacao)

            # 1. Erros de Nickname / Apelido (inclusive 'nickname already exists')
            if any(k in texto_erros for k in [
                "nickname", "apelido", "display name", "already exists", "already in use",
                "ja existe", "ja esta em uso", "taken", "profanity", "profanidade",
                "apelido contem", "nickname contains", "offensive", "ofensiv",
                "nickname is invalid", "display name is invalid", "invalid nickname", "caracteres invalidos"
            ]):
                sugestao = page.query_selector('a[data-ui-name*="suggestion"], div[class*="Suggestion"] a, div[class*="suggestion"] a, ul[class*="suggestion"] a, .suggestions a, a[href="#"]')
                if sugestao and sugestao.is_visible():
                    novo_nick = sugestao.inner_text().strip()
                    try:
                        sugestao.click()
                        if log_cb: log_cb(f"⚠️ {nome}: Nickname em uso/recusado. Clicou na sugestão da Rockstar: {novo_nick}")
                        nickname = novo_nick
                        _pausa_humana(0.3, 0.6)
                        continue
                    except Exception:
                        pass

                novo_nick = gerar_nickname()
                if log_cb: log_cb(f"⚠️ {nome}: Nickname em uso/recusado ({texto_erros[:45]})! Trocando para novo: {novo_nick}")
                _preencher_campo_fluido(page, 'input[data-ui-name="nicknameInput"]', novo_nick, (30, 60), limpar=True)
                try:
                    page.evaluate("() => { if (document.activeElement) document.activeElement.blur(); }")
                except Exception:
                    pass
                nickname = novo_nick
                _pausa_humana(0.3, 0.5)
                continue

            # 2. Erros de E-mail ou Rate Limit
            if any(k in texto_erros for k in [
                "email already exists", "already registered with this", "ja existente",
                "ja tenha uma conta com este", "ja tem uma conta com este", "already have an account with this",
                "invalid email", "email address is invalid", "enter a valid email",
                "endereco de e-mail invalido", "e-mail invalido", "email invalido", "insira um e-mail valido",
                "too many requests", "too short a time", "come back later", "3.000.2", "muitas solicitacoes", "tente mais tarde", "#3.0"
            ]):
                if log_cb: log_cb(f"⚠️ {nome}: E-mail inválido, já cadastrado ou rate limit ('{texto_erros[:50]}')! Pulando de e-mail...")
                return nickname, "EMAIL_EXISTENTE"

            # 3. Erros de Senha
            if any(k in texto_erros for k in [
                "password must contain", "password is too weak", "senha deve conter", 
                "senha fraca", "senha muito fraca", "least one number", "least one uppercase", 
                "least one lowercase", "characters long"
            ]):
                nova_senha = sanitizar_senha_rockstar(senha_ref[0] if senha_ref else ROCKSTAR_DEFAULT_PASSWORD)
                if senha_ref and nova_senha == senha_ref[0]:
                    nova_senha = ROCKSTAR_DEFAULT_PASSWORD
                if senha_ref:
                    senha_ref[0] = nova_senha
                if log_cb: log_cb(f"🔑 {nome}: Senha sem número/fraca na validação. Corrigida automaticamente para: {nova_senha}")
                _preencher_campo_fluido(page, 'input[data-ui-name="passwordInput"]', nova_senha, (30, 60), limpar=True)
                try:
                    page.evaluate("() => { if (document.activeElement) document.activeElement.blur(); }")
                except Exception:
                    pass
                _pausa_humana(0.3, 0.6)
                continue

            if any(k in texto_erros for k in [
                "could not be verified", "not be verified", "1.1900", "please refresh", "refresh and try again"
            ]):
                tentativas_verificacao_detalhes += 1
                if log_cb: log_cb(f"⚠️ {nome}: Detalhes não verificados na validação (#1.1900.1). Aguardando e tentando Next novamente ({tentativas_verificacao_detalhes}/5)...")
                time.sleep(random.uniform(4.0, 6.5))
                if tentativas_verificacao_detalhes >= 5:
                    return nickname, "IP_BLOQUEADO"
                continue

            if any(k in texto_erros for k in [
                "unable to handle", "nao e possivel resolver", "1.500", "sorry"
            ]):
                if log_cb: log_cb(f"⚠️ {nome}: Bloqueio de IP/Sessão detectado na validação!")
                return nickname, "IP_BLOQUEADO"

            if log_cb: log_cb(f"⚠️ {nome}: Erro validação: {texto_erros[:80]}")
            time.sleep(2)
            continue

        break
    else:
        if log_cb: log_cb(f"❌ {nome}: Falhou após {max_tentativas} tentativas!")
        return nickname, "FALHOU"

    return nickname, "OK"

def _configurar_2fa(page, senha, nome, log_cb=None):
    if log_cb: log_cb(f"🔐 {nome}: Acessando página de segurança...")

    urls_seguranca = [
        "https://signin.rockstargames.com/account/security",
        "https://www.rockstargames.com/account/security",
        "https://socialclub.rockstargames.com/settings/mfa"
    ]

    current_url = (page.url or "").lower()
    if "account/security" not in current_url and "settings/mfa" not in current_url:
        for u in urls_seguranca:
            try:
                page.goto(u, wait_until="domcontentloaded", timeout=20000)
                break
            except Exception:
                try:
                    page.goto(u, timeout=20000)
                    break
                except Exception as e:
                    if log_cb: log_cb(f"⚠️ {nome}: Tentativa {u} falhou: {str(e)[:40]}")

    btn_setup_seletor = (
        '[data-testid="startMfaSetupButton"], '
        'button[data-testid*="startMfaSetup"], '
        'button[data-testid*="mfa-setup"], '
        'button[data-testid*="MfaSetup"], '
        'button[aria-label*="Authenticator"], '
        'button[aria-label*="2-Step"], '
        'button:has-text("Set Up"), '
        'button:has-text("Configurar"), '
        'button:has-text("Setup Authenticator"), '
        'button:has-text("Ativar Verificação em 2 Etapas"), '
        'button:has-text("Ativar"), '
        'a[href*="/mfa"], '
        '[data-ui-name="mfaSetupButton"]'
    )

    btn_setup = None
    for tentativa in range(35):
        try:
            _aceitar_cookies(page, nome, log_cb)
        except Exception:
            pass

        # Se cair em tela de erro (399, "doesn't exist", "another error occurred", etc.) ou deslogado
        try:
            cur_body = (page.inner_text("body") or "").lower() if page else ""
            if "399" in cur_body or "doesn't exist" in cur_body or "another error occurred" in cur_body or "an error occurred" in cur_body:
                if log_cb: log_cb(f"🔄 {nome}: Erro 399 detectado! Redirecionando direto para signin.rockstargames.com/account/security...")
                time.sleep(1.5)
                page.goto("https://signin.rockstargames.com/account/security", wait_until="domcontentloaded", timeout=25000)
                continue
        except Exception:
            pass

        try:
            btn_setup = page.query_selector(btn_setup_seletor)
            if btn_setup and btn_setup.is_visible():
                break
        except Exception:
            pass

        # Tentativa de scroll para baixo caso o botão esteja fora da tela no mobile
        if tentativa == 10:
            try:
                page.evaluate("window.scrollBy(0, 400)")
            except Exception:
                pass
        elif tentativa == 20:
            try:
                page.goto("https://signin.rockstargames.com/account/security", timeout=20000)
            except Exception:
                pass

        time.sleep(0.6)

    if not btn_setup or not btn_setup.is_visible():
        try:
            btn_setup = page.wait_for_selector(btn_setup_seletor, timeout=10000)
        except Exception:
            # Fallback: clica via javascript se encontrar qualquer elemento de setup
            achou_js = page.evaluate("""() => {
                const btns = Array.from(document.querySelectorAll('button, a'));
                for (const b of btns) {
                    const txt = (b.innerText || b.textContent || '').toLowerCase();
                    if (txt.includes('set up') || txt.includes('configurar') || txt.includes('authenticator') || txt.includes('2-step')) {
                        b.scrollIntoView({block: 'center'});
                        b.click();
                        return true;
                    }
                }
                return false;
            }""")
            if achou_js:
                if log_cb: log_cb(f"🔐 {nome}: Clicou Setup Authenticator via JS fallback!")
                btn_setup = True
            else:
                raise Exception("Botão Setup 2FA não apareceu")

    if btn_setup and btn_setup is not True:
        try:
            btn_setup.scroll_into_view_if_needed(timeout=2000)
        except Exception:
            pass
        btn_setup.click()
        if log_cb: log_cb(f"🔐 {nome}: Clicou Setup Authenticator!")

    # 1. Confirmação inicial de senha para habilitar 2FA
    page.wait_for_selector('[data-testid="mfa-password-verification-input"]', timeout=20000)
    _preencher_campo_fluido(page, '[data-testid="mfa-password-verification-input"]', senha, (30, 60), limpar=True)
    page.click('button[type="submit"]')
    if log_cb: log_cb(f"🔑 {nome}: Senha enviada!")

    # 2. Captura da Secret Key
    page.wait_for_selector('[data-testid="secret-key-modal-trigger"]', timeout=30000)
    page.click('[data-testid="secret-key-modal-trigger"]')

    page.wait_for_selector('[data-testid="secret-key"]', timeout=10000)
    secret_key = page.inner_text('[data-testid="secret-key"]').strip()
    if log_cb: log_cb(f"🔐 {nome}: Secret key: {secret_key}")

    page.keyboard.press("Escape")
    _pausa_humana(0.2, 0.4)

    # 3. Preenchimento 1º: Senha Atual (Current Password estritamente dentro do modal do 2FA)
    pwd_input_seletor = (
        'form:has([data-testid="mfa-code-verification-input"]) input[type="password"], '
        '[role="dialog"] input[type="password"], '
        '[data-testid="mfa-password-input"], '
        'input[type="password"]'
    )
    pwd_input = None
    try:
        pwd_input = page.wait_for_selector(pwd_input_seletor, timeout=10000)
    except Exception:
        pass

    if pwd_input and pwd_input.is_visible():
        if log_cb: log_cb(f"🔑 {nome}: Preenchendo senha no 2FA...")
        try:
            pwd_input.scroll_into_view_if_needed(timeout=1500)
        except Exception:
            pass
        try:
            pwd_input.fill(senha)
            val_atual = pwd_input.input_value()
            if val_atual != senha:
                page.evaluate("""(sel, s) => {
                    const el = document.querySelector(sel);
                    if (el) {
                        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
                        if (setter) setter.call(el, s);
                        else el.value = s;
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                }""", pwd_input_seletor, senha)
        except Exception:
            page.fill(pwd_input_seletor, senha)
        
        # Fecha o teclado virtual (Gboard) para não cobrir o botão Verify
        try:
            page.evaluate("() => { if (document.activeElement) document.activeElement.blur(); }")
        except Exception:
            pass
        _pausa_humana(0.2, 0.4)

    # 4. Geração e Preenchimento 2º: Código de Verificação 2FA (TOTP fresco e direto)
    totp = gerar_totp(secret_key)
    if log_cb: log_cb(f"🔐 {nome}: TOTP: {totp}")

    code_input = None
    try:
        code_input = page.wait_for_selector('[data-testid="mfa-code-verification-input"]', timeout=10000)
    except Exception:
        pass

    if code_input and code_input.is_visible():
        if log_cb: log_cb(f"🔐 {nome}: Preenchendo código 2FA...")
        code_input.fill(totp)
        try:
            page.evaluate("() => { if (document.activeElement) document.activeElement.blur(); }")
        except Exception:
            pass
        _pausa_humana(0.2, 0.3)

    # 5. Finalização e Submissão do 2FA
    page.click('[data-testid="mfa-verification-submit"], button:has-text("Verify")')
    if log_cb: log_cb(f"🔐 {nome}: Verify clicado!")

    # 6. Aguarda a resposta real do servidor (Sucesso ou Erro de senha)
    senha_usada_final = senha
    for _ in range(12):
        time.sleep(0.8)
        # Se o botão de submit sumiu da tela, o 2FA foi concluído com sucesso
        btn_v = page.query_selector('[data-testid="mfa-verification-submit"]')
        if not btn_v or not btn_v.is_visible():
            break

        # Verifica se apareceu erro de senha incorreta
        erro_encontrado = False
        try:
            for el in page.query_selector_all('[data-ui-name="validationError"], div[class*="error"], span[class*="error"], p[class*="error"]'):
                if el.is_visible():
                    txt = _normalizar_texto(el.inner_text())
                    if "incorrect password" in txt or "senha incorreta" in txt:
                        erro_encontrado = True
                        break
        except Exception:
            pass

        if erro_encontrado:
            alt_senha = gerar_senha_rockstar_dinamica()
            if log_cb: log_cb(f"🔑 {nome}: Senha incorreta confirmada no 2FA. Tentando senha alternativa ({alt_senha})...")
            if pwd_input:
                pwd_input.fill(alt_senha)
                _pausa_humana(0.2, 0.3)
                novo_totp = gerar_totp(secret_key)
                if code_input:
                    code_input.fill(novo_totp)
                _pausa_humana(0.2, 0.3)
                page.click('[data-testid="mfa-verification-submit"], button:has-text("Verify")')
                senha_usada_final = alt_senha
                time.sleep(1.5)
            break

    try:
        page.wait_for_selector('[data-testid="mfa-verification-submit"]', state="hidden", timeout=15000)
    except Exception:
        pass
    time.sleep(1.0)

    if log_cb: log_cb(f"✅ {nome}: 2FA configurado com sucesso!")
    return secret_key, senha_usada_final

# ============================================================================
# FLUXO DE CADASTRO (DATA → TERMOS → CAMPOS → CÓDIGO → 2FA)
# ============================================================================

def _executar_fluxo_formulario(page, obter_conta_fn, nome, buscar_codigo_fn, log_cb=None, is_mhmdo=True, pw=None, manager=None):
    """
    Executa o fluxo completo do formulário Rockstar:
    Data de Nascimento → Termos → Obtém Credenciais → Preenche Cadastro → Submete
    → código de verificação → confirmação → 2FA.
    
    obter_conta_fn() -> (email, senha, task_id) é chamado SOMENTE quando o formulário
    de cadastro estiver visível na tela, garantindo zero desperdício de e-mails comprados.
    """
    _aceitar_cookies(page, nome, log_cb)

    # 1. Data de Nascimento
    mes, dia, ano = gerar_data_nascimento()
    if log_cb: log_cb(f"🎂 {nome}: Data gerada → {dia:02d}/{mes:02d}/{ano}")

    while True:
        _aceitar_cookies(page, nome, log_cb)
        try:
            page.wait_for_selector('select[aria-label="Mês"], select[aria-label="Month"]', timeout=20000)
            _mover_mouse_aleatorio(page)
            _pausa_humana(0.8, 1.5)
            page.select_option('select[aria-label="Mês"], select[aria-label="Month"]', str(mes))
            _pausa_humana(0.5, 1.2)
            page.wait_for_selector('select[aria-label="Dia"], select[aria-label="Day"]', timeout=10000)
            page.select_option('select[aria-label="Dia"], select[aria-label="Day"]', str(dia))
            _pausa_humana(0.5, 1.2)
            page.wait_for_selector('select[aria-label="Ano"], select[aria-label="Year"]', timeout=10000)
            page.select_option('select[aria-label="Ano"], select[aria-label="Year"]', str(ano))
            _pausa_humana(0.5, 1.2)
            if log_cb: log_cb(f"📝 {nome}: Data de nascimento preenchida!")
            break
        except Exception:
            if log_cb: log_cb(f"🔄 {nome}: Recarregando formulário...")
            try:
                page.goto("https://signin.rockstargames.com/create/date-of-birth?cid=rsg&returnUrl=%2F", wait_until="domcontentloaded", timeout=20000)
            except Exception as e_nav:
                if "ERR_INTERNET_DISCONNECTED" in str(e_nav):
                    if log_cb: log_cb(f"⚠️ {nome}: Internet oscilou no celular. Reativando dados 4G...")
                    if manager and hasattr(manager, "serial"):
                        adb_c = f"adb -s {manager.serial}" if manager.serial else "adb"
                        subprocess.run(f"{adb_c} shell svc data disable", shell=True, timeout=5)
                        time.sleep(0.5)
                        subprocess.run(f"{adb_c} shell svc data enable", shell=True, timeout=5)
                        if hasattr(manager, "aguardar_conexao_4g"):
                            manager.aguardar_conexao_4g(timeout=14)
                    time.sleep(2)
                    page.goto("https://signin.rockstargames.com/create/date-of-birth?cid=rsg&returnUrl=%2F", wait_until="domcontentloaded", timeout=25000)
                else:
                    raise
            time.sleep(1)
            _aceitar_cookies(page, nome, log_cb)

    # Next (data)
    _pausa_humana(1.0, 2.0)
    page.click('button[data-ui-name="nextButton"]')
    if log_cb: log_cb(f"➡️ {nome}: Next (data)!")

    # 2. Aceitar Termos
    page.wait_for_selector('label[for="policyAccept"]', timeout=15000)
    _pausa_humana(1.0, 2.0)
    page.click('label[for="policyAccept"]')
    if log_cb: log_cb(f"☑️ {nome}: Termos aceitos!")

    _pausa_humana(0.8, 1.8)
    page.click('button[data-ui-name="nextButton"]')
    if log_cb: log_cb(f"➡️ {nome}: Next (termos)!")

    # 3. Preencher Cadastro (AQUI O FORMULÁRIO JÁ ESTÁ PRONTO NA TELA)
    page.wait_for_selector('input[data-ui-name="emailInput"]', timeout=15000)
    _pausa_humana(0.8, 1.5)
    if log_cb: log_cb(f"📋 {nome}: Campo de e-mail pronto na tela! Obtendo credenciais...")

    if manager and hasattr(manager, "checar_pausa"):
        manager.checar_pausa()
    if manager and not manager.running:
        return False, None, None, None, "PARADO"

    # Compra / gera o e-mail SOMENTE neste momento exato
    email, senha, task_id = obter_conta_fn()
    if not email:
        return False, None, None, None, "ERRO_OBTER_EMAIL"

    nome_dinamico = email.split("@")[0]
    nickname = gerar_nickname()
    senha_ref = [senha]
    senha_usada = _preencher_cadastro(page, email, senha, nickname, nome_dinamico, log_cb)
    senha_ref[0] = senha_usada
    nickname, status = _submeter_cadastro(page, nickname, nome_dinamico, log_cb, senha_ref=senha_ref)

    w_id = getattr(manager, 'serial', None) or getattr(manager, 'name', None) or 'mobile'
    # Tratamento caso haja bloqueio temporário de IP (#1.500.7 / unable to handle)
    if status == "IP_BLOQUEADO":
        if is_mhmdo and email:
            descartar_email_mhmdo_invalido(email, worker_id=w_id)
        if manager:
            manager.ultimo_status = "IP_BLOQUEADO"
        return False, None, email, None, "IP_BLOQUEADO"

    if status == "EMAIL_EXISTENTE":
        while status == "EMAIL_EXISTENTE":
            if is_mhmdo:
                if log_cb: log_cb(f"🔄 {nome_dinamico}: E-mail {email} recusado / rate limit. Descartando e obtendo novo e-mail...")
                descartar_email_mhmdo_invalido(email, worker_id=w_id)
            else:
                if log_cb: log_cb(f"🔄 {nome_dinamico}: E-mail {email} recusado / rate limit. Carregando próximo e-mail de outlook.txt...")
            email, senha, task_id = obter_conta_fn()
            if not email:
                if log_cb: log_cb(f"❌ {nome_dinamico}: Não há mais e-mails disponíveis na fila!")
                return False, None, None, None, "SEM_MAIS_CONTAS"
            if senha_ref:
                senha_ref[0] = sanitizar_senha_rockstar(senha)
            nome_dinamico = email.split("@")[0]
            nickname = gerar_nickname()
            if log_cb: log_cb(f"📧 {nome_dinamico}: Preenchendo novo e-mail ({email})...")
            _preencher_cadastro(page, email, senha_ref[0] if senha_ref else senha, nickname, nome_dinamico, log_cb, limpar=True)
            nickname, status = _submeter_cadastro(page, nickname, nome_dinamico, log_cb, senha_ref=senha_ref)
            if status == "IP_BLOQUEADO":
                if is_mhmdo and email:
                    descartar_email_mhmdo_invalido(email, worker_id=w_id)
                if manager:
                    manager.ultimo_status = "IP_BLOQUEADO"
                return False, None, email, None, "IP_BLOQUEADO"

    if status == "SOLICITACAO_INDISPONIVEL":
        return False, None, email, None, "SOLICITACAO_INDISPONIVEL"

    if status == "FALHOU":
        return False, None, email, None, "FALHOU"

    # 4. Código de Verificação
    while True:
        if log_cb: log_cb(f"📧 {nome_dinamico}: Aguardando campo de verificação...")
        page.wait_for_selector('input[data-ui-name="evCodeInput"]', timeout=60000)
        if log_cb: log_cb(f"✅ {nome_dinamico}: Campo de verificação apareceu!")

        if log_cb: log_cb(f"📡 {nome_dinamico}: Buscando código de verificação...")
        codigo = buscar_codigo_fn(nome_dinamico, task_id)

        # Se não encontrou o código, descarta o e-mail inválido e tenta com outro novo imediatamente
        if not codigo:
            if log_cb: log_cb(f"⚠️ {nome_dinamico}: Código não recebido em 40s para {email}. Pulando imediatamente para novo e-mail...")
            if is_mhmdo and email:
                descartar_email_mhmdo_invalido(email, worker_id=w_id)

            if manager and not manager.running:
                return False, None, email, None, "PARADO"

            # Recarrega o fluxo de cadastro limpo do zero
            try:
                page.goto("https://signin.rockstargames.com/create/date-of-birth?cid=rsg&returnUrl=%2F", wait_until="domcontentloaded", timeout=25000)
            except Exception:
                pass

            _aceitar_cookies(page, "NovoEmail", log_cb)
            mes_n, dia_n, ano_n = gerar_data_nascimento()
            try:
                page.wait_for_selector('select[aria-label="Mês"], select[aria-label="Month"]', timeout=15000)
                page.select_option('select[aria-label="Mês"], select[aria-label="Month"]', str(mes_n))
                _pausa_humana(0.3, 0.6)
                page.wait_for_selector('select[aria-label="Dia"], select[aria-label="Day"]', timeout=10000)
                page.select_option('select[aria-label="Dia"], select[aria-label="Day"]', str(dia_n))
                _pausa_humana(0.3, 0.6)
                page.wait_for_selector('select[aria-label="Ano"], select[aria-label="Year"]', timeout=10000)
                page.select_option('select[aria-label="Ano"], select[aria-label="Year"]', str(ano_n))
                _pausa_humana(0.5, 1.0)
                page.click('button[data-ui-name="nextButton"]')
                page.wait_for_selector('label[for="policyAccept"]', timeout=15000)
                _pausa_humana(0.4, 0.8)
                page.click('label[for="policyAccept"]')
                _pausa_humana(0.4, 0.8)
                page.click('button[data-ui-name="nextButton"]')
            except Exception as e_nav:
                if log_cb: log_cb(f"⚠️ Erro ao preparar data/termos para o novo e-mail: {e_nav}")

            if manager and not manager.running:
                return False, None, email, None, "PARADO"

            # Aguarda o campo de email estar pronto na tela
            try:
                page.wait_for_selector('input[data-ui-name="emailInput"]', timeout=15000)
            except Exception:
                pass

            # Obtém novo e-mail da API
            email, senha, task_id = obter_conta_fn()
            if not email:
                if log_cb: log_cb("❌ Não há mais e-mails disponíveis para tentar.")
                return False, None, None, None, "SEM_MAIS_CONTAS"

            if senha_ref:
                senha_ref[0] = sanitizar_senha_rockstar(senha)
            nome_dinamico = email.split("@")[0]
            nickname = gerar_nickname()
            if log_cb: log_cb(f"📧 {nome_dinamico}: Preenchendo novo e-mail ({email})...")
            try:
                _preencher_cadastro(page, email, senha_ref[0] if senha_ref else senha, nickname, nome_dinamico, log_cb, limpar=True)
                nickname, status = _submeter_cadastro(page, nickname, nome_dinamico, log_cb, senha_ref=senha_ref)
                if status == "IP_BLOQUEADO":
                    if is_mhmdo and email:
                        descartar_email_mhmdo_invalido(email, worker_id=w_id)
                    if manager:
                        manager.ultimo_status = "IP_BLOQUEADO"
                    return False, None, email, None, "IP_BLOQUEADO"
            except Exception as e:
                if log_cb: log_cb(f"⚠️ Erro ao preencher novo e-mail: {e}")
                return False, None, email, None, "ERRO_FORMULARIO"
            continue

        break

    if codigo == "ERRO_400":
        return False, None, email, None, "ERRO_400"

    if log_cb: log_cb(f"🔑 {nome_dinamico}: Código encontrado → {codigo}")
    _pausa_humana(0.5, 1.2)
    _preencher_campo_robusto(page, 'input[data-ui-name="evCodeInput"], input[name="evCode"]', str(codigo), (120, 220))
    _pausa_humana(0.5, 1.0)
    try:
        page.evaluate("() => { if (document.activeElement) document.activeElement.blur(); }")
    except Exception:
        pass
    _pausa_humana(0.3, 0.6)
    try:
        page.eval_on_selector('button[data-ui-name="submitEmailVerifyButton"]', 'el => { el.scrollIntoView({block: "center"}); el.click(); }')
    except Exception:
        try:
            page.click('button[data-ui-name="submitEmailVerifyButton"]', timeout=5000)
        except Exception:
            pass
    if log_cb: log_cb(f"➡️ {nome_dinamico}: Código enviado!")

    # 5. Confirmação Resiliente (evita travamento de carregamento infinito)
    if log_cb: log_cb(f"⏳ {nome_dinamico}: Aguardando confirmação...")
    confirmado = False
    for i in range(12):
        if manager and not manager.running:
            return False, None, email, None, "PARADO"
        # A. Mensagem de sucesso direta
        msg_sucesso = page.query_selector('[data-ui-name="accountSuccessMessage"], div[class*="success"], div[class*="Success"]')
        if msg_sucesso and msg_sucesso.is_visible():
            confirmado = True
            break
        # B. Redirecionamento automático para segurança / socialclub / profile
        current_url = page.url.lower()
        if "account/security" in current_url or "socialclub.rockstargames.com" in current_url or "/settings" in current_url:
            confirmado = True
            break
        # C. Re-clique preventivo caso o botão de enviar tenha continuado ativo após 5s
        btn_reenvio = page.query_selector('button[data-ui-name="submitEmailVerifyButton"]')
        if btn_reenvio and btn_reenvio.is_visible() and btn_reenvio.is_enabled() and i in [3, 7]:
            try:
                btn_reenvio.click()
            except Exception:
                pass
        time.sleep(1.5)

    if log_cb: log_cb(f"🎉 {nome_dinamico}: Conta validada com sucesso!")
    time.sleep(1.0)

    # 6. Configurar 2FA
    if manager and hasattr(manager, "checar_pausa"):
        manager.checar_pausa()
    if manager and not manager.running:
        return False, None, email, None, "PARADO"

    if log_cb: log_cb(f"🔐 {nome_dinamico}: Configurando 2FA...")
    secret_key, senha_confirmada = _configurar_2fa(page, senha_ref[0], nome_dinamico, log_cb)

    return True, secret_key, email, senha_confirmada, "OK"

# ============================================================================
# FLUXO GRAPH API (CONTAS DE CRIAR.TXT)
# ============================================================================

def executar_fluxo_graph(pw, conta, log_cb=None, manager=None):
    nome = conta.get("email", "Conta").split("@")[0]
    browser = None
    conta_ref = [conta]
    try:
        cdp_port = getattr(manager, 'cdp_port', 9222) if manager else 9222
        for i in range(15):
            if manager and not manager.running:
                return False
            try:
                browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")
                break
            except Exception:
                time.sleep(1)

        if not browser or (manager and not manager.running):
            if log_cb and not (manager and not manager.running):
                log_cb(f"❌ {nome}: Não conectou ao Chrome Mobile via CDP")
            return False

        if manager:
            manager.current_browser = browser

        page = None
        for p in browser.contexts[0].pages:
            try:
                if "rockstargames" in p.url and "chromewebdata" not in p.url:
                    page = p
                    break
            except Exception:
                pass
        if not page:
            page = browser.contexts[0].pages[0]
            try:
                page.goto("https://signin.rockstargames.com/create/date-of-birth?cid=rsg&returnUrl=%2F", wait_until="domcontentloaded", timeout=25000)
            except Exception as e_p:
                if "ERR_INTERNET_DISCONNECTED" in str(e_p):
                    if manager and hasattr(manager, "serial"):
                        adb_c = f"adb -s {manager.serial}" if manager.serial else "adb"
                        subprocess.run(f"{adb_c} shell svc data disable", shell=True, timeout=5)
                        time.sleep(0.5)
                        subprocess.run(f"{adb_c} shell svc data enable", shell=True, timeout=5)
                        if hasattr(manager, "aguardar_conexao_4g"):
                            manager.aguardar_conexao_4g(timeout=14)
                    time.sleep(2)
                    page.goto("https://signin.rockstargames.com/create/date-of-birth?cid=rsg&returnUrl=%2F", wait_until="domcontentloaded", timeout=25000)
                else:
                    raise

        primeira_vez_graph = [True]
        def obter_conta_graph():
            if primeira_vez_graph[0]:
                primeira_vez_graph[0] = False
                c = conta_ref[0]
                c_pwd = c.get("password", "")
                if not c_pwd or c_pwd == ROCKSTAR_DEFAULT_PASSWORD:
                    c_pwd = gerar_senha_rockstar_dinamica()
                return c["email"], c_pwd, None
            else:
                conta_anterior = conta_ref[0]
                if conta_anterior:
                    salvar_erro(conta_anterior, "Rate limit / Erro servidor (#3.000.2)", log_cb)
                nova_conta = carregar_proxima_conta()
                if not nova_conta:
                    if log_cb: log_cb("⚠️ Nenhuma outra conta encontrada na fila (outlook.txt / criar.txt)!")
                    return None, None, None
                conta_ref[0] = nova_conta
                if log_cb: log_cb(f"📥 Próxima conta carregada da fila: {nova_conta['email']}")
                return nova_conta["email"], nova_conta.get("password", "") or gerar_senha_rockstar_dinamica(), None

        def buscar_codigo_fn(n, tid):
            return buscar_codigo_graph(conta_ref[0], n, log_cb=log_cb, timeout=90)

        sucesso, secret_key, email_final, senha_final, status = _executar_fluxo_formulario(
            page, obter_conta_graph, nome, buscar_codigo_fn, log_cb, is_mhmdo=False, pw=pw, manager=manager
        )

        return tratar_resultado_conta_graph(conta_ref[0], sucesso, status, secret_key, email_final, senha_final, nome, log_cb)

    except Exception as e:
        if not (manager and not manager.running):
            if log_cb: log_cb(f"❌ {nome}: Erro: {e}")
            tratar_resultado_conta_graph(conta, False, str(e)[:100], None, None, None, nome, log_cb)
        return False
    finally:
        if manager:
            manager.current_browser = None
        if browser:
            try:
                browser.close()
            except Exception:
                pass

# ============================================================================
# FLUXO MHMDO API (GERA EMAIL NA HORA, SEM CRIAR.TXT)
# ============================================================================

def executar_fluxo_mhmdo(pw, email_type="custom", log_cb=None, manager=None):
    if not _MHMDO_DISPONIVEL:
        if log_cb: log_cb("❌ mhmdo_mail.py ou config.py não encontrado! Instale ambos no diretório.")
        return False

    browser = None
    email_atual = [None]
    task_id_atual = [None]
    try:
        # 1. Conectar ao Chrome Mobile via CDP PRIMEIRO (zero emails comprados se CDP falhar)
        cdp_port = getattr(manager, 'cdp_port', 9222) if manager else 9222
        for i in range(15):
            if manager and not manager.running:
                return False
            try:
                browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")
                break
            except Exception:
                time.sleep(1)

        if not browser or (manager and not manager.running):
            if log_cb and not (manager and not manager.running):
                log_cb("❌ Não conectou ao Chrome Mobile via CDP")
            return False

        if manager:
            manager.current_browser = browser

        page = None
        for p in browser.contexts[0].pages:
            try:
                if "rockstargames" in p.url and "chromewebdata" not in p.url:
                    page = p
                    break
            except Exception:
                pass
        if not page:
            page = browser.contexts[0].pages[0]
            try:
                page.goto("https://signin.rockstargames.com/create/date-of-birth?cid=rsg&returnUrl=%2F", wait_until="domcontentloaded", timeout=25000)
            except Exception as e_p:
                if "ERR_INTERNET_DISCONNECTED" in str(e_p):
                    if manager and hasattr(manager, "serial"):
                        adb_c = f"adb -s {manager.serial}" if manager.serial else "adb"
                        subprocess.run(f"{adb_c} shell svc data disable", shell=True, timeout=5)
                        time.sleep(0.5)
                        subprocess.run(f"{adb_c} shell svc data enable", shell=True, timeout=5)
                        if hasattr(manager, "aguardar_conexao_4g"):
                            manager.aguardar_conexao_4g(timeout=14)
                    time.sleep(2)
                    page.goto("https://signin.rockstargames.com/create/date-of-birth?cid=rsg&returnUrl=%2F", wait_until="domcontentloaded", timeout=25000)
                else:
                    raise

        # 2. Callback para obter/comprar email SOMENTE quando o formulário estiver pronto na tela
        worker_id = getattr(manager, 'serial', None) or getattr(manager, 'name', None) or 'mobile'
        def obter_email_na_hora():
            tipo_label = {"custom": "Custom ($1/1k)", "short": "Short ($2/1k)", "full": "Full Access ($6/1k)"}.get(email_type, email_type)
            if log_cb: log_cb(f"🛒 Comprando/gerando email mhmdo ({tipo_label}) agora no momento do cadastro...")
            email, task_id = obter_ou_gerar_email_mhmdo(target="rockstar", email_type=email_type, worker_id=worker_id)
            email_atual[0] = email
            task_id_atual[0] = task_id
            if log_cb: log_cb(f"✅ Email obtido: {email}")
            return email, gerar_senha_rockstar_dinamica(), task_id

        # 3. Callback de busca de código
        def buscar_codigo_fn(n, tid):
            if log_cb: log_cb(f"📡 {n}: Buscando código via API mhmdo.email (task_id: {tid[:20] if tid else ''}...)...")
            codigo, link = aguardar_codigo_mhmdo(tid, timeout=40, should_abort=lambda: manager and not manager.running)
            return codigo

        # 4. Executar fluxo completo
        sucesso, secret_key, email_final, senha_final, status = _executar_fluxo_formulario(
            page, obter_email_na_hora, "MHMDO", buscar_codigo_fn, log_cb, is_mhmdo=True, pw=pw, manager=manager
        )

        if not sucesso:
            if manager:
                manager.ultimo_status = status
            if email_atual[0]:
                conta_erro = {"email": email_atual[0], "password": ROCKSTAR_DEFAULT_PASSWORD}
                salvar_erro(conta_erro, status, log_cb)
                descartar_email_mhmdo_invalido(email_atual[0], worker_id=worker_id)
            return False

        # 5. Salvar sucesso
        salvar_feita(email_final, senha_final or gerar_senha_rockstar_dinamica(), secret_key, log_cb)
        marcar_email_mhmdo_consumido(email_final, worker_id=worker_id)
        if log_cb: log_cb(f"🎉 Conta criada e salva com sucesso: {email_final}")
        return True

    except Exception as e:
        if not (manager and not manager.running):
            if log_cb: log_cb(f"❌ Erro no fluxo mhmdo: {e}")
            if email_atual[0]:
                conta_erro = {"email": email_atual[0], "password": ROCKSTAR_DEFAULT_PASSWORD if _MHMDO_DISPONIVEL else ""}
                salvar_erro(conta_erro, str(e)[:100], log_cb)
                w_id = getattr(manager, 'serial', None) or getattr(manager, 'name', None) or 'mobile'
                descartar_email_mhmdo_invalido(email_atual[0], worker_id=w_id)
        return False
    finally:
        if manager:
            manager.current_browser = None
        if browser:
            try:
                browser.close()
            except Exception:
                pass

# ============================================================================
# FLUXO DESKTOP (PC) — MHMDO & GRAPH
# ============================================================================

SHARED_DISK_CACHE_DIR = os.path.join(tempfile.gettempdir(), "rsg_shared_disk_cache")
os.makedirs(SHARED_DISK_CACHE_DIR, exist_ok=True)

def aplicar_bloqueio_economia_dados(page, log_cb=None):
    """Economiza dados do proxy respondendo rastreadores e anúncios de terceiros com HTTP 204 No Content sem quebrar a integridade do navegador ou disparar proteções anti-bot."""
    def _interceptar(route):
        url = route.request.url.lower()
        
        # Responde HTTP 204 No Content para rastreadores pesados externos (0 bytes de tráfego no proxy, sem erros de rede no Akamai)
        if any(t in url for t in ['google-analytics', 'googletagmanager', 'doubleclick', 'facebook', 'optimizely', 'newrelic', 'nr-data', 'hotjar', 'tiktok', 'bing.com']):
            try:
                route.fulfill(status=204, body="")
                return
            except Exception:
                pass

        try:
            route.continue_()
        except Exception:
            pass

    try:
        page.route("**/*", _interceptar)
    except Exception:
        pass

def aplicar_stealth_anti_bot(page):
    """Injeta assinaturas reais de navegador para eliminar detecção de automação e evitar erro #1.500.7."""
    stealth_js = """
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        window.chrome = {
            app: { isInstalled: false },
            runtime: {},
            loadTimes: function() {},
            csi: function() {}
        };
        Object.defineProperty(navigator, 'languages', { get: () => ['pt-BR', 'pt', 'en-US', 'en'] });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
        Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
    """
    try:
        page.add_init_script(stealth_js)
    except Exception:
        pass

def executar_limpeza_estilo_revo(log_cb=None):
    """Executa limpeza profunda no estilo Revo Uninstaller (processos, diretórios temporários, perfis e DNS)."""
    if log_cb: log_cb("🧹 [Revo Clean] Executando limpeza profunda de perfis, caches e registros...")
    
    # 1. Encerra processos residuais de navegadores e launcher
    procs = ["chrome.exe", "chromium.exe", "msedge.exe", "Launcher.exe", "LauncherPatcher.exe", "SocialClubHelper.exe", "RockstarService.exe"]
    for proc in procs:
        try:
            subprocess.run(f"taskkill /F /IM {proc} /T", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
    
    # 2. Deleta pastas temporárias de perfis rsg_* e playwright*
    temp_root = tempfile.gettempdir()
    try:
        for item in os.listdir(temp_root):
            if any(item.startswith(prefix) for prefix in ["rsg_", "playwright", "scoped_dir", ".org.chromium"]):
                full_p = os.path.join(temp_root, item)
                try:
                    if os.path.isdir(full_p):
                        shutil.rmtree(full_p, ignore_errors=True)
                    else:
                        os.remove(full_p)
                except Exception:
                    pass
    except Exception:
        pass

    # 3. Limpeza do Launcher e AppData Rockstar
    limpar_cache_profundo_rockstar(log_cb=None)

    # 4. Flush DNS
    try:
        subprocess.run("ipconfig /flushdns", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

    if log_cb: log_cb("✨ [Revo Clean] Limpeza profunda concluída com sucesso!")

def executar_fluxo_mhmdo_pc(pw, email_type="custom", log_cb=None, manager=None):
    if not _MHMDO_DISPONIVEL:
        if log_cb: log_cb("❌ mhmdo_mail.py ou config.py não encontrado! Instale ambos no diretório.")
        return False

    browser_context = None
    email_atual = [None]
    task_id_atual = [None]
    user_data_dir = os.path.join(tempfile.gettempdir(), f"rsg_pc_{int(time.time() * 1000)}")
    try:
        if log_cb: log_cb("🌐 [PC] Conectando navegador limpo...")
        args_otimizados = [
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
            "--disable-component-update",
            "--disable-sync",
            "--disable-background-networking",
            "--disable-default-apps",
            "--mute-audio",
            "--window-size=1280,850"
        ]
        try:
            browser = pw.chromium.launch(
                headless=False,
                channel="chrome",
                args=args_otimizados
            )
        except Exception:
            browser = pw.chromium.launch(
                headless=False,
                args=args_otimizados
            )

        browser_context = browser.new_context(viewport={"width": 1280, "height": 850})
        if manager:
            manager.current_browser = browser_context

        page = browser_context.new_page()
        page.goto("https://signin.rockstargames.com/create/date-of-birth?cid=rsg&returnUrl=%2F")

        # Callback para obter email no momento do cadastro
        def obter_email_na_hora():
            tipo_label = {"custom": "Custom ($1/1k)", "short": "Short ($2/1k)", "full": "Full Access ($6/1k)"}.get(email_type, email_type)
            if log_cb: log_cb(f"🛒 Comprando/gerando email mhmdo ({tipo_label}) agora no momento do cadastro...")
            email, task_id = obter_ou_gerar_email_mhmdo(target="rockstar", email_type=email_type, worker_id="pc")
            email_atual[0] = email
            task_id_atual[0] = task_id
            if log_cb: log_cb(f"✅ Email obtido: {email}")
            return email, gerar_senha_rockstar_dinamica(), task_id

        # Callback de busca de código
        def buscar_codigo_fn(n, tid):
            if log_cb: log_cb(f"📡 {n}: Buscando código via API mhmdo.email (task_id: {tid[:20] if tid else ''}...)...")
            codigo, link = aguardar_codigo_mhmdo(tid, timeout=40, should_abort=lambda: manager and not manager.running)
            return codigo

        sucesso, secret_key, email_final, senha_final, status = _executar_fluxo_formulario(
            page, obter_email_na_hora, "PC_MHMDO", buscar_codigo_fn, log_cb, is_mhmdo=True, pw=pw, manager=manager
        )

        if not sucesso:
            if manager:
                manager.ultimo_status = status
            if email_atual[0]:
                conta_erro = {"email": email_atual[0], "password": ROCKSTAR_DEFAULT_PASSWORD}
                salvar_erro(conta_erro, status, log_cb)
                descartar_email_mhmdo_invalido(email_atual[0], worker_id="pc")
            return False

        salvar_feita(email_final, senha_final or gerar_senha_rockstar_dinamica(), secret_key, log_cb)
        marcar_email_mhmdo_consumido(email_final, worker_id="pc")
        if log_cb: log_cb(f"🎉 Conta criada e salva com sucesso: {email_final}")
        return True

    except Exception as e:
        if not (manager and not manager.running):
            if log_cb: log_cb(f"❌ Erro no fluxo PC: {e}")
            if email_atual[0]:
                conta_erro = {"email": email_atual[0], "password": ROCKSTAR_DEFAULT_PASSWORD if _MHMDO_DISPONIVEL else ""}
                salvar_erro(conta_erro, str(e)[:100], log_cb)
                descartar_email_mhmdo_invalido(email_atual[0], worker_id="pc")
        return False
    finally:
        if manager:
            manager.current_browser = None
        if browser_context:
            try:
                browser_context.close()
            except Exception:
                pass
        try:
            shutil.rmtree(user_data_dir, ignore_errors=True)
        except Exception:
            pass

def executar_fluxo_graph_pc(pw, conta, log_cb=None, manager=None):
    nome = conta.get("email", "Conta").split("@")[0]
    browser_context = None
    conta_ref = [conta]
    user_data_dir = os.path.join(tempfile.gettempdir(), f"rsg_pc_graph_{int(time.time() * 1000)}")
    try:
        if log_cb: log_cb(f"🌐 [PC] Abrindo navegador limpo para {nome}...")
        args_otimizados = [
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
            "--disable-component-update",
            "--disable-sync",
            "--disable-background-networking",
            "--disable-default-apps",
            "--mute-audio",
            "--window-size=1280,850"
        ]
        try:
            browser = pw.chromium.launch(
                headless=False,
                channel="chrome",
                args=args_otimizados
            )
        except Exception:
            browser = pw.chromium.launch(
                headless=False,
                args=args_otimizados
            )

        browser_context = browser.new_context(viewport={"width": 1280, "height": 850})
        if manager:
            manager.current_browser = browser_context

        page = browser_context.new_page()
        page.goto("https://signin.rockstargames.com/create/date-of-birth?cid=rsg&returnUrl=%2F")

        primeira_vez_graph_pc = [True]
        def obter_conta_graph():
            if primeira_vez_graph_pc[0]:
                primeira_vez_graph_pc[0] = False
                c = conta_ref[0]
                c_pwd = c.get("password", "")
                if not c_pwd or c_pwd == ROCKSTAR_DEFAULT_PASSWORD:
                    c_pwd = gerar_senha_rockstar_dinamica()
                return c["email"], c_pwd, None
            else:
                conta_anterior = conta_ref[0]
                if conta_anterior:
                    salvar_erro(conta_anterior, "Rate limit / Erro servidor (#3.000.2)", log_cb)
                nova_conta = carregar_proxima_conta()
                if not nova_conta:
                    if log_cb: log_cb("⚠️ Nenhuma outra conta encontrada na fila (outlook.txt / criar.txt)!")
                    return None, None, None
                conta_ref[0] = nova_conta
                if log_cb: log_cb(f"📥 Próxima conta carregada da fila: {nova_conta['email']}")
                return nova_conta["email"], nova_conta.get("password", "") or gerar_senha_rockstar_dinamica(), None

        def buscar_codigo_fn(n, tid):
            return buscar_codigo_graph(conta_ref[0], n, log_cb=log_cb, timeout=90)

        sucesso, secret_key, email_final, senha_final, status = _executar_fluxo_formulario(
            page, obter_conta_graph, f"PC_{nome}", buscar_codigo_fn, log_cb, is_mhmdo=False, pw=pw, manager=manager
        )

        return tratar_resultado_conta_graph(conta_ref[0], sucesso, status, secret_key, email_final, senha_final, f"PC_{nome}", log_cb)

    except Exception as e:
        if not (manager and not manager.running):
            if log_cb: log_cb(f"❌ {nome}: Erro: {e}")
            tratar_resultado_conta_graph(conta, False, str(e)[:100], None, None, None, f"PC_{nome}", log_cb)
        return False
    finally:
        if manager:
            manager.current_browser = None
        if browser_context:
            try:
                browser_context.close()
            except Exception:
                pass
        try:
            shutil.rmtree(user_data_dir, ignore_errors=True)
        except Exception:
            pass

# ============================================================================
# GERENCIADOR MOBILE (ADB, SCRCPY, 4G, CHROME)
# ============================================================================

def dispensar_via_adb_dump(serial=None, log_cb=None):
    """
    Fallback puro via ADB (uiautomator dump) caso uiautomator2 nao esteja funcionando.
    Funciona diretamente em qualquer aparelho Android (como Samsung S20) sem dependencias.
    """
    adb_prefix = f"adb -s {serial} " if serial else "adb "
    try:
        subprocess.run(f"{adb_prefix}shell uiautomator dump /data/local/tmp/uidump.xml", shell=True, capture_output=True, timeout=4)
        res = subprocess.run(f"{adb_prefix}shell cat /data/local/tmp/uidump.xml", shell=True, capture_output=True, text=True, timeout=4)
        xml = res.stdout or ""
        if not xml:
            return False

        padroes = [
            (r'(?i)usar sem uma conta|sem fazer login|sem conta|without an account|use without', "Usar sem uma conta"),
            (r'(?i)aceitar e continuar|accept & continue|accept and continue', "Aceitar e continuar"),
            (r'(?i)agora n[aã]o|no thanks|not now|n[aã]o, obrigado', "Agora não"),
            (r'(?i)recarregar|carregando flags', "Recarregar flags"),
            (r'(?i)entendi|confirmar', "Confirmar/Entendi"),
        ]

        # 1. Busca por texto / content-desc
        nodes = re.findall(r'(?:text="([^"]*)"|content-desc="([^"]*)")[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml)
        for t1, t2, x1, y1, x2, y2 in nodes:
            texto = (t1 or t2 or "").strip()
            for padrao, nome_btn in padroes:
                if re.search(padrao, texto):
                    cx = (int(x1) + int(x2)) // 2
                    cy = (int(y1) + int(y2)) // 2
                    subprocess.run(f"{adb_prefix}shell input tap {cx} {cy}", shell=True, timeout=3)
                    if log_cb: log_cb(f"🔓 Chrome: Clicado em '{nome_btn}' via ADB puro ({cx},{cy})!")
                    return True

        # 2. Busca por resource-id
        id_nodes = re.findall(r'resource-id="([^"]*)"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml)
        for rid, x1, y1, x2, y2 in id_nodes:
            if any(k in rid for k in ["signin_fre_dismiss_button", "signin_fre_secondary_button", "secondary_button", "terms_accept", "negative_button", "dismiss_button"]):
                cx = (int(x1) + int(x2)) // 2
                cy = (int(y1) + int(y2)) // 2
                subprocess.run(f"{adb_prefix}shell input tap {cx} {cy}", shell=True, timeout=3)
                if log_cb: log_cb(f"🔓 Chrome: Clicado em botão de dispensa ({rid}) via ADB puro ({cx},{cy})!")
                return True
    except Exception:
        pass
    return False

def dispensar_telas_iniciais_chrome(log_cb=None, timeout=10, serial=None, manager=None):
    """
    Detecta e clica automaticamente em 'Usar sem uma conta', 'Continuar sem fazer login',
    'Agora não', 'Aceitar e continuar', 'Não usar uma conta', 'Recarregar', etc.
    na primeira abertura do Chrome pós-limpeza.
    Usa uiautomator2 com fallback automático para ADB dump nativo.
    """
    adb_prefix = f"adb -s {serial} " if serial else "adb "
    fim = time.time() + timeout
    notificou_flags = False

    u2_device = None
    try:
        import uiautomator2 as u2
        u2_device = u2.connect(serial) if serial else u2.connect()
    except Exception:
        u2_device = None

    while time.time() < fim:
        if manager:
            if not getattr(manager, 'running', True): break
            mgr = getattr(manager, 'manager', None)
            if mgr and not getattr(mgr, 'running', True): break

        clicou = False

        if u2_device:
            try:
                # 1. Tela de login do Google ("Usar sem uma conta" / "Continuar sem fazer login")
                alvos_login = [
                    u2_device(textMatches="(?i).*usar sem uma conta.*|.*sem fazer login.*|.*sem conta.*|.*sem uma conta.*|.*without an account.*|.*use without.*"),
                    u2_device(resourceIdMatches=".*signin_fre_dismiss_button.*|.*signin_fre_secondary_button.*|.*secondary_button.*"),
                    u2_device(descriptionMatches="(?i).*usar sem uma conta.*|.*sem fazer login.*")
                ]
                for btn in alvos_login:
                    if btn.exists:
                        info = btn.info
                        bounds = info.get("bounds")
                        if bounds:
                            cx = (bounds["left"] + bounds["right"]) // 2
                            cy = (bounds["top"] + bounds["bottom"]) // 2
                            subprocess.run(f"{adb_prefix}shell input tap {cx} {cy}", shell=True, timeout=3)
                        else:
                            btn.click()
                        if log_cb: log_cb("🔓 Chrome: Clicado em 'Usar sem uma conta'!")
                        clicou = True
                        time.sleep(0.5)
                        break

                # 2. Tela de Termos / Aceite Inicial ("Aceitar e continuar")
                if not clicou:
                    alvos_termos = [
                        u2_device(textMatches="(?i).*aceitar e continuar.*|.*accept.*continue.*"),
                        u2_device(resourceIdMatches=".*terms_accept.*")
                    ]
                    for btn in alvos_termos:
                        if btn.exists:
                            btn.click()
                            if log_cb: log_cb("🔓 Chrome: Termos iniciais aceitos!")
                            clicou = True
                            time.sleep(0.5)
                            break

                # 3. Notificações / Sync ("Agora não" / "dismiss")
                if not clicou:
                    alvos_neg = [
                        u2_device(textMatches="(?i).*agora n.*o.*|.*no thanks.*|.*not now.*|.*n.*o, obrigado.*"),
                        u2_device(resourceIdMatches=".*negative_button.*|.*dismiss_button.*")
                    ]
                    for btn in alvos_neg:
                        if btn.exists:
                            info = btn.info
                            bounds = info.get("bounds")
                            if bounds:
                                cx = (bounds["left"] + bounds["right"]) // 2
                                cy = (bounds["top"] + bounds["bottom"]) // 2
                                subprocess.run(f"{adb_prefix}shell input tap {cx} {cy}", shell=True, timeout=3)
                            else:
                                btn.click()
                            if log_cb: log_cb("🔓 Chrome: Clicado em 'Agora não' nas notificações!")
                            clicou = True
                            time.sleep(0.5)
                            break

                # 4. Banner de flags de linha de comando
                if not clicou:
                    btn_flags = u2_device(textMatches="(?i).*recarregar.*|.*carregando flags.*")
                    if btn_flags.exists:
                        btn_flags.click()
                        if not notificou_flags and log_cb:
                            log_cb("🔓 Chrome: Banner de flags/linha de comando dispensado!")
                            notificou_flags = True
                        clicou = True
                        time.sleep(0.5)

            except Exception:
                pass

        # 2. Se uiautomator2 nao clicou ou nao esta instalado: roda ADB dump nativo
        if not clicou:
            clicou = dispensar_via_adb_dump(serial=serial, log_cb=log_cb)

        if not clicou:
            time.sleep(0.7)

# ============================================================================
# GERENCIAMENTO E IDENTIFICAÇÃO DE DISPOSITIVOS ADB
# ============================================================================

_device_info_cache = {}

def obter_propriedade_adb(serial, comando, timeout=2):
    try:
        res = subprocess.check_output(
            f"adb -s {serial} {comando}",
            shell=True,
            stderr=subprocess.DEVNULL,
            timeout=timeout
        ).decode("utf-8", errors="ignore").strip()
        return res if res and res != "null" else ""
    except Exception:
        return ""

def obter_info_dispositivo(serial):
    if serial in _device_info_cache:
        return _device_info_cache[serial]

    # 1. Nome comercial direto de mercado (Samsung, Xiaomi, etc.)
    nome = obter_propriedade_adb(serial, "shell getprop ro.product.marketname")

    # 2. Nome personalizado definido pelo usuário nas configurações do celular
    if not nome:
        nome = obter_propriedade_adb(serial, "shell settings get global device_name")

    # 3. Marca e Modelo do produto
    marca = obter_propriedade_adb(serial, "shell getprop ro.product.brand").capitalize()
    modelo = obter_propriedade_adb(serial, "shell getprop ro.product.model")

    if not nome:
        if marca and modelo:
            nome = f"{marca} {modelo}" if marca.lower() not in modelo.lower() else modelo
        elif modelo:
            nome = modelo
        else:
            nome = serial

    # Classificação de conveniência/legado
    nome_lower = nome.lower()
    serial_lower = serial.lower()
    if "r9xy" in serial_lower or any(k in nome_lower for k in ["a9", "tab", "sm-x", "gta9"]):
        tipo = "a9"
        rotulo = f"Tab A9+ ({nome})" if "a9" not in nome_lower else nome
    elif "ab3eb" in serial_lower or any(k in nome_lower for k in ["redmi", "xiaomi", "23129", "sapphire"]):
        tipo = "redmi"
        rotulo = f"Redmi ({nome})" if "redmi" not in nome_lower else nome
    else:
        tipo = "outro"
        rotulo = nome

    info = {
        "serial": serial,
        "nome": rotulo,
        "tipo": tipo,
        "marca": marca,
        "modelo": modelo
    }
    _device_info_cache[serial] = info
    return info

def listar_dispositivos_adb():
    try:
        out = subprocess.check_output("adb devices", shell=True, stderr=subprocess.DEVNULL, timeout=3).decode()
    except Exception:
        return []

    linhas = [l.strip() for l in out.splitlines() if l.strip() and not l.startswith("List")]
    dispositivos = []
    for l in linhas:
        partes = l.split()
        if not partes:
            continue
        serial = partes[0]
        status = partes[1] if len(partes) > 1 else "unknown"
        try:
            info = obter_info_dispositivo(serial)
        except Exception:
            info = {"nome": f"Aparelho ({serial[:8]})", "tipo": "outro", "marca": "", "modelo": ""}
        dispositivos.append({
            "serial": serial,
            "nome": info.get("nome", serial),
            "tipo": info.get("tipo", "outro"),
            "marca": info.get("marca", ""),
            "modelo": info.get("modelo", ""),
            "status": status
        })
    return dispositivos

# ============================================================================
# WORKER INDEPENDENTE POR DISPOSITIVO
# ============================================================================

class MobileDeviceWorker:
    def __init__(self, serial, name, cdp_port, manager, log_cb, scrcpy_pos_x=None):
        self.serial = serial
        self.name = name
        self.cdp_port = cdp_port
        self.manager = manager
        self.log_cb = log_cb
        self.scrcpy_pos_x = scrcpy_pos_x
        self.running = False
        self.paused = False
        self.tipo_execucao = "mobile"
        self.scrcpy_proc = None
        self._watchdog_active = False
        self.current_browser = None
        self.current_pw = None
        self.contas_criadas = 0

    def checar_pausa(self):
        while (self.paused or (self.manager and self.manager.paused)) and self.running and (self.manager and self.manager.running):
            time.sleep(0.5)

    def log(self, msg):
        if self.log_cb:
            self.log_cb(f"[{self.name}] {msg}")

    def parar_instantaneo(self):
        self.running = False
        self.paused = False
        self._watchdog_active = False

        # Salva referências locais antes de resetar os atributos do worker
        br = self.current_browser
        pw = self.current_pw
        proc = self.scrcpy_proc
        self.current_browser = None
        self.current_pw = None
        self.scrcpy_proc = None

        serial = self.serial
        cdp_port = self.cdp_port

        def _cleanup_bg():
            # 1. Encerra o processo Scrcpy se ainda existir
            if proc:
                try:
                    proc.kill()
                except Exception:
                    pass

            # 2. Fecha Playwright / Browser sem bloquear a UI
            if br:
                try:
                    br.close()
                except Exception:
                    pass
            if pw:
                try:
                    pw.stop()
                except Exception:
                    pass

            # 3. Limpeza ADB em segundo plano
            adb_cmd = f"adb -s {serial}" if serial else "adb"
            try:
                subprocess.Popen(f"{adb_cmd} forward --remove tcp:{cdp_port}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.Popen(f"{adb_cmd} shell am force-stop com.android.chrome", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.Popen(f"{adb_cmd} shell settings put global http_proxy :0", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

        threading.Thread(target=_cleanup_bg, daemon=True).start()
        self.log("⏹️ Worker interrompido.")

    def _iniciar_watchdog(self):
        self._watchdog_active = True
        serial = self.serial
        adb_prefix = f"adb -s {serial} " if serial else "adb "
        def _watchdog_loop():
            try:
                import uiautomator2 as u2
                d = u2.connect(serial) if serial else u2.connect()
                last_autofill_dismiss = 0
                while self._watchdog_active and self.running and self.manager.running:
                    try:
                        now = time.time()
                        if (now - last_autofill_dismiss > 6.0):
                            btn_cancel = d(resourceIdMatches=".*cancel_button.*|.*credential_cancel.*|.*dismiss_button.*|.*touch_outside.*")
                            if btn_cancel.exists:
                                btn_cancel.click()
                                last_autofill_dismiss = now
                                self.log("⚡ Watchdog: Fechou pop-up de credenciais!")
                            elif d(textMatches="(?i).*usar a senha salva.*|.*usar senha salva.*").exists:
                                subprocess.run(f"{adb_prefix}shell input tap 500 100", shell=True, timeout=2)
                                last_autofill_dismiss = now
                                self.log("⚡ Watchdog: Dispensou pop-up 'Usar a senha salva?'!")

                        btn = d(resourceIdMatches=".*negative_button.*|.*signin_fre_dismiss_button.*") or d(textMatches="(?i).*agora n.*o.*|.*sem fazer login.*|.*recarregar.*")
                        if btn.exists:
                            info = btn.info
                            bounds = info.get("bounds")
                            if bounds:
                                cx = (bounds["left"] + bounds["right"]) // 2
                                cy = (bounds["top"] + bounds["bottom"]) // 2
                                subprocess.run(f"{adb_prefix}shell input tap {cx} {cy}", shell=True, timeout=2)
                            else:
                                btn.click()
                            self.log("⚡ Watchdog: Fechou pop-up do Chrome ('Agora não' / 'Banner')!")
                            time.sleep(1.0)
                    except Exception:
                        pass
                    time.sleep(0.8)
            except Exception:
                pass
        threading.Thread(target=_watchdog_loop, daemon=True).start()

    def _parar_watchdog(self):
        self._watchdog_active = False

    def abrir_scrcpy(self):
        if self.scrcpy_proc and self.scrcpy_proc.poll() is None:
            return
        try:
            port_base = 27183 + (self.cdp_port - 9222) * 2
            cmd = [
                SCRCPY_PATH,
                f"--window-title=Espelhamento Mobile - {self.name}",
                "--always-on-top",
                "--max-fps=60",
                "--stay-awake",
                "--max-size=850",
                "--no-audio",
                f"--port={port_base}:{port_base+1}"
            ]
            if self.serial:
                cmd.extend(["-s", self.serial])
            if self.scrcpy_pos_x is not None:
                cmd.append(f"--window-x={self.scrcpy_pos_x}")
            flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            self.scrcpy_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                creationflags=flags
            )
            self.log(f"🚀 Janela Scrcpy aberta!")
        except Exception as e:
            self.log(f"⚠️ Erro ao abrir Scrcpy: {e}")

    def aguardar_dispositivo_usb(self, timeout=60):
        adb_cmd = f"adb -s {self.serial}" if self.serial else "adb"
        try:
            out = subprocess.check_output(f"{adb_cmd} get-state", shell=True, stderr=subprocess.DEVNULL).decode()
            if "device" in out:
                return True
        except Exception:
            pass
        self.log("⚠️ Cabo USB desconectado/oscilou! Aguardando reconexão...")
        inicio = time.time()
        while time.time() - inicio < timeout and self.running and self.manager.running:
            try:
                out = subprocess.check_output(f"{adb_cmd} get-state", shell=True, stderr=subprocess.DEVNULL).decode()
                if "device" in out:
                    self.log("🔌 Celular USB reconectado com sucesso!")
                    time.sleep(2)
                    self.abrir_scrcpy()
                    return True
            except Exception:
                pass
            time.sleep(2)
        return False

    def aguardar_conexao_4g(self, timeout=14):
        inicio = time.time()
        adb_cmd = f"adb -s {self.serial}" if self.serial else "adb"
        while time.time() - inicio < timeout:
            if not self.running or not self.manager.running:
                return False

            # Teste 1: Ping com resolução DNS em google.com (toybox ping nativo em 100% dos Androids)
            try:
                res_ping = subprocess.run(
                    f"{adb_cmd} shell ping -c 1 -w 2 google.com",
                    shell=True, capture_output=True, text=True, timeout=3.0
                )
                out_p = (res_ping.stdout or "") + (res_ping.stderr or "")
                if "bytes from" in out_p or "1 received" in out_p or "1 packets received" in out_p or "PING google.com (" in out_p:
                    return True
            except Exception:
                pass

            # Teste 2: Ping direto no IP 8.8.8.8
            try:
                res_p2 = subprocess.run(
                    f"{adb_cmd} shell ping -c 1 -w 2 8.8.8.8",
                    shell=True, capture_output=True, text=True, timeout=3.0
                )
                out_p2 = res_p2.stdout or ""
                if "bytes from" in out_p2 or "1 received" in out_p2 or "1 packets received" in out_p2:
                    return True
            except Exception:
                pass

            # Teste 3: Status nativo do ConnectivityManager do Android (sem depender de binários externos)
            try:
                res_conn = subprocess.run(
                    f"{adb_cmd} shell cmd connectivity is-active",
                    shell=True, capture_output=True, text=True, timeout=2.5
                )
                if (res_conn.stdout or "").strip().lower() == "true":
                    return True
            except Exception:
                pass

            # Teste 4: Dumpsys connectivity (detecta estado de rede celular conectada/validada)
            try:
                res_dump = subprocess.run(
                    f"{adb_cmd} shell dumpsys connectivity",
                    shell=True, capture_output=True, text=True, timeout=3.0
                )
                out_d = res_dump.stdout or ""
                if "CONNECTED/CONNECTED" in out_d or "state: CONNECTED" in out_d or "NET_CAPABILITY_VALIDATED" in out_d:
                    return True
            except Exception:
                pass

            # Teste 5: curl HTTP 204 (se o celular tiver curl instalado)
            try:
                res = subprocess.run(
                    f"{adb_cmd} shell curl -s -I --max-time 2 http://connectivitycheck.gstatic.com/generate_204",
                    shell=True, capture_output=True, text=True, timeout=3.0
                )
                if "204" in (res.stdout or "") or "HTTP/" in (res.stdout or ""):
                    return True
            except Exception:
                pass

            # Teste 6: wget HTTP 204 (se o celular tiver wget instalado)
            try:
                res_w = subprocess.run(
                    f"{adb_cmd} shell wget -q -O - http://connectivitycheck.gstatic.com/generate_204",
                    shell=True, capture_output=True, text=True, timeout=3.0
                )
                if res_w.returncode == 0:
                    return True
            except Exception:
                pass

            time.sleep(0.5)
        return False

    def obter_ip_celular(self):
        adb_cmd = f"adb -s {self.serial}" if self.serial else "adb"
        # 1. Tenta curl primeiro
        for url in ["https://api.ipify.org", "http://api.ipify.org", "https://ifconfig.me/ip", "http://icanhazip.com"]:
            try:
                res = subprocess.run(f"{adb_cmd} shell curl -s --max-time 2 {url}", shell=True, capture_output=True, text=True, timeout=3)
                ip = (res.stdout or "").strip()
                if ip and len(ip.split('.')) == 4 and not any(c in ip for c in [":", " ", "\n", "/"]):
                    return ip
            except Exception:
                pass
        # 2. Tenta wget em HTTP puro (caso curl não esteja instalado no Android)
        for url in ["http://api.ipify.org", "http://icanhazip.com"]:
            try:
                res = subprocess.run(f"{adb_cmd} shell wget -q -O - {url}", shell=True, capture_output=True, text=True, timeout=3)
                ip = (res.stdout or "").strip()
                if ip and len(ip.split('.')) == 4 and not any(c in ip for c in [":", " ", "\n", "/"]):
                    return ip
            except Exception:
                pass
        return None

    def rotacionar_ip_4g(self, ip_referencia=None):
        self.log("🔄 Rotacionando IP celular via Modo Avião...")
        adb_cmd = f"adb -s {self.serial}" if self.serial else "adb"
        ip_antigo = self.obter_ip_celular()
        if ip_antigo:
            self.log(f"📍 IP atual: {ip_antigo}")
        ref = ip_referencia or ip_antigo

        max_tentativas = 4 if ip_referencia else 2
        for tentativa in range(1, max_tentativas + 1):
            try:
                # 1. Ativa Modo Avião (desconecta rádio da operadora)
                subprocess.run(f"{adb_cmd} shell cmd connectivity airplane-mode enable", shell=True, timeout=5)
                subprocess.run(f"{adb_cmd} shell settings put global airplane_mode_on 1", shell=True, timeout=5)
                
                tempo_espera = 3.0 if tentativa == 1 else 4.5
                time.sleep(tempo_espera)

                # 2. Desativa Modo Avião e reativa os dados no modem (compatível com Samsung, Xiaomi, Motorola)
                subprocess.run(f"{adb_cmd} shell cmd connectivity airplane-mode disable", shell=True, timeout=5)
                subprocess.run(f"{adb_cmd} shell settings put global airplane_mode_on 0", shell=True, timeout=5)
                time.sleep(1.2)
                subprocess.run(f"{adb_cmd} shell svc data enable", shell=True, timeout=5)

                # 3. Aguarda restabelecimento da conectividade
                conectou = self.aguardar_conexao_4g(timeout=10)
                if not conectou:
                    subprocess.run(f"{adb_cmd} shell svc data disable", shell=True, timeout=5)
                    time.sleep(0.5)
                    subprocess.run(f"{adb_cmd} shell svc data enable", shell=True, timeout=5)
                    conectou = self.aguardar_conexao_4g(timeout=8)

                # Se obteve IP novo, valida a troca
                ip_novo = self.obter_ip_celular()
                if ip_novo:
                    if ref and ip_novo == ref and tentativa < max_tentativas:
                        self.log(f"⚠️ Operadora manteve o mesmo IP ({ip_novo}) [Tentativa {tentativa}/{max_tentativas}]. Repetindo ciclo...")
                        continue
                    if ip_antigo and ip_novo != ip_antigo:
                        self.log(f"✅ IP 4G trocado com sucesso: {ip_antigo} -> {ip_novo}")
                    else:
                        self.log(f"✅ IP 4G conectado: {ip_novo}")
                    return True
                elif conectou:
                    self.log("✅ IP 4G conectado e validado!")
                    return True
                else:
                    if tentativa < max_tentativas:
                        self.log(f"⚠️ Aguardando sincronização com a torre da operadora [Tentativa {tentativa}/{max_tentativas}]...")
                        continue

            except Exception as e:
                self.log(f"⚠️ Erro no ciclo de rotação: {e}")

        # Se após os ciclos o modem reiniciou, prossegue sem travar o usuário
        self.log("✅ Conexão 4G reiniciada! Prosseguindo com o fluxo...")
        time.sleep(1.0)
        return True

    def preparar_chrome_mobile(self):
        if not self.running or not self.manager.running:
            return
        self.log("🧹 Limpando Chrome Mobile e preparando sessão...")
        adb_cmd = f"adb -s {self.serial}" if self.serial else "adb"
        try:
            # Checagem leve de conectividade antes de abrir o Chrome
            if not self.aguardar_conexao_4g(timeout=4):
                time.sleep(1.0)

            subprocess.run(f"{adb_cmd} shell pm clear com.android.chrome", shell=True, timeout=10)
            if not self.running or not self.manager.running: return
            time.sleep(0.5)
            if not self.running or not self.manager.running: return
            subprocess.run(f"{adb_cmd} shell settings put secure autofill_service null", shell=True, timeout=5)
            if not self.running or not self.manager.running: return
            subprocess.run(f"{adb_cmd} shell appops set com.android.chrome POST_NOTIFICATION ignore", shell=True, timeout=5)
            if not self.running or not self.manager.running: return
            subprocess.run(f"{adb_cmd} shell settings put global http_proxy :0", shell=True, timeout=5)
            if not self.running or not self.manager.running: return
            subprocess.run(f"{adb_cmd} shell am set-debug-app --persistent com.android.chrome", shell=True, timeout=5)
            if not self.running or not self.manager.running: return
            chrome_flags = "chrome --disable-fre --no-first-run --no-default-browser-check --disable-save-password-bubble --disable-autofill --disable-password-generation --disable-single-click-autofill"
            subprocess.run(f'{adb_cmd} shell "echo \'{chrome_flags}\' > /data/local/tmp/chrome-command-line"', shell=True, timeout=5)
            if not self.running or not self.manager.running: return
            subprocess.run(f'{adb_cmd} shell "chmod 777 /data/local/tmp/chrome-command-line"', shell=True, timeout=5)
            if not self.running or not self.manager.running: return

            url = "https://signin.rockstargames.com/create/date-of-birth?cid=rsg&returnUrl=%2F"
            subprocess.run(f'{adb_cmd} shell am start -n com.android.chrome/com.google.android.apps.chrome.Main -d "{url}" --ez create_new_tab true --ez com.android.chrome.disable_first_run true --activity-clear-task', shell=True, timeout=10)
            if not self.running or not self.manager.running: return
            time.sleep(1.2)
            if not self.running or not self.manager.running: return
            dispensar_telas_iniciais_chrome(log_cb=self.log, serial=self.serial, manager=self)
            if not self.running or not self.manager.running: return
            subprocess.run(f"{adb_cmd} forward tcp:{self.cdp_port} localabstract:chrome_devtools_remote", shell=True, timeout=5)
            time.sleep(0.3)
            if not self.running or not self.manager.running: return
            self.log(f"✅ Chrome Mobile pronto (CDP {self.cdp_port})!")
        except Exception as e:
            if self.running and self.manager.running:
                self.log(f"⚠️ Erro ao preparar Chrome: {e}")

    def loop_worker(self):
        self.running = True
        self.log("🚀 Iniciando automação no dispositivo...")
        self.abrir_scrcpy()
        self._iniciar_watchdog()

        try:
            pw = sync_playwright().start()
            self.current_pw = pw
            while self.running and self.manager.running:
                if self.paused or self.manager.paused:
                    time.sleep(1)
                    continue

                if not self.aguardar_dispositivo_usb():
                    self.log("⚠️ Aguardando conexão USB...")
                    time.sleep(2)
                    continue

                self.abrir_scrcpy()
                self.preparar_chrome_mobile()
                if not self.running or not self.manager.running:
                    break

                self.checar_pausa()
                if not self.running or not self.manager.running:
                    break

                self.ultimo_status = ""
                if self.manager.modo_email == "mhmdo":
                    sucesso = executar_fluxo_mhmdo(pw, email_type=self.manager.mhmdo_email_type, log_cb=self.log, manager=self)
                else:
                    conta = carregar_proxima_conta()
                    if not conta:
                        self.log("🎉 Fila de contas finalizada!")
                        break
                    sucesso = executar_fluxo_graph(pw, conta, log_cb=self.log, manager=self)

                if sucesso:
                    self.contas_criadas += 1
                    atingiu_meta = self.manager.registrar_conta_criada(self.name)
                    if atingiu_meta:
                        self.log(f"🎯 Meta de {self.manager.meta_contas} contas atingida! Finalizando este aparelho...")
                        self.running = False
                        # Se todos os workers terminaram ou não estão mais rodando, encerra o manager
                        outros_rodando = any(w != self and w.running for w in getattr(self.manager, 'workers', []))
                        if not outros_rodando:
                            self.manager.running = False
                        break

                    # Pausa preventiva de 2 minutos a cada 5 contas deste aparelho
                    if (self.manager.infinito or self.manager.meta_contas > 5) and (self.contas_criadas % 5 == 0):
                        self.log(f"⏳ Bloco de 5 contas concluído! Pausa de 2 minutos para esfriar ({self.contas_criadas} contas criadas neste aparelho)...")
                        try:
                            if self.current_browser:
                                self.current_browser.close()
                        except Exception:
                            pass
                        adb_cmd = f"adb -s {self.serial}" if self.serial else "adb"
                        try:
                            subprocess.run(f"{adb_cmd} shell am force-stop com.android.chrome", shell=True, timeout=5)
                        except Exception:
                            pass
                        self.rotacionar_ip_4g()
                        for sec in range(120, 0, -1):
                            if not self.running or not self.manager.running:
                                break
                            while (self.paused or self.manager.paused) and self.running and self.manager.running:
                                time.sleep(1)
                            if sec in [120, 90, 60, 30, 10]:
                                self.log(f"⏳ Retomando em {sec}s...")
                            time.sleep(1)
                        if self.running and self.manager.running:
                            self.log("▶️ Retomando fluxo!")
                        continue

                    # Rotação de IP a cada 3 contas criadas neste aparelho
                    if self.contas_criadas % 3 == 0:
                        self.log(f"🔄 Bloco de 3 contas concluído ({self.contas_criadas} total). Rotacionando IP 4G...")
                        self.rotacionar_ip_4g()
                        time.sleep(1.0)

                else:
                    # Tratamento do erro #1.500.7 ("Sorry, we are unable to handle your request at this time")
                    if getattr(self, "ultimo_status", "") == "IP_BLOQUEADO":
                        ip_bloqueado = self.obter_ip_celular()
                        self.log("🛑 Bloqueio #1.500.7 (Unable to handle request) detectado neste aparelho!")
                        if ip_bloqueado:
                            self.log(f"🚫 IP bloqueado registrado: {ip_bloqueado}")
                        self.log("🛑 Fechando fluxo e limpando navegador neste aparelho...")
                        try:
                            if self.current_browser:
                                self.current_browser.close()
                        except Exception:
                            pass
                        self.current_browser = None

                        adb_cmd = f"adb -s {self.serial}" if self.serial else "adb"
                        try:
                            subprocess.run(f"{adb_cmd} shell am force-stop com.android.chrome", shell=True, timeout=5)
                            subprocess.run(f"{adb_cmd} shell pm clear com.android.chrome", shell=True, timeout=5)
                        except Exception:
                            pass

                        self.log("☕ Aguardando 5 minutos (300s) para esfriar o aparelho antes de reiniciar...")
                        for sec in range(300, 0, -1):
                            if not self.running or not self.manager.running:
                                break
                            while (self.paused or self.manager.paused) and self.running and self.manager.running:
                                time.sleep(1)
                            if sec in [300, 240, 180, 120, 60, 30, 10]:
                                self.log(f"⏳ Cooldown #1.500.7: Retomando fluxo em {sec}s...")
                            time.sleep(1)

                        if not self.running or not self.manager.running:
                            break

                        self.log("🚀 Intervalo concluído! Trocando para um IP diferente antes de reiniciar o processo...")
                        self.rotacionar_ip_4g(ip_referencia=ip_bloqueado)
                        self.ultimo_status = ""
                        self.log("▶️ Processo reiniciado com novo IP e novo e-mail!")
                        continue

        except Exception as e:
            if self.running and self.manager.running:
                self.log(f"❌ Erro no worker: {e}")
        finally:
            self._parar_watchdog()
            if self.current_pw:
                try: self.current_pw.stop()
                except Exception: pass
                self.current_pw = None
            self.running = False
            self.log("⏹️ Worker finalizado.")

# ============================================================================
# GERENCIADOR PRINCIPAL MULTI-DISPOSITIVO & PC
# ============================================================================

class MobileManager:
    def __init__(self, log_cb, stats_cb):
        self.log_cb = log_cb
        self.stats_cb = stats_cb
        self.running = False
        self.paused = False
        self.tipo_execucao = "mobile"  # "mobile", "pc_4g" ou "pc_local"
        self.modo_email = "mhmdo"  # "mhmdo" ou "graph"
        self.mhmdo_email_type = "short"  # "short", "custom" ou "full"
        self.meta_contas = 10
        self.infinito = False
        self.contas_criadas_sessao = 0
        self._stats_lock = threading.Lock()
        self._thread_lock = threading.Lock()
        self.workers = []
        # Campos de compatibilidade para modo PC
        self.current_browser = None
        self.current_pw = None

    def checar_pausa(self):
        while self.paused and self.running:
            time.sleep(0.5)

    def log(self, msg):
        if self.log_cb:
            self.log_cb(msg)

    def pausar_worker_individual(self, tipo_ou_nome):
        """Pausa ou retoma individualmente um worker por serial, tipo ou nome."""
        tipo = str(tipo_ou_nome).strip().lower()
        alvo = None
        for w in self.workers:
            w_nome = getattr(w, "name", "").lower()
            w_serial = getattr(w, "serial", "").lower()
            if tipo == w_serial or tipo in w_nome:
                alvo = w
                break
            if tipo == "a9" and ("a9" in w_nome or "tab" in w_nome):
                alvo = w
                break
            if tipo == "redmi" and "redmi" in w_nome:
                alvo = w
                break
        if not alvo:
            self.log(f"⚠️ Aparelho '{tipo_ou_nome}' não encontrado ativo na execução.")
            return None

        alvo.paused = not alvo.paused
        estado = "⏸ PAUSADO" if alvo.paused else "▶ RETOMADO"
        self.log(f"📱 [{alvo.name}] {estado} individualmente.")
        if self.stats_cb:
            self.stats_cb()
        return alvo.paused

    def obter_status_pausa_worker(self, tipo_ou_nome):
        """Retorna True se pausado, False se em execução ativa, None se não estiver rodando."""
        tipo = str(tipo_ou_nome).strip().lower()
        for w in self.workers:
            w_nome = getattr(w, "name", "").lower()
            w_serial = getattr(w, "serial", "").lower()
            match = (tipo == w_serial or tipo in w_nome)
            if not match and tipo == "a9" and ("a9" in w_nome or "tab" in w_nome):
                match = True
            if not match and tipo == "redmi" and "redmi" in w_nome:
                match = True
            if match and w.running:
                return bool(w.paused or self.paused)
        return None

    def registrar_conta_criada(self, worker_name=""):
        with self._stats_lock:
            self.contas_criadas_sessao += 1
            atingiu = (not self.infinito and self.meta_contas > 0 and self.contas_criadas_sessao >= self.meta_contas)
        if self.stats_cb:
            self.stats_cb()
        return atingiu

    def parar_instantaneo(self):
        """Para todos os workers mobile e instâncias de PC imediatamente."""
        self.running = False
        self.paused = False

        for w in list(self.workers):
            try:
                w.parar_instantaneo()
            except Exception:
                pass
        self.workers.clear()

        if hasattr(self, "standalone_scrcpy_workers"):
            for w in list(self.standalone_scrcpy_workers):
                try:
                    w.parar_instantaneo()
                except Exception:
                    pass
            self.standalone_scrcpy_workers.clear()

        br = self.current_browser
        pw = self.current_pw
        self.current_browser = None
        self.current_pw = None

        if br or pw:
            def _cleanup_pc():
                if br:
                    try: br.close()
                    except Exception: pass
                if pw:
                    try: pw.stop()
                    except Exception: pass
            threading.Thread(target=_cleanup_pc, daemon=True).start()

        self.log("⏹️ Automação interrompida com sucesso.")
        if self.stats_cb:
            self.stats_cb()

    def abrir_scrcpy(self):
        if self.workers:
            self.log(f"📱 Abrindo espelhamento Scrcpy para os {len(self.workers)} aparelhos em execução...")
            for idx, w in enumerate(self.workers):
                w.abrir_scrcpy()
                if idx < len(self.workers) - 1:
                    time.sleep(0.6)
            return

        dispositivos = [d for d in listar_dispositivos_adb() if d["status"] == "device"]
        if not dispositivos:
            self.log("⚠️ Nenhum aparelho conectado via USB com depuração ativa para abrir Scrcpy!")
            return

        if not hasattr(self, "standalone_scrcpy_workers"):
            self.standalone_scrcpy_workers = []

        self.standalone_scrcpy_workers = [w for w in self.standalone_scrcpy_workers if w.scrcpy_proc and w.scrcpy_proc.poll() is None]

        x_offsets = [40, 890, 1300]
        self.log(f"📱 Abrindo Scrcpy para {len(dispositivos)} aparelho(s) conectado(s)...")
        for idx, dev in enumerate(dispositivos):
            pos_x = x_offsets[idx] if idx < len(x_offsets) else 100
            ja_rodando = any(w.serial == dev["serial"] and w.scrcpy_proc and w.scrcpy_proc.poll() is None for w in self.standalone_scrcpy_workers)
            if not ja_rodando:
                w = MobileDeviceWorker(dev["serial"], dev["nome"], 9222 + idx, self, self.log_cb, scrcpy_pos_x=pos_x)
                w.abrir_scrcpy()
                self.standalone_scrcpy_workers.append(w)
                if idx < len(dispositivos) - 1:
                    time.sleep(0.6)

    def rotacionar_ip_4g(self):
        dispositivos = [d for d in listar_dispositivos_adb() if d["status"] == "device"]
        if not dispositivos:
            self.log("⚠️ Nenhum aparelho conectado para rotacionar 4G!")
            return
        for dev in dispositivos:
            w = MobileDeviceWorker(dev["serial"], dev["nome"], 9222, self, self.log_cb)
            threading.Thread(target=w.rotacionar_ip_4g, daemon=True).start()

    def preparar_chrome_mobile(self):
        dispositivos = [d for d in listar_dispositivos_adb() if d["status"] == "device"]
        if not dispositivos:
            self.log("⚠️ Nenhum aparelho conectado para preparar Chrome!")
            return
        for idx, dev in enumerate(dispositivos):
            w = MobileDeviceWorker(dev["serial"], dev["nome"], 9222 + idx, self, self.log_cb)
            threading.Thread(target=w.preparar_chrome_mobile, daemon=True).start()

    def iniciar_multi_mobile(self, usar_redmi=True, usar_a9=True, seriais_selecionados=None):
        self.running = True
        self.paused = False
        self.workers.clear()

        todos = listar_dispositivos_adb()
        dispositivos_online = [d for d in todos if d["status"] == "device"]

        alvos = []
        if seriais_selecionados is not None:
            # Seleção dinâmica de dispositivos por serial
            for idx, dev in enumerate(dispositivos_online):
                if dev["serial"] in seriais_selecionados:
                    porta = 9222 + len(alvos)
                    pos_x = 40 + len(alvos) * 450
                    alvos.append((dev["serial"], dev["nome"], porta, pos_x))
        else:
            # Modo fallback / legado
            dev_redmi = next((d for d in dispositivos_online if d["tipo"] == "redmi"), None)
            dev_a9 = next((d for d in dispositivos_online if d["tipo"] == "a9"), None)

            sobrantes = [d for d in dispositivos_online if d not in [dev_redmi, dev_a9]]
            if usar_redmi and not dev_redmi and sobrantes:
                dev_redmi = sobrantes.pop(0)
                dev_redmi["nome"] = f"Redmi ({dev_redmi['nome']})"
                dev_redmi["tipo"] = "redmi"
            if usar_a9 and not dev_a9 and sobrantes:
                dev_a9 = sobrantes.pop(0)
                dev_a9["nome"] = f"Tab A9+ ({dev_a9['nome']})"
                dev_a9["tipo"] = "a9"

            if usar_redmi:
                if dev_redmi:
                    alvos.append((dev_redmi["serial"], dev_redmi.get("nome", "Redmi"), 9222, 40))
                else:
                    self.log("❌ Redmi selecionado, mas não está conectado ou autorizado via USB!")

            if usar_a9:
                if dev_a9:
                    alvos.append((dev_a9["serial"], dev_a9.get("nome", "Tab A9+"), 9223, 890))
                else:
                    self.log("❌ Tab A9+ selecionado, mas não está conectado ou autorizado via USB!")

        if not alvos:
            self.log("⚠️ Nenhum dos dispositivos selecionados está disponível. Conecte os aparelhos via USB e tente novamente.")
            self.running = False
            if self.stats_cb: self.stats_cb()
            return

        modo_txt = '📨 MHMDO API' if self.modo_email == 'mhmdo' else '📊 Graph API (criar.txt)'
        if len(alvos) > 1:
            nomes_str = " + ".join(f"{nome} (Porta {porta})" for _, nome, porta, _ in alvos)
            self.log(f"🚀 INICIANDO MODO MULTI-MOBILE ({len(alvos)} aparelhos): {nomes_str} — {modo_txt}")
        else:
            self.log(f"🚀 INICIANDO DISPOSITIVO ÚNICO: {alvos[0][1]} (Porta {alvos[0][2]}) — {modo_txt}")

        threads = []
        for idx, (serial, nome, port, pos_x) in enumerate(alvos):
            w = MobileDeviceWorker(serial, nome, port, self, self.log_cb, scrcpy_pos_x=pos_x)
            self.workers.append(w)
            w.abrir_scrcpy()
            if idx < len(alvos) - 1:
                time.sleep(0.8)
            t = threading.Thread(target=w.loop_worker, daemon=True)
            threads.append(t)
            t.start()

        def _monitor():
            while self.running:
                vivos = any(t.is_alive() for t in threads)
                if not vivos:
                    break
                time.sleep(0.5)
            self.running = False
            self.log("⏹️ Todos os dispositivos finalizaram a execução.")
            if self.stats_cb: self.stats_cb()

        threading.Thread(target=_monitor, daemon=True).start()

    def loop_automacao(self):
        """Loop utilizado exclusivamente para execução no Computador (PC)."""
        if not self._thread_lock.acquire(blocking=False):
            if self.current_browser:
                try: self.current_browser.close()
                except Exception: pass
            if self.current_pw:
                try: self.current_pw.stop()
                except Exception: pass
            time.sleep(0.3)
            if not self._thread_lock.acquire(blocking=True, timeout=2.0):
                self.log("⚠️ Aguardando processo anterior finalizar...")
                return
        try:
            if self.tipo_execucao == "mobile":
                self.iniciar_multi_mobile(True, True)
                return

            if self.tipo_execucao == "pc_4g":
                self.log(f"🌐 Iniciando automação PC (Proxy DataImpulse BR) — Modo: {'📨 MHMDO API' if self.modo_email == 'mhmdo' else '📊 Graph API (criar.txt)'}")
            else:
                self.log(f"🏠 Iniciando automação PC na REDE LOCAL (sem proxy) — Modo: {'📨 MHMDO API' if self.modo_email == 'mhmdo' else '📊 Graph API (criar.txt)'}")

            pw = sync_playwright().start()
            self.current_pw = pw
            try:
                while self.running:
                    if self.paused:
                        time.sleep(1)
                        continue

                    if self.modo_email == "mhmdo":
                        sucesso = executar_fluxo_mhmdo_pc(pw, email_type=self.mhmdo_email_type, log_cb=self.log, manager=self)
                    else:
                        conta = carregar_proxima_conta()
                        if not conta:
                            self.log("🎉 Todas as contas em criar.txt foram processadas! 🟢")
                            self.running = False
                            break
                        sucesso = executar_fluxo_graph_pc(pw, conta, log_cb=self.log, manager=self)

                    if sucesso:
                        self.contas_criadas_sessao += 1
                        if not self.infinito and self.meta_contas > 0 and self.contas_criadas_sessao >= self.meta_contas:
                            self.log(f"🎯 Meta de {self.meta_contas} contas atingida com sucesso! 🎉")
                            if self.stats_cb:
                                self.stats_cb()
                            self.running = False
                            break

                        bloco_limite = 4
                        if (self.infinito or self.meta_contas > bloco_limite) and (self.contas_criadas_sessao % bloco_limite == 0):
                            self.log(f"⏳ Bloco de {bloco_limite} contas (PC) concluído! Executando pausa de 2 minutos para esfriar ({self.contas_criadas_sessao} contas criadas)...")
                            try:
                                if self.current_browser:
                                    self.current_browser.close()
                            except Exception:
                                pass
                            executar_limpeza_estilo_revo(self.log)

                            for sec in range(120, 0, -1):
                                if not self.running:
                                    break
                                if sec in [120, 90, 60, 30, 10]:
                                    self.log(f"⏳ Reabrindo navegador em {sec}s...")
                                time.sleep(1)
                            if self.running:
                                self.log("▶️ Retomando fluxo de criação de contas!")
                            continue
                    else:
                        if getattr(self, "ultimo_status", "") == "IP_BLOQUEADO":
                            self.log("🛑 Bloqueio #1.500.7 (Unable to handle request) detectado no PC!")
                            self.log("🛑 Fechando navegador e limpando sessão...")
                            try:
                                if self.current_browser:
                                    self.current_browser.close()
                            except Exception:
                                pass
                            self.current_browser = None
                            executar_limpeza_estilo_revo(self.log)
                            self.log("☕ Aguardando intervalo de 5 minutos (300s) para esfriar antes de reiniciar...")
                            for sec in range(300, 0, -1):
                                if not self.running:
                                    break
                                if sec in [300, 240, 180, 120, 60, 30, 10]:
                                    self.log(f"⏳ Cooldown #1.500.7: Retomando fluxo em {sec}s...")
                                time.sleep(1)
                            if self.running:
                                self.log("🚀 Intervalo concluído! Trocando IP antes de reiniciar o processo...")
                                if self.tipo_execucao == "pc_4g":
                                    rotacionar_ip_dataimpulse(self.log)
                                self.ultimo_status = ""
                                self.log("▶️ Retomando processo no PC com novo IP e novo e-mail...")
                                continue

                    if self.stats_cb:
                        self.stats_cb()

                    if self.running:
                        time.sleep(1)

            except Exception as e:
                if self.running:
                    self.log(f"❌ Erro no loop: {e}")
            finally:
                try:
                    pw.stop()
                except Exception:
                    pass
                self.current_pw = None
                self.running = False
                self.log("⏹️ Automação finalizada.")
                if self.stats_cb:
                    self.stats_cb()
        finally:
            try:
                self._thread_lock.release()
            except Exception:
                pass

# ============================================================================
# DESIGN SYSTEM & CORES ULTRA-MODERNAS
# ============================================================================
C_BG_MAIN        = "#0A0B10"   # Fundo ultra escuro elegante
C_BG_SIDEBAR     = "#05060A"   # Sidebar profunda
C_BG_HEADER      = "#08090E"   # Top bar
C_BG_CARD        = "#131622"   # Superfície de cards nítida
C_BG_CARD_INNER  = "#191D2C"   # Sub-cards e containers
C_BG_INPUT       = "#161A28"   # Inputs e caixas de texto
C_BORDER         = "#262D42"   # Linhas de contorno visíveis
C_BORDER_LIGHT   = "#37415D"   # Contornos com foco
C_TEXT_TITLE     = "#FFFFFF"   # Títulos e valores primários
C_TEXT_BODY      = "#CBD5E1"   # Textos secundários
C_TEXT_MUTED     = "#64748B"   # Legendas e textos apagados
C_CYAN           = "#00E5FF"   # Ciano Neon Pokas
C_GREEN          = "#00F59B"   # Esmeralda Neon (Sucesso/Play)
C_AMBER          = "#F59E0B"   # Âmbar/Dourado (Códigos)
C_PURPLE         = "#A855F7"   # Roxo/Violeta (Prontas)
C_BLUE           = "#0EA5E9"   # Azul 4G
C_INDIGO         = "#6366F1"   # Roxo Local
C_RED            = "#EF4444"   # Vermelho Perigo

def _obter_versao_app():
    try:
        import updater
        return updater.get_local_version()
    except Exception:
        pass
    try:
        vpath = os.path.join(BASE_DIR, "version.json")
        if os.path.exists(vpath):
            with open(vpath, "r", encoding="utf-8") as f:
                return json.load(f).get("version", "1.0.5")
    except Exception:
        pass
    return "1.0.5"

def aplicar_tema_escuro_janela(root):
    """
    Elimina a barra branca padrão do Windows e ativa o DWM Immersive Dark Mode,
    integrando a barra de título perfeitamente ao tema escuro do aplicativo.
    """
    try:
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        if hwnd == 0:
            hwnd = root.winfo_id()
        val = ctypes.c_int(1)
        res = ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(val), ctypes.sizeof(val))
        if res != 0:
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(val), ctypes.sizeof(val))
        try:
            cor_caption = ctypes.c_uint32(0x00170E0B)  # #0B0E17 em COLORREF BGR
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(cor_caption), ctypes.sizeof(cor_caption))
            cor_texto = ctypes.c_uint32(0x00FFFFFF)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(cor_texto), ctypes.sizeof(cor_texto))
        except Exception:
            pass
        return True
    except Exception:
        return False

# ============================================================================
# INTERFACE GRÁFICA MODERNA COM SIDEBAR & GERENCIADOR
# ============================================================================

class MobileAutomationGUI:
    def __init__(self, root, license_info=None):
        self.root = root
        self.versao_app = _obter_versao_app()
        self.license_info = license_info or {}
        lic_txt = f" [{self.license_info.get('msg', 'Ativo')}]" if self.license_info else ""
        self.root.title(f"Pokas Ideia Store v{self.versao_app} — Automação & Resgate de Licenças Rockstar{lic_txt}")
        self.root.geometry("1060x800")
        self.root.minsize(700, 460)
        self.root.configure(bg=C_BG_MAIN)
        self.root.bind("<Configure>", self._on_window_configure)
        self.root.protocol("WM_DELETE_WINDOW", self._fechar_janela)
        self._ativar_janela_sem_borda_nativa()
        self.root.after(20, self._ativar_janela_sem_borda_nativa)
        self.root.after(150, self._ativar_janela_sem_borda_nativa)

        # Configurar Ícone Nativo do Aplicativo (Janela + Barra de Tarefas)
        ico_path = os.path.join(BASE_DIR, "app_icon.ico")
        if os.path.exists(ico_path):
            try:
                self.root.iconbitmap(ico_path)
            except Exception:
                pass

        logo_path = os.path.join(BASE_DIR, "logo.png")
        if os.path.exists(logo_path):
            try:
                pil_icon = Image.open(logo_path).convert("RGBA").resize((32, 32), Image.Resampling.LANCZOS)
                self._app_icon_photo = ImageTk.PhotoImage(pil_icon)
                self.root.iconphoto(True, self._app_icon_photo)
            except Exception:
                pass

        self.manager = MobileManager(
            log_cb=self.adicionar_log,
            stats_cb=self.atualizar_contadores
        )

        self.redeem_running = False
        self.redeem_paused = False
        self.current_redeem_pw = None
        self.current_redeem_browser = None
        self.teve_limpeza = False

        self.arquivo_ativo = "codigos"
        self.fluxo_ativo = "mobile"  # "mobile" ou "pc"

        self.device_vars = {}
        self.device_checkboxes = {}
        self.dispositivos_detectados_cache = []
        self._ultimo_seriais_detectados = None
        self.botoes_pausa_individuais = {}

        self.usar_redmi_var = tk.BooleanVar(value=True)
        self.usar_a9_var = tk.BooleanVar(value=True)

        self._configurar_estilos()
        self._construir_interface()
        self.atualizar_contadores()
        self._iniciar_loop_tempo_real()
        self._iniciar_watchdog_licenca()

    def _selecionar_todos_dispositivos(self):
        for var in self.device_vars.values():
            var.set(True)
        self.atualizar_contadores()

    def _deselecionar_todos_dispositivos(self):
        for var in self.device_vars.values():
            var.set(False)
        self.atualizar_contadores()

    def _selecionar_ambos(self):
        self._selecionar_todos_dispositivos()

    def _selecionar_so_redmi(self):
        for serial, var in self.device_vars.items():
            info = _device_info_cache.get(serial, {})
            nome = info.get("nome", "").lower()
            if "redmi" in nome or "ab3eb" in serial.lower():
                var.set(True)
            else:
                var.set(False)
        self.atualizar_contadores()

    def _selecionar_so_a9(self):
        for serial, var in self.device_vars.items():
            info = _device_info_cache.get(serial, {})
            nome = info.get("nome", "").lower()
            if "a9" in nome or "tab" in nome or "r9xy" in serial.lower():
                var.set(True)
            else:
                var.set(False)
        self.atualizar_contadores()

    def _iniciar_loop_tempo_real(self):
        """Atualização contínua a cada 1 segundo em tempo real de contadores e saldo da API."""
        def _loop_stats():
            while True:
                try:
                    self.atualizar_contadores()
                except Exception:
                    pass
                time.sleep(1)

        def _loop_api_e_adb():
            while True:
                try:
                    self._atualizar_saldo_mhmdo()
                    self._atualizar_status_adb()
                except Exception:
                    pass
                time.sleep(3)

        threading.Thread(target=_loop_stats, daemon=True).start()
        threading.Thread(target=_loop_api_e_adb, daemon=True).start()

    def _configurar_estilos(self):
        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.style.configure("TFrame", background=C_BG_MAIN)
        self.style.configure("Primary.TButton", background="#059669", foreground="#FFFFFF", font=("Segoe UI", 9, "bold"), borderwidth=0, padding=(14, 8))
        self.style.map("Primary.TButton", background=[("active", "#10B981")])
        self.style.configure("Pc4g.TButton", background="#0284C7", foreground="#FFFFFF", font=("Segoe UI", 9, "bold"), borderwidth=0, padding=(14, 8))
        self.style.map("Pc4g.TButton", background=[("active", "#0EA5E9")])
        self.style.configure("PcLocal.TButton", background="#4F46E5", foreground="#FFFFFF", font=("Segoe UI", 9, "bold"), borderwidth=0, padding=(14, 8))
        self.style.map("PcLocal.TButton", background=[("active", "#6366F1")])
        self.style.configure("Cyan.TButton", background="#0891B2", foreground="#FFFFFF", font=("Segoe UI", 9, "bold"), borderwidth=0, padding=(14, 8))
        self.style.map("Cyan.TButton", background=[("active", "#06B6D4")])
        self.style.configure("Secondary.TButton", background="#1E2333", foreground="#CBD5E1", font=("Segoe UI", 9, "bold"), borderwidth=0, padding=(10, 6))
        self.style.map("Secondary.TButton", background=[("active", "#2A3146")], foreground=[("active", "#FFFFFF")])
        self.style.configure("Danger.TButton", background="#DC2626", foreground="#FFFFFF", font=("Segoe UI", 9, "bold"), borderwidth=0, padding=(14, 8))
        self.style.map("Danger.TButton", background=[("active", "#EF4444")])

        # Estilo moderno da tabela de licenças (Cloudflare KV)
        self.style.configure("Licenses.Treeview",
            background="#0C1017",
            foreground=C_TEXT_BODY,
            fieldbackground="#0C1017",
            borderwidth=0,
            font=("Segoe UI", 9),
            rowheight=28
        )
        self.style.configure("Licenses.Treeview.Heading",
            background="#161B26",
            foreground=C_CYAN,
            font=("Segoe UI", 8, "bold"),
            borderwidth=0,
            relief="flat"
        )
        self.style.map("Licenses.Treeview",
            background=[("selected", "#1F293D")],
            foreground=[("selected", "#FFFFFF")]
        )

    def _ativar_janela_sem_borda_nativa(self):
        try:
            self.root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            if hwnd == 0:
                hwnd = self.root.winfo_id()
            self.hwnd = hwnd

            GWL_STYLE = -16
            WS_CAPTION = 0x00C00000
            WS_THICKFRAME = 0x00040000
            WS_MINIMIZEBOX = 0x00020000
            WS_MAXIMIZEBOX = 0x00010000

            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
            new_style = (style & ~WS_CAPTION) | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, new_style)

            # Atributos DWM: elimina totalmente a listra branca sem quebrar o canvas GDI
            dark_val = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark_val), 4) # DWMWA_USE_IMMERSIVE_DARK_MODE
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(dark_val), 4) # Fallback Win10

            cor_bg = ctypes.c_uint32(0x00080605) # BGR para #050608 (Dark Obsidian)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(cor_bg), 4) # DWMWA_BORDER_COLOR (Win11)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(cor_bg), 4) # DWMWA_CAPTION_COLOR (Win11)

            SWP_FRAMECHANGED = 0x0020
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOZORDER = 0x0004
            ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER)
        except Exception:
            pass

    def _iniciar_arrasto_janela(self, event=None):
        if event:
            self._drag_start_x = event.x_root
            self._drag_start_y = event.y_root
            self._win_start_x = self.root.winfo_x()
            self._win_start_y = self.root.winfo_y()
            self._drag_last_time = 0
            self._drag_pending = False
            self._drag_target_x = self._win_start_x
            self._drag_target_y = self._win_start_y

    def _executar_movimento_janela(self):
        try:
            self._drag_pending = False
            hwnd = getattr(self, "hwnd", None)
            if not hwnd:
                hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            SWP_NOSIZE = 0x0001
            SWP_NOZORDER = 0x0004
            SWP_NOACTIVATE = 0x0010
            ctypes.windll.user32.SetWindowPos(hwnd, 0, self._drag_target_x, self._drag_target_y, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
        except Exception:
            pass

    def _arrastar_janela(self, event=None):
        try:
            if not event or not hasattr(self, "_drag_start_x"):
                return

            if getattr(self, "_is_maximized", False):
                self._toggle_maximizar()
                self._drag_start_x = event.x_root
                self._drag_start_y = event.y_root
                self._win_start_x = max(0, event.x_root - 150)
                self._win_start_y = max(0, event.y_root - 18)
                self._drag_target_x = self._win_start_x
                self._drag_target_y = self._win_start_y
                self._executar_movimento_janela()
                return

            dx = event.x_root - self._drag_start_x
            dy = event.y_root - self._drag_start_y
            self._drag_target_x = self._win_start_x + dx
            self._drag_target_y = self._win_start_y + dy

            now = time.perf_counter()
            # Throttling fluido a 120 FPS (8.3ms) para zero lag e movimentacao instantanea
            if (now - getattr(self, "_drag_last_time", 0)) >= 0.008:
                self._drag_last_time = now
                self._executar_movimento_janela()
            elif not getattr(self, "_drag_pending", False):
                self._drag_pending = True
                self.root.after(4, self._executar_movimento_janela)
        except Exception:
            pass

    def _minimizar_janela(self):
        try:
            hwnd = getattr(self, "hwnd", None)
            if not hwnd:
                hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            ctypes.windll.user32.ShowWindow(hwnd, 6) # SW_MINIMIZE = 6
        except Exception:
            try: self.root.iconify()
            except Exception: pass

    def _aplicar_maximizacao_workarea(self):
        try:
            hwnd = getattr(self, "hwnd", None)
            if not hwnd:
                hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()

            out = wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(out))
            if not getattr(self, "_is_maximized", False):
                self._prev_rect = (out.left, out.top, out.right - out.left, out.bottom - out.top)

            class MONITORINFO(ctypes.Structure):
                _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT),
                            ('rcWork', wintypes.RECT), ('dwFlags', wintypes.DWORD)]

            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(MONITORINFO)
            hMon = ctypes.windll.user32.MonitorFromWindow(hwnd, 2) # MONITOR_DEFAULTTONEAREST = 2
            ctypes.windll.user32.GetMonitorInfoW(hMon, ctypes.byref(mi))

            x = mi.rcWork.left
            y = mi.rcWork.top
            w = mi.rcWork.right - mi.rcWork.left
            h = mi.rcWork.bottom - mi.rcWork.top

            # Checa se a barra de tarefas do Windows (Shell_TrayWnd) está no monitor ativo
            hTaskbar = ctypes.windll.user32.FindWindowW("Shell_TrayWnd", None)
            if hTaskbar:
                rcTask = wintypes.RECT()
                ctypes.windll.user32.GetWindowRect(hTaskbar, ctypes.byref(rcTask))
                if rcTask.top < mi.rcWork.bottom and rcTask.top > mi.rcWork.top:
                    h = min(h, rcTask.top - y)

            # Folga de seguranca de 6px para NUNCA tampar ou encostar na barra de tarefas
            h = max(200, h - 6)

            # Libera minsize temporariamente para permitir encolhimento perfeito em qualquer notebook/escala
            self.root.minsize(100, 100)

            # Move a janela fisicamente e sincroniza a geometria do Tkinter de forma imediata (sem borda preta)
            ctypes.windll.user32.MoveWindow(hwnd, x, y, w, h, True)
            self.root.geometry(f"{w}x{h}+{x}+{y}")
            self.root.update()

            self._is_maximized = True
            if hasattr(self, "btn_title_max_lbl"):
                self.btn_title_max_lbl.config(text="❐")
        except Exception:
            pass

    def _toggle_maximizar(self):
        try:
            hwnd = getattr(self, "hwnd", None)
            if not hwnd:
                hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()

            if getattr(self, "_is_maximized", False):
                self._is_maximized = False
                self.root.minsize(700, 460)
                if hasattr(self, "_prev_rect") and self._prev_rect:
                    px, py, pw, ph = self._prev_rect
                else:
                    px, py, pw, ph = 100, 100, 1060, 800

                ctypes.windll.user32.MoveWindow(hwnd, px, py, pw, ph, True)
                self.root.geometry(f"{pw}x{ph}+{px}+{py}")
                self.root.update()

                if hasattr(self, "btn_title_max_lbl"):
                    self.btn_title_max_lbl.config(text="▢")
            else:
                self._aplicar_maximizacao_workarea()
        except Exception:
            pass

    def _on_window_configure(self, event):
        try:
            if event.widget == self.root:
                if self.root.state() == "zoomed":
                    self.root.state("normal")
                    self._aplicar_maximizacao_workarea()
        except Exception:
            pass

    def _fechar_janela(self):
        try:
            self.root.destroy()
        except Exception:
            pass
        os._exit(0)

    def _construir_custom_titlebar(self):
        # Header Topo Unificado inspirado no layout Stealth / Ninox
        self.custom_titlebar = tk.Frame(self.root, bg="#050608", height=36)
        self.custom_titlebar.pack(side="top", fill="x")
        self.custom_titlebar.pack_propagate(False)

        # Divisor sutil inferior
        tk.Frame(self.root, bg="#10141D", height=1).pack(side="top", fill="x")

        # 1. BOTOES DA JANELA NO CANTO DIREITO (Empacotados primeiro para NUNCA serem empurrados para fora em telas menores)
        btn_box = tk.Frame(self.custom_titlebar, bg="#050608")
        btn_box.pack(side="right", fill="y", padx=(0, 10))

        # Estilo dos botões da janela inspirado no Ninox (cards discretos com borda e hover)
        def _criar_win_ctrl(parent, icone, cmd, hover_bg="#161B26", hover_fg="#00F0FF", is_close=False):
            card = tk.Frame(parent, bg="#111622", padx=1, pady=1)
            card.pack(side="left", padx=3, pady=6)
            inner = tk.Frame(card, bg="#080B10", padx=9, pady=2, cursor="hand2")
            inner.pack()
            lbl = tk.Label(inner, text=icone, font=("Segoe UI", 9, "bold"), fg="#7E8B9F", bg="#080B10", cursor="hand2")
            lbl.pack()

            def on_enter(e):
                bg = "#E81123" if is_close else hover_bg
                fg = "#FFFFFF" if is_close else hover_fg
                card.config(bg="#FF3344" if is_close else "#00F0FF")
                inner.config(bg=bg)
                lbl.config(bg=bg, fg=fg)

            def on_leave(e):
                card.config(bg="#111622")
                inner.config(bg="#080B10")
                lbl.config(bg="#080B10", fg="#7E8B9F")

            for w in [card, inner, lbl]:
                w.bind("<Enter>", on_enter)
                w.bind("<Leave>", on_leave)
                w.bind("<Button-1>", lambda e: cmd())
            return lbl

        self.btn_title_min_lbl = _criar_win_ctrl(btn_box, "—", self._minimizar_janela)
        self.btn_title_max_lbl = _criar_win_ctrl(btn_box, "▢", self._toggle_maximizar)
        self.btn_title_close_lbl = _criar_win_ctrl(btn_box, "✕", self._fechar_janela, is_close=True)

        # 2. LADO ESQUERDO: Branding + Status Dot + Título + Versão
        left_box = tk.Frame(self.custom_titlebar, bg="#050608")
        left_box.pack(side="left", fill="y", padx=(10, 0))

        if hasattr(self, "_app_icon_photo") and self._app_icon_photo:
            lbl_ico = tk.Label(left_box, image=self._app_icon_photo, bg="#050608")
            lbl_ico.pack(side="left", padx=(0, 6))
            lbl_ico.bind("<ButtonPress-1>", self._iniciar_arrasto_janela)

        # Título estilo Ninox Solver
        lbl_brand = tk.Label(
            left_box,
            text="Pokas Store",
            font=("Segoe UI", 10, "bold"),
            fg="#F8FAFC",
            bg="#050608"
        )
        lbl_brand.pack(side="left", padx=(0, 4))
        lbl_brand.bind("<ButtonPress-1>", self._iniciar_arrasto_janela)
        lbl_brand.bind("<Double-Button-1>", lambda e: self._toggle_maximizar())

        # Dot luminoso verde status ativo
        dot_status = tk.Label(left_box, text="●", font=("Segoe UI", 8), fg="#00FF66", bg="#050608")
        dot_status.pack(side="left", padx=(0, 8))
        dot_status.bind("<ButtonPress-1>", self._iniciar_arrasto_janela)

        # Versão tag sutil
        lbl_ver = tk.Label(
            left_box,
            text=f"v{self.versao_app}",
            font=("Consolas", 8, "bold"),
            fg="#576170",
            bg="#050608"
        )
        lbl_ver.pack(side="left", padx=(0, 10))
        lbl_ver.bind("<ButtonPress-1>", self._iniciar_arrasto_janela)

        # Subtítulo descritivo com corte automático em telas menores
        lic_txt = f" [{self.license_info.get('msg', 'Licença Ativa')}]" if self.license_info else ""
        self.lbl_title_desc = tk.Label(
            left_box,
            text=f"› Automação & Resgate Rockstar{lic_txt}",
            font=("Segoe UI", 9),
            fg="#72829B",
            bg="#050608"
        )
        self.lbl_title_desc.pack(side="left")
        self.lbl_title_desc.bind("<ButtonPress-1>", self._iniciar_arrasto_janela)
        # 3. Área de arrasto central
        drag_area = tk.Frame(self.custom_titlebar, bg="#050608")
        drag_area.pack(side="left", fill="both", expand=True)

        for w in [self.custom_titlebar, drag_area, left_box, lbl_brand, dot_status, lbl_ver, self.lbl_title_desc]:
            w.bind("<ButtonPress-1>", self._iniciar_arrasto_janela)
            w.bind("<B1-Motion>", self._arrastar_janela)
            w.bind("<Double-Button-1>", lambda e: self._toggle_maximizar())
        if hasattr(self, "_app_icon_photo") and self._app_icon_photo:
            lbl_ico.bind("<ButtonPress-1>", self._iniciar_arrasto_janela)
            lbl_ico.bind("<B1-Motion>", self._arrastar_janela)

    def _construir_interface(self):
        self._construir_custom_titlebar()
        self.main_container = tk.Frame(self.root, bg=C_BG_MAIN)
        self.main_container.pack(fill="both", expand=True)

        self._construir_sidebar()
        self._construir_area_conteudo()

    def _construir_sidebar(self):
        self.sidebar = tk.Frame(self.main_container, bg=C_BG_SIDEBAR, width=80)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # Borda divisória direita
        tk.Frame(self.sidebar, bg=C_BORDER, width=1).pack(side="right", fill="y")

        # Logo Pokas Ideia Store
        logo_box = tk.Frame(self.sidebar, bg=C_BG_SIDEBAR)
        logo_box.pack(pady=(14, 20))

        logo_path = os.path.join(BASE_DIR, "logo.png")
        if os.path.exists(logo_path):
            try:
                pil_img = Image.open(logo_path).convert("RGBA")
                
                # Ícone da Janela
                icon_img = pil_img.resize((32, 32), Image.Resampling.LANCZOS)
                self.img_logo_icon = ImageTk.PhotoImage(icon_img)
                self.root.iconphoto(True, self.img_logo_icon)

                # Logo Sidebar
                sidebar_img = pil_img.resize((60, 60), Image.Resampling.LANCZOS)
                self.img_logo_sidebar = ImageTk.PhotoImage(sidebar_img)

                logo_glow = tk.Frame(logo_box, bg=C_BORDER_LIGHT, padx=1, pady=1)
                logo_glow.pack()
                logo_card = tk.Frame(logo_glow, bg="#06080D", padx=3, pady=3)
                logo_card.pack()

                lbl_img = tk.Label(logo_card, image=self.img_logo_sidebar, bg="#06080D")
                lbl_img.pack()
            except Exception:
                self._criar_logo_fallback(logo_box)
        else:
            self._criar_logo_fallback(logo_box)

        # Badge de Patente / Hierarquia abaixo da Logo
        user_role = (self.license_info.get("role") or "OPERADOR").upper()
        if user_role == "DONO":
            role_text = "👑 DONO"
            role_color = "#FFD700"  # Ouro
            role_bg = "#2B2206"
            role_border = "#66510E"
        elif user_role == "ADMIN":
            role_text = "⚡ ADMIN"
            role_color = "#FF3344"  # Vermelho Neon
            role_bg = "#2B0D0D"
            role_border = "#7F1D1D"
        else:
            role_text = "🛡️ OPERADOR"
            role_color = "#94A3B8"  # Cinza prata
            role_bg = "#161D2B"
            role_border = "#2E3C57"

        badge_role_border = tk.Frame(logo_box, bg=role_border, padx=1, pady=1)
        badge_role_border.pack(pady=(6, 0))
        badge_role_inner = tk.Frame(badge_role_border, bg=role_bg, padx=6, pady=2)
        badge_role_inner.pack()
        tk.Label(badge_role_inner, text=role_text, font=("Segoe UI", 7, "bold"), fg=role_color, bg=role_bg).pack()

        # Badge de Versão embutido na Sidebar
        badge_ver_border = tk.Frame(logo_box, bg="#1E293B", padx=1, pady=1)
        badge_ver_border.pack(pady=(4, 0))
        badge_ver_inner = tk.Frame(badge_ver_border, bg="#070A12", padx=6, pady=2)
        badge_ver_inner.pack()
        tk.Label(badge_ver_inner, text=f"v{self.versao_app}", font=("Consolas", 8, "bold"), fg=C_CYAN, bg="#070A12").pack()

        # Botões de Navegação com Indicador Luminoso
        self.nav_home_frame = self._criar_nav_btn(self.sidebar, "🏠", "Automação", lambda: self._trocar_view("home"))
        self.nav_home_frame.pack(pady=(0, 10), fill="x", padx=8)

        self.nav_redeem_frame = self._criar_nav_btn(self.sidebar, "🎮", "Resgate Licenças", lambda: self._trocar_view("redeem"))
        self.nav_redeem_frame.pack(pady=(0, 10), fill="x", padx=8)

        self.nav_files_frame = self._criar_nav_btn(self.sidebar, "📁", "Arquivos", lambda: self._trocar_view("files"))
        self.nav_files_frame.pack(pady=(0, 10), fill="x", padx=8)

        self.nav_licenses_frame = self._criar_nav_btn(self.sidebar, "🛡️", "Licenças", lambda: self._trocar_view("licenses"))
        self.nav_licenses_frame.pack(pady=(0, 10), fill="x", padx=8)

        self.view_atual = "home"
        self._atualizar_nav_botoes()

    def _criar_logo_fallback(self, parent):
        logo_glow = tk.Frame(parent, bg=C_CYAN, padx=1, pady=1)
        logo_glow.pack()
        logo_card = tk.Frame(logo_glow, bg="#0C1017", padx=6, pady=6)
        logo_card.pack()
        tk.Label(logo_card, text="💀", font=("Segoe UI Emoji", 15), fg="#FFFFFF", bg="#0C1017").pack()
        tk.Label(logo_card, text="POKAS", font=("Segoe UI", 6, "bold"), fg=C_CYAN, bg="#0C1017").pack()
        tk.Label(logo_card, text="IDEIA", font=("Segoe UI", 5, "bold"), fg=C_TEXT_MUTED, bg="#0C1017").pack()

    def _criar_nav_btn(self, parent, icone, tooltip, command):
        frame = tk.Frame(parent, bg=C_BG_SIDEBAR, height=52, cursor="hand2")
        frame.pack_propagate(False)

        indicador = tk.Frame(frame, bg=C_BG_SIDEBAR, width=3)
        indicador.pack(side="left", fill="y")

        btn_box = tk.Frame(frame, bg=C_BG_SIDEBAR)
        btn_box.pack(side="left", expand=True, fill="both", padx=(3, 0))

        lbl = tk.Label(btn_box, text=icone, font=("Segoe UI Emoji", 16), fg=C_TEXT_MUTED, bg=C_BG_SIDEBAR)
        lbl.pack(expand=True)

        frame.indicador = indicador
        frame.btn_box = btn_box
        frame.lbl = lbl

        for w in [frame, btn_box, lbl]:
            w.bind("<Button-1>", lambda e: command())
        return frame

    def _trocar_view(self, view):
        self.view_atual = view
        self._atualizar_nav_botoes()
        self.view_home_container.pack_forget()
        self.view_redeem_container.pack_forget()
        self.view_files_container.pack_forget()
        self.view_licenses_container.pack_forget()

        if view == "home":
            self.view_home_container.pack(fill="both", expand=True)
        elif view == "redeem":
            self.view_redeem_container.pack(fill="both", expand=True)
        elif view == "files":
            self.view_files_container.pack(fill="both", expand=True)
            self._carregar_arquivo_no_editor()
        elif view == "licenses":
            self.view_licenses_container.pack(fill="both", expand=True)
            self._carregar_licencas_tabela()

    def _atualizar_nav_botoes(self):
        botoes = [
            ("home", self.nav_home_frame),
            ("redeem", self.nav_redeem_frame),
            ("files", self.nav_files_frame),
            ("licenses", self.nav_licenses_frame),
        ]
        for key, frame in botoes:
            if self.view_atual == key:
                frame.config(bg="#141722")
                frame.indicador.config(bg=C_CYAN)
                frame.btn_box.config(bg="#1A1E2D")
                frame.lbl.config(fg="#FFFFFF", bg="#1A1E2D")
            else:
                frame.config(bg=C_BG_SIDEBAR)
                frame.indicador.config(bg=C_BG_SIDEBAR)
                frame.btn_box.config(bg=C_BG_SIDEBAR)
                frame.lbl.config(fg=C_TEXT_MUTED, bg=C_BG_SIDEBAR)

    def _construir_area_conteudo(self):
        self.content_area = tk.Frame(self.main_container, bg=C_BG_MAIN)
        self.content_area.pack(side="left", fill="both", expand=True)

        # Header Superior com Pill Badges Modernos
        header_bar = tk.Frame(self.content_area, bg=C_BG_HEADER, padx=20, pady=10)
        header_bar.pack(fill="x")
        tk.Frame(self.content_area, bg=C_BORDER, height=1).pack(fill="x")

        status_dev_box = tk.Frame(header_bar, bg=C_BG_HEADER)
        status_dev_box.pack(side="right")

        self.lbl_status_redmi = tk.Label(status_dev_box, text="● Redmi: Verificando...", font=("Segoe UI", 8, "bold"), fg=C_TEXT_MUTED, bg=C_BG_HEADER)
        self.lbl_status_redmi.pack(side="left", padx=(0, 10))

        self.lbl_status_a9 = tk.Label(status_dev_box, text="● Tab A9+: Verificando...", font=("Segoe UI", 8, "bold"), fg=C_TEXT_MUTED, bg=C_BG_HEADER)
        self.lbl_status_a9.pack(side="left")

        self.lbl_badge_versao_topo = self._criar_badge_moderno(status_dev_box, f"🚀 v{self.versao_app}", C_CYAN, "#0C1B26", "#0E2B3D")
        self.lbl_badge_versao_topo.pack(side="left", padx=(12, 0))

        badges_frame = tk.Frame(header_bar, bg=C_BG_HEADER)
        badges_frame.pack(side="left")

        self.lbl_badge_online = self._criar_badge_moderno(badges_frame, "● ONLINE", C_CYAN, "#0C1B26", "#0E2B3D")
        self.lbl_badge_online.pack(side="left", padx=(0, 6))

        self.lbl_badge_api = self._criar_badge_moderno(badges_frame, "⚡ API: 0 e-mails ($0.00)", "#60A5FA", "#101D33", "#172A4A")
        self.lbl_badge_api.pack(side="left", padx=4)

        self.lbl_badge_rsg = self._criar_badge_moderno(badges_frame, "🎮 Rockstar: 0", C_GREEN, "#0B2419", "#0F3827")
        self.lbl_badge_rsg.pack(side="left", padx=4)

        self.lbl_badge_codigos = self._criar_badge_moderno(badges_frame, "🔑 Códigos: 0", C_AMBER, "#261D0C", "#3D2E12")
        self.lbl_badge_codigos.pack(side="left", padx=4)

        self.lbl_badge_prontas = self._criar_badge_moderno(badges_frame, "🏆 Prontas: 0", C_PURPLE, "#1E1430", "#301F4E")
        self.lbl_badge_prontas.pack(side="left", padx=4)

        self.lbl_status_device = self.lbl_status_redmi  # alias para compatibilidade

        # Containers das Telas
        self.view_home_container = tk.Frame(self.content_area, bg=C_BG_MAIN)
        self.view_home_container.pack(fill="both", expand=True)

        self.view_redeem_container = tk.Frame(self.content_area, bg=C_BG_MAIN)
        self.view_files_container = tk.Frame(self.content_area, bg=C_BG_MAIN)
        self.view_licenses_container = tk.Frame(self.content_area, bg=C_BG_MAIN)

        self._construir_view_home()
        self._construir_view_redeem()
        self._construir_view_files()
        self._construir_view_licenses()

    def _criar_badge_moderno(self, parent, texto, cor_texto, cor_bg, cor_border):
        card = tk.Frame(parent, bg=cor_border, padx=1, pady=1)
        inner = tk.Frame(card, bg=cor_bg, padx=10, pady=4)
        inner.pack()
        lbl = tk.Label(inner, text=texto, font=("Segoe UI", 8, "bold"), fg=cor_texto, bg=cor_bg)
        lbl.pack()
        card.lbl = lbl
        card.inner = inner
        return card

    # ========================================================================
    # VIEW 1: 🏠 AUTOMAÇÃO DE CONTAS
    # ========================================================================
    def _construir_view_home(self):
        home_box = tk.Frame(self.view_home_container, bg=C_BG_MAIN, padx=20, pady=12)
        home_box.pack(fill="both", expand=True)

        # Card 1: Configuração do Provedor de E-mail & Saldo
        cfg_card = tk.Frame(home_box, bg=C_BORDER, padx=1, pady=1)
        cfg_card.pack(fill="x", pady=(0, 10))
        cfg_inner = tk.Frame(cfg_card, bg=C_BG_CARD, padx=14, pady=10)
        cfg_inner.pack(fill="x")

        top_cfg = tk.Frame(cfg_inner, bg=C_BG_CARD)
        top_cfg.pack(fill="x")

        tk.Label(top_cfg, text="PROVEDOR DE E-MAIL", font=("Segoe UI", 8, "bold"), fg=C_TEXT_MUTED, bg=C_BG_CARD).pack(side="left", padx=(0, 10))

        self.modo_var = tk.StringVar(value="mhmdo")

        rb_mhmdo = tk.Radiobutton(
            top_cfg, text="📨 mhmdo API (Gera e-mail na hora)", variable=self.modo_var, value="mhmdo",
            font=("Segoe UI", 9, "bold"), fg=C_TEXT_BODY, bg=C_BG_CARD, selectcolor=C_BG_CARD_INNER,
            activebackground=C_BG_CARD, activeforeground=C_CYAN, command=self._on_modo_change
        )
        rb_mhmdo.pack(side="left", padx=6)
        if not _MHMDO_DISPONIVEL:
            rb_mhmdo.config(state="disabled", fg="#555555")

        rb_graph = tk.Radiobutton(
            top_cfg, text="📊 Graph API (outlook.txt)", variable=self.modo_var, value="graph",
            font=("Segoe UI", 9, "bold"), fg=C_TEXT_BODY, bg=C_BG_CARD, selectcolor=C_BG_CARD_INNER,
            activebackground=C_BG_CARD, activeforeground=C_CYAN, command=self._on_modo_change
        )
        rb_graph.pack(side="left", padx=6)

        self.lbl_modo_info = tk.Label(top_cfg, text="", font=("Segoe UI", 8), fg=C_TEXT_MUTED, bg=C_BG_CARD)
        self.lbl_modo_info.pack(side="right")

        # Painel mhmdo Saldo
        self.mhmdo_panel = tk.Frame(cfg_inner, bg=C_BG_CARD)
        self.mhmdo_panel.pack(fill="x", pady=(8, 0))

        tk.Frame(self.mhmdo_panel, bg=C_BORDER, height=1).pack(fill="x", pady=(0, 8))

        saldo_row = tk.Frame(self.mhmdo_panel, bg=C_BG_CARD)
        saldo_row.pack(fill="x")

        tk.Label(saldo_row, text="💰 SALDO DISPONÍVEL:", font=("Segoe UI", 8, "bold"), fg=C_TEXT_MUTED, bg=C_BG_CARD).pack(side="left")
        self.lbl_saldo_usd = tk.Label(saldo_row, text="$0.000", font=("Segoe UI", 11, "bold"), fg=C_GREEN, bg=C_BG_CARD)
        self.lbl_saldo_usd.pack(side="left", padx=(6, 12))

        self.email_type_var = tk.StringVar(value="short")
        for val, txt, cor in [("custom", "📧 Custom ($1/1k)", "#81D8F7"), ("short", "📩 Short ($2/1k)", C_AMBER), ("full", "📬 Full Access ($6/1k)", "#C084FC")]:
            rb = tk.Radiobutton(
                saldo_row, text=txt, variable=self.email_type_var, value=val,
                font=("Segoe UI", 8, "bold"), fg=cor, bg=C_BG_CARD, selectcolor=C_BG_CARD_INNER,
                activebackground=C_BG_CARD, activeforeground=cor, command=self._on_email_type_change
            )
            rb.pack(side="left", padx=4)

        ttk.Button(saldo_row, text="🔄", style="Secondary.TButton", command=lambda: threading.Thread(target=self._atualizar_saldo_mhmdo, daemon=True).start()).pack(side="right")

        tipos_cards_frame = tk.Frame(self.mhmdo_panel, bg=C_BG_CARD)
        tipos_cards_frame.pack(fill="x", pady=(8, 0))

        self.card_custom = self._criar_card_mhmdo(tipos_cards_frame, "CUSTOM", "$1/1k", "0", "#81D8F7")
        self.card_short = self._criar_card_mhmdo(tipos_cards_frame, "SHORT", "$2/1k", "0", C_AMBER)
        self.card_full = self._criar_card_mhmdo(tipos_cards_frame, "FULL ACCESS", "$6/1k", "0", "#C084FC")
        self.card_custom.pack(side="left", expand=True, fill="x", padx=(0, 4))
        self.card_short.pack(side="left", expand=True, fill="x", padx=4)
        self.card_full.pack(side="left", expand=True, fill="x", padx=(4, 0))

        # Card 2: Meta e Métricas
        top_meta = tk.Frame(home_box, bg=C_BG_MAIN)
        top_meta.pack(fill="x", pady=(0, 10))

        meta_card = tk.Frame(top_meta, bg=C_BORDER, padx=1, pady=1)
        meta_card.pack(fill="x")
        meta_inner = tk.Frame(meta_card, bg=C_BG_CARD, padx=14, pady=8)
        meta_inner.pack(fill="x")

        tk.Label(meta_inner, text="🎯 META DE CONTAS:", font=("Segoe UI", 8, "bold"), fg=C_TEXT_MUTED, bg=C_BG_CARD).pack(side="left", padx=(0, 8))

        self.qtd_var = tk.StringVar(value="10")
        self.infinito_var = tk.BooleanVar(value=False)

        def _on_infinito_toggle():
            if self.infinito_var.get():
                self.entry_qtd.config(state="disabled")
            else:
                self.entry_qtd.config(state="normal")

        self.entry_qtd = tk.Entry(
            meta_inner, textvariable=self.qtd_var, width=6, font=("Segoe UI", 10, "bold"),
            bg=C_BG_INPUT, fg=C_GREEN, insertbackground="#FFFFFF", justify="center", bd=1, relief="solid"
        )
        self.entry_qtd.pack(side="left", padx=(0, 8))

        chk_inf = tk.Checkbutton(
            meta_inner, text="♾️ Infinito (sem limites)", variable=self.infinito_var,
            font=("Segoe UI", 9, "bold"), fg=C_TEXT_BODY, bg=C_BG_CARD, selectcolor=C_BG_CARD_INNER,
            activebackground=C_BG_CARD, activeforeground="#FFFFFF", command=_on_infinito_toggle
        )
        chk_inf.pack(side="left", padx=8)

        self.lbl_progresso_meta = tk.Label(meta_inner, text="Progresso: 0 / 10", font=("Segoe UI", 9, "bold"), fg=C_CYAN, bg=C_BG_CARD)
        self.lbl_progresso_meta.pack(side="right")

        # Métricas Cards
        stats_frame = tk.Frame(home_box, bg=C_BG_MAIN)
        stats_frame.pack(fill="x", pady=(0, 10))

        self.card_fila = self._criar_card_stat(stats_frame, "NA FILA", "0", C_TEXT_TITLE)
        self.card_feitas = self._criar_card_stat(stats_frame, "CRIADAS (ROCKSTAR)", "0", C_GREEN)
        self.card_erros = self._criar_card_stat(stats_frame, "FALHAS / ERROS", "0", C_RED)
        self.card_fila.pack(side="left", expand=True, fill="x", padx=(0, 5))
        self.card_feitas.pack(side="left", expand=True, fill="x", padx=5)
        self.card_erros.pack(side="left", expand=True, fill="x", padx=(5, 0))

        # Card 3: Seletor de Fluxo Segmented (Mobile vs PC)
        flow_card = tk.Frame(home_box, bg=C_BORDER, padx=1, pady=1)
        flow_card.pack(fill="x", pady=(0, 10))
        flow_inner = tk.Frame(flow_card, bg=C_BG_CARD, padx=12, pady=10)
        flow_inner.pack(fill="x")

        # Tabs de Switch Flat
        tabs_header = tk.Frame(flow_inner, bg=C_BG_CARD)
        tabs_header.pack(fill="x", pady=(0, 10))

        self.btn_tab_flow_mobile = tk.Button(
            tabs_header, text="📱 FLUXO MOBILE (ANDROID 4G)", font=("Segoe UI", 9, "bold"),
            bg="#1E2333", fg="#FFFFFF", bd=0, padx=16, pady=6, cursor="hand2",
            command=lambda: self._trocar_fluxo("mobile")
        )
        self.btn_tab_flow_mobile.pack(side="left", padx=(0, 6))

        self.btn_tab_flow_pc = tk.Button(
            tabs_header, text="💻 FLUXO COMPUTADOR (PC / DESKTOP)", font=("Segoe UI", 9, "bold"),
            bg=C_BG_CARD_INNER, fg=C_TEXT_MUTED, bd=0, padx=16, pady=6, cursor="hand2",
            command=lambda: self._trocar_fluxo("pc")
        )
        self.btn_tab_flow_pc.pack(side="left", padx=6)

        # Container do Painel Mobile
        self.panel_flow_mobile = tk.Frame(flow_inner, bg=C_BG_CARD)
        self.panel_flow_mobile.pack(fill="x")

        # Barra de Seleção Dinâmica de Dispositivos USB
        self.dev_select_box = tk.Frame(self.panel_flow_mobile, bg=C_BG_CARD_INNER, padx=12, pady=6)
        self.dev_select_box.pack(fill="x", pady=(0, 8))

        tk.Label(self.dev_select_box, text="DISPOSITIVOS USB:", font=("Segoe UI", 8, "bold"), fg=C_CYAN, bg=C_BG_CARD_INNER).pack(side="left", padx=(0, 8))

        self.dev_checkboxes_frame = tk.Frame(self.dev_select_box, bg=C_BG_CARD_INNER)
        self.dev_checkboxes_frame.pack(side="left", fill="x")

        # Ações de seleção rápida
        btn_dev_acoes = tk.Frame(self.dev_select_box, bg=C_BG_CARD_INNER)
        btn_dev_acoes.pack(side="right")

        tk.Button(btn_dev_acoes, text="Todos", font=("Segoe UI", 7, "bold"), bg="#1E2333", fg=C_CYAN, bd=0, padx=8, pady=2, cursor="hand2", command=self._selecionar_todos_dispositivos).pack(side="left", padx=2)
        tk.Button(btn_dev_acoes, text="Nenhum", font=("Segoe UI", 7, "bold"), bg="#1E2333", fg=C_TEXT_MUTED, bd=0, padx=6, pady=2, cursor="hand2", command=self._deselecionar_todos_dispositivos).pack(side="left", padx=2)
        tk.Button(btn_dev_acoes, text="🔄 Atualizar", font=("Segoe UI", 7, "bold"), bg="#1E2333", fg=C_GREEN, bd=0, padx=6, pady=2, cursor="hand2", command=self._acao_forcar_refresh_adb).pack(side="left", padx=(2, 0))

        btn_bar = tk.Frame(self.panel_flow_mobile, bg=C_BG_CARD)
        btn_bar.pack(fill="x")

        self.btn_iniciar_mobile = ttk.Button(btn_bar, text="▶ INICIAR MOBILE", style="Primary.TButton", command=self.acao_iniciar_mobile)
        self.btn_iniciar_mobile.pack(side="left", padx=(0, 4))

        self.btn_pausar_mob = ttk.Button(btn_bar, text="⏸ PAUSAR TODOS", style="Secondary.TButton", command=self.acao_pausar)
        self.btn_pausar_mob.pack(side="left", padx=3)

        self.container_pausas_individuais = tk.Frame(btn_bar, bg=C_BG_CARD)
        self.container_pausas_individuais.pack(side="left")

        ttk.Button(btn_bar, text="📱 SCRCPY", style="Secondary.TButton", command=self.manager.abrir_scrcpy).pack(side="left", padx=3)
        ttk.Button(btn_bar, text="🔄 ROTACIONAR 4G", style="Secondary.TButton", command=lambda: threading.Thread(target=self.manager.rotacionar_ip_4g, daemon=True).start()).pack(side="left", padx=3)
        ttk.Button(btn_bar, text="🧹 LIMPAR CHROME", style="Danger.TButton", command=lambda: threading.Thread(target=self.manager.preparar_chrome_mobile, daemon=True).start()).pack(side="right", padx=3)

        # Container do Painel PC
        self.panel_flow_pc = tk.Frame(flow_inner, bg=C_BG_CARD)

        self.btn_iniciar_pc_4g = ttk.Button(self.panel_flow_pc, text="🌐 INICIAR CRIAÇÃO (PROXY DATAIMPULSE)", style="Pc4g.TButton", command=self.acao_iniciar_pc_4g)
        self.btn_iniciar_pc_4g.pack(side="left", padx=(0, 6))

        self.btn_iniciar_pc_local = ttk.Button(self.panel_flow_pc, text="🏠 INICIAR PC (REDE LOCAL)", style="PcLocal.TButton", command=self.acao_iniciar_pc_local)
        self.btn_iniciar_pc_local.pack(side="left", padx=4)

        self.btn_pausar_pc = ttk.Button(self.panel_flow_pc, text="⏸ PAUSAR", style="Secondary.TButton", command=self.acao_pausar)
        self.btn_pausar_pc.pack(side="left", padx=4)

        tk.Label(self.panel_flow_pc, text="💡 Proxy DataImpulse BR integrado com rotação a cada conta e intervalo a cada 4 contas", font=("Segoe UI", 8), fg=C_TEXT_MUTED, bg=C_BG_CARD).pack(side="right", padx=6)

        # Terminal de Logs Moderno
        log_frame = tk.Frame(home_box, bg=C_BORDER, padx=1, pady=1)
        log_frame.pack(fill="both", expand=True)
        log_inner = tk.Frame(log_frame, bg="#07080D", padx=10, pady=8)
        log_inner.pack(fill="both", expand=True)

        log_hdr = tk.Frame(log_inner, bg="#07080D")
        log_hdr.pack(fill="x", pady=(0, 6))
        tk.Label(log_hdr, text="TERMINAL DE EXECUÇÃO EM TEMPO REAL", font=("Segoe UI", 8, "bold"), fg=C_TEXT_MUTED, bg="#07080D").pack(side="left")
        ttk.Button(log_hdr, text="🧹 LIMPAR", style="Secondary.TButton", command=self.acao_limpar_log).pack(side="right")

        self.txt_log = scrolledtext.ScrolledText(
            log_inner, bg="#07080D", fg=C_GREEN, insertbackground=C_CYAN,
            font=("Consolas", 10), borderwidth=0, highlightthickness=0
        )
        self.txt_log.pack(fill="both", expand=True)

    def _trocar_fluxo(self, fluxo):
        self.fluxo_ativo = fluxo
        if fluxo == "mobile":
            self.btn_tab_flow_mobile.config(bg="#1E2333", fg="#FFFFFF")
            self.btn_tab_flow_pc.config(bg=C_BG_CARD_INNER, fg=C_TEXT_MUTED)
            self.panel_flow_pc.pack_forget()
            self.panel_flow_mobile.pack(fill="x")
        else:
            self.btn_tab_flow_pc.config(bg="#1E2333", fg="#FFFFFF")
            self.btn_tab_flow_mobile.config(bg=C_BG_CARD_INNER, fg=C_TEXT_MUTED)
            self.panel_flow_mobile.pack_forget()
            self.panel_flow_pc.pack(fill="x")

    # ========================================================================
    # VIEW 2: 🎮 RESGATE DE LICENÇAS / ROCKSTAR LAUNCHER
    # ========================================================================
    def _construir_view_redeem(self):
        redeem_box = tk.Frame(self.view_redeem_container, bg=C_BG_MAIN, padx=20, pady=12)
        redeem_box.pack(fill="both", expand=True)

        # Banner Header Moderno
        banner_border = tk.Frame(redeem_box, bg=C_BORDER, padx=1, pady=1)
        banner_border.pack(fill="x", pady=(0, 10))
        banner_inner = tk.Frame(banner_border, bg=C_BG_CARD, padx=16, pady=12)
        banner_inner.pack(fill="x")

        tk.Label(banner_inner, text="🎮 Resgate de Licenças Rockstar", font=("Segoe UI", 15, "bold"), fg=C_TEXT_TITLE, bg=C_BG_CARD).pack(anchor="w")
        tk.Label(banner_inner, text="Automação de login com 2FA TOTP, resgate de chaves de ativação e finalização de contas prontas.", font=("Segoe UI", 9), fg=C_TEXT_MUTED, bg=C_BG_CARD).pack(anchor="w", pady=(2, 0))

        # Cards de Métricas do Resgate
        stats_redeem = tk.Frame(redeem_box, bg=C_BG_MAIN)
        stats_redeem.pack(fill="x", pady=(0, 10))

        self.card_redeem_feitas = self._criar_card_stat(stats_redeem, "CONTAS DISPONÍVEIS (ROCKSTAR)", "0", C_GREEN)
        self.card_redeem_codigos = self._criar_card_stat(stats_redeem, "CÓDIGOS NA FILA (LICENÇAS)", "0", C_AMBER)
        self.card_redeem_prontas = self._criar_card_stat(stats_redeem, "CONTAS ATIVADAS (PRONTAS)", "0", C_PURPLE)
        self.card_redeem_feitas.pack(side="left", expand=True, fill="x", padx=(0, 5))
        self.card_redeem_codigos.pack(side="left", expand=True, fill="x", padx=5)
        self.card_redeem_prontas.pack(side="left", expand=True, fill="x", padx=(5, 0))

        # Meta de Resgates
        meta_redeem_card = tk.Frame(redeem_box, bg=C_BORDER, padx=1, pady=1)
        meta_redeem_card.pack(fill="x", pady=(0, 10))
        meta_redeem_inner = tk.Frame(meta_redeem_card, bg=C_BG_CARD, padx=14, pady=8)
        meta_redeem_inner.pack(fill="x")

        tk.Label(meta_redeem_inner, text="🎯 QUANTIDADE A RESGATAR:", font=("Segoe UI", 8, "bold"), fg=C_TEXT_MUTED, bg=C_BG_CARD).pack(side="left", padx=(0, 8))

        self.qtd_redeem_var = tk.StringVar(value="10")
        self.infinito_redeem_var = tk.BooleanVar(value=False)

        def _on_infinito_redeem_toggle():
            if self.infinito_redeem_var.get():
                self.entry_qtd_redeem.config(state="disabled")
            else:
                self.entry_qtd_redeem.config(state="normal")

        self.entry_qtd_redeem = tk.Entry(
            meta_redeem_inner, textvariable=self.qtd_redeem_var, width=6, font=("Segoe UI", 10, "bold"),
            bg=C_BG_INPUT, fg=C_PURPLE, insertbackground="#FFFFFF", justify="center", bd=1, relief="solid"
        )
        self.entry_qtd_redeem.pack(side="left", padx=(0, 8))

        chk_inf_redeem = tk.Checkbutton(
            meta_redeem_inner, text="♾️ Infinito (resgatar toda a fila)", variable=self.infinito_redeem_var,
            font=("Segoe UI", 9, "bold"), fg=C_TEXT_BODY, bg=C_BG_CARD, selectcolor=C_BG_CARD_INNER,
            activebackground=C_BG_CARD, activeforeground="#FFFFFF", command=_on_infinito_redeem_toggle
        )
        chk_inf_redeem.pack(side="left", padx=8)

        self.lbl_progresso_redeem = tk.Label(meta_redeem_inner, text="Progresso: 0 / 10", font=("Segoe UI", 9, "bold"), fg=C_PURPLE, bg=C_BG_CARD)
        self.lbl_progresso_redeem.pack(side="right")

        # Controles
        ctrl_card = tk.Frame(redeem_box, bg=C_BORDER, padx=1, pady=1)
        ctrl_card.pack(fill="x", pady=(0, 10))
        ctrl_inner = tk.Frame(ctrl_card, bg=C_BG_CARD, padx=14, pady=10)
        ctrl_inner.pack(fill="x")

        ttk.Button(ctrl_inner, text="🚀 ABRIR ROCKSTAR LAUNCHER", style="Cyan.TButton", command=lambda: abrir_rockstar_launcher(self.adicionar_log_redeem)).pack(side="left", padx=(0, 8))

        self.btn_iniciar_redeem = ttk.Button(ctrl_inner, text="▶ INICIAR AUTOMAÇÃO", style="Primary.TButton", command=self.acao_iniciar_resgate)
        self.btn_iniciar_redeem.pack(side="left", padx=4)

        def _exec_limpeza_manual():
            self.teve_limpeza = True
            limpar_cache_profundo_rockstar(self.adicionar_log_redeem)
            _rotacionar_ip_direto(self.adicionar_log_redeem)

        ttk.Button(ctrl_inner, text="🧹 LIMPEZA PROFUNDA LAUNCHER", style="Danger.TButton", command=lambda: threading.Thread(target=_exec_limpeza_manual, daemon=True).start()).pack(side="left", padx=6)
        ttk.Button(ctrl_inner, text="🔄 ROTACIONAR 4G", style="Secondary.TButton", command=lambda: threading.Thread(target=lambda: _rotacionar_ip_direto(self.adicionar_log_redeem), daemon=True).start()).pack(side="left", padx=4)

        self.lbl_redeem_status = tk.Label(ctrl_inner, text="Pronto para iniciar.", font=("Segoe UI", 9, "bold"), fg=C_TEXT_MUTED, bg=C_BG_CARD)
        self.lbl_redeem_status.pack(side="right", padx=6)

        # Terminal de Logs do Resgate
        log_card = tk.Frame(redeem_box, bg=C_BORDER, padx=1, pady=1)
        log_card.pack(fill="both", expand=True)
        log_inner = tk.Frame(log_card, bg="#07080D", padx=10, pady=8)
        log_inner.pack(fill="both", expand=True)

        top_log = tk.Frame(log_inner, bg="#07080D")
        top_log.pack(fill="x", pady=(0, 6))
        tk.Label(top_log, text="LOG DE ATIVAÇÃO DE CÓDIGOS EM TEMPO REAL", font=("Segoe UI", 8, "bold"), fg=C_TEXT_MUTED, bg="#07080D").pack(side="left")
        ttk.Button(top_log, text="🧹 LIMPAR", style="Secondary.TButton", command=lambda: self.txt_log_redeem.delete("1.0", tk.END)).pack(side="right")

        self.txt_log_redeem = scrolledtext.ScrolledText(
            log_inner, bg="#07080D", fg=C_CYAN, insertbackground=C_CYAN,
            font=("Consolas", 10), borderwidth=0, highlightthickness=0
        )
        self.txt_log_redeem.pack(fill="both", expand=True)

    def adicionar_log_redeem(self, texto):
        def _append():
            ts = time.strftime("[%H:%M:%S] ")
            self.txt_log_redeem.insert(tk.END, ts + texto + "\n")
            self.txt_log_redeem.see(tk.END)
        self.root.after(0, _append)

    def acao_iniciar_resgate(self):
        if self.redeem_running:
            self.redeem_running = False
            self.btn_iniciar_redeem.config(text="▶ INICIAR AUTOMAÇÃO", style="Primary.TButton")
            self.lbl_redeem_status.config(text="⏹️ Automação interrompida.", fg=C_RED)
            if self.current_redeem_browser:
                try: self.current_redeem_browser.close()
                except Exception: pass
            if self.current_redeem_pw:
                try: self.current_redeem_pw.stop()
                except Exception: pass
        else:
            self.redeem_running = True
            self.redeem_paused = False
            self.btn_iniciar_redeem.config(text="⏹ PARAR AUTOMAÇÃO", style="Danger.TButton")
            self.lbl_redeem_status.config(text="⚡ Executando automação...", fg=C_CYAN)
            threading.Thread(target=self._loop_resgate, daemon=True).start()

    def acao_pausar_resgate(self):
        if not self.redeem_running:
            return
        self.redeem_paused = not self.redeem_paused
        txt = "▶ RETOMAR" if self.redeem_paused else "⏸ PAUSAR"
        self.btn_pausar_redeem.config(text=txt)
        if self.redeem_paused:
            self.adicionar_log_redeem("⏸ Resgate pausado.")
        else:
            self.adicionar_log_redeem("▶ Resgate retomado.")

    def _loop_resgate(self):
        self.adicionar_log_redeem("🚀 Iniciando fluxo de login e resgate de licenças...")
        pw = sync_playwright().start()
        self.current_redeem_pw = pw
        contas_resgatadas_bloco = 0
        resgatadas_sessao = 0
        ultimo_email_falha = None
        falhas_consecutivas_conta = 0

        if self.infinito_redeem_var.get():
            meta_redeem = 0
            infinito = True
        else:
            try:
                meta_redeem = max(1, int(self.qtd_redeem_var.get().strip()))
            except Exception:
                meta_redeem = 10
            infinito = False

        self.root.after(0, lambda: self.lbl_progresso_redeem.config(text=f"Progresso: 0 / {meta_redeem}" if not infinito else "Progresso: 0 resgatadas (♾️)"))

        # Garante que o Launcher está aberto e pronto antes de iniciar as contas
        hwnd_inicial = obter_hwnd_launcher()
        if not hwnd_inicial:
            self.adicionar_log_redeem("🚀 Launcher não encontrado aberto. Inicializando Rockstar Games Launcher...")
            abrir_rockstar_launcher(self.adicionar_log_redeem)
            hwnd_inicial = aguardar_janela_launcher(self.adicionar_log_redeem, timeout=40, manager=self)
            if hwnd_inicial:
                trazer_janela_frente(hwnd_inicial)
                self.adicionar_log_redeem("⏳ Aguardando 10s para carregamento completo da interface...")
                _sleep_check(10.0, self)

        try:
            while self.redeem_running:
                if self.redeem_paused:
                    time.sleep(1)
                    continue

                if not infinito and resgatadas_sessao >= meta_redeem:
                    self.adicionar_log_redeem(f"🎯 Meta de {meta_redeem} contas resgatadas atingida com sucesso!")
                    break

                conta = carregar_proxima_conta_feita()
                if not conta:
                    self.adicionar_log_redeem("🎉 Todas as contas de rockstar.txt já foram resgatadas!")
                    break

                codigo = carregar_proximo_codigo()
                if not codigo:
                    self.adicionar_log_redeem("⚠️ Não há mais códigos de licença disponíveis em codigos.txt! Cole mais códigos na aba Arquivos.")
                    break

                precisa_popup = getattr(self, 'teve_limpeza', False)
                is_primeira = (resgatadas_sessao == 0)
                sucesso = executar_fluxo_resgate_codigo(pw, conta, codigo, log_cb=self.adicionar_log_redeem, manager=self, precisa_fechar_popup=precisa_popup, is_primeira_conta=is_primeira)
                self.atualizar_contadores()

                if sucesso:
                    self.teve_limpeza = False
                    resgatadas_sessao += 1
                    contas_resgatadas_bloco += 1
                    ultimo_email_falha = None
                    falhas_consecutivas_conta = 0

                    if infinito:
                        self.root.after(0, lambda r=resgatadas_sessao: self.lbl_progresso_redeem.config(text=f"Progresso: {r} resgatadas (♾️)"))
                    else:
                        self.root.after(0, lambda r=resgatadas_sessao, m=meta_redeem: self.lbl_progresso_redeem.config(text=f"Progresso: {r} / {m}"))

                    if not infinito and resgatadas_sessao >= meta_redeem:
                        self.adicionar_log_redeem(f"🎯 Meta de {meta_redeem} contas resgatadas concluída com sucesso! 🟢")
                        break

                    # Quando meta > 6 ou infinito, a cada 6 contas faz a limpeza profunda + rotação 4G + pausa de 2 minutos
                    if (infinito or meta_redeem > 6) and (contas_resgatadas_bloco % 6 == 0):
                        self.adicionar_log_redeem("⏳ Bloco de 6 contas concluído! Executando LIMPEZA PROFUNDA do Launcher e renovando IP 4G...")
                        limpar_cache_profundo_rockstar(self.adicionar_log_redeem)
                        self.teve_limpeza = True
                        _rotacionar_ip_direto(self.adicionar_log_redeem)
                        self.adicionar_log_redeem("⏳ Pausando por 2 minutos (120s) para esfriar conexão e resetar rate limit...")
                        for sec in range(120, 0, -1):
                            if not self.redeem_running:
                                break
                            if sec in [120, 90, 60, 30, 10]:
                                self.adicionar_log_redeem(f"⏳ Retomando resgate em {sec}s...")
                            time.sleep(1)
                        if self.redeem_running:
                            self.adicionar_log_redeem("🚀 Reabrindo Rockstar Games Launcher limpo...")
                            abrir_rockstar_launcher(self.adicionar_log_redeem)
                            hwnd = aguardar_janela_launcher(self.adicionar_log_redeem, timeout=45, manager=self)
                            if hwnd:
                                trazer_janela_frente(hwnd)
                            self.adicionar_log_redeem("⏳ Aguardando 12s para o Launcher carregar por completo pós-intervalo de 2 minutos...")
                            if not _sleep_check(12.0, self):
                                break
                            self.adicionar_log_redeem("▶️ Retomando fluxo de resgate de licenças!")
                            contas_resgatadas_bloco = 0
                            continue
                else:
                    if self.redeem_running:
                        email_atual = conta.get("email", "").strip().lower()
                        if email_atual == ultimo_email_falha:
                            falhas_consecutivas_conta += 1
                        else:
                            ultimo_email_falha = email_atual
                            falhas_consecutivas_conta = 1

                        if falhas_consecutivas_conta >= 2:
                            tempo_espera = 300
                            tempo_str = "5 minutos (300s)"
                            proxima_tentativa = falhas_consecutivas_conta + 1
                            self.adicionar_log_redeem(f"⚠️ Rate limit consecutivo detectado (#1.000.7) em {email_atual} ({falhas_consecutivas_conta}ª falha). Aumentando intervalo para a {proxima_tentativa}ª tentativa para 5 minutos...")
                        else:
                            tempo_espera = 120
                            tempo_str = "2 minutos (120s)"
                            self.adicionar_log_redeem(f"⚠️ Rate limit detectado (#1.000.7) em {email_atual}. Executando Limpeza Profunda, renovando IP 4G e aguardando 2 minutos para a 2ª tentativa...")

                        limpar_cache_profundo_rockstar(self.adicionar_log_redeem)
                        self.teve_limpeza = True
                        _rotacionar_ip_direto(self.adicionar_log_redeem)
                        self.adicionar_log_redeem(f"⏳ Pausando por {tempo_str} para esfriar conexão e resetar rate limit...")
                        for sec in range(tempo_espera, 0, -1):
                            if not self.redeem_running:
                                break
                            if sec in [300, 240, 180, 120, 90, 60, 30, 10]:
                                self.adicionar_log_redeem(f"⏳ Retomando em {sec}s...")
                            time.sleep(1)
                        if self.redeem_running:
                            self.adicionar_log_redeem("🚀 Reabrindo Rockstar Games Launcher limpo...")
                            abrir_rockstar_launcher(self.adicionar_log_redeem)
                            hwnd = aguardar_janela_launcher(self.adicionar_log_redeem, timeout=45, manager=self)
                            if hwnd:
                                trazer_janela_frente(hwnd)
                            self.adicionar_log_redeem(f"⏳ Aguardando 12s para o Launcher carregar por completo pós-intervalo de {tempo_str}...")
                            if not _sleep_check(12.0, self):
                                break
                            self.adicionar_log_redeem(f"🔁 Retomando resgate da MESMA conta (Tentativa {falhas_consecutivas_conta + 1}): {conta.get('email', '')}")
                            contas_resgatadas_bloco = 0
                            continue

                if self.redeem_running:
                    time.sleep(1)
        except Exception as e:
            self.adicionar_log_redeem(f"❌ Erro no loop de resgate: {e}")
        finally:
            try: pw.stop()
            except Exception: pass
            self.current_redeem_pw = None
            self.redeem_running = False
            self.root.after(0, lambda: self.btn_iniciar_redeem.config(text="▶ INICIAR AUTOMAÇÃO", style="Primary.TButton"))
            self.root.after(0, lambda: self.lbl_redeem_status.config(text="Finalizado.", fg=C_TEXT_MUTED))
            self.adicionar_log_redeem("⏹️ Processo de resgate encerrado.")
            self.atualizar_contadores()

    # ========================================================================
    # VIEW 3: 📁 ARQUIVOS (GERENCIADOR DE PROJETO)
    # ========================================================================
    def _construir_view_files(self):
        files_box = tk.Frame(self.view_files_container, bg=C_BG_MAIN, padx=20, pady=12)
        files_box.pack(fill="both", expand=True)

        # Header da Seção Arquivos
        hdr_border = tk.Frame(files_box, bg=C_BORDER, padx=1, pady=1)
        hdr_border.pack(fill="x", pady=(0, 10))
        hdr_card = tk.Frame(hdr_border, bg=C_BG_CARD, padx=16, pady=12)
        hdr_card.pack(fill="x")

        tk.Label(hdr_card, text="📁 Gerenciador de Arquivos do Projeto", font=("Segoe UI", 15, "bold"), fg=C_TEXT_TITLE, bg=C_BG_CARD).pack(anchor="w")
        tk.Label(hdr_card, text="Edite, revise e salve seus arquivos de contas, chaves e licenças diretamente com persistência segura.", font=("Segoe UI", 9), fg=C_TEXT_MUTED, bg=C_BG_CARD).pack(anchor="w", pady=(2, 0))

        # Card Principal do Editor
        proj_border = tk.Frame(files_box, bg=C_BORDER, padx=1, pady=1)
        proj_border.pack(fill="both", expand=True)
        proj_card = tk.Frame(proj_border, bg=C_BG_CARD, padx=14, pady=12)
        proj_card.pack(fill="both", expand=True)

        # Barra de Abas dos Arquivos
        tabs_bar = tk.Frame(proj_card, bg=C_BG_CARD)
        tabs_bar.pack(fill="x", pady=(0, 10))

        self.btn_tab_criar = tk.Button(
            tabs_bar, text="📧 [ Outlooks ]", font=("Segoe UI", 8, "bold"),
            bg=C_BG_CARD_INNER, fg=C_TEXT_MUTED, bd=0, padx=12, pady=5, cursor="hand2",
            command=lambda: self._selecionar_aba_arquivo("criar")
        )
        self.btn_tab_criar.pack(side="left", padx=(0, 4))

        self.btn_tab_feitas = tk.Button(
            tabs_bar, text="🎮 [ Rockstar ]", font=("Segoe UI", 8, "bold"),
            bg=C_BG_CARD_INNER, fg=C_TEXT_MUTED, bd=0, padx=12, pady=5, cursor="hand2",
            command=lambda: self._selecionar_aba_arquivo("feitas")
        )
        self.btn_tab_feitas.pack(side="left", padx=4)

        self.btn_tab_codigos = tk.Button(
            tabs_bar, text="🔑 [ Códigos ]", font=("Segoe UI", 8, "bold"),
            bg="#1E2333", fg="#FFFFFF", bd=0, padx=12, pady=5, cursor="hand2",
            command=lambda: self._selecionar_aba_arquivo("codigos")
        )
        self.btn_tab_codigos.pack(side="left", padx=4)

        self.btn_tab_prontas = tk.Button(
            tabs_bar, text="🏆 [ Prontas ]", font=("Segoe UI", 8, "bold"),
            bg=C_BG_CARD_INNER, fg=C_TEXT_MUTED, bd=0, padx=12, pady=5, cursor="hand2",
            command=lambda: self._selecionar_aba_arquivo("prontas")
        )
        self.btn_tab_prontas.pack(side="left", padx=4)

        self.btn_tab_erro = tk.Button(
            tabs_bar, text="❌ [ Erros ]", font=("Segoe UI", 8, "bold"),
            bg=C_BG_CARD_INNER, fg=C_TEXT_MUTED, bd=0, padx=12, pady=5, cursor="hand2",
            command=lambda: self._selecionar_aba_arquivo("erro")
        )
        self.btn_tab_erro.pack(side="left", padx=4)

        self.lbl_file_status_badge = tk.Label(tabs_bar, text="Pronto.", font=("Segoe UI", 8, "bold"), fg=C_CYAN, bg=C_BG_CARD)
        self.lbl_file_status_badge.pack(side="right")

        # Editor de Texto
        editor_border = tk.Frame(proj_card, bg=C_BORDER, padx=1, pady=1)
        editor_border.pack(fill="both", expand=True, pady=(0, 10))

        self.txt_editor = scrolledtext.ScrolledText(
            editor_border, bg="#07080D", fg=C_TEXT_BODY, insertbackground=C_CYAN,
            font=("Consolas", 10), borderwidth=0, highlightthickness=0
        )
        self.txt_editor.pack(fill="both", expand=True)

        # Barra Inferior com Informações e Ações
        bot_bar = tk.Frame(proj_card, bg=C_BG_CARD)
        bot_bar.pack(fill="x")

        self.lbl_file_info = tk.Label(bot_bar, text="Arquivo: contas/codigos.txt | 0 registros", font=("Segoe UI", 8), fg=C_TEXT_MUTED, bg=C_BG_CARD)
        self.lbl_file_info.pack(side="left")

        actions_frame = tk.Frame(bot_bar, bg=C_BG_CARD)
        actions_frame.pack(side="right")

        ttk.Button(actions_frame, text="🧹 LIMPAR", style="Secondary.TButton", command=self._acao_limpar_editor).pack(side="left", padx=3)
        ttk.Button(actions_frame, text="📋 COPIAR TUDO", style="Secondary.TButton", command=self._acao_copiar_editor).pack(side="left", padx=3)
        ttk.Button(actions_frame, text="🔄 RECARREGAR", style="Secondary.TButton", command=self._carregar_arquivo_no_editor).pack(side="left", padx=3)
        ttk.Button(actions_frame, text="💾 SALVAR", style="Primary.TButton", command=self._acao_salvar_editor).pack(side="left", padx=(3, 0))

    def _selecionar_aba_arquivo(self, arquivo):
        self.arquivo_ativo = arquivo
        botoes = [
            (self.btn_tab_criar, "criar"),
            (self.btn_tab_feitas, "feitas"),
            (self.btn_tab_codigos, "codigos"),
            (self.btn_tab_prontas, "prontas"),
            (self.btn_tab_erro, "erro")
        ]
        for btn, key in botoes:
            if key == arquivo:
                btn.config(bg="#1E2333", fg="#FFFFFF")
            else:
                btn.config(bg=C_BG_CARD_INNER, fg=C_TEXT_MUTED)
        self._carregar_arquivo_no_editor()

    def _obter_caminho_arquivo_ativo(self):
        if self.arquivo_ativo == "criar":
            return OUTLOOK_FILE
        elif self.arquivo_ativo == "feitas":
            return ROCKSTAR_FILE
        elif self.arquivo_ativo == "codigos":
            return CODIGOS_FILE
        elif self.arquivo_ativo == "prontas":
            return PRONTAS_FILE
        else:
            return ERRO_FILE

    def _carregar_arquivo_no_editor(self):
        caminho = self._obter_caminho_arquivo_ativo()
        conteudo = ""
        linhas = 0
        if os.path.exists(caminho):
            try:
                with open(caminho, "r", encoding="utf-8") as f:
                    conteudo = f.read()
                linhas = len([l for l in conteudo.splitlines() if l.strip() and not l.startswith("#")])
            except Exception as e:
                conteudo = f"Erro ao ler arquivo: {e}"

        self.txt_editor.delete("1.0", tk.END)
        self.txt_editor.insert(tk.END, conteudo)
        self.lbl_file_info.config(text=f"Arquivo: {os.path.basename(caminho)} | {linhas} registros carregados")
        self.lbl_file_status_badge.config(text="Arquivo carregado.", fg=C_CYAN)

    def _acao_salvar_editor(self):
        caminho = self._obter_caminho_arquivo_ativo()
        conteudo = self.txt_editor.get("1.0", tk.END).strip()
        try:
            with open(caminho, "w", encoding="utf-8") as f:
                f.write(conteudo + ("\n" if conteudo else ""))
            linhas = len([l for l in conteudo.splitlines() if l.strip() and not l.startswith("#")])
            self.lbl_file_status_badge.config(text=f"✅ Salvo com sucesso! ({linhas} registros)", fg=C_GREEN)
            self.lbl_file_info.config(text=f"Arquivo: {os.path.basename(caminho)} | {linhas} registros salvos")
            self.atualizar_contadores()
        except Exception as e:
            self.lbl_file_status_badge.config(text=f"❌ Erro ao salvar: {e}", fg=C_RED)

    def _acao_copiar_editor(self):
        conteudo = self.txt_editor.get("1.0", tk.END).strip()
        self.root.clipboard_clear()
        self.root.clipboard_append(conteudo)
        self.lbl_file_status_badge.config(text="📋 Copiado para a área de transferência!", fg=C_CYAN)

    def _acao_limpar_editor(self):
        self.txt_editor.delete("1.0", tk.END)
        self.lbl_file_status_badge.config(text="🧹 Editor limpo. Clique em Salvar para gravar.", fg=C_AMBER)

    # ========================================================================
    # VIEW 4: 🛡️ GESTÃO DE LICENÇAS & DISPOSITIVOS (CLOUDFLARE KV)
    # ========================================================================
    def _obter_admin_secret(self):
        if getattr(self, "_admin_secret_session", None):
            return self._admin_secret_session
        key_path = os.path.join(BASE_DIR, "admin_master.key")
        if os.path.exists(key_path):
            try:
                with open(key_path, "r", encoding="utf-8") as f:
                    sec = f.read().strip()
                    if sec:
                        self._admin_secret_session = sec
                        return sec
            except Exception:
                pass
        env_sec = os.environ.get("POKAS_ADMIN_SECRET", "").strip()
        if env_sec:
            self._admin_secret_session = env_sec
            return env_sec
        return ""

    def _fazer_requisicao_admin(self, path, method="GET", body=None, token_override=None):
        server_url = "https://pokas-auth.leolcw2.workers.dev"
        url = f"{server_url.rstrip('/')}{path}"
        secret = token_override or self._obter_admin_secret()
        headers = {
            "Authorization": f"Bearer {secret}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 PokasAdmin/1.0"
        }
        data = json.dumps(body).encode("utf-8") if body else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=6) as res:
                return json.loads(res.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read().decode("utf-8"))
            except Exception:
                return {"error": f"HTTP {e.code}"}
        except Exception as e:
            return {"error": f"Falha de conexão ({e})"}

    def _formatar_timestamp_ms(self, ts):
        if not ts:
            return "—"
        try:
            return datetime.fromtimestamp(ts / 1000.0).strftime("%d/%m/%Y %H:%M")
        except Exception:
            return str(ts)

    def _construir_view_licenses(self):
        self._licencas_cache = []

        # Box de Autenticação (quando compilado sem admin_master.key)
        self.lic_auth_box = tk.Frame(self.view_licenses_container, bg=C_BG_MAIN, padx=20, pady=40)
        
        auth_card_border = tk.Frame(self.lic_auth_box, bg=C_BORDER, padx=1, pady=1)
        auth_card_border.pack(pady=40)
        auth_card = tk.Frame(auth_card_border, bg=C_BG_CARD, padx=30, pady=25)
        auth_card.pack()

        tk.Label(auth_card, text="🔒", font=("Segoe UI Emoji", 26), bg=C_BG_CARD).pack()
        tk.Label(auth_card, text="Painel do Administrador Protegido", font=("Segoe UI", 13, "bold"), fg=C_TEXT_TITLE, bg=C_BG_CARD).pack(pady=(6, 4))
        tk.Label(auth_card, text="Insira o Token Mestre de Administrador para gerenciar e emitir licenças:", font=("Segoe UI", 9), fg=C_TEXT_MUTED, bg=C_BG_CARD).pack(pady=(0, 14))

        self.entry_admin_token = tk.Entry(auth_card, font=("Segoe UI", 11), bg=C_BG_INPUT, fg="#FFFFFF", insertbackground=C_CYAN, bd=1, relief="solid", width=34, show="•")
        self.entry_admin_token.pack(pady=(0, 12))
        self.entry_admin_token.bind("<Return>", lambda e: self._tentar_desbloquear_admin())

        self.lbl_auth_status = tk.Label(auth_card, text="", font=("Segoe UI", 8), fg=C_RED, bg=C_BG_CARD)
        self.lbl_auth_status.pack(pady=(0, 8))

        ttk.Button(auth_card, text="🔓 ACESSAR PAINEL ADMIN", style="Primary.TButton", command=self._tentar_desbloquear_admin).pack()

        # Box Principal do Gerenciador de Licenças
        self.lic_main_box = tk.Frame(self.view_licenses_container, bg=C_BG_MAIN)
        lic_box = tk.Frame(self.lic_main_box, bg=C_BG_MAIN, padx=20, pady=12)
        lic_box.pack(fill="both", expand=True)

        # Header da Seção
        hdr_border = tk.Frame(lic_box, bg=C_BORDER, padx=1, pady=1)
        hdr_border.pack(fill="x", pady=(0, 10))
        hdr_card = tk.Frame(hdr_border, bg=C_BG_CARD, padx=16, pady=12)
        hdr_card.pack(fill="x")

        hdr_top = tk.Frame(hdr_card, bg=C_BG_CARD)
        hdr_top.pack(fill="x")

        tk.Label(hdr_top, text="🛡️ Painel de Gerenciamento de Licenças", font=("Segoe UI", 15, "bold"), fg=C_TEXT_TITLE, bg=C_BG_CARD).pack(side="left")

        self.lbl_lic_server_status = tk.Label(hdr_top, text="● Cloudflare KV Conectado", font=("Segoe UI", 8, "bold"), fg=C_GREEN, bg="#0B2419", padx=10, pady=3)
        self.lbl_lic_server_status.pack(side="right")

        tk.Label(hdr_card, text="Gere novas chaves com auto-bind no primeiro uso, acompanhe computadores vinculados e revogue acessos instantaneamente.", font=("Segoe UI", 9), fg=C_TEXT_MUTED, bg=C_BG_CARD).pack(anchor="w", pady=(2, 0))

        # Cards de Métricas
        stats_lic = tk.Frame(lic_box, bg=C_BG_MAIN)
        stats_lic.pack(fill="x", pady=(0, 10))

        self.card_lic_total = self._criar_card_stat(stats_lic, "TOTAL DE CHAVES", "0", C_TEXT_TITLE)
        self.card_lic_vinculadas = self._criar_card_stat(stats_lic, "ATIVAS (VINCULADAS)", "0", C_GREEN)
        self.card_lic_livres = self._criar_card_stat(stats_lic, "AGUARDANDO 1º USO", "0", C_AMBER)
        self.card_lic_revogadas = self._criar_card_stat(stats_lic, "REVOGADAS / BLOQUEADAS", "0", C_RED)

        self.card_lic_total.pack(side="left", expand=True, fill="x", padx=(0, 4))
        self.card_lic_vinculadas.pack(side="left", expand=True, fill="x", padx=4)
        self.card_lic_livres.pack(side="left", expand=True, fill="x", padx=4)
        self.card_lic_revogadas.pack(side="left", expand=True, fill="x", padx=(4, 0))

        # Card de Geração de Chaves
        gen_border = tk.Frame(lic_box, bg=C_BORDER, padx=1, pady=1)
        gen_border.pack(fill="x", pady=(0, 10))
        gen_card = tk.Frame(gen_border, bg=C_BG_CARD, padx=16, pady=12)
        gen_card.pack(fill="x")

        tk.Label(gen_card, text="⚡ GERADOR DE NOVA CHAVE (AUTO-BIND NO 1º USO)", font=("Segoe UI", 10, "bold"), fg=C_CYAN, bg=C_BG_CARD).pack(anchor="w")

        gen_inputs = tk.Frame(gen_card, bg=C_BG_CARD)
        gen_inputs.pack(fill="x", pady=(8, 6))

        tk.Label(gen_inputs, text="Operador / Rótulo:", font=("Segoe UI", 9, "bold"), fg=C_TEXT_BODY, bg=C_BG_CARD).pack(side="left", padx=(0, 6))
        self.entry_lic_operador = tk.Entry(gen_inputs, font=("Segoe UI", 10), bg=C_BG_INPUT, fg="#FFFFFF", insertbackground=C_CYAN, bd=1, relief="solid", width=22)
        self.entry_lic_operador.insert(0, "Operador 01")
        self.entry_lic_operador.pack(side="left", padx=(0, 16))

        tk.Label(gen_inputs, text="Validade:", font=("Segoe UI", 9, "bold"), fg=C_TEXT_BODY, bg=C_BG_CARD).pack(side="left", padx=(0, 6))
        self.combo_lic_dias = ttk.Combobox(gen_inputs, values=["7 dias", "15 dias", "30 dias", "60 dias", "90 dias", "Vitalícia"], state="readonly", width=12, font=("Segoe UI", 9))
        self.combo_lic_dias.set("30 dias")
        self.combo_lic_dias.pack(side="left", padx=(0, 14))

        tk.Label(gen_inputs, text="Nível:", font=("Segoe UI", 9, "bold"), fg=C_TEXT_BODY, bg=C_BG_CARD).pack(side="left", padx=(0, 6))
        self.combo_lic_role = ttk.Combobox(gen_inputs, values=["OPERADOR", "ADMIN"], state="readonly", width=13, font=("Segoe UI", 9))
        self.combo_lic_role.set("OPERADOR")
        self.combo_lic_role.pack(side="left", padx=(0, 16))

        self.btn_gerar_chave = ttk.Button(gen_inputs, text="➕ GERAR CHAVE ONLINE", style="Primary.TButton", command=self._acao_gerar_chave_gui)
        self.btn_gerar_chave.pack(side="left")

        # Linha com Chave Gerada e Botão de Cópia
        self.frame_chave_gerada = tk.Frame(gen_card, bg=C_BG_CARD_INNER, padx=12, pady=8)
        self.frame_chave_gerada.pack(fill="x", pady=(4, 0))

        tk.Label(self.frame_chave_gerada, text="ÚLTIMA CHAVE GERADA:", font=("Segoe UI", 8, "bold"), fg=C_TEXT_MUTED, bg=C_BG_CARD_INNER).pack(side="left", padx=(0, 8))

        self.entry_chave_display = tk.Entry(
            self.frame_chave_gerada, font=("Consolas", 10, "bold"), bg="#080C14", fg=C_GREEN,
            insertbackground=C_GREEN, bd=1, relief="solid", justify="center", width=26
        )
        self.entry_chave_display.insert(0, "POKAS - xxxx - xxxx - xxxx")
        self.entry_chave_display.config(state="readonly")
        self.entry_chave_display.pack(side="left", padx=(0, 8))

        self.btn_copiar_chave_gerada = ttk.Button(self.frame_chave_gerada, text="📋 COPIAR", style="Secondary.TButton", command=self._acao_copiar_chave_gerada)
        self.btn_copiar_chave_gerada.pack(side="left", padx=(0, 12))

        self.lbl_chave_feedback = tk.Label(self.frame_chave_gerada, text="💡 Ao enviar ao subordinado, ela travará no HWID dele no 1º uso automaticamente.", font=("Segoe UI", 8), fg=C_TEXT_MUTED, bg=C_BG_CARD_INNER)
        self.lbl_chave_feedback.pack(side="left")

        # Tabela de Licenças
        table_border = tk.Frame(lic_box, bg=C_BORDER, padx=1, pady=1)
        table_border.pack(fill="both", expand=True)
        table_card = tk.Frame(table_border, bg=C_BG_CARD, padx=14, pady=10)
        table_card.pack(fill="both", expand=True)

        # Toolbar da Tabela
        tbl_top = tk.Frame(table_card, bg=C_BG_CARD)
        tbl_top.pack(fill="x", pady=(0, 8))

        tk.Label(tbl_top, text="REGISTRO DE LICENÇAS NO CLOUDFLARE KV", font=("Segoe UI", 9, "bold"), fg=C_TEXT_TITLE, bg=C_BG_CARD).pack(side="left")

        # Filtro de Busca
        filtro_box = tk.Frame(tbl_top, bg=C_BG_CARD)
        filtro_box.pack(side="left", padx=(20, 0))

        tk.Label(filtro_box, text="🔍", font=("Segoe UI", 9), fg=C_TEXT_MUTED, bg=C_BG_CARD).pack(side="left", padx=(0, 4))
        self.entry_lic_filtro = tk.Entry(filtro_box, font=("Segoe UI", 9), bg=C_BG_INPUT, fg="#FFFFFF", insertbackground=C_CYAN, bd=1, relief="solid", width=22)
        self.entry_lic_filtro.pack(side="left")
        self.entry_lic_filtro.bind("<KeyRelease>", lambda e: self._filtrar_licencas_tabela())

        btn_box = tk.Frame(tbl_top, bg=C_BG_CARD)
        btn_box.pack(side="right")

        ttk.Button(btn_box, text="🔄 ATUALIZAR LISTA", style="Secondary.TButton", command=self._carregar_licencas_tabela).pack(side="left", padx=3)
        ttk.Button(btn_box, text="📋 COPIAR CHAVE", style="Secondary.TButton", command=self._acao_copiar_chave_selecionada).pack(side="left", padx=3)
        ttk.Button(btn_box, text="🔓 RESETAR HWID", style="Secondary.TButton", command=self._acao_resetar_hwid_gui).pack(side="left", padx=3)
        ttk.Button(btn_box, text="🚫 REVOGAR CHAVE", style="Danger.TButton", command=self._acao_revogar_chave_gui).pack(side="left", padx=3)
        ttk.Button(btn_box, text="🧹 LIMPAR REVOGADAS", style="Secondary.TButton", command=self._acao_limpar_revogadas_gui).pack(side="left", padx=(3, 0))

        # Container do Treeview
        tree_container = tk.Frame(table_card, bg="#0C1017")
        tree_container.pack(fill="both", expand=True)

        colunas = ("status", "role", "key", "label", "validade", "restante", "hwid", "criada", "ativada")
        self.tree_licencas = ttk.Treeview(
            tree_container,
            columns=colunas,
            show="headings",
            style="Licenses.Treeview",
            selectmode="browse"
        )

        self.tree_licencas.heading("status", text="STATUS")
        self.tree_licencas.heading("role", text="PATENTE")
        self.tree_licencas.heading("key", text="CHAVE DE ATIVAÇÃO")
        self.tree_licencas.heading("label", text="IDENTIFICADOR")
        self.tree_licencas.heading("validade", text="VALIDADE")
        self.tree_licencas.heading("restante", text="RESTANTE")
        self.tree_licencas.heading("hwid", text="HWID VINCULADO")
        self.tree_licencas.heading("criada", text="CRIADA EM")
        self.tree_licencas.heading("ativada", text="ATIVADA EM")

        self.tree_licencas.column("status", width=120, minwidth=100, anchor="center")
        self.tree_licencas.column("role", width=130, minwidth=110, anchor="center")
        self.tree_licencas.column("key", width=180, minwidth=160, anchor="center")
        self.tree_licencas.column("label", width=130, minwidth=100, anchor="w")
        self.tree_licencas.column("validade", width=85, minwidth=70, anchor="center")
        self.tree_licencas.column("restante", width=85, minwidth=70, anchor="center")
        self.tree_licencas.column("hwid", width=210, minwidth=160, anchor="center")
        self.tree_licencas.column("criada", width=110, minwidth=90, anchor="center")
        self.tree_licencas.column("ativada", width=110, minwidth=90, anchor="center")

        sb_y = ttk.Scrollbar(tree_container, orient="vertical", command=self.tree_licencas.yview)
        self.tree_licencas.configure(yscrollcommand=sb_y.set)

        self.tree_licencas.pack(side="left", fill="both", expand=True)
        sb_y.pack(side="right", fill="y")

        # Tags de cores para o Treeview
        self.tree_licencas.tag_configure("ativa", foreground=C_GREEN)
        self.tree_licencas.tag_configure("livre", foreground=C_AMBER)
        self.tree_licencas.tag_configure("revogada", foreground=C_RED)

        # Barra de Rodapé da Tabela
        tbl_bot = tk.Frame(table_card, bg=C_BG_CARD)
        tbl_bot.pack(fill="x", pady=(6, 0))

        self.lbl_lic_tabela_info = tk.Label(tbl_bot, text="Pronto.", font=("Segoe UI", 8), fg=C_TEXT_MUTED, bg=C_BG_CARD)
        self.lbl_lic_tabela_info.pack(side="left")

        # Exibição condicional conforme token de administrador
        if self._obter_admin_secret():
            self.lic_main_box.pack(fill="both", expand=True)
        else:
            self.lic_auth_box.pack(fill="both", expand=True)

    def _tentar_desbloquear_admin(self):
        token = self.entry_admin_token.get().strip()
        if not token:
            self.lbl_auth_status.config(text="Digite o token mestre de administrador.", fg=C_RED)
            return

        self.lbl_auth_status.config(text="Verificando token...", fg=C_CYAN)

        def _verify():
            res = self._fazer_requisicao_admin("/admin/list", method="GET", token_override=token)

            def _apply():
                if res.get("success"):
                    self._admin_secret_session = token
                    self.lic_auth_box.pack_forget()
                    self.lic_main_box.pack(fill="both", expand=True)
                    self._carregar_licencas_tabela()
                else:
                    self.lbl_auth_status.config(text="❌ Token incorreto ou não autorizado.", fg=C_RED)

            self.root.after(0, _apply)

        threading.Thread(target=_verify, daemon=True).start()

    def _carregar_licencas_tabela(self):
        if not self._obter_admin_secret():
            self.lic_main_box.pack_forget()
            self.lic_auth_box.pack(fill="both", expand=True)
            return

        self.lbl_lic_tabela_info.config(text="🔄 Consultando Cloudflare KV...", fg=C_CYAN)

        def _fetch():
            res = self._fazer_requisicao_admin("/admin/list", method="GET")

            def _apply():
                if not res.get("success"):
                    erro = res.get("error", "Erro ao conectar ao servidor de licenças.")
                    self.lbl_lic_tabela_info.config(text=f"❌ {erro}", fg=C_RED)
                    self.lbl_lic_server_status.config(text="● Servidor Inacessível", fg=C_RED, bg="#2B0D0D")
                    return

                self.lbl_lic_server_status.config(text="● Cloudflare KV Conectado", fg=C_GREEN, bg="#0B2419")
                lics = res.get("licenses", [])
                # Ordena as mais recentes primeiro no topo da lista
                lics.sort(key=lambda x: x.get("created_at") or 0, reverse=True)
                self._licencas_cache = lics
                self._renderizar_licencas(self._licencas_cache)

            self.root.after(0, _apply)

        threading.Thread(target=_fetch, daemon=True).start()

    def _renderizar_licencas(self, licencas):
        for item in self.tree_licencas.get_children():
            self.tree_licencas.delete(item)

        total = len(licencas)
        vinculadas = 0
        livres = 0
        revogadas = 0
        agora_ms = time.time() * 1000

        for lic in licencas:
            st = lic.get("status", "active")
            hwid = lic.get("bound_hwid")
            key = lic.get("key", "—")
            label = lic.get("label", "Operador")
            dias = lic.get("days", 30)
            val_str = "Vitalícia" if dias == 0 else f"{dias} dias"

            criada_em = self._formatar_timestamp_ms(lic.get("created_at"))
            ativada_em = self._formatar_timestamp_ms(lic.get("activated_at"))
            exp_ms = lic.get("expires_at")

            if st == "revoked":
                status_str = "🔴 REVOGADA"
                tag = "revogada"
                restante_str = "Bloqueado"
                revogadas += 1
            elif hwid:
                if exp_ms and agora_ms > exp_ms:
                    status_str = "🔴 EXPIRADA"
                    tag = "revogada"
                    restante_str = "0 dias"
                    revogadas += 1
                else:
                    status_str = "🟢 ATIVA"
                    tag = "ativa"
                    restante_dias = max(0, int((exp_ms - agora_ms) / 86400000)) if exp_ms else "∞"
                    restante_str = f"{restante_dias}d" if exp_ms else "∞ Vitalício"
                    vinculadas += 1
            else:
                status_str = "🟡 LIVRE (1º USO)"
                tag = "livre"
                restante_str = f"{dias}d" if dias > 0 else "∞"
                livres += 1

            role_val = str(lic.get("role") or "OPERADOR").upper()
            if role_val == "ADMIN":
                role_disp = "⚡ ADMIN"
            elif role_val == "DONO":
                role_disp = "👑 DONO"
            else:
                role_disp = "🛡️ OPERADOR"

            hwid_disp = hwid if hwid else "Aguardando 1º uso..."

            self.tree_licencas.insert(
                "", "end",
                values=(status_str, role_disp, key, label, val_str, restante_str, hwid_disp, criada_em, ativada_em),
                tags=(tag,)
            )

        self.card_lic_total.lbl_valor.config(text=str(total))
        self.card_lic_vinculadas.lbl_valor.config(text=str(vinculadas))
        self.card_lic_livres.lbl_valor.config(text=str(livres))
        self.card_lic_revogadas.lbl_valor.config(text=str(revogadas))
        self.lbl_lic_tabela_info.config(text=f"Total: {total} chaves sincronizadas com a nuvem.", fg=C_TEXT_MUTED)

    def _filtrar_licencas_tabela(self):
        termo = self.entry_lic_filtro.get().strip().lower()
        if not termo:
            self._renderizar_licencas(self._licencas_cache)
            return

        filtradas = []
        for lic in self._licencas_cache:
            k = str(lic.get("key", "")).lower()
            lbl = str(lic.get("label", "")).lower()
            h = str(lic.get("bound_hwid", "")).lower()
            s = str(lic.get("status", "")).lower()
            if termo in k or termo in lbl or termo in h or termo in s:
                filtradas.append(lic)

        self._renderizar_licencas(filtradas)

    def _acao_gerar_chave_gui(self):
        label = self.entry_lic_operador.get().strip() or "Operador"
        val_sel = self.combo_lic_dias.get()
        role_sel = self.combo_lic_role.get().strip().upper() if hasattr(self, "combo_lic_role") else "OPERADOR"
        d_map = {
            "7 dias": 7,
            "15 dias": 15,
            "30 dias": 30,
            "60 dias": 60,
            "90 dias": 90,
            "Vitalícia": 0
        }
        dias = d_map.get(val_sel, 30)

        self.btn_gerar_chave.config(state="disabled", text="⏳ GERANDO...")
        self.lbl_chave_feedback.config(text="⏳ Enviando solicitação ao Cloudflare KV...", fg=C_AMBER)

        def _worker():
            res = self._fazer_requisicao_admin("/admin/generate", method="POST", body={"days": dias, "label": label, "role": role_sel})

            def _apply():
                self.btn_gerar_chave.config(state="normal", text="➕ GERAR CHAVE ONLINE")
                if res.get("success"):
                    key = res.get("key")
                    self.entry_chave_display.config(state="normal")
                    self.entry_chave_display.delete(0, tk.END)
                    self.entry_chave_display.insert(0, key)
                    self.entry_chave_display.config(state="readonly")
                    try:
                        pyperclip.copy(key)
                        copiado = True
                    except Exception:
                        copiado = False
                    txt_copiado = " (Copiada automaticamente!)" if copiado else ""
                    self.lbl_chave_feedback.config(text=f"✅ Chave {key} gerada com sucesso!{txt_copiado}", fg=C_GREEN)
                    self._carregar_licencas_tabela()
                else:
                    erro = res.get("error", "Erro desconhecido ao gerar chave.")
                    self.lbl_chave_feedback.config(text=f"❌ Falha: {erro}", fg=C_RED)

            self.root.after(0, _apply)

        threading.Thread(target=_worker, daemon=True).start()

    def _acao_copiar_chave_gerada(self):
        k = self.entry_chave_display.get().strip()
        if k and "xxxx" not in k:
            self.root.clipboard_clear()
            self.root.clipboard_append(k)
            self.lbl_chave_feedback.config(text="📋 Chave copiada para a área de transferência!", fg=C_CYAN)

    def _acao_copiar_chave_selecionada(self):
        sel = self.tree_licencas.selection()
        if not sel:
            messagebox.showinfo("Aviso", "Selecione uma licença na tabela para copiar a chave.")
            return
        vals = self.tree_licencas.item(sel[0], "values")
        if vals and len(vals) >= 3:
            key = vals[2]
            self.root.clipboard_clear()
            self.root.clipboard_append(key)
            self.lbl_lic_tabela_info.config(text=f"📋 Chave {key} copiada!", fg=C_CYAN)

    def _acao_resetar_hwid_gui(self):
        sel = self.tree_licencas.selection()
        if not sel:
            messagebox.showinfo("Aviso", "Selecione na tabela a licença cujo HWID deseja resetar/desvincular.")
            return
        vals = self.tree_licencas.item(sel[0], "values")
        if not vals or len(vals) < 4:
            return
        key = vals[2]
        operador = vals[3]
        hwid_atual = vals[6] if len(vals) > 6 else ""

        if not hwid_atual or "Aguardando" in hwid_atual:
            messagebox.showinfo("Aviso", f"A chave {key} ainda não possui nenhum HWID vinculado.")
            return

        confirmar = messagebox.askyesno(
            "Desvincular HWID",
            f"Deseja desvincular o computador atual ({hwid_atual}) da chave:\n\n{key} ({operador})?\n\nApós o reset, a chave poderá ser ativada em outro computador (ou no mesmo computador caso o hardware tenha mudado)."
        )
        if not confirmar:
            return

        self.lbl_lic_tabela_info.config(text=f"⏳ Resetando HWID de {key} no Cloudflare...", fg=C_AMBER)

        def _worker():
            res = self._fazer_requisicao_admin("/admin/reset-hwid", method="POST", body={"key": key})

            def _apply():
                if res.get("success"):
                    msg = res.get("message", "HWID desvinculado com sucesso!")
                    self.lbl_lic_tabela_info.config(text=f"🔓 {msg}", fg=C_GREEN)
                    messagebox.showinfo("Sucesso", f"O HWID vinculado à chave {key} foi removido com sucesso!\n\nAgora o subordinado pode entrar com a chave normalmente.")
                    self._carregar_licencas_tabela()
                else:
                    erro = res.get("error", "Erro ao resetar HWID.")
                    messagebox.showerror("Erro", f"Não foi possível resetar o HWID:\n{erro}\n\nCertifique-se de que o cf_worker.js atualizado foi publicado no Cloudflare.")

            self.root.after(0, _apply)

        threading.Thread(target=_worker, daemon=True).start()

    def _acao_revogar_chave_gui(self):
        sel = self.tree_licencas.selection()
        if not sel:
            messagebox.showinfo("Aviso", "Selecione na tabela a licença que deseja revogar.")
            return
        vals = self.tree_licencas.item(sel[0], "values")
        if not vals or len(vals) < 4:
            return
        status = vals[0]
        role = vals[1]
        key = vals[2]
        operador = vals[3]

        if "REVOGADA" in status:
            messagebox.showinfo("Aviso", f"A chave {key} já está revogada.")
            return

        confirmar = messagebox.askyesno(
            "Confirmar Revogação",
            f"Deseja realmente REVOGAR o acesso da chave:\n\n{key} ({operador} - {role})?\n\nO computador do subordinado perderá o acesso imediatamente."
        )
        if not confirmar:
            return

        self.lbl_lic_tabela_info.config(text=f"⏳ Revogando {key} no Cloudflare...", fg=C_AMBER)

        def _worker():
            res = self._fazer_requisicao_admin("/admin/revoke", method="POST", body={"key": key})

            def _apply():
                if res.get("success"):
                    self.lbl_lic_tabela_info.config(text=f"🚫 Chave {key} foi revogada com sucesso!", fg=C_GREEN)
                    self._carregar_licencas_tabela()
                else:
                    erro = res.get("error", "Erro ao revogar chave.")
                    messagebox.showerror("Erro", f"Não foi possível revogar a chave:\n{erro}")

            self.root.after(0, _apply)

        threading.Thread(target=_worker, daemon=True).start()

    def _acao_limpar_revogadas_gui(self):
        confirmar = messagebox.askyesno(
            "Limpar Chaves Revogadas",
            "Deseja realmente EXCLUIR PERMANENTEMENTE todas as chaves revogadas/bloqueadas do Cloudflare KV?\n\nEssa ação não pode ser desfeita e liberará o banco de licenças."
        )
        if not confirmar:
            return

        self.lbl_lic_tabela_info.config(text="🧹 Limpando chaves revogadas no Cloudflare KV...", fg=C_AMBER)

        def _worker():
            res = self._fazer_requisicao_admin("/admin/clear-revoked", method="POST")

            def _apply():
                if res.get("success"):
                    qtd = res.get("count", 0)
                    self.lbl_lic_tabela_info.config(text=f"🧹 Limpeza concluída: {qtd} chaves revogadas removidas!", fg=C_GREEN)
                    messagebox.showinfo("Sucesso", f"{qtd} chave(s) revogada(s) foram apagadas com sucesso do Cloudflare KV.")
                    self._carregar_licencas_tabela()
                else:
                    erro = res.get("error", "Erro ao limpar chaves revogadas.")
                    messagebox.showerror("Erro", f"Não foi possível limpar as chaves revogadas:\n{erro}\n\nCertifique-se de que o cf_worker.js atualizado foi publicado no Cloudflare.")

            self.root.after(0, _apply)

        threading.Thread(target=_worker, daemon=True).start()

    # ========================================================================
    # HELPERS DE CARDS E CALLBACKS
    # ========================================================================
    def _criar_card_stat(self, parent, titulo, valor_inicial, cor_valor):
        card_border = tk.Frame(parent, bg=C_BORDER, padx=1, pady=1)
        card_inner = tk.Frame(card_border, bg=C_BG_CARD, padx=14, pady=10)
        card_inner.pack(fill="both", expand=True)

        tk.Label(card_inner, text=titulo, font=("Segoe UI", 7, "bold"), fg=C_TEXT_MUTED, bg=C_BG_CARD).pack(anchor="w")
        lbl_val = tk.Label(card_inner, text=valor_inicial, font=("Segoe UI", 16, "bold"), fg=cor_valor, bg=C_BG_CARD)
        lbl_val.pack(anchor="w", pady=(2, 0))
        card_border.lbl_valor = lbl_val
        return card_border

    def _criar_card_mhmdo(self, parent, titulo, preco, valor_inicial, cor_valor):
        card_border = tk.Frame(parent, bg=C_BORDER, padx=1, pady=1)
        card_inner = tk.Frame(card_border, bg=C_BG_CARD_INNER, padx=10, pady=6)
        card_inner.pack(fill="both", expand=True)

        header = tk.Frame(card_inner, bg=C_BG_CARD_INNER)
        header.pack(fill="x")
        tk.Label(header, text=titulo, font=("Segoe UI", 7, "bold"), fg=C_TEXT_MUTED, bg=C_BG_CARD_INNER).pack(side="left")
        tk.Label(header, text=preco, font=("Segoe UI", 6), fg=C_TEXT_MUTED, bg=C_BG_CARD_INNER).pack(side="right")
        lbl_val = tk.Label(card_inner, text=valor_inicial, font=("Segoe UI", 13, "bold"), fg=cor_valor, bg=C_BG_CARD_INNER)
        lbl_val.pack(anchor="w", pady=(1, 0))
        tk.Label(card_inner, text="contas disponíveis", font=("Segoe UI", 6), fg=C_TEXT_MUTED, bg=C_BG_CARD_INNER).pack(anchor="w")
        card_border.lbl_valor = lbl_val
        return card_border

    def _on_email_type_change(self):
        tipo = self.email_type_var.get()
        self.manager.mhmdo_email_type = tipo

    def _atualizar_saldo_mhmdo(self):
        info = consultar_saldo_mhmdo()
        def _update():
            if info:
                self.lbl_saldo_usd.config(text=f"${info['balance_usd']:.3f}")
                self.card_custom.lbl_valor.config(text=str(info['custom']))
                self.card_short.lbl_valor.config(text=str(info['short']))
                self.card_full.lbl_valor.config(text=str(info['full']))
                total_disp = info.get(self.manager.mhmdo_email_type, info.get("short", 0))
                self.lbl_badge_api.lbl.config(text=f"⚡ API: {total_disp} e-mails (${info['balance_usd']:.2f})")
            else:
                self.lbl_saldo_usd.config(text="Erro")
                self.lbl_badge_api.lbl.config(text="⚡ API: Indisponível")
        self.root.after(0, _update)

    def _on_modo_change(self):
        modo = self.modo_var.get()
        self.manager.modo_email = modo
        if modo == "mhmdo":
            self.lbl_modo_info.config(text="Emails gerados automaticamente via mhmdo.email API")
            self.card_fila.lbl_valor.config(text="∞")
            threading.Thread(target=self._atualizar_saldo_mhmdo, daemon=True).start()
        else:
            self.lbl_modo_info.config(text="Emails de contas/outlook.txt com graph_refresh_token")
            self.atualizar_contadores()

    def acao_limpar_log(self):
        self.txt_log.delete("1.0", tk.END)

    def adicionar_log(self, texto):
        def _append():
            ts = time.strftime("[%H:%M:%S] ")
            self.txt_log.insert(tk.END, ts + texto + "\n")
            self.txt_log.see(tk.END)
        self.root.after(0, _append)

    def _acao_forcar_refresh_adb(self):
        self.adicionar_log("🔄 Verificando dispositivos USB conectados...")
        threading.Thread(target=self._atualizar_status_adb, daemon=True).start()

    def _atualizar_status_adb(self):
        """Checa status da conexão ADB em background para qualquer dispositivo conectado."""
        try:
            dispositivos = listar_dispositivos_adb()
            self.dispositivos_detectados_cache = dispositivos

            def _fmt_status(dev):
                nome = dev.get("nome", dev.get("serial", "Aparelho"))
                st = dev.get("status", "")
                if st == "device":
                    return f"● {nome}: Conectado 🟢", C_GREEN
                elif st == "unauthorized":
                    return f"● {nome}: USB Pendente ⚠️", C_AMBER
                elif st == "offline":
                    return f"● {nome}: Offline ⚠️", C_AMBER
                else:
                    return f"● {nome}: {st} ⚠️", C_AMBER

            seriais_atuais = [d["serial"] for d in dispositivos]

            def _update_ui():
                if hasattr(self, 'lbl_status_redmi'):
                    if not dispositivos:
                        self.lbl_status_redmi.config(text="● Celular: Desconectado 🔴", fg=C_RED)
                        if hasattr(self, 'lbl_status_a9'):
                            self.lbl_status_a9.config(text="")
                    else:
                        txt_p, cor_p = _fmt_status(dispositivos[0])
                        self.lbl_status_redmi.config(text=txt_p, fg=cor_p)
                        if hasattr(self, 'lbl_status_a9'):
                            if len(dispositivos) > 1:
                                txt_s, cor_s = _fmt_status(dispositivos[1])
                                self.lbl_status_a9.config(text=txt_s, fg=cor_s)
                            else:
                                self.lbl_status_a9.config(text="")

                total_online = sum(1 for d in dispositivos if d.get("status") == "device")
                if total_online > 1:
                    self.lbl_badge_online.lbl.config(text=f"● {total_online}x CELULARES ONLINE", fg=C_GREEN)
                elif total_online == 1:
                    self.lbl_badge_online.lbl.config(text="● 1x CELULAR ONLINE", fg=C_CYAN)
                else:
                    self.lbl_badge_online.lbl.config(text="● SEM CELULAR (PC)", fg="#81D8F7")

                if seriais_atuais != self._ultimo_seriais_detectados:
                    self._ultimo_seriais_detectados = list(seriais_atuais)
                    for widget in self.dev_checkboxes_frame.winfo_children():
                        widget.destroy()

                    self.device_checkboxes.clear()
                    if not dispositivos:
                        tk.Label(
                            self.dev_checkboxes_frame,
                            text="Nenhum aparelho conectado via USB (ative a depuração USB)",
                            font=("Segoe UI", 8, "italic"),
                            fg=C_TEXT_MUTED, bg=C_BG_CARD_INNER
                        ).pack(side="left", padx=4)
                    else:
                        for dev in dispositivos:
                            s = dev["serial"]
                            if s not in self.device_vars:
                                self.device_vars[s] = tk.BooleanVar(value=True)
                            var = self.device_vars[s]
                            st_icon = "🟢" if dev["status"] == "device" else "⚠️"
                            label_chk = f"📱 {dev['nome']} {st_icon}"
                            chk = tk.Checkbutton(
                                self.dev_checkboxes_frame,
                                text=label_chk,
                                variable=var,
                                font=("Segoe UI", 9, "bold"),
                                fg="#FFFFFF",
                                bg=C_BG_CARD_INNER,
                                selectcolor="#1E2333",
                                activebackground=C_BG_CARD_INNER,
                                activeforeground=C_CYAN,
                                cursor="hand2",
                                command=self.atualizar_contadores
                            )
                            chk.pack(side="left", padx=5)
                            self.device_checkboxes[s] = chk

            self.root.after(0, _update_ui)
        except Exception:
            pass

    def atualizar_contadores(self):
        def _update():
            try:
                modo = self.modo_var.get()
                qtd_criar = contar_linhas(OUTLOOK_FILE)
                qtd_pendentes_rsg, qtd_prontas_rsg, qtd_erros_rsg, qtd_total_rsg = contar_contas_rockstar()
                qtd_disp_codigos, qtd_resg_codigos = contar_codigos_disponiveis()
                qtd_prontas = contar_linhas(PRONTAS_FILE)
                qtd_erro = contar_linhas(ERRO_FILE)

                if modo == "graph":
                    self.card_fila.lbl_valor.config(text=str(qtd_criar))
                else:
                    self.card_fila.lbl_valor.config(text="∞")
                self.card_feitas.lbl_valor.config(text=str(qtd_total_rsg))
                self.card_erros.lbl_valor.config(text=str(qtd_erro))

                total_prontas = max(qtd_prontas, qtd_prontas_rsg)

                if hasattr(self, 'card_redeem_feitas'):
                    self.card_redeem_feitas.lbl_valor.config(text=f"{qtd_pendentes_rsg} disponíveis")
                    self.card_redeem_codigos.lbl_valor.config(text=f"{qtd_disp_codigos} disponíveis ({qtd_resg_codigos} ok)")
                    self.card_redeem_prontas.lbl_valor.config(text=str(total_prontas))

                self.lbl_badge_rsg.lbl.config(text=f"🎮 Rockstar: {qtd_pendentes_rsg}")
                self.lbl_badge_codigos.lbl.config(text=f"🔑 Códigos: {qtd_disp_codigos}")
                self.lbl_badge_prontas.lbl.config(text=f"🏆 Prontas: {total_prontas}")

                if self.manager.infinito:
                    self.lbl_progresso_meta.config(text=f"Progresso: {self.manager.contas_criadas_sessao} criadas (♾️)")
                else:
                    self.lbl_progresso_meta.config(text=f"Progresso: {self.manager.contas_criadas_sessao} / {self.manager.meta_contas}")

                if not self.manager.running:
                    selecionados = [s for s, var in self.device_vars.items() if var.get()]
                    if len(selecionados) > 1:
                        txt_mob = f"▶ INICIAR {len(selecionados)}x APARELHOS (SIMULTÂNEO)"
                    elif len(selecionados) == 1:
                        info_s = _device_info_cache.get(selecionados[0], {})
                        nome_d = info_s.get("nome", "CELULAR")
                        txt_mob = f"▶ INICIAR {nome_d.upper()} (4G)"
                    else:
                        txt_mob = "▶ INICIAR MOBILE (SELECIONE)"
                    self.btn_iniciar_mobile.config(text=txt_mob, style="Primary.TButton")
                    self.btn_iniciar_pc_4g.config(text="🌐 INICIAR CRIAÇÃO (PROXY DATAIMPULSE)", style="Pc4g.TButton")
                    self.btn_iniciar_pc_local.config(text="🏠 INICIAR PC (REDE LOCAL)", style="PcLocal.TButton")
                elif self.manager.running:
                    if self.manager.tipo_execucao == "mobile":
                        self.btn_iniciar_mobile.config(text="⏹ PARAR", style="Danger.TButton")
                    elif self.manager.tipo_execucao == "pc_4g":
                        self.btn_iniciar_pc_4g.config(text="⏹ PARAR", style="Danger.TButton")
                    else:
                        self.btn_iniciar_pc_local.config(text="⏹ PARAR", style="Danger.TButton")

                # Botões de pausa individuais sincronizados dinamicamente com os workers ativos
                if hasattr(self, 'container_pausas_individuais'):
                    if self.manager.running and self.manager.tipo_execucao == "mobile" and self.manager.workers:
                        seriais_workers = [w.serial for w in self.manager.workers]
                        for s in list(self.botoes_pausa_individuais.keys()):
                            if s not in seriais_workers:
                                self.botoes_pausa_individuais[s].destroy()
                                del self.botoes_pausa_individuais[s]

                        for w in self.manager.workers:
                            if w.serial not in self.botoes_pausa_individuais:
                                btn_p = ttk.Button(
                                    self.container_pausas_individuais,
                                    style="Secondary.TButton",
                                    command=lambda s=w.serial: self.acao_pausar_individual(s)
                                )
                                btn_p.pack(side="left", padx=3)
                                self.botoes_pausa_individuais[w.serial] = btn_p

                            txt_p = f"▶ Retomar {w.name}" if (w.paused or self.manager.paused) else f"⏸ Pausar {w.name}"
                            self.botoes_pausa_individuais[w.serial].config(text=txt_p)
                    else:
                        for btn in self.botoes_pausa_individuais.values():
                            btn.destroy()
                        self.botoes_pausa_individuais.clear()

                if hasattr(self, 'btn_pausar_mob'):
                    self.btn_pausar_mob.config(text="▶ RETOMAR TODOS" if self.manager.paused else "⏸ PAUSAR TODOS")
            except Exception:
                pass

        self.root.after(0, _update)

    def _iniciar_com_tipo(self, tipo):
        if self.manager.running:
            self.manager.running = False
            self.manager.paused = False
            for w in list(getattr(self.manager, 'workers', [])):
                w.running = False
                w.paused = False
            self.atualizar_contadores()
            self.btn_iniciar_pc_4g.config(text="🌐 INICIAR CRIAÇÃO (PROXY DATAIMPULSE)", style="Pc4g.TButton")
            self.btn_iniciar_pc_local.config(text="🏠 INICIAR PC (REDE LOCAL)", style="PcLocal.TButton")
            threading.Thread(target=self.manager.parar_instantaneo, daemon=True).start()
        else:
            self.manager.tipo_execucao = tipo
            if self.infinito_var.get():
                self.manager.infinito = True
                self.manager.meta_contas = 0
            else:
                self.manager.infinito = False
                try:
                    val = int(self.qtd_var.get().strip())
                    self.manager.meta_contas = max(1, val)
                except ValueError:
                    self.manager.meta_contas = 10
            self.manager.contas_criadas_sessao = 0
            self.manager.running = True
            self.manager.paused = False
            if tipo == "mobile":
                seriais_sel = [s for s, var in self.device_vars.items() if var.get()]
                if not seriais_sel:
                    self.adicionar_log("⚠️ Selecione ao menos um dispositivo na lista acima para iniciar!")
                    self.manager.running = False
                    return
                self.btn_iniciar_mobile.config(text="⏹ PARAR", style="Danger.TButton")
                threading.Thread(target=lambda: self.manager.iniciar_multi_mobile(seriais_selecionados=seriais_sel), daemon=True).start()
            elif tipo == "pc_4g":
                self.btn_iniciar_pc_4g.config(text="⏹ PARAR", style="Danger.TButton")
                threading.Thread(target=self.manager.loop_automacao, daemon=True).start()
            else:
                self.btn_iniciar_pc_local.config(text="⏹ PARAR", style="Danger.TButton")
                threading.Thread(target=self.manager.loop_automacao, daemon=True).start()

    def acao_iniciar_mobile(self):
        self._iniciar_com_tipo("mobile")

    def acao_iniciar_pc_4g(self):
        self._iniciar_com_tipo("pc_4g")

    def acao_iniciar_pc_local(self):
        self._iniciar_com_tipo("pc_local")

    def acao_pausar(self):
        if not self.manager.running:
            return
        self.manager.paused = not self.manager.paused
        txt_mob = "▶ RETOMAR TODOS" if self.manager.paused else "⏸ PAUSAR TODOS"
        txt_pc = "▶ RETOMAR" if self.manager.paused else "⏸ PAUSAR"
        self.btn_pausar_mob.config(text=txt_mob)
        self.btn_pausar_pc.config(text=txt_pc)
        if self.manager.paused:
            self.adicionar_log("⏸ Automação geral pausada (todos os aparelhos).")
        else:
            self.adicionar_log("▶ Automação geral retomada.")
        self.atualizar_contadores()

    def acao_pausar_individual(self, tipo):
        if not self.manager.running:
            self.adicionar_log("⚠️ Inicie a automação antes de pausar aparelhos.")
            return
        self.manager.pausar_worker_individual(tipo)
        self.atualizar_contadores()

    # ========================================================================
    # WATCHDOG DE LICENÇA EM TEMPO REAL (REVOGAÇÃO INSTANTÂNEA)
    # ========================================================================
    def _iniciar_watchdog_licenca(self):
        """Revalida a licença contra o Cloudflare KV a cada 60s.
        Se revogada/expirada, força o encerramento do app."""
        # Admin master não precisa de watchdog
        if self.license_info.get("msg") == "Admin Master":
            return
        if os.path.exists(os.path.join(BASE_DIR, "admin_master.key")):
            return

        def _loop_watchdog():
            while True:
                time.sleep(15)
                try:
                    hwid = self.license_info.get("hwid", "")
                    key = self.license_info.get("key", "")
                    if not hwid or not key:
                        continue

                    from license_gate import validar_online, LICENSE_FILE
                    ok, msg = validar_online(key, hwid)

                    if ok is False:
                        # Kill instantâneo — sem tocar no tkinter, sem travar janela
                        try:
                            if os.path.exists(LICENSE_FILE):
                                os.remove(LICENSE_FILE)
                        except Exception:
                            pass
                        os._exit(0)
                except Exception:
                    pass

        threading.Thread(target=_loop_watchdog, daemon=True).start()


if __name__ == "__main__":
    from license_gate import verificar_licenca_ou_solicitar, carregar_licenca_local
    valido, hwid, lic_msg, role = verificar_licenca_ou_solicitar()

    # Recupera a chave ativa para o watchdog de revogação
    active_key = ""
    if lic_msg != "Admin Master":
        active_key, role_local = carregar_licenca_local(hwid)
        role = role or role_local or "OPERADOR"

    root = tk.Tk()
    app = MobileAutomationGUI(root, license_info={"hwid": hwid, "msg": lic_msg, "key": active_key, "role": role})

    def _bg_update_check():
        time.sleep(3)
        while True:
            try:
                import updater
                has, data = updater.check_for_updates()
                if has:
                    ver = data.get("version", "")
                    if updater.apply_update(data):
                        def _notificar():
                            try:
                                resp = messagebox.askyesno(
                                    "Atualização Disponível",
                                    f"Uma nova versão (v{ver}) foi baixada com sucesso!\n\nDeseja reiniciar o aplicativo agora para aplicar as novidades?",
                                    parent=root
                                )
                                if resp:
                                    updater.restart_process()
                            except Exception:
                                pass
                        root.after(100, _notificar)
                        break
            except Exception:
                pass
            time.sleep(15)

    threading.Thread(target=_bg_update_check, daemon=True).start()

    root.mainloop()
