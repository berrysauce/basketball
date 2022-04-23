print("[...] Importing packages")
try:
    import uvicorn
    from fastapi import FastAPI, Request, HTTPException
    from fastapi.responses import HTMLResponse, RedirectResponse
    from fastapi.staticfiles import StaticFiles
    from fastapi.templating import Jinja2Templates
    from starlette.exceptions import HTTPException as StarletteHTTPException
    from dotenv import load_dotenv
    import os
    import sys
    from functools import lru_cache
    import requests
    from typing import Optional
    import json
    from datetime import datetime
    from bs4 import BeautifulSoup
    from deta import Deta
except:
    print("[-!-] Failed to import packages \n..... Try <pip install -r requirements.txt>")
    sys.exit(1)


"""
===========================================================
                        SETUP
===========================================================
"""

# LOAD ENV
print("[...] Loading .env values")
try:
    load_dotenv()
    DRIBBBLE_TOKEN = str(os.getenv("DRIBBBLE_TOKEN"))
    APP_HOST = str(os.getenv("APP_HOST"))
    APP_PORT = os.getenv("APP_PORT")
    CACHE_EXPIRY = os.getenv("CACHE_EXPIRY")

    if DRIBBBLE_TOKEN == "None":
        print("[ ! ] Dribbble Token not in .env \n..... See how to get it in the docs")
    if APP_HOST == "None":
        print("[ ! ] Host not in .env \n..... defaulting to localhost")
        APP_HOST = "localhost"
    if APP_PORT == None:
        print("[ ! ] Port not in .env \n..... defaulting to 8000")
        APP_PORT = 8000
    if CACHE_EXPIRY == None:
        print("[ ! ] CACHE_EXPIRY not in .env \n..... defaulting to 3600")
        CACHE_EXPIRY = 3600
except:
    print("[-!-] Failed to load .env \n..... Make sure you've created a .env and filled it with the correct information")
    sys.exit(1)

# LOAD DETA ENV
DETA_RUNTIME = os.getenv("DETA_RUNTIME")
if DETA_RUNTIME == "true":
    DETA_TOKEN = None
else:
    DETA_TOKEN = str(os.getenv("DETA_TOKEN"))
    if DETA_TOKEN == "None":
        print("[-!-] DETA Token missing \n..... You're in a local runtime and the DETA Token is required")
        sys.exit(1)

# INITIALIZE APP
app = FastAPI(docs_url=None, redoc_url=None)
templates = Jinja2Templates(directory="templates")
deta = Deta(DETA_TOKEN)
cachedb = deta.Base("basketball_cache")

app.mount("/assets", StaticFiles(directory="templates/assets"), name="assets")


"""
===========================================================
                        FUNCTIONS
===========================================================
"""

def cache_handler(key, data):
    """
    Checks if data is in cache and adds it if it's not there
    :return: Data from cache
    """

    res = cachedb.fetch(query={"cache_key": key}).items

    if len(res) == 0 and data is None:
        return False

    if len(res) == 0 and data is not None:
        # No item in cache, creating item
        cache_data = {"cache_key": key,
                      "cache_data": data}
        cachedb.put(data=cache_data, expire_in=int(CACHE_EXPIRY))
        return data
    else:
        # Item in cache, returning from cache
        return res[0]["cache_data"]


def get_shot_grid():
    """
    Generates the HTML grid of shots from Dribbble
    :return: HTML shot grid
    """

    # Get cache
    cached = cache_handler(key="shots", data=None)

    # Get user's shots from Dribbble API
    if cached is False:
        r = requests.get(f"https://api.dribbble.com/v2/user/shots?access_token={DRIBBBLE_TOKEN}")
        data = json.loads(r.text)
        data = cache_handler(key="shots", data=data)
    else:
        data = cached

    # Get image card HTML
    with open("templates/components/image-card.html", "r") as f:
        image_card = f.read()
    shots_html = """"""

    for shot in data:
        soup = BeautifulSoup(shot["description"], features="html.parser")
        if shot["images"]["hidpi"]:
            shot_hidpi = shot["images"]["hidpi"]
        else:
            shot_hidpi = shot["images"]["normal"]
        shot_card = image_card\
            .replace("{{ img_src }}", shot["images"]["normal"])\
            .replace("{{ imghidpi_src }}", shot_hidpi)\
            .replace("{{ shot_url }}", shot["html_url"])\
            .replace("{{ shot_id }}", str(shot["id"]))\
            .replace("{{ shot_title }}", shot["title"])\
            .replace("{{ shot_description }}", soup.get_text())
        shots_html = shots_html + shot_card

    return shots_html


def get_profile_data():
    """
    Requests profile info from Dribbble API and returns it along with links in HTML
    :return: profile data, HTML links
    """

    # Step 0: Check cache
    cached = cache_handler(key="profile", data=None)

    # Step 1: Get profile data
    if cached is False:
        r = requests.get(f"https://api.dribbble.com/v2/user?access_token={DRIBBBLE_TOKEN}")
        data = json.loads(r.text)
        data = cache_handler(key="profile", data=data)
    else:
        data = cached

    # Step 2: Generate footer links
    link_html = """<li class="list-inline-item"><a href="{{ url }}" target="_blank">{{ name }}</a></li>"""
    links_html = """"""
    for link in data["links"]:
        links_html = links_html + link_html.replace("{{ url }}", data["links"][link]).replace("{{ name }}", link.capitalize())

    return data, links_html


"""
===========================================================
                        ROUTES
===========================================================
"""

@app.get("/", response_class=HTMLResponse)
def get_root(request: Request):
    """
    Main page with profile info and shots
    """

    if DRIBBBLE_TOKEN == "None":
        raise HTTPException(status_code=500, detail="Dribbble Token not in .env (more about this in the docs)")

    shots_html = get_shot_grid()
    data, links_html = get_profile_data()
    year = datetime.now().year
    return templates.TemplateResponse("index.html", {
        "request": request,
        "avatar_url": data["avatar_url"],
        "name": data["name"],
        "login": data["login"],
        "bio": data["bio"],
        "location": data["location"],
        "dribbble_url": data["html_url"],
        "shots_html": shots_html,
        "links_html": links_html,
        "year": year
    })


"""
===========================================================
              RUNNER & EXCEPTION HANDLER
===========================================================
"""

@app.exception_handler(StarletteHTTPException)
async def my_custom_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return templates.TemplateResponse("error.html", {"request": request, "code": "404", "detail": "The requested resource couldn't be found."})
    elif exc.status_code == 500:
        return templates.TemplateResponse("error.html", {"request": request, "code": "500", "detail": exc.detail})
    else:
        return templates.TemplateResponse('error.html', {"request": request, "code": "Error", "detail": exc.detail})


if __name__ == "__main__":
    print(
    """

    ____            _        _   _           _ _ 
    | __ )  __ _ ___| | _____| |_| |__   __ _| | |
    |  _ \ / _` / __| |/ / _ \ __| '_ \ / _` | | |
    | |_) | (_| \__ \   <  __/ |_| |_) | (_| | | |
    |____/ \__,_|___/_|\_\___|\__|_.__/ \__,_|_|_|
    [ by berrysauce                Version 0.1.X ]

    """)
    print(f"[ √ ] Starting Server \n..... at {APP_HOST}:{APP_PORT} \n..... with CACHE_EXPIRY {CACHE_EXPIRY}")
    # converting APP_PORT to int here to not interfere with .env reading check (try/except)
    uvicorn.run(app, host=APP_HOST, port=int(APP_PORT))