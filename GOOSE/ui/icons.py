# Map used Material Design Icons to Unicode characters
class Icons:
    check_circle = "\U000F05E0"
    wifi = "\U000F05A9"
    battery = "\U000F007A"
    cog = "\U000F0493"
    camera = "\U000F0104"
    video = "\U000F00FC"
    rotate_3d = "\U000F0C85"
    arrow_top_right = "\U000F005C"
    arrow_up_down = "\U000F0E79"
    alert_circle = "\U000F0028"
    circle_outline = "\U000F015F"
    sync = "\U000F04E6"
    rotate_right = "\U000F0466"
    alert_octagon = "\U000F0029"
    content_save = "\U000F0193"
    arrow_bottom_right = "\U000F0043"

    # Media Gallery icons
    image = "\U000F0E09"           # mdi-image-outline
    image_multiple = "\U000F0E0B"  # mdi-image-multiple-outline
    video_outline = "\U000F0BFC"   # mdi-video-outline
    star = "\U000F04CE"            # mdi-star
    star_outline = "\U000F04D2"    # mdi-star-outline
    folder_media = "\U000F0253"    # mdi-folder
    cloud_upload = "\U000F0168"    # mdi-cloud-upload
    download = "\U000F01DA"        # mdi-download
    delete = "\U000F01B4"          # mdi-delete
    magnify = "\U000F0349"         # mdi-magnify
    import_icon = "\U000F012C"     # mdi-application-import
    view_grid = "\U000F0588"       # mdi-view-grid
    view_list = "\U000F058B"       # mdi-view-list
    close = "\U000F0156"           # mdi-close
    filter_variant = "\U000F0236"  # mdi-filter-variant
    play_circle = "\U000F040D"     # mdi-play-circle
    chevron_down = "\U000F0140"    # mdi-chevron-down
    arrow_left = "\U000F004D"      # mdi-arrow-left
    bell = "\U000F009A"            # mdi-bell
    account_circle = "\U000F0009"  # mdi-account-circle
    refresh = "\U000F0453"         # mdi-refresh
    four_k = "\U000F0E14"          # mdi-quality-high (for 4K badge)
    clock = "\U000F0954"           # mdi-clock-outline
    file_size = "\U000F0224"       # mdi-file (for file size display)
    calendar = "\U000F00ED"        # mdi-calendar

    @classmethod
    def get_battery_icon(cls, percentage_str):
        try:
            val = int(percentage_str.strip('%'))
            if val >= 95: return "\U000F0079"
            if val >= 85: return "\U000F0082" 
            if val >= 75: return "\U000F0081" 
            if val >= 65: return "\U000F0080" 
            if val >= 55: return "\U000F007F" 
            if val >= 45: return "\U000F007E" 
            if val >= 35: return "\U000F007D" 
            if val >= 25: return "\U000F007C" 
            if val >= 15: return "\U000F007B" 
            if val >= 5: return "\U000F007A"  
            return "\U000F008E" 
        except ValueError:
            return "\U000F008E"
