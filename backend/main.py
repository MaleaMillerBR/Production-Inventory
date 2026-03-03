import os
from pathlib import Path
from typing import List, Optional

import xmlrpc.client
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles


ODOO_URL = os.getenv("ODOO_URL", "https://erp.bluerobotics.com/")
ODOO_DB = os.getenv("ODOO_DB", "master")
ODOO_USERNAME = os.getenv("ODOO_USERNAME", "malea@bluerobotics.com")
ODOO_API_KEY = os.getenv("ODOO_API_KEY", "25032fc88871796f24ef7413fd37536f8cc2bb40")

# Custom field on mrp.bom that stores the Work Area (Many2one to work area model)
WORK_AREA_FIELD = "work_area"
# Model name for the work area records (the table that has "Sensors", "Thrusters", etc.)
# Change if your Odoo uses a different model (e.g. mrp.work.area, x_work.area).
WORK_AREA_MODEL = os.getenv("ODOO_WORK_AREA_MODEL", "mrp.work.area")

WORK_AREAS = [
    "Sensors",
    "Sensors-Custom",
    "Sensors-Misc",
    "Thrusters",
    "Thrusters-Custom",
    "ROV",
    "FXTI/SPOOL/TETHER",
    "BlueBoat",
    "FAA",
    "WetLink",
    "Packing",
    "BB120 Packing",
]


class OdooClient:
    def __init__(self) -> None:
        self.url = ODOO_URL.rstrip("/")
        self.db = ODOO_DB
        self.username = ODOO_USERNAME
        self.api_key = ODOO_API_KEY
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
            opts["limit"] = limit  # 0 = no limit in Odoo
        return self.models.execute_kw(
            self.db,
            self.uid,
            self.api_key,
            model,
            "search_read",
            [domain],
            opts,
        )


odoo_client = OdooClient()

app = FastAPI(title="Production Inventory Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/work-areas")
def get_work_areas() -> List[str]:
    return WORK_AREAS


@app.get("/api/work-areas-from-odoo")
def get_work_areas_from_odoo():
    """
    Return work area names as stored in Odoo (mrp.work.area).
    Use this to verify exact spelling for Packing and other areas.
    """
    try:
        records = odoo_client.search_read(
            WORK_AREA_MODEL,
            [],
            fields=["id", "name"],
            limit=500,
        )
        return {"work_areas": [{"id": r["id"], "name": r["name"]} for r in records]}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/test-connection")
def test_odoo_connection():
    """
    Test endpoint to verify Odoo connection and credentials.
    """
    try:
        # Test authentication
        uid = odoo_client.uid
        return {
            "status": "success",
            "message": "Successfully connected to Odoo",
            "uid": uid,
            "url": ODOO_URL,
            "db": ODOO_DB,
            "username": ODOO_USERNAME,
        }
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Odoo connection error: {error_details}")  # Log to console
        raise HTTPException(
            status_code=502,
            detail=f"Failed to connect to Odoo: {str(e)}. Check your credentials (URL, DB, username, API key).",
        )
@app.get("/api/debug-boms")
def debug_boms():
    """Temporary: list BoMs and their work_area to see what Odoo returns."""
    try:
        # Get ALL BoMs (no work area filter), with work_area and product info
        boms = odoo_client.search_read(
            "mrp.bom",
            [],  # empty domain = all BoMs
            fields=["id", "product_id", "product_tmpl_id", "work_area"],
            limit=50,
        )
        return {"count": len(boms), "boms": boms}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/dashboard")
