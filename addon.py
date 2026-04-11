import os
import sys
import json
import xbmc
import xbmcgui
import xbmcaddon
import xbmcplugin
import xbmcvfs
import sqlite3
import re
import html
import math
import socket
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone

# Config constants
ADDON_NAME = "plugin.video.cb20"
ADDON_SHORTNAME = "CB20"
BASE_DIR = os.path.dirname(__file__)
DB_FAVOURITES_FILE = "favourites-cb.db"
DB_FAVOURITES = xbmcvfs.translatePath("special://profile/addon_data/%s/%s" % (ADDON_NAME, DB_FAVOURITES_FILE))
DB_TEXTURES = xbmcvfs.translatePath("special://userdata/Database/Textures13.db")
PATH_THUMBS = xbmcvfs.translatePath("special://userdata/Thumbnails/")

# Queries
Q_THUMBNAILS = "SELECT url,cachedurl FROM texture WHERE url LIKE '%thumb.live.mmcdn.com%'"
Q_DEL_THUMBNAILS = "DELETE FROM texture WHERE url LIKE '%thumb.live.mmcdn.com%'"

# Addon init
PLUGIN_ID = int(sys.argv[1])
ADDON = xbmcaddon.Addon(id=ADDON_NAME)

# Thumbnail URL constants
THUMB_WIDE    = "https://thumb.live.mmcdn.com/riw/{0}.jpg"
THUMB_SQUARE  = "https://thumb.live.mmcdn.com/ri/{0}.jpg"

# Headers
REQUEST_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.7680.178 Safari/537.36',
    'Referer': 'https://chaturbate.com/',
    'Origin': 'https://chaturbate.com',
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate',
}

# API endpoints
API_ENDPOINT_BIO     = "https://chaturbate.com/api/biocontext/{0}/"
API_ENDPOINT_TAGLIST = "https://chaturbate.com/api/ts/hashtags/tag-table-data/?g={0}&page={1}&limit={2}&sort={3}"
API_ENDPOINT_ROOMS   = "https://chaturbate.com/api/ts/roomlist/room-list/?enable_recommendations=false"
HLS_EDGE_ENDPOINT    = "https://chaturbate.com/get_edge_hls_url_ajax/"

# Site specific constants
USER_STATES = {
    'public' : '',
    'private' : 'pvt',
    'hidden' : 'hidden',
    'offline' : 'off'
}
USER_STATES_NICE = {
    'public' : 'Public',
    'private' : 'Private Session',
    'hidden' : 'Hidden',
    'offline' : 'Offline'
}
    
DEL_THUMBS_ON_STARTUP = ADDON.getSettingBool('del_thumbs_on_startup')
REQUEST_TIMEOUT = ADDON.getSettingInt('request_timeout')
TAG_SORT_BY_OPTIONS = ["ht", "-rc", "-vc"]
TAG_SORT_BY_STD = TAG_SORT_BY_OPTIONS[ADDON.getSettingInt('tag_sort_by')]
TAG_LIST_LIMITS = [10, 25, 50, 75, 100]
TAG_LIST_LIMIT = TAG_LIST_LIMITS[ADDON.getSettingInt('tag_list_limit')]

CAM_LIST_LIMITS = [10, 25, 50, 75, 100]
CAM_LIST_LIMIT = TAG_LIST_LIMITS[ADDON.getSettingInt('cam_list_limit')]

# Tuples for menu and categories on site
SITE_MENU = (('Categories - All', "catlist", "Show cams by categories featured, female, male, couple, trans."), 
             ('Categories - Female', "catlist&genders=f", "Show female cams only."), 
             ('Categories - Male', "catlist&genders=m", "Show male cams only."), 
             ('Categories - Couple', "catlist&genders=c", "Show couple cams only."), 
             ('Categories - Trans', "catlist&genders=t", "Show trans cams only."), 
             ("Tags", "tagsmenu", "Show cams by tags for above categories. "),
             ("Favourites", "favourites", "Favourites list. Offline cams will have default picture."), 
             ("Search", "search", "Search for an exact username.\nShows on- AND offline cams."),
             ("Fuzzy search", "fuzzy", "List cams containing term in username.\nONLINE CAMS ONLY!"),
             ("Tools", "tools", "Some tools for cleanup and favourites.")
             )
SITE_TAGS = (('Tags - Featured', 'taglist', ""), 
             ('Tags - Female', 'taglist&genders=f', ""),
             ('Tags - Male', 'taglist&genders=m', ""), 
             ('Tags - Couple', 'taglist&genders=c', ""), 
             ('Tags - Transsexual', 'taglist&genders=t', ""),)
SITE_TOOLS = (("Backup Favourites", "tool=fav-backup", "Backup favourites (Set backup location in settings first). \nExisting favourites file will be overwritten without warning."),
              ("Restore Favourites", "tool=fav-restore", "Restore your favourites from backup location."),
              ("Delete Thumbnails", "tool=thumbnails-delete", "Delete cached chaturbate related thumbnail files and database entries."))

# Strings
STRINGS = {
    'na' : 'User is not available',
    'last_status' : 'Last status: ',
    'last_broadcast' : 'Last broadcast: ',
    'status' : 'Status: ',
    'unknown_status' : 'Unkown status: ',
    'not_live' : 'User is not live at the moment'
}

