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
import urllib.request
import urllib.parse
import urllib.error

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

# URLs and headers for requests
SITE_URL = "https://chaturbate.com"
SITE_REFFERER = "https://chaturbate.com"
SITE_ORIGIN = "https://chaturbate.com"
THUMB_WIDE = "https://roomimg.stream.highwebmedia.com/riw/{0}.jpg"
THUMB_SQUARE = "https://roomimg.stream.highwebmedia.com/ri/{0}.jpg"
THUMB_HIRES = "https://cbjpeg.stream.highwebmedia.com/stream?room={0}"
API_ENDPOINT_BIO = "https://chaturbate.com/api/biocontext/{0}/"
API_ENDPOINT_VIDEO = "https://chaturbate.com/api/chatvideocontext/{0}/"

# User agent(s)
USER_AGENT = " Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.182 Safari/537.36"
USER_AGENT2 = 'Mozilla/5.0 (iPad; CPU OS 8_1 like Mac OS X) AppleWebKit/600.1.4 (KHTML, like Gecko) Version/8.0 Mobile/12B410 Safari/600.1.4'
USER_AGENT3 = 'User-Agent=Mozilla/5.0 (iPad; CPU OS 8_1 like Mac OS X) AppleWebKit/600.1.4 (KHTML, like Gecko) Version/8.0 Mobile/12B410 Safari/600.1.4'

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

# Pattern matchings for HTML scraping
PAT_PLAYLIST = rb"(http.*?://.*?.stream.highwebmedia.com.*?m3u8)"
PAT_PLAYLIST2 = rb"\"hls_source\": \"(http.*?://.*?.stream.highwebmedia.com.*?m3u8)"
PAT_ACTOR_TOPIC = rb'og:description" content="(.*?)" />'
PAT_ACTOR_THUMB = rb'og:image\" content=\"(.*)\?[0-9]'
#PAT_ACTOR_LIST = rb'<li class=\"room_list_room\"[\s\S]*?<a href=\"\/(.*?)\/\"[\s\S]*?<img src=\"(.*?)\S\d{10}\"'
#PAT_ACTOR_LIST2 = rb'<li class=\"room_list_room\"[\s\S]*?<a href=\"\/(.*?)\/\"[\s\S]*?<img src=\"(.*?)\S\d{10}\"[\s\S]*?<li title=\"(.*?)">[\s\S]*?\"cams\">(.*)<'
PAT_ACTOR_LIST3 = rb'<li class=\"room_list_room[\s\S]*?data-room=\"(.*?)\"[\s\S]*?<img src=\"(.*?)\?\d{10}\"[\s\S]*?\">(.*)<\/[\s\S]*?class=\"age[\s\S]*?\">(.*)<\/span[\s\S]*?<li title=\"(.*?)\">[\s\S]*?class=\"location[\s\S]*?\">(.*)<\/li>[\s\S]*?\"cams\">[\s\S]*?<span[\s\S]*?>(.*)<\/span><span[\s\S]*?<span[\s\S]*?>(.*)<\/span>[\s\S]*?<\/li>'
PAT_ACTOR_LIST_TAGS = rb'<li class=\"room_list_room[\s\S]*?data-room=\"(.*?)\"[\s\S]*?<img src=\"(.*?)\?\d{10}\"[\s\S]*?\">(.*)<\/[\s\S]*?class=\"age[\s\S]*?\">(.*)<\/span[\s\S]*?<li title=\"(.*?)\">[\s\S]*?class=\"location[\s\S]*?\">(.*)<\/li>[\s\S]*?\"cams\">[\s\S]*?<span[\s\S]*?>(.*)<\/span><span[\s\S]*?<span[\s\S]*?>(.*)<\/span>[\s\S]*?<\/li>'
PAT_ACTOR_BIO = rb'<div class="attribute">\n[\s\S]*?<div class="label">(.*?)<[\s\S]*?data">(.*?)<'
PAT_LAST_BROADCAST = rb'<div class=\"attribute\">[\s\S]*?<div class=\"label\">Last Broadcast:<[\s\S]*?data\">(.*?)<'
PAT_TAG_LIST = rb'<div class=\"tag_row\"[\s\S]*?href=\"(.*?)\" title=\"(.*?)\"[\s\S]*?\"viewers\">(.*?)<[\s\S]*?\"rooms\">(.*?)<'
PAT_PAGINATION = rb'endless_page_link[\s\S]*?data-floating[\s\S]*?>([\d*][^a-z]?)<\/a'