def get_dashboard(
    work_area: Optional[List[str]] = Query(
        None, description="Filter by one or more work area names"
    )
):
    """
    Return inventory dashboard rows filtered by Work Area.

    Each row contains:
    - internal_reference
    - name
    - work_area
    - qty_on_hand_unreserved
    - min_qty
    - to_order
    - status (red | yellow | blue)
    """
    if work_area:
        invalid = [w for w in work_area if w not in WORK_AREAS]
        if invalid:
            raise HTTPException(status_code=400, detail=f"Invalid work area(s): {invalid}")
        selected_work_areas = work_area
    else:
        selected_work_areas = WORK_AREAS

    # 1a) Resolve work area names to IDs (Many2one: BoM.work_area -> work area model)
    try:
        work_area_records = odoo_client.search_read(
            WORK_AREA_MODEL,
            [("name", "in", selected_work_areas)],
            fields=["id", "name"],
            limit=500,
        )
    except Exception as e:  # noqa: BLE001
        import traceback
        error_details = traceback.format_exc()
        print(f"Odoo work area query error: {error_details}")
        raise HTTPException(
            status_code=502,
            detail=f"Odoo work area lookup failed: {e}. Is WORK_AREA_MODEL '{WORK_AREA_MODEL}' correct?",
        )

    work_area_ids = [r["id"] for r in work_area_records]
    if not work_area_ids:
        print(f"No work area records found for: {selected_work_areas}. Check names in {WORK_AREA_MODEL} (exact match).")
        return []

    # 1b) Pull BoMs for the selected work area IDs (product_id and product_tmpl_id)
    bom_domain = [(WORK_AREA_FIELD, "in", work_area_ids)]
    try:
        boms = odoo_client.search_read(
            "mrp.bom",
            bom_domain,
            fields=["id", "product_id", "product_tmpl_id", WORK_AREA_FIELD],
            limit=10000,  # get all BoMs (Odoo default is 80); Vehicles needs ROV+FXTI+BlueBoat
        )
    except Exception as e:  # noqa: BLE001
        import traceback
        error_details = traceback.format_exc()
        print(f"Odoo BoM query error: {error_details}")  # Log to console
        error_msg = str(e)
        if "field" in error_msg.lower() or "does not exist" in error_msg.lower():
            error_msg += f" Note: The field '{WORK_AREA_FIELD}' might not exist in your Odoo. Check your BoM model for the correct Work Area field name."
        raise HTTPException(status_code=502, detail=f"Odoo BoM query failed: {error_msg}")

    if not boms:
        return []

    # Resolve BoM -> product(s): use product_id when set, else product_tmpl_id -> variant ids
    bom_product_pairs: List[tuple] = []  # (bom, product_id)
    product_ids_from_bom: set = set()
    template_ids_from_bom: set = set()

    for bom in boms:
        product_field = bom.get("product_id")
        tmpl_field = bom.get("product_tmpl_id")
        if product_field and isinstance(product_field, (list, tuple)) and len(product_field) >= 1:
            pid = product_field[0]
            bom_product_pairs.append((bom, pid))
            product_ids_from_bom.add(pid)
        elif tmpl_field and isinstance(tmpl_field, (list, tuple)) and len(tmpl_field) >= 1:
            template_ids_from_bom.add(tmpl_field[0])

    if template_ids_from_bom:
        try:
            variants = odoo_client.search_read(
                "product.product",
                [("product_tmpl_id", "in", list(template_ids_from_bom))],
                fields=["id", "product_tmpl_id"],
            )
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"Odoo product (by template) query failed: {e}")
        for bom in boms:
            tmpl_field = bom.get("product_tmpl_id")
            if not tmpl_field or not isinstance(tmpl_field, (list, tuple)) or len(tmpl_field) < 1:
                continue
            if bom.get("product_id") and isinstance(bom["product_id"], (list, tuple)):
                continue  # already handled
            tmpl_id = tmpl_field[0]
            for v in variants:
                vt = v.get("product_tmpl_id")
                if vt and isinstance(vt, (list, tuple)) and vt[0] == tmpl_id:
                    pid = v["id"]
                    bom_product_pairs.append((bom, pid))
                    product_ids_from_bom.add(pid)
                    break  # one variant per BoM when BoM is by template
            else:
                # no variant found for this template, still add template for name lookup
                pass
        # If we only had templates and no variants found, we might have no product_ids
        pass

    product_ids = product_ids_from_bom
    if not product_ids:
        return []

    # 2) Pull product data (variants) including unreserved quantity
    try:
        products = odoo_client.search_read(
            "product.product",
            [("id", "in", list(product_ids))],
            fields=["id", "name", "default_code", "free_qty", "qty_available", "outgoing_qty", "product_tmpl_id"],
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Odoo product query failed: {e}")

    product_by_id = {p["id"]: p for p in products}

    # 2b) Pull product.template names for display (field: name, model: product.template)
    template_ids = set()
    for p in products:
        pt = p.get("product_tmpl_id")
        if pt and isinstance(pt, (list, tuple)) and len(pt) >= 1:
            template_ids.add(pt[0])
    template_by_id: dict = {}
    if template_ids:
        try:
            templates = odoo_client.search_read(
                "product.template",
                [("id", "in", list(template_ids))],
                fields=["id", "name"],
            )
            template_by_id = {t["id"]: t for t in templates}
        except Exception as e:  # noqa: BLE001
            pass  # fall back to product.product name

    def _product_name(prod: dict) -> str:
        if not prod:
            return ""
        tid = None
        pt = prod.get("product_tmpl_id")
        if pt and isinstance(pt, (list, tuple)) and len(pt) >= 1:
            tid = pt[0]
        if tid and tid in template_by_id:
            return (template_by_id[tid].get("name") or "").strip() or prod.get("name") or ""
        return prod.get("name") or ""

    # 3) Pull minimum quantities from reordering rules
    try:
        orderpoints = odoo_client.search_read(
            "stock.warehouse.orderpoint",
            [("product_id", "in", list(product_ids))],
            fields=["product_id", "product_min_qty"],
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=502, detail=f"Odoo orderpoint query failed: {e}"
        )

    min_qty_by_product: dict[int, float] = {}
    for op in orderpoints:
        product_field = op.get("product_id")
        if not product_field or not isinstance(product_field, list):
            continue
        pid = product_field[0]
        min_qty_by_product[pid] = float(op.get("product_min_qty") or 0.0)

    # 4) Build dashboard rows (one row per (bom, product_id) pair)
    dashboard_rows: List[dict] = []

    for bom, pid in bom_product_pairs:
        product = product_by_id.get(pid)
        if not product:
            continue

        # On hand minus outgoing (can go negative when backordered)
        qty_available = float(product.get("qty_available") if product.get("qty_available") is not None else product.get("free_qty") or 0.0)
        outgoing_qty = float(product.get("outgoing_qty") or 0.0)
        qty_on_hand = qty_available - outgoing_qty
        min_qty = min_qty_by_product.get(pid, 0.0)
        to_order = max(0.0, min_qty - qty_on_hand)

        # Color rules:
        # - red: qty_on_hand < 0
        # - yellow: 0 <= qty_on_hand <= min_qty
        # - blue: qty_on_hand > min_qty
        if qty_on_hand < 0:
            status = "red"
        elif qty_on_hand <= min_qty:
            status = "yellow"
        else:
            status = "blue"

        wa = bom.get(WORK_AREA_FIELD)
        work_area_name = wa[1] if isinstance(wa, (list, tuple)) and len(wa) >= 2 else (wa or "")

        # Use product name from product.template when available
        product_name = _product_name(product)

        dashboard_rows.append(
            {
                "product_id": pid,
                "internal_reference": product.get("default_code"),
                "name": product_name,
                "work_area": work_area_name,
                "qty_on_hand_unreserved": qty_on_hand,
                "min_qty": min_qty,
                "to_order": to_order,
                "status": status,
            }
        )

    return dashboard_rows


# Serve frontend so one URL works when sharing (open http://<this-machine-ip>:8001)
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)

