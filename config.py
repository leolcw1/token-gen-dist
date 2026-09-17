"""
Configuração local para o projeto gn roc.
Valores importados pelo mhmdo_mail.py e app_mobile.py.
"""
import os

# ============================================================================
# API mhmdo.email (3 tipos: 'short', 'custom', 'full')
# ============================================================================
MHMDO_API_KEY = os.environ.get(
    "NEXUSFY_MHMDO_API_KEY",
    "leolcw83b0_ac5d149ce2ea2df30ff2f75b89d2eedb",
).strip()

MHMDO_EMAIL_TYPE = os.environ.get("NEXUSFY_MHMDO_EMAIL_TYPE", "short").strip().lower()
MHMDO_CUSTOM_DOMAIN = MHMDO_EMAIL_TYPE == "custom" or os.environ.get(
    "NEXUSFY_MHMDO_CUSTOM", "0"
).strip().lower() in ("1", "true", "yes", "on")

# Senha padrão para contas Rockstar criadas via mhmdo
ROCKSTAR_DEFAULT_PASSWORD = os.environ.get("NEXUSFY_ROCKSTAR_PASSWORD", "M@ik2025Roc!").strip()

# ============================================================================
# PROXY DATAIMPULSE (NAVEGADOR PC)
# ============================================================================
PROXY_DATAIMPULSE = {
    "server": "http://gw.dataimpulse.com:823",
    "username": "c9324c6bbdf5a1717a1c__cr.br",
    "password": "8c7a29423e9f74a1",
}
