# DineSmartAI (HackHayward)

DineSmartAI is an AI-powered dining assistant that helps users discover restaurants, make reservations, and manage food-related interactions through a conversational interface.

---

## Setup

### Backend (required for AI chat)

From the project root (the folder containing `main.py`):

```bash
source .venv/bin/activate   # optional
pip install -r requirements.txt
python main.py

When the server starts, it will print a URL like:

DineSmartAI → http://127.0.0.1:8000

If port 8000 is unavailable, it will automatically use 8001, 8002, etc.

Always open the exact URL printed in the terminal.

Environment Variables

Create a .env file in the project root.

Example:

GOOGLE_PLACES_API_KEY=your_key_here
DATABASE_URL=sqlite:///./smartdine.db

# LLM (Gemini preferred)
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=your_model_here

# Retell AI (for phone-call automation)
RETELL_API_KEY=your_key_here
RETELL_FROM_NUMBER=your_number_here
RETELL_AGENT_ID=your_agent_id_here

# Server config
CORS_ORIGINS=*
TRUSTED_HOSTS=

HOST=127.0.0.1
PORT=8000

SMARTDINE_OPEN_BROWSER=0
UVICORN_RELOAD=1
SMARTDINE_PAUSE_ON_ERROR=0
Notes
Do not commit your .env file
Add .env to .gitignore
If API keys are missing:
AI responses may not work
phone call features will be simulated
Available routes
Marketing site
http://127.0.0.1:PORT/
(requires frontend build)
AI assistant
http://127.0.0.1:PORT/assistant
Health check
http://127.0.0.1:PORT/health
Debug
http://127.0.0.1:PORT/debug
Frontend (build for backend)
cd web
npm install
npm run build

This creates the web/dist folder.

Frontend (development mode)
cd web
npm install
npm run dev

Open:

http://127.0.0.1:5173
Notes
Frontend runs on port 5173
Backend runs on 8000+
AI chat requires backend
Troubleshooting

If the site does not load:

Ensure python main.py is running
Check the correct port in terminal
Do not assume it is always 8000
Project structure
main.py
requirements.txt
web/
  ├── src/
  ├── dist/
  └── package.json
Notes
Backend handles AI, booking, and execution logic
Frontend handles UI and user interaction
/assistant is the main AI interface
Important
Do not expose API keys publicly
Always use .env for secrets
Retell AI integration requires valid credentials
