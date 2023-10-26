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
Q_THUMBNAILS = "SELECT url,cachedurl FROM texture WHERE url LIKE '%.highwebmedia.com%'"
Q_DEL_THUMBNAILS = "DELETE FROM texture WHERE url LIKE '%.highwebmedia.com%'"

# Addon init
PLUGIN_ID = int(sys.argv[1])
ADDON = xbmcaddon.Addon(id=ADDON_NAME)

# Thumbnail URL constants
THUMB_WIDE    = "https://roomimg.stream.highwebmedia.com/riw/{0}.jpg"
THUMB_SQUARE  = "https://roomimg.stream.highwebmedia.com/ri/{0}.jpg"
THUMB_HIRES   = "https://cbjpeg.stream.highwebmedia.com/stream?room={0}"

# Headers
REQUEST_HEADERS = {
    'Referer': 'https://chaturbate.com',
    'Origin': 'https://chaturbate.com',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:118.0) Gecko/20100101 Firefox/118.0'
}

# API endpoints
API_ENDPOINT_BIO     = "https://chaturbate.com/api/biocontext/{0}/"
API_ENDPOINT_VIDEO   = "https://chaturbate.com/api/chatvideocontext/{0}/"
API_ENDPOINT_TAGLIST = "https://chaturbate.com/api/ts/hashtags/tag-table-data/?g={0}&page={1}&limit={2}&sort={3}"
API_ENDPOINT_ROOMS   = "https://chaturbate.com/api/ts/roomlist/room-list/?enable_recommendations=false"

# Site specific constants
USER_STATES = {
    'public' : '',
    'private' : 'pvt',
    'hidden' : 'hidden',
    'offline' : 'off'
}
CURRENT_SHOW = {
    'public' : 'public',
    'private' : 'private',
    'hidden' : 'hidden',
    'offline' : 'offline'
}
USER_STATES_NICE = {
    'public' : 'Public',
    'private' : 'Private Session',
    'hidden' : 'Hidden',
    'offline' : 'Offline'
}
GENRE_CAMS = ('std-cams', 'new-cams', 'gaming-cams', 'region-cams', 'age-cams')
REGIONS = ('NA', 'O', 'ER', 'AS', 'SA')
AGE_CAMS = {'18+' : {'18','20'}, '18-21' : {'18','22'}, '20-30' : {'20','31'}, '30-50' : {'30','51'}, '50+' : {'50','200'}}

    
DEL_THUMBS_ON_STARTUP = ADDON.getSettingBool('del_thumbs_on_startup')
REQUEST_TIMEOUT = ADDON.getSettingInt('request_timeout')
TAG_SORT_BY_OPTIONS = ["ht", "-rc", "-vc"]
TAG_SORT_BY_STD = TAG_SORT_BY_OPTIONS[ADDON.getSettingInt('tag_sort_by')]
TAG_LIST_LIMITS = [10, 25, 50, 75, 100]
TAG_LIST_LIMIT = TAG_LIST_LIMITS[ADDON.getSettingInt('tag_list_limit')]

CAM_LIST_LIMITS = [10, 25, 50, 75, 100]
CAM_LIST_LIMIT = TAG_LIST_LIMITS[ADDON.getSettingInt('cam_list_limit')]

# Pattern matchings for HTML scraping
PAT_PLAYLIST = rb"(http.*?://.*?.stream.highwebmedia.com.*?m3u8)"
PAT_PLAYLIST2 = rb"\"hls_source\": \"(http.*?://.*?.stream.highwebmedia.com.*?m3u8)"
PAT_ACTOR_TOPIC = rb'og:description" content="(.*?)" />'
PAT_ACTOR_THUMB = rb'og:image\" content=\"(.*)\?[0-9]'
PAT_ACTOR_LIST_TAGS = rb'<li class=\"room_list_room[\s\S]*?data-room=\"(.*?)\"[\s\S]*?<img src=\"(.*?)\?\d{10}\"[\s\S]*?\">(.*)<\/[\s\S]*?class=\"age[\s\S]*?\">(.*)<\/span[\s\S]*?<li title=\"(.*?)\">[\s\S]*?class=\"location[\s\S]*?\">(.*)<\/li>[\s\S]*?\"cams\">[\s\S]*?<span[\s\S]*?>(.*)<\/span><span[\s\S]*?<span[\s\S]*?>(.*)<\/span>[\s\S]*?<\/li>'
PAT_ACTOR_BIO = rb'<div class="attribute">\n[\s\S]*?<div class="label">(.*?)<[\s\S]*?data">(.*?)<'
PAT_LAST_BROADCAST = rb'<div class=\"attribute\">[\s\S]*?<div class=\"label\">Last Broadcast:<[\s\S]*?data\">(.*?)<'
#PAT_TAG_LIST = rb'<div class=\"tag_row\"[\s\S]*?href=\"(.*?)\" title=\"(.*?)\"[\s\S]*?\"viewers\">(.*?)<[\s\S]*?\"rooms\">(.*?)<'
PAT_PAGINATION = rb'endless_page_link[\s\S]*?data-floating[\s\S]*?>([\d*][^a-z]?)<\/a'

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