# Tuples for menu and categories on site
SITE_MENU = (('Categories - All', "categories", "Show cams by categories featured, female, male, couple, trans."), 
             ('Categories - Female', "cats-f", "Show female cams only."), 
             ('Categories - Male', "cats-m", "Show male cams only."), 
             ('Categories - Couple', "cats-c", "Show couple cams only."), 
             ('Categories - Trans', "cats-t", "Show trans cams only."), 
             ("Tags", "tagsmenu", "Show cams by tags for above categories. "),
             ("Favourites", "favourites", "Favourites list. Offline cams will have default picture."), 
             ("Search", "search", "Search for an exact username.\nShows on- AND offline cams."),
             ("Fuzzy search", "fuzzy", "List cams containing term in username.\nONLINE CAMS ONLY!"),
             ("Tools", "tools", "Some tools for cleanup and favourites.")
             )
SITE_CATEGORIES = (('Featured', "featured-cams", ""),
                   ("New cams", "new-cams", ""),
                   ("Teen cams (18+)", "teen-cams", ""),
                   ("18-21 cams", "18to21-cams", ""),
                   ("20-30 cams", "20to30-cams", ""),
                   ("30-50 cams", "30to50-cams", ""),
                   ("Mature cams (50+)", "mature-cams", ""),
                   ("North american cams", "north-american-cams", ""),
                   ("South american cams", "south-american-cams", ""),
                   ("Euro russian cams", "euro-russian-cams", ""),
                   ("Asian cams", "asian-cams", ""),
                   ("Other region cams", "other-region-cams", ""))
SITE_CATS_F     = (('All', "female-cams", ""),
                   ("New cams", "new-cams/female", ""),
                   ("Teen cams (18+)", "teen-cams/female", ""),
                   ("18-21 cams", "18to21-cams/female", ""),
                   ("20-30 cams", "20to30-cams/female", ""),
                   ("30-50 cams", "30to50-cams/female", ""),
                   ("Mature cams (50+)", "mature-cams/female", ""),
                   ("North american cams", "north-american-cams/female", ""),
                   ("South american cams", "south-american-cams/female", ""),
                   ("Euro russian cams", "euro-russian-cams/female", ""),
                   ("Asian cams", "asian-cams/female", ""),
                   ("Other region cams", "other-region-cams/female", ""))
SITE_CATS_M     = (('All', "male-cams", ""),
                   ("New cams", "new-cams/male", ""),
                   ("Teen cams (18+)", "teen-cams/male", ""),
                   ("18-21 cams", "18to21-cams/male", ""),
                   ("20-30 cams", "20to30-cams/male", ""),
                   ("30-50 cams", "30to50-cams/male", ""),
                   ("Mature cams (50+)", "mature-cams/male", ""),
                   ("North american cams", "north-american-cams/male", ""),
                   ("South american cams", "south-american-cams/male", ""),
                   ("Euro russian cams", "euro-russian-cams/male", ""),
                   ("Asian cams", "asian-cams/male", ""),
                   ("Other region cams", "other-region-cams/male", ""))
SITE_CATS_C     = (('All', "couple-cams", ""),
                   ("New cams", "new-cams/couple", ""),
                   ("Teen cams (18+)", "teen-cams/couple", ""),
                   ("18-21 cams", "18to21-cams/couple", ""),
                   ("20-30 cams", "20to30-cams/couple", ""),
                   ("30-50 cams", "30to50-cams/couple", ""),
                   ("Mature cams (50+)", "mature-cams/couple", ""),
                   ("North american cams", "north-american-cams/couple", ""),
                   ("South american cams", "south-american-cams/couple", ""),
                   ("Euro russian cams", "euro-russian-cams/couple", ""),
                   ("Asian cams", "asian-cams/couple", ""),
                   ("Other region cams", "other-region-cams/couple", ""))