# LL-HLS manifest handling
#
# CDN JWT token on llhls.m3u8 is single-use and fingerprint-validated.
# The first Python urllib fetch succeeds; the token is then burned — any
# subsequent fetch (e.g. by inputstream.adaptive) returns 403.
#
# Solution: pre-fetch the manifest ourselves, rewrite URIs to absolute,
# then serve it once via a one-shot localhost HTTP server that shuts itself
# down immediately after serving one request. No lingering threads.


def _bind_manifest_socket():
    """Bind a listening socket on a free port. Returns (socket, url) or (None, None)."""
    for port in range(34521, 34526):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            srv.bind(('127.0.0.1', port))
            srv.listen(4)
            srv.settimeout(5)
            xbmc.log(f"{ADDON_SHORTNAME}: manifest socket bound on 127.0.0.1:{port}", 1)
            return srv, f'http://127.0.0.1:{port}/{ADDON_SHORTNAME}_manifest.m3u8'
        except OSError:
            srv.close()
    xbmc.log(f"{ADDON_SHORTNAME}: manifest socket bind failed — all ports 34521-34525 in use",
             level=xbmc.LOGERROR)
    return None, None


def _serve_manifest_once(srv_sock, content):
    """Serve manifest to every inbound connection until a 5-second idle silence."""
    response = (
        b'HTTP/1.1 200 OK\r\n'
        b'Content-Type: application/vnd.apple.mpegurl\r\n'
        b'Content-Length: ' + str(len(content)).encode() + b'\r\n'
        b'Cache-Control: no-cache\r\n'
        b'Connection: close\r\n'
        b'\r\n'
        + content.encode('utf-8')
    )
    try:
        while True:
            try:
                conn, _ = srv_sock.accept()
            except socket.timeout:
                break
            try:
                conn.settimeout(5)
                conn.recv(4096)  # drain request headers
                conn.sendall(response)
            except Exception:
                pass
            finally:
                conn.close()
    finally:
        srv_sock.close()


def _fetch_manifest_content(url):
    """Fetch LL-HLS master manifest and rewrite all relative URIs to absolute."""
    from urllib.parse import urljoin
    req = urllib.request.Request(url, headers={**REQUEST_HEADERS, 'Accept': '*/*'})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            if 'gzip' in (resp.headers.get('Content-Encoding') or '').lower():
                import gzip
                raw = gzip.decompress(raw)
    except Exception as e:
        xbmc.log(f"{ADDON_SHORTNAME}: manifest fetch failed: {repr(e)}", level=xbmc.LOGERROR)
        return None

    def make_absolute(line):
        # Rewrite quoted URI="..." attributes (EXT-X-MEDIA, EXT-X-MAP, etc.)
        line = re.sub(
            r'URI="([^"]*)"',
            lambda m: f'URI="{urljoin(url, m.group(1))}"' if not m.group(1).startswith('http') else m.group(0),
            line
        )
        # Rewrite bare URI lines (variant/chunklist paths not starting with #)
        if not line.startswith('#') and line.strip() and not line.startswith('http'):
            line = urljoin(url, line.strip())
        return line

    lines = raw.decode('utf-8', errors='replace').splitlines()
    return '\n'.join(make_absolute(l) for l in lines)

def evaluate_request():
    """Evaluate what has been picked in Kodi"""
    
    if not sys.argv[2]:
        get_menu()
        return

    param = sys.argv[2]
    
    # Map parameters to functions
    param_map = {
        "tagsmenu": lambda: get_menu(SITE_TAGS),
        "tools": lambda: get_menu(SITE_TOOLS),
        "favourites": get_favourites,
        "search": search_actor,
        "fuzzy": search_actor2,
        "tool=": handle_tool,
        "catlist": get_catlist,
        "roomlist": get_roomlist,
        "taglist": get_tag_list,
        "playactor=": lambda x: play_actor(x, ["Chaturbate"])
    }

    # Find matching parameter and call corresponding function
    for key, func in param_map.items():
        if key in param:
            if key == "tool=":
                tool = re.findall(r'\?tool=(.*)', param)[0]
                handle_tool(tool)
            elif key == "playactor=":
                actor = re.findall(r'\?playactor=(.*)', param)[0]
                func(actor)
            else:
                func()
            return

    # If no matching parameter found
    xbmc.log(f"{ADDON_SHORTNAME}: Unhandled parameter: {param}", level=xbmc.LOGERROR)

def handle_tool(tool):
    tool_map = {
        "fav-backup": tool_fav_backup,
        "fav-restore": tool_fav_restore,
        "thumbnails-delete": tool_thumbnails_delete
    }
    if tool in tool_map:
        tool_map[tool]()
    else:
        xbmc.log(f"{ADDON_SHORTNAME}: Unhandled tool: {tool}", level=xbmc.LOGERROR)

def get_menu(itemlist=SITE_MENU):
    """Decision tree. Shows main menu by default"""
        
    # Build menu items
    items = []
    for item in itemlist:
        url = sys.argv[0] + '?' + item[1]
        li = xbmcgui.ListItem(item[0])
        vit = li.getVideoInfoTag()
        vit.setPlot(item[2])
        items.append((url, li, True))

    xbmcplugin.addDirectoryItems(PLUGIN_ID, items)
    xbmcplugin.endOfDirectory(PLUGIN_ID)

