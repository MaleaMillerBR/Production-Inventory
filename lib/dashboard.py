from typing import List

from lib.constants import WORK_AREAS, WORK_AREA_FIELD, WORK_AREA_MODEL
from lib.odoo_client import OdooClient


def build_dashboard_rows(odoo_client: OdooClient, selected_work_areas: List[str]) -> List[dict]:
    if not selected_work_areas:
        selected_work_areas = WORK_AREAS
    invalid = [w for w in selected_work_areas if w not in WORK_AREAS]
    if invalid:
        raise ValueError(f"Invalid work area(s): {invalid}")

    work_area_records = odoo_client.search_read(
        WORK_AREA_MODEL,
        [("name", "in", selected_work_areas)],
        fields=["id", "name"],
        limit=500,
    )
    work_area_ids = [r["id"] for r in work_area_records]
    if not work_area_ids:
        return []

    boms = odoo_client.search_read(
        "mrp.bom",
        [(WORK_AREA_FIELD, "in", work_area_ids)],
        fields=["id", "product_id", "product_tmpl_id", WORK_AREA_FIELD],
        limit=10000,
    )
    if not boms:
        return []

    bom_product_pairs: List[tuple] = []
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
        variants = odoo_client.search_read(
            "product.product",
            [("product_tmpl_id", "in", list(template_ids_from_bom))],
            fields=["id", "product_tmpl_id"],
        )
        for bom in boms:
            tmpl_field = bom.get("product_tmpl_id")
            if not tmpl_field or not isinstance(tmpl_field, (list, tuple)) or len(tmpl_field) < 1:
                continue
            if bom.get("product_id") and isinstance(bom["product_id"], (list, tuple)):
                continue
            tmpl_id = tmpl_field[0]
            for v in variants:
                vt = v.get("product_tmpl_id")
                if vt and isinstance(vt, (list, tuple)) and vt[0] == tmpl_id:
                    pid = v["id"]
                    bom_product_pairs.append((bom, pid))
                    product_ids_from_bom.add(pid)
                    break

    product_ids = product_ids_from_bom
    if not product_ids:
        return []

    products = odoo_client.search_read(
        "product.product",
        [("id", "in", list(product_ids))],
        fields=["id", "name", "default_code", "free_qty", "qty_available", "outgoing_qty", "product_tmpl_id"],
    )
    product_by_id = {p["id"]: p for p in products}

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
        except Exception:
            pass

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

    orderpoints = odoo_client.search_read(
        "stock.warehouse.orderpoint",
        [("product_id", "in", list(product_ids))],
        fields=["product_id", "product_min_qty"],
    )
    min_qty_by_product: dict = {}
    for op in orderpoints:
        product_field = op.get("product_id")
        if not product_field or not isinstance(product_field, list):
            continue
        pid = product_field[0]
        min_qty_by_product[pid] = float(op.get("product_min_qty") or 0.0)

    dashboard_rows: List[dict] = []
    for bom, pid in bom_product_pairs:
        product = product_by_id.get(pid)
        if not product:
            continue

        qty_available = float(
            product.get("qty_available")
            if product.get("qty_available") is not None
            else product.get("free_qty") or 0.0
        )
        outgoing_qty = float(product.get("outgoing_qty") or 0.0)
        qty_on_hand = qty_available - outgoing_qty
        min_qty = min_qty_by_product.get(pid, 0.0)
        to_order = max(0.0, min_qty - qty_on_hand)

        if qty_on_hand < 0:
            status = "red"
        elif qty_on_hand <= min_qty:
            status = "yellow"
        else:
            status = "blue"

        wa = bom.get(WORK_AREA_FIELD)
        work_area_name = wa[1] if isinstance(wa, (list, tuple)) and len(wa) >= 2 else (wa or "")
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