SITE_CATS_T     = (('All', "trans-cams", ""),
                   ("New cams", "new-cams/trans", ""),
                   ("Teen cams (18+)", "teen-cams/trans", ""),
                   ("18-21 cams", "18to21-cams/trans", ""),
                   ("20-30 cams", "20to30-cams/trans", ""),
                   ("30-50 cams", "30to50-cams/trans", ""),
                   ("Mature cams (50+)", "mature-cams/trans", ""),
                   ("North american cams", "north-american-cams/trans", ""),
                   ("South american cams", "south-american-cams/trans", ""),
                   ("Euro russian cams", "euro-russian-cams/trans", ""),
                   ("Asian cams", "asian-cams/trans", ""),
                   ("Other region cams", "other-region-cams/trans", ""))
SITE_TAGS = (('Tags - Featured', 'taglist-featured', ""), 
             ('Tags - Female', 'taglist-f', ""),
             ('Tags - Male', 'taglist-m', ""), 
             ('Tags - Couple', 'taglist-c', ""), 
             ('Tags - Transsexual', 'taglist-s', ""),)
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
        
        # Handle static menu
        if "categories" in param:
            get_menu("categories")
        elif "cats-f" in param:
            get_menu("cats-f")
        elif "cats-m" in param:
            get_menu("cats-m")
        elif "cats-c" in param:
            get_menu("cats-c")
        elif "cats-t" in param:
            get_menu("cats-t")
        elif "tagsmenu" in param:
            get_menu("tags")
        elif "tools" in param:
            get_menu("tools")
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
        # Handle dynamic menus
        if "-cams" in param:
            get_cams_by_category()
        elif "taglist-" in param:
            get_tag_list()
        elif "tag=" in param:
            get_cams_by_tag()
        elif "playactor=" in param:
            play_actor(re.findall(r'\?playactor=(.*)', param)[0], ["Livecam"])
    else:
        get_menu("main")

def get_menu(param):
    """Decision tree. Shows main menu by default"""
    itemlist = SITE_MENU
    if param == "categories":
        itemlist = SITE_CATEGORIES
    elif param == "cats-f":
        itemlist = SITE_CATS_F
    elif param == "cats-m":
        itemlist = SITE_CATS_M
    elif param == "cats-c":
        itemlist = SITE_CATS_C
    elif param == "cats-t":
        itemlist = SITE_CATS_T
    elif param == "tags":
        itemlist = SITE_TAGS
    elif param == "tools":
        itemlist = SITE_TOOLS
        
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


def get_cam_list(param):
    """List cams by category, keywords or tag"""

    #direct categories: cat=name
    #keywords: cat=search&keywords=...
    #tag: cat=tag&tagstring=... (tag/[]|f|m|c|s)

    #page: always add or read from parameters &page=...
    