def tool_fav_backup():
    path = ADDON.getSetting('fav_path_backup')
    source = DB_FAVOURITES
    destination = path + DB_FAVOURITES_FILE
    
    if path == "":
        xbmcgui.Dialog().ok("Backup Favourites", "Backup path is empty. Please set a valid path in settings menu under \"Favourites\" first.")  
        xbmcaddon.Addon(id=ADDON_NAME).openSettings()
    else:
        # Ask for confirmation before backup
        if xbmcgui.Dialog().yesno("Backup Favourites", "Do you really want to backup your favourites database?\nThis will overwrite any existing backup file.",
                                  yeslabel="Yes, backup", nolabel="Cancel"):
            if xbmcvfs.exists(source):
                if xbmcvfs.copy(source, destination):
                    xbmcgui.Dialog().ok("Backup Favourites", "Backup of favourites to backup path succesful.")
                else:
                    xbmcgui.Dialog().ok("Backup Favourites", "Something went wrong.")
            else:
                xbmcgui.Dialog().ok("Backup Favourites", "Favourites file is empty. Nothing to backup.")

def tool_fav_restore():
    path = ADDON.getSetting('fav_path_backup')
    source = path + DB_FAVOURITES_FILE
    destination = DB_FAVOURITES
    
    if path == "":
        xbmcgui.Dialog().ok("Restore Favourites", "Restore path is empty. Please set a valid path in settings menu under \"Favourites\" first.")  
        xbmcaddon.Addon(id=ADDON_NAME).openSettings()
    else:
        if xbmcvfs.exists(source):
            # Ask for confirmation before restore
            if xbmcgui.Dialog().yesno("Restore Favourites", "Do you really want to restore your favourites database?\nThis will overwrite your current favourites!", 
                                      yeslabel="Yes, restore", nolabel="Cancel"):
                if xbmcvfs.copy(source, destination):
                    xbmcgui.Dialog().ok("Restore Favourites", "Restore of favourites succesful.")
                else:
                    xbmcgui.Dialog().ok("Restore Favourites", "Something went wrong.")
        else:
            xbmcgui.Dialog().ok("Restore Favourites", "No valid file found in restore location. Make a backup first or check location.")

def connect_favourites_db():
    "Connect to favourites database and create one, if it does not exist."

    db_con = sqlite3.connect(DB_FAVOURITES)
    c = db_con.cursor()
    try:
        c.execute("SELECT * FROM favourites;")
    except sqlite3.OperationalError:
        c.executescript("CREATE TABLE favourites (user primary key);")
    return db_con

def get_favourites():
    """Get list of favourites from addon's db"""    

    # Clean Thumbnails before opening the list
    if DEL_THUMBS_ON_STARTUP:
        tool_thumbnails_delete2()

    # Connect to favourites db
    db_con = connect_favourites_db()
    c = db_con.cursor()
    c.execute("SELECT * FROM favourites")
    res = []
    for (user) in c.fetchall():
        res.append((user[0]))
    res.sort()

    # Build kodi listems for virtual directory
    items = []
    for item in res:
        url = sys.argv[0] + '?playactor=' + item
        li = xbmcgui.ListItem(item)
        li.setLabel(item)
        li.setArt({'icon': THUMB_SQUARE.format(item), 'thumb': THUMB_SQUARE.format(item)})

        # Context menu
        commands = []
        commands.append((ADDON_SHORTNAME + ' - Remove favourite','RunScript(' + ADDON_NAME + ', ' + str(sys.argv[1]) + ', remove_favourite, ' + item + ')'))
        commands.append(('[COLOR orange]' + ADDON_SHORTNAME + ' - Refresh thumbnails [/COLOR]','RunScript(' + ADDON_NAME + ', ' + str(sys.argv[1]) + ', ctx_thumbnails_delete)'))
        
        li.addContextMenuItems(commands, True)
        li.setProperty('IsPlayable', 'true')
        items.append((url, li, False))

    # Put items to virtual directory listing and set sortings
    xbmcplugin.setContent(int(sys.argv[1]), 'videos')
    xbmcplugin.addSortMethod(int(sys.argv[1]), xbmcplugin.SORT_METHOD_LABEL)
    xbmcplugin.addDirectoryItems(PLUGIN_ID, items)
    xbmcplugin.endOfDirectory(PLUGIN_ID)

def get_catlist():
    # Disect url arguments
    args = urllib.parse.parse_qs(sys.argv[2][1:])
    genders = args.get('genders', [''])[0]
    
    # Menu items
    itemlist = (("All", "roomlist&genders="+genders, ""),
                   ("New cams", "roomlist&genders="+genders+"&new_cams=true", ""),
                   ("Teen cams (18+)", "roomlist&genders="+genders+"&from_age=18&to_age=20", ""),
                   ("18-21 cams", "roomlist&genders="+genders+"&from_age=18&to_age=22", ""),
                   ("20-30 cams", "roomlist&genders="+genders+"&from_age=20&to_age=31", ""),
                   ("30-50 cams", "roomlist&genders="+genders+"&from_age=30&to_age=51", ""),
                   ("Mature cams (50+)", "roomlist&genders="+genders+"&from_age=50&to_age=200", ""),
                   ("North american cams", "roomlist&genders="+genders+"&regions=NA", ""),
                   ("South american cams", "roomlist&genders="+genders+"&regions=SA", ""),
                   ("Euro russian cams", "roomlist&genders="+genders+"&regions=ER", ""),
                   ("Asian cams", "roomlist&genders="+genders+"&regions=AS", ""),
                   ("Other region cams", "roomlist&genders="+genders+"&regions=O", ""),
                   ("Gaming cams", "roomlist&genders="+genders+"&gaming_cams=true", ""))
    
    # Build menu items
    items = []
    for item in itemlist:
        url = sys.argv[0] + '?' + item[1]
        li = xbmcgui.ListItem(item[0])
        vit = li.getVideoInfoTag()
        vit.setPlot(item[2])
        items.append((url, li, True))

    xbmcplugin.addDirectoryItems(PLUGIN_ID, items)
    xbmcplugin.endOfDirectory(PLUGIN_ID)
    
