import os
import sys
import json
import time
import base64
import hashlib
import datetime
import urllib.request
import urllib.error
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk

from hwid_engine import obter_hwid
from security_guard import iniciar_watchdog_seguranca

if getattr(sys, 'frozen', False):
    _APP_DIR = os.path.dirname(sys.executable)
else:
    _APP_DIR = os.path.dirname(os.path.abspath(__file__))

LICENSE_FILE = os.path.join(_APP_DIR, "license.lic")

# URL DO SEU SERVIDOR DE LICENCAS (Cloudflare Worker)
API_SERVER_URL = "https://pokas-auth.leolcw2.workers.dev"

def _obter_chave_cifra_local(hwid):
    return hashlib.sha256(f"{hwid}-POKAS-SECURE-VAULT-2026".encode()).digest()

def _criptografar_dados(dados_str, chave):
    dados_bytes = dados_str.encode("utf-8")
    cifrado = bytearray()
    for i, b in enumerate(dados_bytes):
        cifrado.append(b ^ chave[i % len(chave)])
    return base64.b64encode(cifrado).decode("utf-8")

def _descriptografar_dados(cifrado_str, chave):
    try:
        cifrado = base64.b64decode(cifrado_str.encode("utf-8"))
        decifrado = bytearray()
        for i, b in enumerate(cifrado):
            decifrado.append(b ^ chave[i % len(chave)])
        return decifrado.decode("utf-8")
    except Exception:
        return ""

def validar_online(key_str, hwid):
    """
    Comunica com o Cloudflare Worker para auto-vincular o HWID no primeiro uso
    e verificar status / banimento / expiracao.
    """
    if not API_SERVER_URL or not API_SERVER_URL.startswith("http"):
        return None, "Servidor online nao configurado."

    endpoint = f"{API_SERVER_URL.rstrip('/')}/activate"
    payload = json.dumps({"key": key_str.strip().upper(), "hwid": hwid.strip().upper()}).encode("utf-8")

    req = urllib.request.Request(
        endpoint,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 PokasStore/4.2"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=6) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            if res_data.get("success"):
                role = res_data.get("role", "OPERADOR")
                return True, res_data.get("message", "Licenca valida!"), role
            else:
                return False, res_data.get("message", "Chave invalida."), None
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode("utf-8"))
            return False, err_body.get("message", f"Erro HTTP {e.code}"), None
        except Exception:
            return False, f"Acesso negado (HTTP {e.code})", None
    except urllib.error.URLError:
        return None, "Sem conexao com o servidor de ativacao.", None
    except Exception as e:
        return None, f"Falha na comunicacao: {e}", None

def salvar_licenca_local(hwid, key_str, exp_str="", role="OPERADOR"):
    try:
        chave = _obter_chave_cifra_local(hwid)
        conteudo = f"{hwid}|{key_str.strip().upper()}|{exp_str}|{role.strip().upper()}"
        cifrado = _criptografar_dados(conteudo, chave)
        with open(LICENSE_FILE, "w", encoding="utf-8") as f:
            f.write(cifrado)
        return True
    except Exception:
        return False

def carregar_licenca_local(hwid):
    if not os.path.exists(LICENSE_FILE):
        return None, "OPERADOR"
    try:
        chave = _obter_chave_cifra_local(hwid)
        with open(LICENSE_FILE, "r", encoding="utf-8") as f:
            cifrado = f.read().strip()
        decifrado = _descriptografar_dados(cifrado, chave)
        if "|" in decifrado:
            partes = decifrado.split("|")
            hwid_salvo = partes[0]
            key_salva = partes[1]
            role_salvo = partes[3].strip() if len(partes) >= 4 else "OPERADOR"
            if hwid_salvo.strip().upper() == hwid.strip().upper():
                return key_salva.strip(), role_salvo
    except Exception:
        pass
    return None, "OPERADOR"

def _obter_versao_app():
    try:
        vpath = os.path.join(_APP_DIR, "version.json")
        if os.path.exists(vpath):
            with open(vpath, "r", encoding="utf-8") as f:
                return json.load(f).get("version", "1.0.5")
    except Exception:
        pass
    return "1.0.5"

def aplicar_tema_escuro_janela(root):
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
            cor_caption = ctypes.c_uint32(0x00170E0B)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(cor_caption), ctypes.sizeof(cor_caption))
            cor_texto = ctypes.c_uint32(0x00FFFFFF)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(cor_texto), ctypes.sizeof(cor_texto))
        except Exception:
            pass
        return True
    except Exception:
        return False