def get_cams_by_category():
    """List available cams by category"""

    # Clean Thumbnails before opening the list
    if DEL_THUMBS_ON_STARTUP:
        tool_thumbnails_delete2()

    # Filter category
    cat = sys.argv[2].replace("?", "")

    # Filter page or set page=1
    if not "page=" in cat:
        page = 1
    else:
        t = cat.split("&")
        cat = t[0]
        page = int(t[1].replace("page=", ""))

    # Featured category is always an empty string on site, so handle it
    if cat == "featured-cams":
        data = get_site_page("/?" + "page=" + str(page))
    else:
        data = get_site_page(cat + "/?" + "page=" + str(page))

    # Regex for available rooms
    cams = re.findall(PAT_ACTOR_LIST3, data)

    # Build kodi list items for virtual directory
    items = []
    id = 0
    for item in cams:
        #xbmc.log("Item: " + str(item), 1)
        url = sys.argv[0] + '?playactor=' + item[0].decode("utf-8")
        li = xbmcgui.ListItem(item[0].decode("utf-8"))
        tag = li.getVideoInfoTag()
        # Extract viewers count for playcounter
        s = item[7].decode("utf-8")
        s = s.split(" ")[-2]
        #xbmc.log("Viewers: '" + str(s)+"'", 1)
        li.setLabel(item[0].decode("utf-8"))
        li.setArt({'icon': item[1].decode("utf-8")})
        tag.setSortTitle(str(id).zfill(2) + " - " + item[0].decode("utf-8"))
        #xbmc.log("SortTitle: " + str(id).zfill(2) + " - " + item[0].decode("utf-8"), 1)
        id = id + 1
        tag.setPlot("Stats: " 
                           + item[6].decode("utf-8") + ", " + item[7].decode("utf-8")
                           + "\nAge: " + item[3].decode("utf-8").replace("&nbsp;","-") 
                           + "\nLabel: " + item[2].decode("utf-8") 
                           + "\nLocation: " + item[5].decode("utf-8") 
                           + "\n\n"+item[4].decode("utf-8"))
        #xbmc.log("PlayCount: " + str(s), 1)
        #tag.setPlaycount(int(s)) #Not working probperly at the moment
        li.setInfo('video', {'count': s})
        

        # Context menu
        commands = []
        commands.append(('[COLOR orange]' + ADDON_SHORTNAME + ' - Add as favourite [/COLOR]','RunScript(' + ADDON_NAME + ', ' + str(sys.argv[1]) + ', add_favourite, ' + item[0].decode("utf-8") + ')'))
        commands.append(('[COLOR orange]' + ADDON_SHORTNAME + ' - Refresh thumbnails [/COLOR]','RunScript(' + ADDON_NAME + ', ' + str(sys.argv[1]) + ', ctx_thumbnails_delete)'))
        li.addContextMenuItems(commands, True)
        
        items.append((url, li, True))

    # Next page handling
    try:
        last_page = int(re.findall(PAT_PAGINATION, data)[-1])
    except:
        last_page = 1

    if page < last_page:

        # URL for next page button
        nextpageurl = cat + "&" + "page=" + str(page+1)

        # Next page button as listitem
        li = xbmcgui.ListItem("Next page (%s of %s)" % (str(page + 1),str(last_page)))
        tag = li.getVideoInfoTag()
        li.setArt({'icon': 'DefaultFolder.png'})
        tag.setSortTitle(str(id).zfill(2) + " - Next Page")
        #tag.setPlaycount(-1)
        li.setInfo('video', {'count': str(-1)})

        # Context menu
        commands = []
        commands.append(('Back first page',"Container.Update(%s?%s, replace)" % ( sys.argv[0],  cat)))
        commands.append(('Back main menu',"Container.Update(%s, replace)" % ( sys.argv[0])))
        li.addContextMenuItems(commands, True)
        
        items.append((sys.argv[0] + '?'+nextpageurl, li, True))

    # Put items to virtual directory listing and set sortings
    put_virtual_directoy_listing(items)