def get_roomlist():
    # Disect url arguments
    args = urllib.parse.parse_qs(sys.argv[2][1:])
    
    # Extract URL parameters
    page        = int(args.get('page', [1])[0]) # for navigation
    genders     = args.get('genders', [''])[0]
    if page == 1: # Api returns one over limit for offset = 0
        limit   = int(args.get('limit', [CAM_LIST_LIMIT-1])[0])
    else:
        limit   = int(args.get('limit', [CAM_LIST_LIMIT])[0])
    offset      = int(args.get('offset', [0])[0])
    offset      = (page - 1) * limit
    new_cams    = args.get('new_cams', [None])[0]
    hashtags    = args.get('hashtags', [None])[0] # for tags
    keywords    = args.get('keywords', [None])[0] # for fuzzy search
    gaming_cams = args.get('gaming_cams', [None])[0]
    regions     = args.get('regions', [None])[0]
    from_age    = args.get('from_age', [None])[0]
    to_age      = args.get('to_age', [None])[0]
    
    # Build URL from parameters    
    url = build_api_url_rooms(genders=genders, 
                              offset=offset, 
                              limit=limit, 
                              new_cams=new_cams, 
                              hashtags=hashtags, 
                              keywords=keywords,
                              gaming_cams=gaming_cams, 
                              regions=regions, 
                              from_age=from_age, 
                              to_age=to_age)
    
    # Console log the URL
    xbmc.log(ADDON_SHORTNAME + ": Fetching roomlist from URL: " + url, 1)
    
    # Fetch the JSON data from the URL
    data = fetch_json_from_url(url, REQUEST_TIMEOUT)
    
    # Build kodi list items for virtual directory
    items = []
    id = 0
    
    if data:        
        # Parse JSON data
        try:
            roomlist = extract_roomlist_from_json(data)
            
            # Extract rooms from roomlist and build listitems
            for room in roomlist.get('rooms', []):
                # Set navigation URL for room
                url = sys.argv[0] + '?playactor=' + room.get('username')
                # Build listitem
                li = xbmcgui.ListItem(room.get('username'))
                # Create video info tag
                vit = li.getVideoInfoTag()
                # Extract num_users count for playcounter
                s = room.get('num_users', 0)
                li.setLabel(room.get('username'))
                li.setArt({'icon': room.get('img'), 'thumb': room.get('img'), 'poster': room.get('img')})
                vit.setSortTitle(str(id).zfill(2) + " - " + room.get('username'))
                id = id + 1
                vit.setPlot("Age: " + str(room.get('display_age', "-"))
                            + "\nLabel: " + room.get('label', "-")
                            + "\nViewers: " + str(room.get('num_users', 0)) 
                            + "\nOnline: " + room.get('online_since')
                            + "\nFollowers: " + str(room.get('num_followers', 0)) 
                            + "\nLocation: " + room.get('location', "-")
                            + "\n\n" + room.get('subject', "-")
                            )
                vit.setPlaycount(int(s))
                
                # Context menu
                commands = []
                commands.append(('[COLOR orange]' + ADDON_SHORTNAME + ' - Add as favourite [/COLOR]','RunScript(' + ADDON_NAME + ', ' + str(sys.argv[1]) + ', add_favourite, ' + room.get('username') + ')'))
                commands.append(('[COLOR orange]' + ADDON_SHORTNAME + ' - Refresh thumbnails [/COLOR]','RunScript(' + ADDON_NAME + ', ' + str(sys.argv[1]) + ', ctx_thumbnails_delete)'))
                li.addContextMenuItems(commands, True)
                li.setProperty('IsPlayable', 'true')
                items.append((url, li, False))
        except:
            if keywords:
                xbmcgui.Dialog().ok(ADDON_SHORTNAME + " Fuzzy Search", "No cams found matching keywords.")
            else:
                xbmcgui.Dialog().ok(ADDON_SHORTNAME + " Error", "Error extracting roomlist from JSON.")
            xbmc.log(ADDON_SHORTNAME + ": " + "Error extracting roomlist from JSON.", level=xbmc.LOGERROR)
            return False
        
        # Pagination
        total_count = data.get('total_count', 0)
        if page == 1:
            total_pages = math.ceil(total_count / (limit+1))
        else:
            total_pages = math.ceil(total_count / limit)
        
        xbmc.log("Total count: " + str(total_count) + " Pages: " + str(total_pages), 1)
        
        if page < total_pages:
            next_url = build_roomlist_url(page=page + 1, genders=genders, new_cams=new_cams, hashtags=hashtags, keywords=keywords, gaming_cams=gaming_cams, regions=regions, from_age=from_age, to_age=to_age)
            li = xbmcgui.ListItem(f"Page {page + 1} of {total_pages}")
            vit = li.getVideoInfoTag()
            
            li.setArt({'icon': 'DefaultFolder.png', 'thumb': 'DefaultFolder.png', 'poster': 'DefaultFolder.png'})
            vit.setSortTitle(str(999).zfill(2) + " - Next Page")
            vit.setPlaycount(-1)
            
            # Context menu
            commands = []
            commands.append(('Back to first page',"Container.Update(%s?%s, replace)" % ( sys.argv[0],  "roomlist&genders="+genders)))
            commands.append(('Back to main menu',"Container.Update(%s, replace)" % ( sys.argv[0])))
            li.addContextMenuItems(commands, True)
            
            items.append((sys.argv[0] + '?'+next_url, li, True))
        
    else:
        xbmcgui.Dialog().ok(ADDON_SHORTNAME + " Error", "Error listing available cams. Could not fetch JSON from API.")
        xbmc.log(ADDON_SHORTNAME + ": " + "Could not fetch JSON data from URL: " + url, level=xbmc.LOGERROR)
        return False
    
    # Put items to virtual directory listing and set sortings
    put_virtual_directoy_listing(items)