def evaluate_request():
    """Evaluate what has been picked in Kodi"""

    if sys.argv[2]:
        param = sys.argv[2]
        
        # Handle static menus
        if "tagsmenu" in param:
            get_menu(SITE_TAGS)
        elif "tools" in param:
            get_menu(SITE_TOOLS)
        elif "favourites" in param:
            get_favourites()
        elif "search" in param:
            search_actor()
        elif "fuzzy" in param:
            search_actor2()
        elif "tool=" in param:
            tool = re.findall(r'\?tool=(.*)', param)[0]
            if tool == "fav-backup":
                tool_fav_backup()
            if tool == "fav-restore":
                tool_fav_restore()
            if tool == "thumbnails-delete":
                tool_thumbnails_delete()
        elif "catlist" in param:
            get_catlist()
        elif "roomlist" in param:
            get_roomlist()
        # Handle dynamic menus
        elif "taglist" in param:
            get_tag_list()
        elif "playactor=" in param:
            play_actor(re.findall(r'\?playactor=(.*)', param)[0], ["Stripchat"])
    else:
        get_menu()

def get_menu(itemlist=SITE_MENU):
    """Decision tree. Shows main menu by default"""
        
    # Build menu items
    items = []
    for item in itemlist:
        url = sys.argv[0] + '?' + item[1]
        li = xbmcgui.ListItem(item[0])
        tag = li.getVideoInfoTag()
        tag.setPlot(item[2])
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
        li.setArt({'icon': THUMB_WIDE.format(item)})

        # Context menu
        commands = []
        commands.append((ADDON_SHORTNAME + ' - Remove favourite','RunScript(' + ADDON_NAME + ', ' + str(sys.argv[1]) + ', remove_favourite, ' + item + ')'))
        commands.append(('[COLOR orange]' + ADDON_SHORTNAME + ' - Refresh thumbnails [/COLOR]','RunScript(' + ADDON_NAME + ', ' + str(sys.argv[1]) + ', ctx_thumbnails_delete)'))
        
        li.addContextMenuItems(commands, True)
        
        items.append((url, li, True))

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
        tag = li.getVideoInfoTag()
        tag.setPlot(item[2])
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
    # xbmc.log("API URL: " + str(url), 1)
    
    # Fetch the JSON data from the URL
    data = fetch_json_from_url(url, REQUEST_TIMEOUT)
    
    #Build kodi list items for virtual directory
    items = []
    id = 0
    
    if data:
        # xbmc.log(ADDON_SHORTNAME + ": " + "JSON data fetched from URL: " + url, 1)
        
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
                tag = li.getVideoInfoTag()
                # Extract num_users count for playcounter
                s = room.get('num_users', 0)
                li.setLabel(room.get('username'))
                li.setArt({'icon': room.get('img')})
                tag.setSortTitle(str(id).zfill(2) + " - " + room.get('username'))
                id = id + 1
                tag.setPlot("Age: " + str(room.get('display_age', "-"))
                            + "\nLabel: " + room.get('label', "-")
                            + "\nViewers: " + str(room.get('num_users', 0)) 
                            + "\nOnline: " + room.get('online_since')
                            + "\nFollowers: " + str(room.get('num_followers', 0)) 
                            + "\nLocation: " + room.get('location', "-")
                            + "\n\n" + room.get('subject', "-")
                            )
                li.setInfo('video', {'count': s})
                
                # Context menu
                commands = []
                commands.append(('[COLOR orange]' + ADDON_SHORTNAME + ' - Add as favourite [/COLOR]','RunScript(' + ADDON_NAME + ', ' + str(sys.argv[1]) + ', add_favourite, ' + room.get('username') + ')'))
                commands.append(('[COLOR orange]' + ADDON_SHORTNAME + ' - Refresh thumbnails [/COLOR]','RunScript(' + ADDON_NAME + ', ' + str(sys.argv[1]) + ', ctx_thumbnails_delete)'))
                li.addContextMenuItems(commands, True)
                
                items.append((url, li, True))
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
            # xbmc.log("NEXT PAGE URL: " + str(next_url),1)
            li = xbmcgui.ListItem(f"Page {page + 1} of {total_pages}")
            li.setArt({'icon': 'DefaultFolder.png'})
            li.setInfo('video', {'sorttitle': str(999).zfill(2) + " - Next Page"})
            li.setInfo('video', {'count': str(-1)})
            
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
    xbmcplugin.setContent(int(sys.argv[1]), 'videos')
    xbmcplugin.addSortMethod(int(sys.argv[1]), xbmcplugin.SORT_METHOD_VIDEO_SORT_TITLE)
    xbmcplugin.addSortMethod(int(sys.argv[1]), xbmcplugin.SORT_METHOD_PROGRAM_COUNT)
    xbmcplugin.addSortMethod(int(sys.argv[1]), xbmcplugin.SORT_METHOD_LABEL)
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
        # xbmc.log("Total tags in genders: " + str(total), 1)
        
        id = 0
        for item in roomlist["hashtags"]:
            url = sys.argv[0] + '?roomlist&genders=' + genders + "&hashtags=" + item["hashtag"]
            li = xbmcgui.ListItem(item["hashtag"])
            tag = li.getVideoInfoTag()
            li.setLabel(item["hashtag"] + " (%s)" %
                        item["room_count"])
            # tag.setPlaycount(int(item["room_count"]))
            li.setInfo('video', {'count': item["room_count"]})
            tag.setSortTitle(str(id).zfill(3) + " - " + item["hashtag"])
            items.append((url, li, True))
            id = id + 1
        
        # Pagination
        totalPages = total // int(limit)
        
        if totalPages > 1: # We have enough results for at least two pages
            if int(page) + 1 < totalPages:
                # URL for next page button
                next_url = "taglist&genders=" + genders + "&page=" + str(int(page)+1)
                # xbmc.log("NEXT PAGE URL: " + str(next_url),1)
                li = xbmcgui.ListItem("Next page (%s of %s)" % (str(int(page)+1),str(totalPages)))
                tag = li.getVideoInfoTag()
                li.setArt({'icon': 'DefaultFolder.png'})
                tag.setSortTitle(str(id).zfill(2) + " - Next Page")
                # tag.setPlaycount(-1)
                li.setInfo('video', {'count': str(-1)})
                
                # Context menu
                commands = []
                commands.append(('Back to first page',"Container.Update(%s?%s, replace)" % ( sys.argv[0],  "taglist&genders=" + genders)))
                commands.append(('Back to main menu',"Container.Update(%s, replace)" % ( sys.argv[0])))
                li.addContextMenuItems(commands, True)
                
                items.append((sys.argv[0] + '?'+next_url, li, True))
    
    # Build kodi listems for virtual directory
    # Put items to virtual directory listing and set sortings
    xbmcplugin.addSortMethod(int(sys.argv[1]), xbmcplugin.SORT_METHOD_VIDEO_SORT_TITLE)
    xbmcplugin.addSortMethod(int(sys.argv[1]), xbmcplugin.SORT_METHOD_PROGRAM_COUNT)
    xbmcplugin.addSortMethod(int(sys.argv[1]), xbmcplugin.SORT_METHOD_LABEL)
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
        s += " | Followers: " + str(b['follower_count'])
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
        
    # interested_in (Interested In:) (array 0-3 max) obsolete
    return s