def abrir_janela_ativacao_autobind(hwid, msg_inicial=""):
    resultado = {"sucesso": False, "msg": ""}

    ver_str = _obter_versao_app()
    root = tk.Tk()
    root.title(f"Pokas Store v{ver_str} — Ativação de Acesso")
    root.geometry("460x520")
    root.resizable(False, False)
    root.configure(bg="#0B0E17")
    aplicar_tema_escuro_janela(root)
    root.after(50, lambda: aplicar_tema_escuro_janela(root))

    # Centralizar na tela
    root.update_idletasks()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x = max(0, (sw - 460) // 2)
    y = max(0, (sh - 520) // 2)
    root.geometry(f"460x520+{x}+{y}")

    ico_path = os.path.join(_APP_DIR, "app_icon.ico")
    if os.path.exists(ico_path):
        try:
            root.iconbitmap(ico_path)
        except Exception:
            pass

    # Card Principal
    card = tk.Frame(root, bg="#111625", highlightthickness=1, highlightbackground="#1E293B")
    card.pack(fill="both", expand=True, padx=20, pady=20)

    # Carregar Logo
    logo_img_tk = None
    icon_tk = None
    logo_path = os.path.join(_APP_DIR, "logo.png")
    if os.path.exists(logo_path):
        try:
            img = Image.open(logo_path).convert("RGBA")
            # Ícone da Janela
            icon_img = img.resize((32, 32), Image.Resampling.LANCZOS)
            icon_tk = ImageTk.PhotoImage(icon_img)
            root.iconphoto(True, icon_tk)

            # Logo no Card
            img_card = img.resize((110, 110), Image.Resampling.LANCZOS)
            logo_img_tk = ImageTk.PhotoImage(img_card)
            lbl_logo = tk.Label(card, image=logo_img_tk, bg="#111625")
            lbl_logo.image = logo_img_tk
            lbl_logo.pack(pady=(18, 6))
        except Exception:
            pass

    if not logo_img_tk:
        tk.Label(
            card, text="🛡️", font=("Segoe UI Emoji", 36),
            fg="#00E5FF", bg="#111625"
        ).pack(pady=(22, 6))

    tk.Label(
        card, text="POKAS IDEIA STORE",
        font=("Segoe UI", 13, "bold"), fg="#F8FAFC", bg="#111625"
    ).pack()

    tk.Label(
        card, text="SISTEMA DE ACESSO EXCLUSIVO",
        font=("Segoe UI", 8, "bold"), fg="#00E5FF", bg="#111625"
    ).pack(pady=(2, 12))

    tk.Label(
        card,
        text="Insira sua chave de licença para desbloquear o acesso.\nNo primeiro uso, o sistema vinculará seu hardware automaticamente.",
        font=("Segoe UI", 9), fg="#94A3B8", bg="#111625", justify="center"
    ).pack(padx=24, pady=(0, 16))

    # Campo da Chave
    field_frame = tk.Frame(card, bg="#111625")
    field_frame.pack(fill="x", padx=30)

    tk.Label(
        field_frame, text="CHAVE DE ACESSO (KEY)",
        font=("Segoe UI", 8, "bold"), fg="#64748B", bg="#111625"
    ).pack(anchor="w", pady=(0, 5))

    entry_border = tk.Frame(field_frame, bg="#334155", padx=1, pady=1)
    entry_border.pack(fill="x")

    entry_key = tk.Entry(
        entry_border, font=("Consolas", 12, "bold"), fg="#00F59B", bg="#0B0E17",
        bd=0, justify="center", insertbackground="#00E5FF"
    )
    entry_key.pack(fill="x", ipady=8)
    entry_key.focus_set()

    lbl_feedback = tk.Label(
        card, text=msg_inicial or "", font=("Segoe UI", 8, "bold"),
        fg="#EF4444" if msg_inicial else "#64748B", bg="#111625", wraplength=380
    )
    lbl_feedback.pack(pady=(12, 14))

    def _ativar():
        chave_digitada = entry_key.get().strip().upper()
        if not chave_digitada:
            lbl_feedback.config(text="⚠️ Digite ou cole sua chave de acesso.", fg="#F59E0B")
            return

        btn_ativar.config(state="disabled", text="VALIDANDO...", bg="#0F766E")
        lbl_feedback.config(text="Conectando e vinculando dispositivo...", fg="#00E5FF")
        root.update_idletasks()

        sucesso_online, msg_online, role_online = validar_online(chave_digitada, hwid)

        if sucesso_online is True:
            salvar_licenca_local(hwid, chave_digitada, role=role_online or "OPERADOR")
            resultado["sucesso"] = True
            resultado["msg"] = msg_online
            resultado["role"] = role_online or "OPERADOR"
            lbl_feedback.config(text=f"✓ {msg_online}", fg="#00F59B")
            btn_ativar.config(text="✓ ATIVADO COM SUCESSO", bg="#059669")
            root.after(800, root.destroy)
            return
        elif sucesso_online is False:
            btn_ativar.config(state="normal", text="ATIVAR & ENTRAR", bg="#00E5FF")
            lbl_feedback.config(text=f"✗ {msg_online}", fg="#EF4444")
            return
        else:
            from gerar_licenca_admin import calcular_assinatura
            try:
                if "-" in chave_digitada:
                    exp_str, sig = chave_digitada.split("-", 1)
                    if sig == calcular_assinatura(hwid, exp_str):
                        salvar_licenca_local(hwid, chave_digitada, exp_str, role="OPERADOR")
                        resultado["sucesso"] = True
                        resultado["msg"] = "Licenca Offline Valida"
                        resultado["role"] = "OPERADOR"
                        lbl_feedback.config(text="✓ Licença ativada offline!", fg="#00F59B")
                        root.after(800, root.destroy)
                        return
            except Exception:
                pass

            btn_ativar.config(state="normal", text="ATIVAR & ENTRAR", bg="#00E5FF")
            lbl_feedback.config(text=f"✗ {msg_online}", fg="#EF4444")

    # Atalho Enter
    entry_key.bind("<Return>", lambda e: _ativar())

    btn_ativar = tk.Button(
        card, text="ATIVAR & ENTRAR", font=("Segoe UI", 10, "bold"),
        bg="#00E5FF", fg="#05060A", activebackground="#00B8D4", activeforeground="#05060A",
        bd=0, pady=10, cursor="hand2", command=_ativar
    )
    btn_ativar.pack(fill="x", padx=30, pady=(0, 20))

    def _on_close():
        root.destroy()
        sys.exit(0)

    root.protocol("WM_DELETE_WINDOW", _on_close)
    root.mainloop()

    return resultado["sucesso"], resultado["msg"], resultado.get("role", "OPERADOR")

def verificar_licenca_ou_solicitar():
    """Checa a licença na inicialização ou solicita ativação com auto-bind."""
    iniciar_watchdog_seguranca()
    hwid = obter_hwid()

    # ── ADMIN BYPASS: se admin_master.key existe, é a máquina do dono ──
    admin_key_path = os.path.join(_APP_DIR, "admin_master.key")
    if os.path.exists(admin_key_path):
        return True, hwid, "Admin Master", "DONO"

    key_salva, role_salvo = carregar_licenca_local(hwid)
    if key_salva:
        # Se tem chave salva, revalida online
        ok_online, msg_online, role_online = validar_online(key_salva, hwid)
        if ok_online is True:
            role_final = role_online or role_salvo or "OPERADOR"
            salvar_licenca_local(hwid, key_salva, role=role_final)
            return True, hwid, msg_online, role_final
        elif ok_online is False:
            # Chave foi revogada ou expirou no servidor: limpa o arquivo local para não ficar em loop
            try:
                if os.path.exists(LICENSE_FILE):
                    os.remove(LICENSE_FILE)
            except Exception:
                pass
            # Abre a tela limpa sem texto de erro prévio
            sucesso, msg, role = abrir_janela_ativacao_autobind(hwid)
            if not sucesso: sys.exit(0)
            return True, hwid, msg, role
        else:
            # Servidor inacessivel temporariamente: confia no cache local se for o mesmo HWID
            return True, hwid, "Licenca em Cache Ativa", role_salvo or "OPERADOR"

    # Nenhuma chave salva: abre tela de ativacao
    sucesso, msg, role = abrir_janela_ativacao_autobind(hwid)
    if not sucesso:
        sys.exit(0)
    return True, hwid, msg, role

if __name__ == "__main__":
    verificar_licenca_ou_solicitar()