def put_virtual_directoy_listing(items):
    """Put items to virtual directory listing and set sortings"""
    xbmcplugin.setContent(PLUGIN_ID, 'videos')
    xbmcplugin.addSortMethod(PLUGIN_ID, xbmcplugin.SORT_METHOD_VIDEO_SORT_TITLE)
    xbmcplugin.addSortMethod(PLUGIN_ID, xbmcplugin.SORT_METHOD_PLAYCOUNT, "Viewers")
    xbmcplugin.addSortMethod(PLUGIN_ID, xbmcplugin.SORT_METHOD_LABEL)
    xbmcplugin.addDirectoryItems(PLUGIN_ID, items)
    xbmcplugin.endOfDirectory(PLUGIN_ID)

def get_tag_list():
    """Get list of available tags for the categories"""
    
    # Disect url arguments
    args = urllib.parse.parse_qs(sys.argv[2][1:])
    genders = args.get('genders', [''])[0]
    page = args.get('page', ['1'])[0]
    limit = args.get('limit', [TAG_LIST_LIMIT])[0]
    sortBy = args.get('sort', [TAG_SORT_BY_STD])[0] # ht = hashtag | rc = room count | vc = viewer count. prefix "-" to reverse order

    # Get json data
    roomlist = json.loads(json.dumps(fetch_json_from_url(API_ENDPOINT_TAGLIST.format(genders, page, limit, sortBy), REQUEST_TIMEOUT)))
    
    items = []
    
    if "hashtags" in roomlist: # no error, we have results
        total = int(roomlist["total"])
        
        id = 0
        for item in roomlist["hashtags"]:
            url = sys.argv[0] + '?roomlist&genders=' + genders + "&hashtags=" + item["hashtag"]
            li = xbmcgui.ListItem(item["hashtag"])
            vit = li.getVideoInfoTag()
            li.setLabel(item["hashtag"] + " (%s)" %
                        item["room_count"])
            vit.setPlaycount(0)
            vit.setSortTitle(str(id).zfill(3) + " - " + item["hashtag"])
            items.append((url, li, True))
            id = id + 1
        
        # Pagination
        totalPages = total // int(limit)
        
        if totalPages > 1: # We have enough results for at least two pages
            if int(page) + 1 < totalPages:
                # URL for next page button
                next_url = "taglist&genders=" + genders + "&page=" + str(int(page)+1)
                li = xbmcgui.ListItem("Next page (%s of %s)" % (str(int(page)+1),str(totalPages)))
                vit = li.getVideoInfoTag()
                li.setArt({'icon': 'DefaultFolder.png', 'thumb': 'DefaultFolder.png', 'poster': 'DefaultFolder.png'})
                vit.setSortTitle(str(id).zfill(2) + " - Next Page")
                vit.setPlaycount(-1)
                
                # Context menu
                commands = []
                commands.append(('Back to first page',"Container.Update(%s?%s, replace)" % ( sys.argv[0],  "taglist&genders=" + genders)))
                commands.append(('Back to main menu',"Container.Update(%s, replace)" % ( sys.argv[0])))
                li.addContextMenuItems(commands, True)
                
                items.append((sys.argv[0] + '?'+next_url, li, True))
    
    # Build kodi listems for virtual directory
    # Put items to virtual directory listing and set sortings
    xbmcplugin.addSortMethod(PLUGIN_ID, xbmcplugin.SORT_METHOD_VIDEO_SORT_TITLE)
    xbmcplugin.addSortMethod(PLUGIN_ID, xbmcplugin.SORT_METHOD_LABEL)
    xbmcplugin.addDirectoryItems(PLUGIN_ID, items)
    xbmcplugin.endOfDirectory(PLUGIN_ID)

def get_bio_context_from_actor(actor):
    url = API_ENDPOINT_BIO.format(actor)
    b = json.loads(json.dumps(fetch_json_from_url(url, REQUEST_TIMEOUT)))
    return get_bio_context_from_json(b)

