"""
Cloudflare REST API Domain / Registrar Client.
Implements the official Cloudflare Registrar API (Beta):
- Domain Search (GET /accounts/{id}/registrar/domain-search)
- Real-time Domain Check & Pricing (POST /accounts/{id}/registrar/domain-check)
- Programmatic Registration (POST /accounts/{id}/registrar/registrations)
- Registration Status Polling (GET /accounts/{id}/registrar/registrations/{domain}/registration-status)
"""

import concurrent.futures
import datetime
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from .base import BaseChecker, DomainResult, DomainStatus

logger = logging.getLogger(__name__)

CLOUDFLARE_API_BASE = "https://api.cloudflare.com/client/v4"

# TLDs known not to be supported directly by Cloudflare Registrar (e.g. .es is handled by Red.es)
UNSUPPORTED_CF_TLDS = {
    "es": "Red.es no admite registro directo en Cloudflare Registrar (se recomienda DonDominio o Porkbun)",
    "de": "DENIC (.de) no disponible para registro directo en la API de Cloudflare",
    "fr": "AFNIC (.fr) no disponible para registro directo en la API de Cloudflare",
    "it": "NIC.it (.it) no disponible para registro directo en la API de Cloudflare",
    "eu": "EURid (.eu) no disponible para registro directo en la API de Cloudflare",
}

# Reason code translations for clearer user messages
REASON_MESSAGES = {
    "domain_unavailable": "El dominio ya está registrado por otra persona o no está disponible.",
    "extension_not_supported_via_api": "Esta extensión de dominio aún no está disponible para registro mediante la API beta de Cloudflare.",
    "extension_not_supported": "Esta extensión no está soportada por Cloudflare Registrar.",
    "extension_disallows_registration": "El registro de esta extensión no está permitido actualmente por las políticas del registro.",
}


