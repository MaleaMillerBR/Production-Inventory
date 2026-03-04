import os
from typing import List, Optional

import xmlrpc.client


def get_odoo_config():
    return {
        "url": (os.getenv("ODOO_URL") or "https://erp.bluerobotics.com/").rstrip("/"),
        "db": os.getenv("ODOO_DB", "master"),
        "username": os.getenv("ODOO_USERNAME", "malea@bluerobotics.com"),
        "api_key": os.getenv("ODOO_API_KEY", "25032fc88871796f24ef7413fd37536f8cc2bb40"),
    }


class OdooClient:
    def __init__(self) -> None:
        cfg = get_odoo_config()
        self.url = cfg["url"]
        self.db = cfg["db"]
        self.username = cfg["username"]
        self.api_key = cfg["api_key"]
        self._uid: Optional[int] = None

    @property
    def uid(self) -> int:
        if self._uid is None:
            common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
            uid = common.authenticate(self.db, self.username, self.api_key, {})
            if not uid:
                raise RuntimeError("Failed to authenticate to Odoo. Check credentials.")
            self._uid = uid
        return self._uid

    @property
    def models(self):
        return xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")

    def search_read(
        self,
        model: str,
        domain: List,
        fields: List[str],
        limit: Optional[int] = None,
    ) -> List[dict]:
        opts: dict = {"fields": fields}
        if limit is not None:
            opts["limit"] = limit
        return self.models.execute_kw(
            self.db,
            self.uid,
            self.api_key,
            model,
            "search_read",
            [domain],
            opts,
        )