def get_bio_context_from_json(b):
    s = ""
    # follower_count (int) (Followers: )
    if "follower_count" in b:
        s += "Followers: " + str(b['follower_count'])
    # display_age (Age: )
    if "display_age" in b and not b['display_age'] == None:
        if "display_birthday" in b:
            s += " | Age: " + str(b['display_age']) + " (" + b['display_birthday'] + ")"
        else:
            s += " | Age: " + str(b['display_age'])
    # sex (I am: )
    if "sex" in b and not b['sex'] == "":
        s += " | I am: " + b['sex']
        #s += " | I am: " + b.get('sex', 'na')
    # real_name (Name: )
    if "real_name" in b and not b['real_name'] == "":
        s += " | Real name: " + b['real_name']
    # location (Location: )
    if "location" in b and not b['location'] == "":
        s += " | Location: " + b['location']
    # body_decorations (Body Decorations:)
    if "body_decorations" in b and not b['body_decorations'] == "":
        s += " | Body decorations: " + b['body_decorations']
    # smoke_drink (Smoke / Drink:)
    if "smoke_drink" in b and not b['smoke_drink'] == "":
        s += " | Smoke/drink: " + b['smoke_drink']
    # body_type (Body Type:)
    if "body_type" in b and not b['body_type'] == "":
        s += " | Body type: " + b['body_type']
    # languages (Language(s):) simple stringgenre
    if "languages" in b and not b['languages'] == "":
        s += " | Languages: " + b['languages']
    # time_since_last_broadcast (Last Broadcast:)
    if "time_since_last_broadcast" in b:
        s += " | Last broadcast: " + b['time_since_last_broadcast']
    # fan_club_cost ()
    if "fan_club_cost" in b and not b['fan_club_cost'] == 0:
        s += " | Fan club price: " + str(b['fan_club_cost'])
        
    return s


def play_actor(actor, genre=[""]):
    """Get playlist for actor/username and add m3u8 to kodi's playlist"""

    # Fetch HLS URL and room status
    hls_source, room_status = get_hls_url(actor)

    if room_status == 'not_found':
        xbmcgui.Dialog().ok("User issue (404 error)", "Username does not exist anymore. If this message persists, this user is safe to delete.")
        return

    if room_status is None:
        xbmcgui.Dialog().ok("Connection error", "Could not reach Chaturbate servers. Please try again.")
        return

    if room_status != 'public':
        b = fetch_json_from_url(API_ENDPOINT_BIO.format(actor), REQUEST_TIMEOUT) or {}
        last_broadcast = b.get('time_since_last_broadcast', 'unknown')
        status_nice = USER_STATES_NICE.get(room_status, room_status)
        xbmcgui.Dialog().ok(STRINGS['na'], STRINGS['status'] + status_nice + "\n" + STRINGS['last_broadcast'] + last_broadcast) # type: ignore
        return

    if not hls_source:
        xbmcgui.Dialog().ok(STRINGS['na'], STRINGS['not_live'])
        return

    # Fetch bio metadata
    b = fetch_json_from_url(API_ENDPOINT_BIO.format(actor), REQUEST_TIMEOUT) or {}

    # Plot using bio data
    plot = get_bio_context_from_json(b)

    # Build kodi listitem for playlist
    li = xbmcgui.ListItem(actor)
    tag = li.getVideoInfoTag()
    tag.setGenres(genre)
    tag.setPlot(plot)
    # Thumbnail for OSD (Square)
    li.setArt({'icon': THUMB_SQUARE.format(actor), 'thumb': THUMB_SQUARE.format(actor), 'poster': THUMB_SQUARE.format(actor)})
    li.setMimeType('application/vnd.apple.mpegurl')

    li.setProperty('inputstream', 'inputstream.adaptive')

    if 'llhls' in hls_source:
        content = _fetch_manifest_content(hls_source)
        if content:
            srv_sock, play_url = _bind_manifest_socket()
            if srv_sock:
                li.setPath(play_url)
                xbmc.log(f"{ADDON_SHORTNAME}: LL-HLS via one-shot server - {play_url}", 1)
                xbmcplugin.setResolvedUrl(PLUGIN_ID, True, li)
                xbmc.log(f"{ADDON_SHORTNAME}: setResolvedUrl returned, serving manifest", 1)
                # Block main thread here — serve the one request then exit.
                _serve_manifest_once(srv_sock, content)
                return
            else:
                play_url = hls_source  # socket bind failed, try direct
        else:
            play_url = hls_source  # manifest fetch failed, try direct
    else:
        play_url = hls_source
        xbmc.log(f"{ADDON_SHORTNAME}: HLS play via inputstream.adaptive - {play_url[:80]}", 1)

    li.setPath(play_url)
    xbmcplugin.setResolvedUrl(PLUGIN_ID, True, li)