class CloudflareAPIChecker(BaseChecker):
    """
    Client for Cloudflare's official API v4 Registrar endpoints.
    Requires api_token with Registrar Write permissions and account_id.
    """

    def __init__(self, api_token: Optional[str] = None, account_id: Optional[str] = None, timeout: int = 10):
        self.api_token = api_token.strip() if api_token else None
        self.account_id = account_id.strip() if account_id else None
        self.timeout = timeout

    @property
    def headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "DomainMonitor/1.0",
        }
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers

    def is_configured(self) -> bool:
        """Check if Cloudflare credentials are configured."""
        return bool(self.api_token and self.account_id)

    def check_domain(self, domain: str) -> DomainResult:
        """Check domain status via Cloudflare Registrar / Zone API."""
        clean_domain = domain.strip().lower()

        if not self.is_configured():
            return DomainResult(
                domain=clean_domain,
                status=DomainStatus.UNKNOWN,
                is_available=False,
                engine="cloudflare_api",
                error_message="Cloudflare credentials not configured",
            )

        url = f"{CLOUDFLARE_API_BASE}/accounts/{self.account_id}/registrar/domains/{clean_domain}"

        try:
            req = urllib.request.Request(url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                success = data.get("success", False)
                result_payload = data.get("result")

                if success and result_payload:
                    if isinstance(result_payload, dict):
                        expires_at = result_payload.get("expires_at")
                        exp_dt = None
                        if expires_at:
                            try:
                                exp_dt = datetime.datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                            except Exception:
                                pass

                        res = DomainResult(
                            domain=clean_domain,
                            status=DomainStatus.REGISTERED,
                            is_available=False,
                            registrar="Cloudflare Registrar",
                            expiration_date=exp_dt,
                            engine="cloudflare_api",
                            raw_data=data,
                        )
                        res.calculate_expiration_days()
                        return res

                return DomainResult(
                    domain=clean_domain,
                    status=DomainStatus.UNKNOWN,
                    is_available=False,
                    engine="cloudflare_api",
                    raw_data=data,
                )

        except urllib.error.HTTPError as e:
            if e.code == 404:
                return DomainResult(
                    domain=clean_domain,
                    status=DomainStatus.AVAILABLE,
                    is_available=True,
                    engine="cloudflare_api",
                    raw_status=["NOT_FOUND_404"],
                )
            return DomainResult(
                domain=clean_domain,
                status=DomainStatus.ERROR,
                error_message=f"Cloudflare API HTTP {e.code}: {e.reason}",
                engine="cloudflare_api",
            )
        except Exception as e:
            return DomainResult(
                domain=clean_domain,
                status=DomainStatus.ERROR,
                error_message=str(e),
                engine="cloudflare_api",
            )

    def search_domains(self, query: str, limit: int = 5) -> Dict[str, Any]:
        """
        Use official Cloudflare Registrar domain-search endpoint to discover candidate domains.
        GET /accounts/{account_id}/registrar/domain-search?q={query}&limit={limit}
        """
        if not self.is_configured():
            return {
                "success": False,
                "error": "Faltan credenciales de Cloudflare (CLOUDFLARE_API_TOKEN y CLOUDFLARE_ACCOUNT_ID).",
                "domains": [],
            }

        encoded_q = urllib.parse.quote(query.strip())
        url = f"{CLOUDFLARE_API_BASE}/accounts/{self.account_id}/registrar/domain-search?q={encoded_q}&limit={limit}"

        try:
            req = urllib.request.Request(url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                result = data.get("result", {})
                domains = result.get("domains", []) if isinstance(result, dict) else []
                return {
                    "success": True,
                    "domains": domains,
                }
        except Exception as e:
            logger.error(f"Error searching domains in Cloudflare Registrar: {e}")
            return {
                "success": False,
                "error": str(e),
                "domains": [],
            }

    def check_pricing_and_availability(self, domain: str) -> Dict[str, Any]:
        """
        Check real-time price, renewal cost, and purchasing capability in Cloudflare Registrar.
        Uses official POST /accounts/{account_id}/registrar/domain-check endpoint.
        """
        clean = domain.strip().lower()
        parts = clean.split(".")
        tld = parts[-1] if len(parts) > 1 else ""

        # Check if TLD is known to not be supported by Cloudflare Registrar
        if tld in UNSUPPORTED_CF_TLDS:
            return {
                "domain": clean,
                "supported": False,
                "can_buy_on_cloudflare": False,
                "reason": UNSUPPORTED_CF_TLDS[tld],
                "alternative_url": f"https://www.dondominio.com/es/search/?domain={clean}",
                "alternative_name": "DonDominio",
            }

        if not self.is_configured():
            return {
                "domain": clean,
                "supported": True,
                "can_buy_on_cloudflare": False,
                "error": "Faltan credenciales de Cloudflare (CLOUDFLARE_API_TOKEN y CLOUDFLARE_ACCOUNT_ID) en .env o config.yaml",
                "direct_url": "https://dash.cloudflare.com/?to=/:account/domains/register",
            }

        # Query official domain-check endpoint
        url = f"{CLOUDFLARE_API_BASE}/accounts/{self.account_id}/registrar/domain-check"
        payload = json.dumps({"domains": [clean]}).encode("utf-8")

        try:
            req = urllib.request.Request(url, data=payload, headers=self.headers)
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                result_obj = data.get("result", {})
                
                # Cloudflare API format: {"result": {"domains": [...]}} or {"result": [...]}
                if isinstance(result_obj, dict):
                    domains_list = result_obj.get("domains", [])
                elif isinstance(result_obj, list):
                    domains_list = result_obj
                else:
                    domains_list = []

                if domains_list:
                    item = domains_list[0]
                    registrable = item.get("registrable", True)
                    reason_code = item.get("reason", "")
                    reason_desc = REASON_MESSAGES.get(reason_code, reason_code)

                    pricing = item.get("pricing", {})
                    reg_cost = pricing.get("registration_cost") or item.get("price") or "9.77"
                    ren_cost = pricing.get("renewal_cost") or item.get("renewal_price") or reg_cost
                    currency = pricing.get("currency", "USD")
                    tier = item.get("tier", "standard")

                    return {
                        "domain": clean,
                        "supported": True,
                        "can_buy_on_cloudflare": registrable,
                        "available": registrable,
                        "price": str(reg_cost),
                        "renewal_price": str(ren_cost),
                        "currency": currency,
                        "tier": tier,
                        "reason": reason_desc if not registrable else None,
                        "raw": item,
                    }

                return {
                    "domain": clean,
                    "supported": True,
                    "can_buy_on_cloudflare": True,
                    "available": True,
                    "price": "9.77 (coste mayorista)",
                    "currency": "USD",
                    "raw": data,
                }

        except urllib.error.HTTPError as e:
            err_msg = f"HTTP {e.code}: {e.reason}"
            try:
                raw_body = e.read().decode("utf-8")
                parsed = json.loads(raw_body)
                errors = parsed.get("errors", [])
                if errors:
                    err_msg = errors[0].get("message", err_msg)
            except Exception:
                pass

            return {
                "domain": clean,
                "supported": True,
                "can_buy_on_cloudflare": False,
                "error": f"Error de Cloudflare Registrar: {err_msg}",
                "direct_url": "https://dash.cloudflare.com/?to=/:account/domains/register",
            }
        except Exception as e:
            return {
                "domain": clean,
                "supported": True,
                "can_buy_on_cloudflare": False,
                "error": str(e),
                "direct_url": "https://dash.cloudflare.com/?to=/:account/domains/register",
            }

    def purchase_domain(
        self,
        domain: str,
        auto_poll: bool = True,
        max_poll_seconds: int = 20,
    ) -> Dict[str, Any]:
        """
        Execute domain registration via official Cloudflare Registrar API.
        POST /accounts/{account_id}/registrar/registrations
        """
        clean = domain.strip().lower()

        if not self.is_configured():
            return {
                "success": False,
                "domain": clean,
                "error": "No se han configurado CLOUDFLARE_API_TOKEN y CLOUDFLARE_ACCOUNT_ID en .env o config.yaml.",
            }

        url = f"{CLOUDFLARE_API_BASE}/accounts/{self.account_id}/registrar/registrations"
        payload_dict = {
            "domain_name": clean,
        }
        payload = json.dumps(payload_dict).encode("utf-8")

        try:
            req = urllib.request.Request(url, data=payload, headers=self.headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                status_code = resp.status
                result = data.get("result", {})
                state = result.get("state", "")

                if status_code == 201 and state == "succeeded":
                    return {
                        "success": True,
                        "domain": clean,
                        "state": "succeeded",
                        "status_code": status_code,
                        "message": "¡Dominio registrado con éxito en tu cuenta de Cloudflare!",
                        "result": result,
                    }

                # If 202 Accepted (in progress), poll status endpoint
                if status_code in (200, 202) or state == "in_progress":
                    if auto_poll:
                        return self._poll_registration_status(clean, max_wait=max_poll_seconds)
                    return {
                        "success": True,
                        "domain": clean,
                        "state": "in_progress",
                        "status_code": status_code,
                        "message": "El registro está en proceso en Cloudflare.",
                        "result": result,
                    }

                return {
                    "success": True,
                    "domain": clean,
                    "state": state or "succeeded",
                    "status_code": status_code,
                    "result": result,
                }

        except urllib.error.HTTPError as e:
            err_msg = f"HTTP {e.code}: {e.reason}"
            try:
                raw_err = e.read().decode("utf-8")
                parsed = json.loads(raw_err)
                errors = parsed.get("errors", [])
                if errors:
                    err_msg = errors[0].get("message", err_msg)
            except Exception:
                pass

            return {
                "success": False,
                "domain": clean,
                "error": err_msg,
            }
        except Exception as e:
            return {
                "success": False,
                "domain": clean,
                "error": str(e),
            }

    def _poll_registration_status(self, domain: str, max_wait: int = 20) -> Dict[str, Any]:
        """
        Poll registration status until terminal state:
        GET /accounts/{account_id}/registrar/registrations/{domain}/registration-status
        """
        url = f"{CLOUDFLARE_API_BASE}/accounts/{self.account_id}/registrar/registrations/{domain}/registration-status"
        start_time = time.time()

        while (time.time() - start_time) < max_wait:
            try:
                time.sleep(2)
                req = urllib.request.Request(url, headers=self.headers)
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    result = data.get("result", {})
                    state = result.get("state", "in_progress")

                    if state == "succeeded":
                        return {
                            "success": True,
                            "domain": domain,
                            "state": "succeeded",
                            "message": "¡Dominio registrado con éxito y activo en Cloudflare!",
                            "result": result,
                        }
                    elif state == "action_required":
                        return {
                            "success": False,
                            "domain": domain,
                            "state": "action_required",
                            "error": "Se requiere una acción manual en el panel de Cloudflare (ej. verificar contacto o método de pago).",
                            "result": result,
                        }
                    elif state in ("failed", "blocked"):
                        return {
                            "success": False,
                            "domain": domain,
                            "state": state,
                            "error": f"El registro del dominio ha fallado con estado '{state}'.",
                            "result": result,
                        }

            except Exception as e:
                logger.debug(f"Polling registration status error: {e}")

        # If timeout reached while in progress
        return {
            "success": True,
            "domain": domain,
            "state": "in_progress",
            "message": "El registro ha sido aceptado por Cloudflare y se completará en unos instantes.",
        }

    def check_batch(self, domains: List[str], max_workers: int = 5) -> List[DomainResult]:
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_domain = {
                executor.submit(self.check_domain, domain): domain
                for domain in domains
            }
            for future in concurrent.futures.as_completed(future_to_domain):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    dom = future_to_domain[future]
                    results.append(
                        DomainResult(
                            domain=dom,
                            status=DomainStatus.ERROR,
                            error_message=str(e),
                            engine="cloudflare_api",
                        )
                    )
        return results
