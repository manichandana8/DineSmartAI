````markdown
# DineSmartAI (HackHayward)

DineSmartAI is an AI-powered dining assistant that helps users discover restaurants, make reservations, and manage food-related interactions through a conversational interface.

---

## Setup

### Backend (required for AI chat)

From the project root (the folder containing `main.py`):

```bash
source .venv/bin/activate   # optional, if using a virtual environment
pip install -r requirements.txt   # run once
python main.py
````

When the server starts, it will print a URL like:

```
DineSmartAI → http://127.0.0.1:8000
```

If port 8000 is unavailable, it will automatically use 8001, 8002, etc.

Always open the exact URL printed in the terminal.

---

## Available routes

* Marketing site
  `http://127.0.0.1:PORT/`
  (only works if the frontend has been built)

* AI assistant
  `http://127.0.0.1:PORT/assistant`

* Health check
  `http://127.0.0.1:PORT/health`
  (returns `{"status":"ok"}`)

* Debug endpoint
  `http://127.0.0.1:PORT/debug`

---

## Frontend (build for backend)

To enable the marketing site (`/` route), build the frontend:

```bash
cd web
npm install
npm run build
```

This generates the `web/dist` folder, which the backend serves.

---

## Frontend (development mode)

To run the frontend separately:

```bash
cd web
npm install
npm run dev
```

Open:

```
http://127.0.0.1:5173
```

### Notes

* The frontend dev server runs on port 5173
* The backend runs on port 8000 (or next available port)
* The AI assistant requires the backend to be running

If needed, configure the frontend to point to the correct backend port.

---

## Troubleshooting

If the site does not load:

* Ensure `python main.py` is running
* Verify the correct port from the terminal output
* Do not assume the port is 8000 if it was already in use

---

## Project structure

```
main.py
requirements.txt
web/
  ├── src/
  ├── dist/       
  └── package.json
```

---

## Notes

* The backend handles AI logic and reservation flow
* The frontend provides the UI and user interaction
* The `/assistant` route is the main AI interface