def fetch_json_from_url(url, timeout):
    """Fetch JSON from url, with decompression and error handling."""
    headers = dict(REQUEST_HEADERS)
    headers.setdefault('X-Requested-With', 'XMLHttpRequest')
    req = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = None
            try:
                status = resp.getcode()
            except Exception:
                pass
            content_type = (resp.headers.get('Content-Type') or '')

            raw = resp.read()
            # Decompress if needed
            enc = (resp.headers.get('Content-Encoding') or '').lower()
            if 'gzip' in enc:
                try:
                    import gzip
                    raw = gzip.decompress(raw)
                except Exception as exc:
                    xbmc.log(f"{ADDON_SHORTNAME}: gzip decompress failed for {url} - {repr(exc)}", level=xbmc.LOGERROR)
            elif 'deflate' in enc:
                try:
                    import zlib
                    try:
                        raw = zlib.decompress(raw)
                    except zlib.error:
                        raw = zlib.decompress(raw, -zlib.MAX_WBITS)
                except Exception as exc:
                    xbmc.log(f"{ADDON_SHORTNAME}: deflate decompress failed for {url} - {repr(exc)}", level=xbmc.LOGERROR)

            charset = None
            try:
                charset = resp.headers.get_content_charset()
            except Exception:
                charset = None
            charset = charset or 'utf-8'

            text = raw.decode(charset, errors='replace')
            if text.startswith('\ufeff'):
                text = text.lstrip('\ufeff')

            # If not JSON-ish, log and bail
            if not ('json' in content_type.lower() or text.lstrip().startswith('{') or text.lstrip().startswith('[')):
                snippet = text[:500].replace('\n', ' ')
                xbmc.log(f"{ADDON_SHORTNAME}: Non-JSON response for {url} (status={status}, ct={content_type}). Snippet: {snippet}", level=xbmc.LOGERROR)
                return None

            # Parse JSON
            try:
                return json.loads(text)
            except json.JSONDecodeError as e:
                # Try to recover by finding the JSON start
                for ch in ('{', '['):
                    i = text.find(ch)
                    if i != -1:
                        try:
                            parsed = json.loads(text[i:])
                            xbmc.log(f"{ADDON_SHORTNAME}: Recovered JSON from substring for {url} (idx={i})", level=xbmc.LOGNOTICE)
                            return parsed
                        except Exception:
                            pass

                snippet = text[:500].replace('\n', ' ')
                ctx = text[max(0, e.pos - 80):e.pos + 80].replace('\n', ' ')
                xbmc.log(f"{ADDON_SHORTNAME}: JSONDecodeError for {url} (status={status}) - {e.msg} at {e.pos}. Snippet: {snippet}", level=xbmc.LOGERROR)
                xbmc.log(f"{ADDON_SHORTNAME}: JSON error context: {ctx}", level=xbmc.LOGERROR)
                return None

    except urllib.error.HTTPError as e:
        body = None
        try:
            body = e.read().decode('utf-8', errors='replace')
        except Exception:
            body = None
        body_snip = (body or '')[:500].replace('\n', ' ').replace('\x00', '')
        xbmc.log(f"{ADDON_SHORTNAME}: HTTPError {getattr(e,'code','?')} for {url}. Snippet: {body_snip}", level=xbmc.LOGERROR)
        return None

    except urllib.error.URLError as e:
        xbmc.log(f"{ADDON_SHORTNAME}: URLError for {url} - {getattr(e,'reason',e)}", level=xbmc.LOGERROR)
        return None

    except Exception as e:
        xbmc.log(f"{ADDON_SHORTNAME}: Unexpected error fetching {url} - {repr(e)}", level=xbmc.LOGERROR)
        return None

def search_actor():
    """Search for actor/username and list item if username exists"""

    s = xbmcgui.Dialog().input("Search username (lowercase)")
    if s == '':
        xbmcplugin.endOfDirectory(int(sys.argv[1]), succeeded=False)
    else:
        _, room_status = get_hls_url(s)

        if room_status == 'not_found':
            xbmcgui.Dialog().ok(ADDON_SHORTNAME, "Username does not exist. Please try again.")
            xbmcplugin.endOfDirectory(int(sys.argv[1]), succeeded=False)
            return

        if room_status is None:
            xbmcgui.Dialog().ok(ADDON_SHORTNAME, "Could not reach Chaturbate servers. Please try again.")
            xbmcplugin.endOfDirectory(int(sys.argv[1]), succeeded=False)
            return

        b = fetch_json_from_url(API_ENDPOINT_BIO.format(s), REQUEST_TIMEOUT) or {}

        li = xbmcgui.ListItem(s)
        commands = []
        commands.append((ADDON_SHORTNAME + ' - Add user to favourites', 'RunScript(' + ADDON_NAME + ', ' + str(sys.argv[1]) + ', add_favourite, ' + s + ')'))
        li.addContextMenuItems(commands, True)
        tag = li.getVideoInfoTag()

        status_suffix = {'private': ' | private', 'hidden': ' | hidden', 'offline': ' | offline'}
        li.setLabel(s + status_suffix.get(room_status, ''))

        plot = s + "\n\n" + get_bio_context_from_json(b)
        tag.setPlot(plot)
        li.setArt({'icon': THUMB_SQUARE.format(s), 'thumb': THUMB_SQUARE.format(s), 'poster': THUMB_SQUARE.format(s)})

        url = sys.argv[0] + '?playactor=' + s
        li.setProperty('IsPlayable', 'true')
        xbmcplugin.setContent(int(sys.argv[1]), 'videos')
        xbmcplugin.addDirectoryItems(PLUGIN_ID, [(url, li, False)])
        xbmcplugin.endOfDirectory(PLUGIN_ID)

def search_actor2():
    """Fuzzy Search for actor/username and list item if username is online"""
    
    s = xbmcgui.Dialog().input("Fuzzy search username (lowercase)")
    if s == '':
        xbmcplugin.endOfDirectory(int(sys.argv[1]), succeeded=False)
        return
    
    # Set keywords in sys.argv[2]
    sys.argv[2] = "?roomlist&keywords=" + s
    get_roomlist()    
    
def tool_thumbnails_delete():
    rc = tool_thumbnails_delete2()
    # Summary dialog
    xbmcgui.Dialog().ok("Delete Thumbnails", "Deleted %s thumbnail files and database entries" % (str(rc)))