def get_actor_prices_from_json(v):
    if "allow_private_shows" in v:
        if "spy_private_show_price" in v and not v["spy_private_show_price"] == 0:
            return " | Private: " + str(v['private_show_price']) + " (Spy: " + str(v['spy_private_show_price']) + ")"
        else:
            return " | Private: " + str(v['private_show_price'])
    else:
        return ""


def play_actor(actor, genre=[""]):
    """Get playlist for actor/username and add m3u8 to kodi's playlist"""
    
    # Try to play actor
    try:      
        # Fetch Videocontext
        url = API_ENDPOINT_VIDEO.format(actor)
        v = json.loads(json.dumps(fetch_json_from_url(url, REQUEST_TIMEOUT)))
        
        # Fetch Biocontext
        url = API_ENDPOINT_BIO.format(actor)
        b = json.loads(json.dumps(fetch_json_from_url(url, REQUEST_TIMEOUT)))
        
        # Playlist
        hls_source = v['hls_source']
        # Room status
        status = v['room_status']
        # Viewers
        viewers = v['num_viewers']
        # Topic
        topic = v['room_title']
            
        if not status == "public":
            if status in USER_STATES_NICE:
                xbmcgui.Dialog().ok(STRINGS['na'], STRINGS['status'] + USER_STATES_NICE[status] + "\n" + STRINGS['last_broadcast'] + b['time_since_last_broadcast'])  
                return
            # Unknown state
            else:
                xbmcgui.Dialog().ok(STRINGS['na'], STRINGS['unknown_status'] + status + "\n" + STRINGS['last_broadcast'] + b['time_since_last_broadcast'])  
                return
    
        # Status is public at this point, continue
        
        # Combine plot
        plot = topic + "\n\nViewers: " + str(viewers) + get_bio_context_from_json(b) + get_actor_prices_from_json(v)
    
        # Build kodi listem for playlist
        li = xbmcgui.ListItem(actor)
        tag = li.getVideoInfoTag()
        tag.setGenres(genre)
        tag.setPlot(plot)
        # Thumbnail for OSD (Square)
        li.setArt({'icon': THUMB_SQUARE.format(actor)})
        li.setMimeType('application/vnd.apple.mpegstream_url')

        # Play stream
        xbmc.Player().play(hls_source, li)
    
    except urllib.error.HTTPError as e:
            # Actor does not exist, we got an HTTP 404 error
            if str(e) == "HTTP Error 404: Not Found":
                xbmcgui.Dialog().ok("User issue (404 error)", "Username does not exist anymore. If this message persists, this user is save to delete.")
            # Something else went wrong
            else:
                xbmcgui.Dialog().ok("Unknown error", "Something went wrong with info extraction.\nError: " + str(e))  

