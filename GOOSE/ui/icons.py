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