def get_cams_by_tag():
    """List available cams by tag"""

    # Clean Thumbnails before opening the list
    if DEL_THUMBS_ON_STARTUP:
        tool_thumbnails_delete2()

    # Filter tag. Result is: ['page=int', 'tag=tagname', 'url=/tag/tagname/[f|m|c|s]/']
    tagurl = sys.argv[2].replace("?", "")
    tagurl = tagurl.replace("%2f", "/")
    tagurl = tagurl.split("&")

    # Get page as int for later use
    page = int(tagurl[0].replace("page=", ""))

    # URL to grab
    graburl = tagurl[2].replace("url=/", "") + "?page=" + str(page)

    # Store fetched HTML
    data = get_site_page(graburl)
    
    # Regex for available rooms
    cams = re.findall(PAT_ACTOR_LIST_TAGS, data)
    
    # Build kodi list items for virtual directory
    items = []
    
    id = 0
    for item in cams:
        url = sys.argv[0] + '?playactor=' + item[0].decode("utf-8")
        li = xbmcgui.ListItem(item[0].decode("utf-8"))
        tag = li.getVideoInfoTag()

        # Extract viewers count for playcounter
        s = item[7].decode("utf-8")
        s = s.split(" ")[-2]
        
        li.setLabel(item[0].decode("utf-8"))
        li.setArt({'icon': item[1].decode("utf-8")})
        tag.setSortTitle(str(id).zfill(2) + " - " + item[0].decode("utf-8"))
        id = id + 1
        tag.setPlot("Stats: "
                           + item[6].decode("utf-8") + ", " + item[7].decode("utf-8")
                           + "\nAge: " + item[3].decode("utf-8").replace("&nbsp;","-") 
                           + "\nLabel: " + item[2].decode("utf-8") 
                           + "\nLocation: " + item[5].decode("utf-8") 
                           + "\n\n"+item[4].decode("utf-8"))
        #tag.setPlaycount(int(s)) #Not working probperly at the moment
        li.setInfo('video', {'count': s})

        # Context menu
        commands = []
        commands.append(('[COLOR orange]' + ADDON_SHORTNAME + ' - Add as favourite[/COLOR]','RunScript(' + ADDON_NAME + ', ' + str(sys.argv[1]) + ', add_favourite, ' + item[0].decode("utf-8") + ')'))
        commands.append(('[COLOR orange]' + ADDON_SHORTNAME + ' - Refresh thumbnails [/COLOR]','RunScript(' + ADDON_NAME + ', ' + str(sys.argv[1]) + ', ctx_thumbnails_delete)'))
        li.addContextMenuItems(commands, True)

        items.append((url, li, True))

    # Next page handling
    try:
        last_page = int(re.findall(PAT_PAGINATION, data)[-1])
    except:
        last_page = 1

    if page < last_page:

        # URL for next page button
        nextpageurl = sys.argv[0] + '?page=' + str(page+1) + "&" + tagurl[1] + "&" + tagurl[2].replace("/", "%2f")

        # Next page button as listitem
        li = xbmcgui.ListItem("Next page (%s of %s)" % (str(page + 1),str(last_page)))
        tag = li.getVideoInfoTag()
        tag.setSortTitle(str(id).zfill(2) + " - Next Page")
        #tag.setPlaycount(-1)
        li.setInfo('video', {'count': str(-1)})
        li.setArt({'icon': 'DefaultFolder.png'})

        # TODO: Context menu
        commands = []
        commands.append(('Back first page',"Container.Update(%s?%s, replace)" % ( sys.argv[0],  'page=1' + "&" + tagurl[1] + "&" + tagurl[2].replace("/", "%2f"))))
        commands.append(('Back main menu',"Container.Update(%s, replace)" % ( sys.argv[0])))
        li.addContextMenuItems(commands, True)

        items.append((nextpageurl, li, True))

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
    """Get list of available tag for the categories"""

    taglist = re.findall(r'taglist-(.*)', sys.argv[2].replace("?", ""))[0]

    # Featured category is always an empty string on site, so handle it and grab URL
    if taglist == "featured":
        url = "tags/"
    else:
        url = "tags/"+taglist+"/"
    data = get_site_page(url)

    # Regex for available tags
    tags = re.findall(PAT_TAG_LIST, data)

    # Build kodi listems for virtual directory
    items = []
    id = 0
    for item in tags:
        url = sys.argv[0] + '?tag=' + \
            item[1].decode("utf-8") + "&page=1" + \
            "&url=" + item[0].decode("utf-8")
        li = xbmcgui.ListItem(item[1].decode("utf-8"))
        tag = li.getVideoInfoTag()
        li.setLabel(item[1].decode("utf-8") + " (%s)" %
                    item[3].decode("utf-8"))
        #tag.setPlaycount(int(item[3].decode("utf-8")))
        li.setInfo('video', {'count': item[3].decode("utf-8")})
        tag.setSortTitle(str(id).zfill(3) + " - " + item[1].decode("utf-8"))
        items.append((url, li, True))
        id = id + 1

    # Put items to virtual directory listing and set sortings
    xbmcplugin.addSortMethod(int(sys.argv[1]), xbmcplugin.SORT_METHOD_VIDEO_SORT_TITLE)
    xbmcplugin.addSortMethod(int(sys.argv[1]), xbmcplugin.SORT_METHOD_PROGRAM_COUNT)
    xbmcplugin.addSortMethod(int(sys.argv[1]), xbmcplugin.SORT_METHOD_LABEL)
    xbmcplugin.addDirectoryItems(PLUGIN_ID, items)
    xbmcplugin.endOfDirectory(PLUGIN_ID)

