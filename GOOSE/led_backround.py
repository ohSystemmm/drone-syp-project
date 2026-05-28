import socket

class TelloLEDController:
    """
    Controller for managing the Tello's 8x8 LED matrix display over UDP.
    Communicates via the Tello SDK command API, operating in non-blocking
    mode to avoid stalling the main graphical thread.
    """
    def __init__(self, ip='192.168.10.1', port=8889):
        self.tello_address = (ip, port)
        
        # Initialize raw UDP socket for low-latency command packets
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # Guard main event loop: set socket timeout to prevent blocking during connection dropouts
        self.sock.settimeout(0.5)

        # Initialize SDK mode handshake immediately to allow subsequent commands
        self.enable_sdk()

    def send_command(self, cmd: str):
        """
        Transmits a raw SDK text command to the drone.
        Encodes the command string as UTF-8 before network transmission.
        """
        try:
            self.sock.sendto(cmd.encode('utf-8'), self.tello_address)
            print(f"[Backend] Sent: {cmd}")
        except Exception as e:
            print(f"[Backend] Socket write error: {e}")

    def enable_sdk(self):
        """
        Triggers the Tello SDK programming mode.
        Must be invoked prior to dispatching any custom accessory or control commands.
        """
        self.send_command("command")

    def send_pattern(self, pattern: str):
        """
        Sends an 8x8 grid state pattern (64 characters) to the LED matrix.
        Valid characters: 
          - '0': Off (Unlit)
          - 'r': Red
          - 'b': Blue
          - 'p': Purple
        """
        if len(pattern) != 64:
            print(f"[Backend] Error: Pattern payload must contain exactly 64 characters (got {len(pattern)}).")
            return

        cmd = f"EXT mled g {pattern}"
        self.send_command(cmd)

    def clear_matrix(self):
        """Clears the 8x8 matrix display by disabling all LED elements."""
        self.send_pattern("0" * 64)

    def send_text(self, text: str, color='r', direction='l', speed=2.5):
        """
        Initiates a scrolling text marquee across the LED matrix.
        
        Parameters:
          - text: The string content to scroll (English/alphanumeric)
          - color: Character color ('r'=Red, 'b'=Blue, 'p'=Purple)
          - direction: Scroll transition vector ('l'=Left, 'r'=Right, 'u'=Up, 'd'=Down)
          - speed: Scroll transition delay (seconds per frame, range: 0.1 - 10.0)
        """
        cmd = f"EXT mled {direction} {color} {speed} {text}"
        self.send_command(cmd)