def tool_thumbnails_delete2():   
    # Connect to textures db
    conn = sqlite3.connect(DB_TEXTURES)
    # Set cursors
    cur = conn.cursor()
    cur_del = conn.cursor()
    # Delete thimbnail files
    cur.execute(Q_THUMBNAILS)
    rc = 0
    rows = cur.fetchall()
    for row in rows:
        rc = rc + 1
        #xbmc.log("Thumb: " + PATH_THUMBS + str(row[1]),1)
        if os.path.exists(PATH_THUMBS + str(row[1])):
            os.remove(PATH_THUMBS + str(row[1]))
            #xbmc.log("The file has been successfully deleted.",1)
        else:
            #xbmc.log("The file does not exist.",1)
            pass
    # Delete entries from db
    cur_del.execute(Q_DEL_THUMBNAILS)
    conn.commit()
    # Close connection
    conn.close()
    # Return number of entries found and log
    xbmc.log(ADDON_SHORTNAME + ": Deleted %s thumbnail files and database entries" % (str(rc)),1)
    return rc

def extract_roomlist_from_json(data):
    # Initialize the result dictionary with a total_count key and an empty rooms list
    result = {'total_count': data.get('total_count', 0), 'rooms': []}
    
    for room in data.get('rooms', []):
        # Initialize a new room dictionary for the current room
        new_room = {}
        
        # Copy selected keys directly 
        direct_keys = ['display_age', 'gender', 'location', 'current_show', 'username', 'is_new', 'num_users', 'num_followers', 'start_timestamp', 'label']
        for key in direct_keys:
            new_room[key] = room.get(key, None)
        
        # Calculate the time online_since based on start_timestamp
        start_timestamp = room.get('start_timestamp', None)
        if start_timestamp:
            new_room['online_since'] = convert_timestamp_to_elapsed(room.get('start_timestamp', None))
        else:
            new_room['online_since'] = "0h 0m"
        
        # Convert tags into a comma-separated list
        tags = room.get('tags', [])
        new_room['tags'] = ', '.join(tags)
        
        # Replace "/riw/" with "/ri/" in the img URL (we want square images, not wide ones)
        img_url = room.get('img', '')
        new_room['img'] = img_url.replace("/riw/", "/ri/")
        
        # Remove a-tags and convert special characters in the subject
        subject = room.get('subject', '')
        subject = filter_and_unescape_html(subject)
        new_room['subject'] = subject
        
        # Append the new room dictionary to the result
        result['rooms'].append(new_room)
        
    return result

def convert_timestamp_to_elapsed(start_timestamp):
    now = datetime.now(timezone.utc).timestamp()
    elapsed_time = int(now - start_timestamp)
    hours, remainder = divmod(elapsed_time, 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{hours}h {minutes}m"

def filter_and_unescape_html(input_str):
    # Replace <a> with the text in between
    filtered_str = re.sub(r'<a .*?>(.*?)<\/a>', r'\1', input_str)
    # convert HTML-entities in readable text
    return html.unescape(filtered_str)

def get_hls_url(actor):
    """
    Fetch HLS stream URL via POST to get_edge_hls_url_ajax.
    Returns (url, room_status) or (None, None) on failure.
    room_status 'not_found' signals HTTP 404.
    """
    post_data = urllib.parse.urlencode({'room_slug': actor, 'bandwidth': 'high'}).encode('utf-8')
    headers = {
        **REQUEST_HEADERS,
        'X-Requested-With': 'XMLHttpRequest',
        'Accept': 'application/json, text/plain, */*',
        'Content-Type': 'application/x-www-form-urlencoded',
    }

    endpoint = HLS_EDGE_ENDPOINT
    try:
        req = urllib.request.Request(endpoint, data=post_data, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            enc = (resp.headers.get('Content-Encoding') or '').lower()
            if 'gzip' in enc:
                import gzip
                raw = gzip.decompress(raw)
            elif 'deflate' in enc:
                import zlib
                try:
                    raw = zlib.decompress(raw)
                except zlib.error:
                    raw = zlib.decompress(raw, -zlib.MAX_WBITS)

            data = json.loads(raw.decode('utf-8', errors='replace').lstrip('\ufeff'))
            room_status = data.get('room_status', '')
            url         = data.get('url', '')
            cmaf_edge   = data.get('cmaf_edge', False)

            if cmaf_edge and url:
                url = build_cmaf_url(url)

            xbmc.log(f"{ADDON_SHORTNAME}: HLS OK: status={room_status}, cmaf={cmaf_edge}", 1)
            return url, room_status

    except urllib.error.HTTPError as e:
        if e.code == 404:
            xbmc.log(f"{ADDON_SHORTNAME}: HLS 404 — user not found: {actor}", level=xbmc.LOGWARNING)
            return None, 'not_found'
        xbmc.log(f"{ADDON_SHORTNAME}: HLS HTTP {e.code} for {endpoint}", level=xbmc.LOGERROR)

    except Exception as e:
        xbmc.log(f"{ADDON_SHORTNAME}: HLS error for {endpoint}: {repr(e)}", level=xbmc.LOGERROR)

    return None, None

def build_cmaf_url(url):
    url = url.replace("playlist.m3u8", "playlist_sfm4s.m3u8")
    url = re.sub(r'live-.+amlst', 'live-c-fhls/amlst', url)
    return url

def build_api_url_rooms(**kwargs):
    url = API_ENDPOINT_ROOMS
    for key, value in kwargs.items():
        if value:
            url += f"&{key}={value}"   
    return url

def build_roomlist_url(**kwargs):
    url = sys.argv[0] + '?roomlist'
    for key, value in kwargs.items():
        if value:
            url += f"&{key}={value}"   
    return url

if __name__ == "__main__":
    evaluate_request()
