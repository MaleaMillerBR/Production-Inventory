# Production Inventory Dashboard (Odoo v17)

This project provides a small web-based dashboard that connects to **Odoo v17** and displays inventory data by **Bill of Materials Work Area**.

It shows, for each product:

- Internal Reference (Odoo `default_code`)
- Name
- Work Area (`mrp.bom` custom field, e.g. `x_work_area`)
- Quantity On Hand (Unreserved) (`product.product.free_qty`)
- Minimum Quantity (`stock.warehouse.orderpoint.product_min_qty`)
- A calculated **To Order** field: `min_qty - qty_on_hand_unreserved` (never below 0)
- Color status:
  - **Red**: On Hand \< 0
  - **Yellow**: 0 ≤ On Hand ≤ Min
  - **Blue**: On Hand \> Min

Each Work Area has its own tab:

- Sensors
- Thrusters
- ROV
- FXTI/SPOOL/TETHER
- BlueBoat

## 1. Backend (FastAPI)

Backend code lives in `backend/main.py`.

It exposes:

- `GET /api/work-areas` — static list of work areas.
- `GET /api/dashboard?work_area=Sensors` — inventory rows for the given work area.

### Odoo models & fields used

- `mrp.bom`
  - `product_id`
  - custom field `x_work_area` (string/selection with the five work areas above)
- `product.product`
  - `name`
  - `default_code`
  - `free_qty` (unreserved on-hand quantity)
- `stock.warehouse.orderpoint`
  - `product_id`
  - `product_min_qty` (minimum quantity)

> If your field names differ (for example you use another custom field instead of `x_work_area`, or a different quantity field instead of `free_qty`), adjust the constants and field lists in `backend/main.py`.

### Configure Odoo connection

Set these environment variables before running the backend:

- `ODOO_URL` — e.g. `https://your-odoo-domain.com`
- `ODOO_DB` — database name
- `ODOO_USERNAME` — technical/API user
- `ODOO_API_KEY` — API key for that user

On macOS with zsh, you can export them like:

```bash
export ODOO_URL="https://erp.bluerobotics.com"
export ODOO_DB="master"
export ODOO_USERNAME="malea@bluerobotics.com"
export ODOO_API_KEY="25032fc88871796f24ef7413fd37536f8cc2bb40"
```

### Install dependencies & run backend

From the project root (`Dashboard Project`):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`.

## 2. Frontend (Static HTML Dashboard)

The frontend is a single static file: `frontend/index.html`.

It:

- Calls `http://localhost:8000/api/dashboard?work_area=...`.
- Renders a table with:
  - Internal Reference
  - Name
  - Work Area
  - On Hand (Unreserved)
  - Min Qty
  - To Order
  - Status (with colored pill)
- Provides tabs for the five Work Areas.
- Applies row background colors based on status:
  - Red / Yellow / Blue according to the rules above.

### Open the dashboard

With the backend running:

1. Open `frontend/index.html` in your browser (double-click the file in Finder or open via your IDE).
2. Use the **tabs** at the top to switch Work Areas.
3. Use the **Refresh data** button to pull the latest numbers from Odoo.

> If you run the backend on a different host or port, update `API_BASE` near the top of `frontend/index.html`.

## 3. Deploy as a shareable website (one link)

You can host the app on **Render** (free tier) so anyone can open a single URL—no local backend needed.

### One-time setup on Render

1. **Push this project to GitHub** (if you haven’t already).  
   Create a repo, then:
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
   git push -u origin main
   ```
   (Use your real repo URL; omit `backend/.env` and `.env` so secrets stay local.)

2. **Sign up at [render.com](https://render.com)** and log in.

3. **Create a new Web Service**  
   - Dashboard → **New** → **Web Service**.  
   - Connect your GitHub account and select the repo that contains this project.  
   - Render will detect `render.yaml` if it’s in the repo root. If it does, use the **Apply** flow and skip to step 5.  
   - If you’re setting the service manually:
     - **Build command:** `pip install -r requirements.txt`
     - **Start command:** `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT`
     - **Root directory:** leave blank (repo root).

4. **Set environment variables** (required for Odoo):
   - In the Render service → **Environment**:
     - `ODOO_URL` — e.g. `https://erp.bluerobotics.com`
     - `ODOO_DB` — e.g. `master`
     - `ODOO_USERNAME` — your Odoo API user email
     - `ODOO_API_KEY` — that user’s API key  
   (Same values as in `backend/.env`; never commit `.env`.)

5. **Deploy**  
   Click **Create Web Service**. After the first deploy, Render will give you a URL like `https://production-inventory-dashboard-xxxx.onrender.com`. That’s your **shareable link**—open it in a browser and the dashboard and API both work from that URL.

### After deployment

- **Share the link** with your team; no need to run anything locally.  
- **Comments/notes** in the dashboard are stored in each browser’s localStorage, so they’re per device, not shared across people.  
- On the free tier, the service may spin down after inactivity; the first open after that can take a short time to wake up.

## 4. Adapting to your Odoo

- If your **Work Area** is stored on another model/field (e.g. a different custom field on `mrp.bom`), change `WORK_AREA_FIELD` in `backend/main.py`.
- If you want a different quantity basis:
  - Replace `free_qty` in the `product.product` query with your preferred field (for example `qty_available`).
- If you track min quantities per location, extend the `stock.warehouse.orderpoint` domain or join to `location_id`/`warehouse_id` as needed.
# Production-Inventory