def get_bio_context_from_actor(actor):
    url = API_ENDPOINT_BIO.format(actor)
    b = get_site_page_full(url)
    b = json.loads(b)    
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
        v = get_site_page_full(url)
        v = json.loads(v)
        
        # Fetch Biocontext
        url = API_ENDPOINT_BIO.format(actor)
        b = get_site_page_full(url)
        b = json.loads(b)  
        
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


def get_site_page(page):
    """Fetch HTML data from site"""

    url = "%s/%s" % (SITE_URL, page)
    req = urllib.request.Request(url)
    req.add_header('Referer', SITE_REFFERER)
    req.add_header('Origin', SITE_ORIGIN)
    req.add_header('User-Agent', USER_AGENT)
    
    return urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT).read()

def get_site_page_full(page):
    """Fetch HTML data from site"""

    req = urllib.request.Request(page)
    req.add_header('Referer', SITE_REFFERER)
    req.add_header('Origin', SITE_ORIGIN)
    req.add_header('User-Agent', USER_AGENT)
    
    return urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT).read()

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
            v = get_site_page_full(url)
            v = json.loads(v)
        
            # Fetch Biocontext
            url = API_ENDPOINT_BIO.format(s)
            b = get_site_page_full(url)
            b = json.loads(b) 
        
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
    
    data = get_site_page("/?keywords=" + s)
        
        
    # Regex for available rooms
    cams = re.findall(PAT_ACTOR_LIST3, data)
    i = len(cams)
    if i == 0:
        xbmcgui.Dialog().notification("Fuzzy search", "No cams for this keyword", "", 1000, False)
        return
    
    # Build kodi listems for virtual directory
    items = []
    id = 0
    for item in cams:
        url = sys.argv[0] + '?playactor=' + item[0].decode("utf-8")
        li = xbmcgui.ListItem(item[0].decode("utf-8"))
        tag = li.getVideoInfoTag()
        
        # Extract viewers count
        s = item[6].decode("utf-8")
        s = s.split(" ")[-2]

        li.setLabel(item[0].decode("utf-8"))
        li.setArt({'icon': item[1].decode("utf-8")})
        tag.setSortTitle(str(id).zfill(2) + " - " + item[0].decode("utf-8"))
        id = id + 1
        tag.setPlot("Stats: " 
                           + item[6].decode("utf-8")
                           + "\nAge: " + item[3].decode("utf-8").replace("&nbsp;","-") 
                           + "\nLabel: " + item[2].decode("utf-8") 
                           + "\nLocation: " + item[5].decode("utf-8") 
                           + "\n\n"+item[4].decode("utf-8"))
        tag.setPlaycount(s)

        # Context menu
        commands = []
        commands.append(('[COLOR orange]' + ' - Add as favourite [/COLOR]','RunScript(' + ADDON_NAME + ', ' + str(sys.argv[1]) + ', add_favourite, ' + item[0].decode("utf-8") + ')'))
        li.addContextMenuItems(commands, True)
        
        items.append((url, li, True))

    # Put items to virtual directory listing and set sortings
    xbmcplugin.setContent(int(sys.argv[1]), 'videos')
    xbmcplugin.addSortMethod(
        int(sys.argv[1]), xbmcplugin.SORT_METHOD_VIDEO_SORT_TITLE)
    xbmcplugin.addSortMethod(
        int(sys.argv[1]), xbmcplugin.SORT_METHOD_PROGRAM_COUNT)
    xbmcplugin.addSortMethod(int(sys.argv[1]), xbmcplugin.SORT_METHOD_LABEL)
    xbmcplugin.addDirectoryItems(PLUGIN_ID, items)
    xbmcplugin.endOfDirectory(PLUGIN_ID)  
    
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

if __name__ == "__main__":
    evaluate_request()
