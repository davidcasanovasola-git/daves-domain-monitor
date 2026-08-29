<div align="center">

# 🎯 Dave's Domain Monitor

**Automated Domain Availability Sniper & 1-Click Cloudflare Registrar Bot**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-green.svg)](https://python.org)
[![Cloudflare Registrar API](https://img.shields.io/badge/Cloudflare_API-Registrar_v4_(Beta)-F38020.svg?logo=cloudflare)](https://developers.cloudflare.com/api/resources/registrar/)
[![Telegram Bot](https://img.shields.io/badge/Telegram-Bot_API-2CA5E0.svg?logo=telegram)](https://core.telegram.org/bots)

*Monitor personal brand domains, catch expired drops, get instant Telegram alerts, and purchase domains directly at wholesale cost with 1-click via Cloudflare Registrar.*

[English](#english) • [Español](#español)

</div>

---

## English

### 🌟 What is Dave's Domain Monitor?
**Dave's Domain Monitor** is an open-source, high-performance domain availability monitor and automated purchasing assistant. It seamlessly integrates with the **Cloudflare Registrar API (Beta)**, **Cloudflare DNS-over-HTTPS (1.1.1.1)**, and standard **RDAP protocols** (RFC 7482/9082).

Track domains for your brand, name, or keywords, detect when they drop or enter redemption periods, and register them instantly from **Telegram** or your **Terminal (CLI)** with real-time wholesale pricing verification.

---

### ✨ Features
- ⚡ **Multi-Engine Detection:**
  - **Cloudflare DoH (1.1.1.1):** Zero-rate-limit, ultra-fast DNS lookups across all TLDs (`.es`, `.com`, `.dev`, `.ai`, etc.).
  - **Official RDAP (ICANN / Verisign / Google / PIR):** Extracts expiration dates, registrars, and redemption lifecycle states (`redemptionPeriod` / `pendingDelete`).
  - **Cloudflare Registrar API (Beta):** Wholesale price checks and automated registration.
- ⏰ **Milestone Expiration Alerts:** Scheduled alerts at 30 days, 15 days, 7 days, and 1 day before expiration.
- 📱 **Interactive Telegram Bot:**
  - Real-time availability alerts with actionable inline buttons.
  - Live wholesale pricing calculation before purchasing.
  - 1-Click secure registration directly linked to your Cloudflare account.
- ⚙️ **Production Ready:** Built-in Linux `systemd` user service with automatic crash recovery (`Restart=always`).

---

### 🚀 Quick Start

#### 1. Clone & Install
```bash
git clone https://github.com/davidcasanovasola-git/daves-domain-monitor.git
cd daves-domain-monitor
pip install -r requirements.txt
pip install -e .
```

#### 2. Initial Setup Wizard
Run the interactive setup assistant to configure your names, target TLDs, and credentials:
```bash
domain-monitor setup
```

#### 3. Start the Interactive Telegram Bot & Monitor
```bash
domain-monitor telegram-bot
```

---

### 💻 CLI Reference

| Command | Description |
|---|---|
| `domain-monitor setup` | Interactive guided configuration wizard. |
| `domain-monitor check` | Scans all monitored domains in real-time. |
| `domain-monitor check <domains...>` | Checks availability for specific domains. |
| `domain-monitor search <keyword>` | Discovers suggestions using Cloudflare's `domain-search` API. |
| `domain-monitor buy <domain>` | Fetches live wholesale pricing and registers domain via Cloudflare. |
| `domain-monitor status` | Displays database monitoring table. |
| `domain-monitor generate` | Generates candidate domain combinations. |
| `domain-monitor add <domain>` | Adds a domain to the monitor list. |
| `domain-monitor remove <domain>` | Removes a domain from the monitor list. |
| `domain-monitor telegram-bot` | Starts interactive Telegram Bot with background scanner. |

---

## Español

### 🌟 ¿Qué es Dave's Domain Monitor?
**Dave's Domain Monitor** es un monitor de disponibilidad de dominios y asistente de compras automatizado de alto rendimiento. Se integra directamente con la **API de Cloudflare Registrar (Beta)**, **Cloudflare DNS-over-HTTPS (1.1.1.1)** y el protocolo estándar **RDAP** (RFC 7482/9082).

Permite vigilar dominios de marca personal o proyectos, detectar cuándo caducan o entran en periodo de redención, y registrarlos al instante desde **Telegram** o la **Terminal (CLI)** a precio de coste oficial.

---

### ✨ Características Principales
- ⚡ **Multi-Motor de Detección:**
  - **Cloudflare DoH (1.1.1.1):** Consultas DNS instantáneas sin límites de tasa para cualquier extensión (`.es`, `.com`, `.dev`, `.ai`, etc.).
  - **RDAP Oficial:** Extracción de fechas exactas de caducidad, registrador actual y periodos de redención (`redemptionPeriod` / `pendingDelete`).
  - **Cloudflare Registrar API:** Comprobación de precios y registro directo.
- ⏰ **Alertas Escalonadas por Hitos:** Notificaciones automáticas a 30 días, 15 días, 7 días y 1 día antes de expirar con fecha y hora estimadas.
- 📱 **Bot Interactivo de Telegram:**
  - Alertas instantáneas con botones de acción interactivos.
  - Verificación de precio exacto antes de confirmar la compra.
  - Registro en 1-clic conectado a tu cuenta de Cloudflare.
- ⚙️ **Servicio Systemd Integrado:** Configuración lista para funcionar 24/7 en servidores Linux con auto-recuperación (`Restart=always`).

---

### 📱 Flujo de Compra en 1-Click desde Telegram

```
🎉 🚀 ¡DOMINIO DISPONIBLE!
carlosdiaz.com

El dominio está libre para registrar ahora mismo.
Motor: rdap

[ 💳 Ver precio y Comprar con Cloudflare ]  [ 🌐 Abrir Cloudflare ]
```

Al pulsar **Ver precio y Comprar**:
1. El bot consulta la API en vivo de Cloudflare Registrar.
2. Muestra el precio mayorista exacto (`$9.77 USD/año`), renovación y cuota ICANN.
3. Solicita confirmación explícita `[ 💳 Confirmar Registro ($9.77 USD) ]` o `[ ❌ Cancelar ]`.
4. Al confirmar, ejecuta el registro y vincula el dominio a tu panel de Cloudflare.

---

### ⚙️ Ejecución 24/7 como Servicio Linux (Systemd)

```bash
mkdir -p ~/.config/systemd/user/
cp systemd/domain-monitor.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now domain-monitor
systemctl --user status domain-monitor
```

---

### 🧪 Tests Unitarios

```bash
python3 -m unittest discover -s tests -v
```

---

### 📄 Licencia

Distribuido bajo la Licencia **MIT**. Consulta [`LICENSE`](LICENSE) para más detalles.