def fetch_json_from_url(url, timeout):
    """Fetch JSON from URL with timeout"""
    
    # Create a Request object with the URL and headers
    req = urllib.request.Request(url, headers=REQUEST_HEADERS)
    
    try:
        # Perform the GET request with a timeout
        with urllib.request.urlopen(req, timeout=timeout) as response:
            # Read and decode the response
            raw_data = response.read().decode()
            
            # Parse the JSON from the response
            data = json.loads(raw_data)
            
            # Return the parsed JSON data
            return data
            
    except urllib.error.HTTPError as e:
        # HTTP errors (e.g., 404 or 501)
        xbmc.log(ADDON_SHORTNAME + ": "f"HTTP Error: {e.code}", level=xbmc.LOGERROR)
        return None  # Indicate failure by returning None
        
    except urllib.error.URLError as e:
        # Other errors (e.g., connection error, timeout)
        xbmc.log(ADDON_SHORTNAME + ": " + f"An error occurred: {e.reason}", level=xbmc.LOGERROR)
        return None  # Indicate failure by returning None

def search_actor():
    """Search for actor/username and list item if username exists"""

    s = xbmcgui.Dialog().input("Search username (lowercase)")
    if s == '':
        xbmcplugin.endOfDirectory(int(sys.argv[1]), succeeded=False)
    else:
        # Grab search result
        try:
            # Fetch Videocontext
            url = API_ENDPOINT_VIDEO.format(s)
            xbmc.log("URL: " + str(url),1)
            v = json.loads(json.dumps(fetch_json_from_url(url, REQUEST_TIMEOUT)))
        
            # Fetch Biocontext
            url = API_ENDPOINT_BIO.format(s)
            b = json.loads(json.dumps(fetch_json_from_url(url, REQUEST_TIMEOUT)))
        
            # Room status
            status = v['room_status']
            # Viewers
            viewers = v['num_viewers']
            # Topic
            topic = v['room_title']
        
            # Build kodi listem for virtual directory
            li = xbmcgui.ListItem(s)

            # Context menu
            commands = []
            commands.append((ADDON_SHORTNAME + ' - Add user to favourites','RunScript(' + ADDON_NAME + ', ' + str(sys.argv[1]) + ', add_favourite, ' + s + ')'))
            li.addContextMenuItems(commands, True)
            tag = li.getVideoInfoTag()
            
            if status=="public":
                li.setLabel(s)
            else:
                if status=="private":    
                    li.setLabel(s + " | private")
                if status=="hidden":
                    li.setLabel(s + " | hidden")
                if status=="offline":
                    li.setLabel(s + " | offline")
            
            # Combine plot
            plot = topic + "\n\nViewers: " + str(viewers) + get_bio_context_from_json(b) + get_actor_prices_from_json(v)
            
            # List item info and art
            tag.setPlot(plot)
            li.setArt({'icon': THUMB_SQUARE.format(s)})

            # Put items to virtual directory listing
            url = sys.argv[0] + '?playactor=' + s
            xbmcplugin.setContent(int(sys.argv[1]), 'videos')
            xbmcplugin.addDirectoryItems(PLUGIN_ID, [(url, li, True)])
            xbmcplugin.endOfDirectory(PLUGIN_ID)

        # Actor does not exist, we got an HTTP 404 error
        except urllib.error.HTTPError as e:
            xbmcgui.Dialog().ok(str(e), "Username does not exist. Please try again.")

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
